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
import shutil
import subprocess
from pathlib import Path

import yaml

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


AGENT_TOOL_RE = re.compile(r"^(?:Agent|Task)(?:\(.*\))?$")


def _frontmatter(text: str) -> str | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    return text[4:end] if end != -1 else None


def _normalise_tools(value) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        return [t.strip() for t in value.split(",") if t.strip()]
    if isinstance(value, (list, tuple)):
        out: list[str] = []
        for item in value:
            out.extend(_normalise_tools(item) or [])
        return out
    return [str(value).strip()]


def _declared_tools(text: str) -> list[str] | None:
    """The `tools` entries an agent definition declares, or None when it
    declares none (the agent would then inherit every tool, Agent included).

    Accepts every form Claude Code reads: a comma string, a YAML block list,
    a flow list, and `Agent(<type>)` entries."""
    fm = _frontmatter(text)
    if fm is None:
        return None
    try:
        data = yaml.safe_load(fm)
    except yaml.YAMLError:
        data = None  # lenient runtimes accept frontmatter strict YAML rejects
    if isinstance(data, dict):
        return _normalise_tools(data.get("tools"))
    # Fallback: parse only the tools key and its indented or dashed continuation.
    lines = fm.splitlines()
    for i, line in enumerate(lines):
        if re.match(r"^tools\s*:", line):
            block = [line]
            for nxt in lines[i + 1 :]:
                if nxt.startswith((" ", "\t", "-")):
                    block.append(nxt)
                else:
                    break
            return _normalise_tools(yaml.safe_load("\n".join(block)).get("tools"))
    return None


def _grants_agent_tool(text: str) -> list[str] | None:
    tools = _declared_tools(text)
    if tools is None:
        return None
    return [t for t in tools if AGENT_TOOL_RE.match(t)]


def test_agent_tool_parser_catches_every_frontmatter_form():
    """Guards the next test against a false pass: each of these grants the
    Agent tool in a form a naive single-line comma split misses."""
    granting = {
        "block list": "---\nname: x\ntools:\n  - Read\n  - Agent\n---\nbody\n",
        "flow list": '---\nname: x\ntools: ["Read", "Agent"]\n---\nbody\n',
        "typed agent": "---\nname: x\ntools: Read, Agent(general-purpose)\n---\nbody\n",
        "legacy Task": "---\nname: x\ntools: Read, Task\n---\nbody\n",
        "non-strict YAML": "---\nname: x\ndescription: Use when: things break\ntools:\n  - Agent(worker)\n---\n",
    }
    for label, text in granting.items():
        assert _grants_agent_tool(text), f"parser missed the Agent tool in the {label} form"
    assert _grants_agent_tool("---\nname: x\ntools: Read, Grep, AgentOps\n---\n") == []
    assert _grants_agent_tool("---\nname: x\n---\nbody\n") is None


def test_single_dispatcher_policy_is_enforced_by_agent_tool_lists():
    """The doctrine now says the single dispatcher is enforced by leaving
    Agent/Task out of every Tess agent definition's `tools` list. Pin it.

    v0.2 ten-role roster (integration seam): the 144-persona roster this
    threshold was written against is gone -- personas are now lenses
    (conductor/lenses/**), and agents-dispatch/.claude/agents hold only the
    nine dispatchable roles (roster.md). 9 core role files + 9 compiled
    .claude/agents/ copies = 18. The substantive check below (no def grants
    Agent/Task) is unchanged and still runs over every one of them."""
    defs = sorted((CORE / "agents-dispatch").glob("*.md")) + sorted((REPO_ROOT / ".claude" / "agents").glob("*.md"))
    assert len(defs) >= 18, f"expected the ten-role roster (9 core + 9 compiled), found {len(defs)} agent definitions"
    problems = []
    for f in defs:
        granted = _grants_agent_tool(f.read_text(encoding="utf-8"))
        if granted is None:
            problems.append(f"{f.relative_to(REPO_ROOT)}: no explicit tools list (would inherit every tool)")
        elif granted:
            problems.append(f"{f.relative_to(REPO_ROOT)}: lists {granted}")
    assert not problems, "\n  ".join(problems)


# ---------------------------------------------------------------------------
# Private overlay: the File Placement Contract must not push kb/** or
# clients/** data into git (docs/DATA_LEAK_SAFETY.md).
# ---------------------------------------------------------------------------

