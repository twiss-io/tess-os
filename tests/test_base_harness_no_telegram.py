"""
v0.2.0 (ws-notg) + v0.2.1: the base harness is runtime-neutral and names no
external chat channel.

Tess OS runs inside whichever runtime the operator uses (Claude Code, Codex,
Gemini CLI, Grok Build, Kimi Code, other AGENTS.md tools). The conductor
reports in the active session. No doctrine, hook, settings entry, command
step, agent or persona line, onboarding prompt, template, default config,
MCP entry, test or doc in the base harness may require, configure or
instruct the removed chat channel. External notification channels are
optional operator add-ons, outside the base harness.

Before v0.2.0 the base shipped a "<channel> is the primary channel" rule, two
PreToolUse hooks and a PostToolUse reminder wired to that channel's plugin
tools, channel steps in /wake, /close, /finalize and /code-red, a wizard
prompt and flag, a heartbeat notifier for it, and two .env.example
placeholders. v0.2.1 removed the placeholders (operator decision,
2026-09-29), so the strict xfail that recorded them is gone.

This guard reads the real files and fails on any case-insensitive match of
the channel's name (NEEDLE below; spelled in two halves so this file does not
match itself), except a small explicit allowlist:

  * CHANGELOG history (dated entries are not rewritten);
  * the one docs note (create-tess/README.md): external notification
    channels are optional operator add-ons, outside the base harness;
  (The bundled create-tess/template/ copies were rebuilt at the v1.0.0
  integration, so they need no allowlist entry.)

test_literal_grep_finds_only_changelog_and_one_doc_line runs a literal
`git grep -i` over the shipped tree and pins the result to exactly the
CHANGELOG and that one doc line.

Scope. In the Tess OS repository (create-tess/src exists) every tracked file
is base harness except the wizard's own test suite (create-tess/test/, never
scaffolded) and reviews/verdicts/ (plus any create-tess/template/reviews/verdicts/
copy): per-PR review records such as a reviewer's verdict on this very change. They are
stripped at integration (integrate_step.sh removes reviews/verdicts/ from
every merge) and are never scaffolded, and a verdict that names the removed
channel must not turn its own PR red. That covers core, doctrine, templates, hooks, settings,
commands, agents, skills, render outputs, the engine, create-tess/src and
the bundled create-tess/template/. In a scaffolded instance only the
framework core (.tess/core/ and the engine) is checked: everything else is
operator space, where an operator may add a channel of their own.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PRODUCT_REPO = (REPO_ROOT / "create-tess" / "src").is_dir()

NEEDLE_TEXT = "tele" "gram"  # two halves: this file must not match itself
NEEDLE = re.compile(NEEDLE_TEXT, re.IGNORECASE)

_THIS = "tests/test_base_harness_no_" + NEEDLE_TEXT + ".py"
ALLOWLIST = {
    "CHANGELOG.md": "dated release history is not rewritten",
    "create-tess/template/CHANGELOG.md": "dated release history is not rewritten",
    "create-tess/README.md": "the one docs note: external notification channels "
    "are optional operator add-ons, outside the base harness",
}

# Not part of the base harness: the wizard's own test suite is never copied
# into a scaffold (it may assert that the removed flag is rejected), and
# reviews/verdicts/ holds per-PR review records (verdicts), stripped at
# integration and never scaffolded; a verdict on this change will name the
# channel. Narrowed from the whole reviews/ tree (Cyra, notg PR #197 low
# finding, decisions item 13): only the verdicts subtree is exempt, so any
# OTHER file under reviews/ still counts as base harness surface.
NOT_BASE_PREFIXES = ("create-tess/test/", "reviews/verdicts/", "create-tess/template/reviews/verdicts/")

# Files that must be in scope, so the scan can never go vacuous.
MUST_SCAN_PRODUCT = (
    ".tess/core/conductor/guardrails.md",
    ".tess/core/conductor/channel-guardrails.md",
    ".tess/core/settings-core.json",
    ".tess/core/templates/CLAUDE.md.tpl",
    ".tess/core/commands/wake.md",
    ".tess/core/hooks/dispatch-guard.sh",
    ".tess/bin/tessctl",
    "CLAUDE.md",
    ".claude/settings.json",
    ".claude/commands/wake.md",
    "conductor/guardrails.md",
    "create-tess/src/journey.js",
    "create-tess/src/args.js",
    "create-tess/template/CLAUDE.md",
    "create-tess/template/.tess/core/conductor/guardrails.md",
    "scripts/heartbeat/notify.py",
    ".env.example",
)
MUST_SCAN_INSTANCE = (
    ".tess/core/conductor/guardrails.md",
    ".tess/core/settings-core.json",
    ".tess/bin/tessctl",
)


def _is_binary(path: Path) -> bool:
    with path.open("rb") as fh:
        return b"\0" in fh.read(8000)


def _tracked_files() -> list[str]:
    if (REPO_ROOT / ".git").exists():
        r = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "ls-files", "-z"],
            capture_output=True, check=False,
        )
        if r.returncode == 0 and r.stdout:
            return sorted(p for p in r.stdout.decode("utf-8", "surrogateescape").split("\0") if p)
    out = []
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
        dirnames[:] = [d for d in dirnames if d not in (".git", "node_modules")]
        for name in filenames:
            out.append(Path(dirpath, name).relative_to(REPO_ROOT).as_posix())
    return sorted(out)


def _in_scope(rel: str) -> bool:
    if PRODUCT_REPO:
        return not rel.startswith(NOT_BASE_PREFIXES)
    return rel.startswith(".tess/core/") or rel == ".tess/bin/tessctl"


def _scanned_files() -> list[str]:
    return [rel for rel in _tracked_files() if _in_scope(rel)]


def _hits() -> list[str]:
    hits = []
    for rel in _scanned_files():
        if rel in ALLOWLIST:
            continue
        path = REPO_ROOT / rel
        if path.is_symlink():
            if NEEDLE.search(os.readlink(path)):
                hits.append(f"{rel}: symlink target names the channel")
            continue
        if not path.is_file() or _is_binary(path):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if not NEEDLE.search(text):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if NEEDLE.search(line):
                hits.append(f"{rel}:{n}: {line.strip()[:160]}")
    return hits


def test_scan_is_not_vacuous():
    scanned = set(_scanned_files())
    must = MUST_SCAN_PRODUCT if PRODUCT_REPO else MUST_SCAN_INSTANCE
    missing = [rel for rel in must if rel not in scanned]
    assert not missing, f"the guard does not scan: {missing}"


@pytest.mark.skipif(not PRODUCT_REPO, reason="product-repo scope rule")
def test_only_review_records_and_wizard_tests_leave_scope():
    """reviews/ and create-tess/test/ are the only exclusions; a look-alike
    path elsewhere (e.g. docs/reviews/) stays in scope."""
    assert not _in_scope("reviews/verdicts/2026-09-24-pr197-notg.cyra.verdict.md")
    assert not _in_scope("create-tess/template/reviews/verdicts/x.md")
    assert not _in_scope("create-tess/test/args.test.js")
    for rel in ("docs/reviews/x.md", "conductor/reviews.md", ".tess/core/conductor/guardrails.md",
                "create-tess/template/conductor/guardrails.md", "create-tess/src/args.js"):
        assert _in_scope(rel), rel


def test_base_harness_names_no_chat_channel():
    hits = _hits()
    assert not hits, (
        "The removed chat channel is named in the base harness (runtime-neutral reporting: the conductor "
        "reports in the active session; external channels are operator add-ons "
        "outside the base):\n  " + "\n  ".join(hits[:80])
        + (f"\n  ... and {len(hits) - 80} more" if len(hits) > 80 else "")
    )


def test_allowlist_stays_small_and_explicit():
    # Exactly the reasons named in the module docstring (the two CHANGELOG
    # copies and the one doc note; the template rebuild at v1.0.0 removed the
    # two pending-rebuild entries). Growing it needs a reason in the docstring.
    assert len(ALLOWLIST) == 3
    assert _THIS not in ALLOWLIST, "this guard must not match itself"
    assert ".env.example" not in ALLOWLIST, "v0.2.1 removed the placeholders"
    for rel, reason in ALLOWLIST.items():
        assert reason.strip(), rel
        assert "*" not in rel and "?" not in rel, f"allowlist entries are exact paths: {rel}"


def _settings_files() -> list[Path]:
    files = [REPO_ROOT / ".tess" / "core" / "settings-core.json"]
    if PRODUCT_REPO:
        files += [
            REPO_ROOT / ".claude" / "settings.json",
            REPO_ROOT / "create-tess" / "template" / ".tess" / "core" / "settings-core.json",
            REPO_ROOT / "create-tess" / "template" / ".claude" / "settings.json",
        ]
    return [f for f in files if f.is_file()]


def test_base_settings_wire_no_external_channel_tool():
    """No base hook targets an MCP plugin tool (an external chat channel),
    and no hook tells the conductor to message anyone outside the session."""
    files = _settings_files()
    assert files, "no settings file found; the check would be vacuous"
    problems = []
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        for event, groups in (data.get("hooks") or {}).items():
            for group in groups:
                matcher = group.get("matcher", "")
                if "mcp__" in matcher:
                    problems.append(f"{f.relative_to(REPO_ROOT)}: {event} matcher {matcher!r}")
                for hook in group.get("hooks", []):
                    cmd = hook.get("command", "")
                    if "mcp__" in cmd or re.search(r"send .{0,40}update to the operator", cmd, re.I):
                        problems.append(f"{f.relative_to(REPO_ROOT)}: {event} command {cmd[:120]!r}")
    assert not problems, "base settings wire an external channel:\n  " + "\n  ".join(problems)


@pytest.mark.skipif(
    not PRODUCT_REPO,
    reason="instance .env.example is operator space: an operator may add a channel of their own",
)
def test_env_example_carries_no_chat_channel_secrets():
    """v0.2.1: the two unused chat-channel placeholders are gone (was a strict xfail)."""
    env = REPO_ROOT / ".env.example"
    assert env.is_file(), ".env.example is missing"
    text = env.read_text(encoding="utf-8")
    keys = [
        line.split("=", 1)[0].strip()
        for line in text.splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    ]
    bad = [k for k in keys if re.search(r"BOT_TOKEN|CHAT_ID", k)]
    assert not bad, f".env.example configures a chat channel: {bad}"
    assert not NEEDLE.search(text), ".env.example still names the removed channel"


def test_this_guard_does_not_match_itself():
    assert not NEEDLE.search((REPO_ROOT / _THIS).read_text(encoding="utf-8"))


def _git_grep_hits() -> dict:
    """{path: [line, ...]} from a literal, case-insensitive `git grep` of the tracked tree."""
    r = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "grep", "-I", "-n", "-i", "-F", NEEDLE_TEXT],
        capture_output=True, text=True, check=False,
    )
    assert r.returncode in (0, 1), r.stderr
    hits: dict = {}
    for line in r.stdout.splitlines():
        rel, _, rest = line.partition(":")
        hits.setdefault(rel, []).append(rest)
    return hits


@pytest.mark.skipif(not PRODUCT_REPO or not (REPO_ROOT / ".git").exists(),
                    reason="product-repo git checkout only")
def test_literal_grep_finds_only_changelog_and_one_doc_line():
    """What an operator sees running `grep -ri <channel>` over the shipped tree
    (create-tess/template/ is a build artifact; see the pending-rebuild xfail)."""
    hits = {rel: lines for rel, lines in _git_grep_hits().items()
            if _in_scope(rel) and not rel.startswith("create-tess/template/")}
    assert set(hits) <= {"CHANGELOG.md", "create-tess/README.md"}, sorted(hits)
    assert len(hits.get("create-tess/README.md", [])) == 1, hits.get("create-tess/README.md")
    doc_line = " ".join(hits["create-tess/README.md"])
    assert "optional" in doc_line, doc_line
