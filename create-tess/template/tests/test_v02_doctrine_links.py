"""
v0.2.0 (ws-doc): shipped doctrine must not point at things that do not ship,
and must state facts about the platform correctly.

Checks, all against the REAL files in this repository:

  * every relative Markdown link in conductor/**, .claude/commands/** and
    CLAUDE.md resolves to an existing file or directory;
  * no doctrine or command file sends the reader to the `clienta-incident`
    workflow (no such workflow ships: there is no .claude/workflows/);
  * no doctrine file cites a dated internal record under kb/wiki/ that is
    not in the repository (e.g. the 2026-06-10 reform memo);
  * Rule Zero carries its scope line (it binds only the top-level
    conductor; dispatched specialists execute directly), both in the
    CLAUDE.md fragment and in the rendered CLAUDE.md;
  * no doctrine says "a subagent cannot spawn subagents". Claude Code can
    nest subagents; Tess keeps a single dispatcher by policy, by leaving
    Agent/Task out of every rendered agent's `tools` list, which the last
    test pins.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CORE = REPO_ROOT / ".tess" / "core"

LINK_RE = re.compile(r"(?<!!)\[[^\]\n]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
DATED_KB_RE = re.compile(r"kb/wiki/[A-Za-z0-9_./-]*\d{4}-\d{2}-\d{2}[A-Za-z0-9_./-]*\.md")
NESTING_LIE_RE = re.compile(r"subagents? cannot spawn|cannot spawn (?:a )?(?:further )?subagents?", re.I)
SCOPE_LINE = "binds only the top-level conductor"


def _md_files(*bases: Path) -> list[Path]:
    out: list[Path] = []
    for b in bases:
        if b.is_file():
            out.append(b)
        elif b.is_dir():
            out.extend(sorted(b.rglob("*.md")))
    return out


def _strip_code(text: str) -> str:
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    return re.sub(r"`[^`\n]*`", "", text)


def _doctrine_files() -> list[Path]:
    return _md_files(
        REPO_ROOT / "conductor",
        REPO_ROOT / ".claude" / "commands",
        CORE / "conductor",
        CORE / "commands",
        CORE / "templates" / "claude-md",
        REPO_ROOT / "CLAUDE.md",
    ) + [CORE / "templates" / "CLAUDE.md.tpl"]


def test_relative_links_in_live_doctrine_resolve():
    files = _md_files(REPO_ROOT / "conductor", REPO_ROOT / ".claude" / "commands", REPO_ROOT / "CLAUDE.md")
    assert len(files) > 40, "doctrine tree not found; the test would be vacuous"
    broken = []
    checked = 0
    for f in files:
        for target in LINK_RE.findall(_strip_code(f.read_text(encoding="utf-8"))):
            if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I) or target.startswith("#"):
                continue  # URL, mailto:, in-page anchor
            path = target.split("#", 1)[0]
            if not path:
                continue
            checked += 1
            if not (f.parent / path).exists():
                broken.append(f"{f.relative_to(REPO_ROOT)} -> {target}")
    assert checked > 100, f"only {checked} relative links found; the test would be vacuous"
    assert not broken, "broken relative links:\n  " + "\n  ".join(broken)


def test_no_reference_to_the_unshipped_clienta_incident_workflow():
    hits = []
    for base in (REPO_ROOT / "conductor", REPO_ROOT / ".claude", CORE / "conductor", CORE / "commands"):
        for f in sorted(p for p in base.rglob("*") if p.is_file()):
            try:
                text = f.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if "clienta-incident" in text:
                hits.append(str(f.relative_to(REPO_ROOT)))
    assert not hits, "doctrine points at a workflow that does not ship:\n  " + "\n  ".join(hits)


def test_no_dated_kb_wiki_citation_that_does_not_ship():
    missing = []
    for f in _doctrine_files():
        for ref in DATED_KB_RE.findall(f.read_text(encoding="utf-8")):
            if not (REPO_ROOT / ref).exists():
                missing.append(f"{f.relative_to(REPO_ROOT)} -> {ref}")
    assert not missing, "doctrine cites internal records that are not shipped:\n  " + "\n  ".join(missing)


def test_rule_zero_carries_its_scope_line():
    fragment = (CORE / "templates" / "claude-md" / "rule-zero.md").read_text(encoding="utf-8")
    rendered = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert SCOPE_LINE in fragment, "rule-zero.md must say Rule Zero binds only the top-level conductor"
    head = rendered.split("\n# ", 1)[0]  # the Rule Zero block at the top of CLAUDE.md
    assert SCOPE_LINE in head, "rendered CLAUDE.md Rule Zero block lacks the scope line"
    assert re.search(r"dispatched specialist[^.]*executes its task directly", fragment), (
        "the scope line must say dispatched specialists execute directly"
    )


def test_no_doctrine_claims_subagents_cannot_spawn_subagents():
    hits = []
    for f in _doctrine_files():
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if NESTING_LIE_RE.search(line):
                hits.append(f"{f.relative_to(REPO_ROOT)}:{i}")
    assert not hits, (
        "Claude Code can nest subagents; single-dispatcher is Tess policy. "
        "False platform claim at:\n  " + "\n  ".join(hits)
    )


def test_single_dispatcher_policy_is_enforced_by_agent_tool_lists():
    """The doctrine now says the single dispatcher is enforced by leaving
    Agent/Task out of every Tess agent definition's `tools` list. Pin it."""
    defs = sorted((CORE / "agents-dispatch").glob("*.md")) + sorted((REPO_ROOT / ".claude" / "agents").glob("*.md"))
    assert len(defs) >= 150, f"expected the full roster, found {len(defs)} agent definitions"
    problems = []
    for f in defs:
        tools = [ln for ln in f.read_text(encoding="utf-8").splitlines()[:40] if ln.startswith("tools:")]
        if len(tools) != 1:
            problems.append(f"{f.relative_to(REPO_ROOT)}: no explicit tools line (would inherit every tool)")
            continue
        names = {t.strip() for t in tools[0].split(":", 1)[1].split(",")}
        if names & {"Agent", "Task"}:
            problems.append(f"{f.relative_to(REPO_ROOT)}: lists {sorted(names & {'Agent', 'Task'})}")
    assert not problems, "\n  ".join(problems)