KB_PATH_RE = re.compile(r"(?:<kb>/|(?<![\w./-])kb/|(?<![\w./-])clients/)")
STAGING_DEMAND_RE = re.compile(
    r"git add`?ed\b|git-added\b|\bstaged in git\b|\bmust be staged\b|must be `?git add\b"
    r"|git add (?!-A\b)(?!-f\b)[^`\n]*(?:kb|clients)/",
    re.I,
)
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z`*(\[])")


def _contract_rows(text: str) -> list[tuple[str, str]]:
    """(what, where) rows of the File Placement Contract table."""
    start = text.find("### File Placement Contract")
    assert start != -1, "File Placement Contract section not found"
    rows = []
    for line in text[start:].splitlines()[1:]:
        if line.startswith("#"):
            break
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.startswith("|") and len(cells) == 2 and not set(cells[1]) <= {"-"} and cells[0] != "What you are writing":
            rows.append((cells[0], cells[1]))
    return rows


def _concrete_paths(pattern: str) -> list[str]:
    """Expand a contract path pattern into concrete probe paths for both the
    internal and a client knowledge base."""
    out = []
    for kb in ("kb", "clients/Acme/kb"):
        p = pattern.replace("<kb>", kb).replace("YYYY-MM-DD", "2026-01-01").replace("[-slug]", "")
        p = re.sub(r"<[^>]+>", "probe", p)
        if p.endswith("/"):
            p += "probe.md"
        m = re.search(r"\{([^}]+)\}", p)
        variants = [p[: m.start()] + ext + p[m.end():] for ext in m.group(1).split(",")] if m else [p]
        out.extend(variants)
    return out


def _kb_destinations() -> list[str]:
    fragment = (CORE / "templates" / "claude-md" / "directory.md").read_text(encoding="utf-8")
    rendered = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    rows = _contract_rows(fragment)
    assert rows == _contract_rows(rendered), "rendered CLAUDE.md contract differs from its fragment; re-render"
    paths = []
    for _what, where in rows:
        for span in re.findall(r"`([^`]+)`", where):
            if "<kb>" in span:
                paths.extend(_concrete_paths(span))
    return paths


def _ignored(repo: Path, rel: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(repo), "check-ignore", "--no-index", "-q", rel], capture_output=True
    ).returncode == 0


def test_every_kb_destination_in_the_contract_is_gitignored(tmp_path):
    paths = _kb_destinations()
    assert len(paths) >= 12, f"only {len(paths)} kb destinations parsed; the test would be vacuous"
    # This repository's own .gitignore ...
    exposed = [p for p in paths if not _ignored(REPO_ROOT, p)]
    # ... and a fresh instance, which starts from the template's .gitignore.
    # (Inside a scaffolded instance there is no create-tess/ tree: the root
    # .gitignore checked above already is the template's copy.)
    template_gitignore = REPO_ROOT / "create-tess" / "template" / ".gitignore"
    if template_gitignore.is_file():
        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
        shutil.copyfile(template_gitignore, tmp_path / ".gitignore")
        exposed += [f"(fresh instance) {p}" for p in paths if not _ignored(tmp_path, p)]
    assert not exposed, "contract sends private overlay data to paths git would stage:\n  " + "\n  ".join(exposed)


def _overlay_scan_files() -> list[Path]:
    extra = [REPO_ROOT / "AGENTS.md", REPO_ROOT / "GEMINI.md"]
    for sub in ("agents-md", "gemini"):
        base = CORE / "templates" / sub
        if base.is_dir():
            extra.extend(sorted(p for p in base.rglob("*") if p.is_file()))
    return _doctrine_files() + [p for p in extra if p.is_file()]


def test_no_doctrine_requires_staging_private_overlay_paths():
    files = _overlay_scan_files()
    assert len(files) > 60, "doctrine tree not found; the test would be vacuous"
    hits = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for para in re.split(r"\n\s*\n|\n(?=\s*(?:[-*|#>]|\d+\.)\s)", text):
            for sentence in SENTENCE_SPLIT_RE.split(" ".join(para.split())):
                if KB_PATH_RE.search(sentence) and STAGING_DEMAND_RE.search(sentence):
                    hits.append(f"{f.relative_to(REPO_ROOT)}: {sentence[:160]}")
    assert not hits, (
        "kb/** and clients/** are private overlay data (gitignored, blocked by the publish-clean "
        "guard); doctrine must not tell agents to stage them:\n  " + "\n  ".join(hits)
    )


def test_staging_detector_flags_the_known_bad_wordings():
    bad = [
        "A file written under `kb/` or `clients/*/kb/` must be `git add`ed in the same session.",
        "A handover is written to `<kb>/wiki/missions/x.md` and staged in git before the session ends.",
        "Run `git add kb/wiki/missions/x.md` before you close.",
    ]
    good = [
        "`kb/**` is private overlay data. Never force it in with `git add -f`.",
        "Commit framework files with a path-scoped add, never `git add -A`.",
    ]
    for s in bad:
        assert KB_PATH_RE.search(s) and STAGING_DEMAND_RE.search(s), s
    for s in good:
        assert not (KB_PATH_RE.search(s) and STAGING_DEMAND_RE.search(s)), s
