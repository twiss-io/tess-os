"""
v0.2.0 (ws-doc): doctrine must not claim a hook mode the hook does not have.

Before v0.2.0, conductor/guardrails.md said the two Rule Zero guards
(`dispatch-guard.sh`, `anti-fabrication-guard.sh`) had been "flipped to
BLOCK-mode" and that off-whitelist calls were "DENIED". The shipped
scripts have never had a deny path: every branch ends in `exit 0` and
neither emits a `permissionDecision`. An operator reading the doctrine
would believe Rule Zero was mechanically enforced when it is only advised.

These tests read the REAL doctrine text and the REAL hook scripts (both the
rendered `.claude/hooks/` copies and the `.tess/core/hooks/` masters) and
check that the two agree, sentence by sentence:

  * a sentence that names a hook and claims block/deny behaviour requires
    that hook file to contain a deny path;
  * a sentence that names a hook and claims warn-only behaviour requires
    that hook file to contain NO deny path.

Struck-through text (``~~...~~``) is a retracted claim and is ignored, as
are fenced code blocks. When a sentence mentions both modes, the LAST mode
phrase wins ("flipped from warn-mode to BLOCK-mode" is a block claim);
negated phrases such as "never denies" or "neither ... denies" count as
warn phrases.

It also exercises the real dispatch-guard.sh to pin the v0.2.0 safe-set
addition: AGENTS.md and GEMINI.md, the entry points for the other
runtimes, are doctrine and must not raise the Rule Zero warning.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK_DIRS = (REPO_ROOT / ".claude" / "hooks", REPO_ROOT / ".tess" / "core" / "hooks")
GUARDRAILS = (
    REPO_ROOT / "conductor" / "guardrails.md",
    REPO_ROOT / ".tess" / "core" / "conductor" / "guardrails.md",
)
# v0.2.0 (notg): the chat-channel companion guard (anti-fabrication-guard.sh)
# was removed with the channel, so dispatch-guard.sh is the one Rule Zero guard.
RULE_ZERO_GUARDS = ("dispatch-guard.sh",)

_BLOCK_PHRASES = (
    r"\bblock[- ]mode\b",
    r"\bdenied\b",
    r"\bdenies\b",
    r"\bdeny\b",
    r"\bcan block\b",
)
_WARN_PHRASES = (
    r"\bwarn[- ]mode\b",
    r"\bnever (?:blocks|denies|denied)\b",
    r"\bneither\b[^.]*?\b(?:blocks|denies)\b",
    r"\b(?:does|do|did) not (?:block|deny)\b",
    r"\bno deny path\b",
    r"\bnever had a deny path\b",
)


def _doctrine_files() -> list[Path]:
    files: list[Path] = []
    for base in (REPO_ROOT / "conductor", REPO_ROOT / ".tess" / "core" / "conductor"):
        files.extend(sorted(base.rglob("*.md")))
    files.append(REPO_ROOT / "CLAUDE.md")
    files.extend(sorted((REPO_ROOT / ".tess" / "core" / "templates" / "claude-md").glob("*.md")))
    files.append(REPO_ROOT / ".tess" / "core" / "templates" / "CLAUDE.md.tpl")
    return [f for f in files if f.is_file()]


def _hook_files() -> dict[str, list[Path]]:
    hooks: dict[str, list[Path]] = {}
    for d in HOOK_DIRS:
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir()):
            if f.suffix in (".sh", ".py") and f.is_file():
                hooks.setdefault(f.name, []).append(f)
    return hooks


def _has_deny_path(hook: Path) -> bool:
    text = hook.read_text(encoding="utf-8")
    code = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )
    if re.search(r"\bexit\s+2\b", code):
        return True
    if re.search(r"\bsys\.exit\(\s*2\s*\)", code):
        return True
    if "permissionDecision" in code and re.search(r"[\"']deny[\"']", code):
        return True
    return False


def _sentences(text: str) -> list[str]:
    text = re.sub(r"```.*?```", " ", text, flags=re.S)       # fenced code
    text = re.sub(r"~~.*?~~", " ", text, flags=re.S)          # retracted claims
    out: list[str] = []
    for block in re.split(r"\n\s*\n|\n(?=\s*(?:[-*] |\d+\. |#|\|))", text):
        block = " ".join(block.split())
        out.extend(s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z*`(\[])", block) if s)
    return out


def _claimed_mode(sentence: str) -> str | None:
    hits: list[tuple[int, int, str]] = []
    for pat in _BLOCK_PHRASES:
        hits.extend((m.end(), 0, "block") for m in re.finditer(pat, sentence, re.I))
    for pat in _WARN_PHRASES:
        hits.extend((m.end(), 1, "warn") for m in re.finditer(pat, sentence, re.I))
    if not hits:
        return None
    hits.sort()  # by end position; on a tie the warn phrase (1) sorts last and wins
    return hits[-1][2]


def _claims() -> list[tuple[Path, str, str, str]]:
    """(doctrine file, hook basename, 'block'|'warn', sentence) for every
    sentence that names a shipped hook and claims a mode for it."""
    hooks = _hook_files()
    claims = []
    for doc in _doctrine_files():
        for sentence in _sentences(doc.read_text(encoding="utf-8")):
            mode = _claimed_mode(sentence)
            if mode is None:
                continue
            for name in hooks:
                if re.search(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", sentence):
                    claims.append((doc, name, mode, sentence))
    return claims


def test_hook_mode_claims_match_the_hook_scripts():
    hooks = _hook_files()
    assert hooks, "no hook scripts found; the test would be vacuous"
    problems = []
    for doc, name, mode, sentence in _claims():
        for hook in hooks[name]:
            deny = _has_deny_path(hook)
            if mode == "block" and not deny:
                problems.append(
                    f"{doc.relative_to(REPO_ROOT)} claims block/deny for {name}, but "
                    f"{hook.relative_to(REPO_ROOT)} has no deny path:\n    {sentence[:300]}"
                )
            if mode == "warn" and deny:
                problems.append(
                    f"{doc.relative_to(REPO_ROOT)} claims warn-only for {name}, but "
                    f"{hook.relative_to(REPO_ROOT)} has a deny path:\n    {sentence[:300]}"
                )
    assert not problems, "doctrine/hook mode mismatch:\n  " + "\n  ".join(problems)


def test_guardrails_states_a_mode_for_each_rule_zero_guard():
    """Keeps the check above from going vacuous: guardrails.md must make an
    explicit, checkable mode claim about each of the two Rule Zero guards."""
    for g in GUARDRAILS:
        assert g.is_file(), f"missing {g}"
    claimed = {(doc, name) for doc, name, _m, _s in _claims() if doc in GUARDRAILS}
    for g in GUARDRAILS:
        for name in RULE_ZERO_GUARDS:
            assert (g, name) in claimed, (
                f"{g.relative_to(REPO_ROOT)} makes no explicit mode claim about {name}"
            )


def test_rule_zero_guards_really_have_no_deny_path():
    """Pins the fact the doctrine now states: the two dispatch guards are
    warn-mode. If a future change adds a deny path, the doctrine has to
    change with it (and the test above will say so)."""
    hooks = _hook_files()
    for name in RULE_ZERO_GUARDS:
        assert hooks.get(name), f"{name} not shipped"
        for hook in hooks[name]:
            assert not _has_deny_path(hook), f"{hook} now has a deny path; update guardrails Rule 1"


# ---------------------------------------------------------------------------
# dispatch-guard.sh safe set: AGENTS.md and GEMINI.md are doctrine entry points
# ---------------------------------------------------------------------------

HAS_TOOLS = shutil.which("bash") is not None and shutil.which("jq") is not None


def _run_guard(hook: Path, payload: dict, project_dir: Path):
    env = dict(os.environ)
    env.pop("TESS_HEADLESS", None)
    env.pop("TESS_NO_SUBAGENTS", None)
    env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    return subprocess.run(["bash", str(hook)], input=json.dumps(payload),
                          capture_output=True, text=True, env=env)


@pytest.mark.skipif(not HAS_TOOLS, reason="bash and jq required to run the real hook")
@pytest.mark.parametrize("hook_dir", HOOK_DIRS, ids=["live", "core"])
@pytest.mark.parametrize("entry", ["AGENTS.md", "GEMINI.md"])
def test_dispatch_guard_treats_runtime_entry_points_as_doctrine(hook_dir, entry, tmp_path):
    hook = hook_dir / "dispatch-guard.sh"
    # Control: an off-whitelist edit must warn. If it does not, a live
    # dispatch lock on this host is suppressing every warning and the check
    # below would prove nothing.
    control = _run_guard(hook, {"tool_name": "Edit",
                                "tool_input": {"file_path": str(tmp_path / "src.py")}}, tmp_path)
    if "RULE ZERO WARNING" not in control.stdout:
        pytest.skip("a dispatch lock on this host suppresses dispatch-guard warnings")

    for payload in (
        {"tool_name": "Edit", "tool_input": {"file_path": str(tmp_path / entry)}},
        {"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / entry)}},
        {"tool_name": "Bash", "tool_input": {"command": f"cat {entry}"}},
    ):
        r = _run_guard(hook, payload, tmp_path)
        assert r.returncode == 0, r.stderr
        assert r.stdout.strip() == "", f"{payload} should be in the safe set, got {r.stdout!r}"
