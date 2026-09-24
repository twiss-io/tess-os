"""v0.2 ten-role roster: the shipped roster data, role files, lens library and
the codex render of the roles.

Asserts behaviour on the REAL shipped files (roster-paths.json, the nine role
files, conductor/lenses/) plus the codex target's compile step on a synthetic
root (sandbox fail-closed, TOML escaping, benched roles not emitted).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from conftest import REPO_ROOT

ROLES = ["ada", "clio", "cyra", "iris", "leah", "morwenna", "quinn", "reid", "vega"]
READ_ONLY_TOOL_ROLES = {"morwenna", "leah", "reid", "cyra", "quinn"}
DISPATCHED_LINE = (
    "You are a dispatched specialist: execute directly, never re-delegate or spawn agents."
)
CORE = REPO_ROOT / ".tess" / "core"
LENS_DIR = CORE / "conductor" / "lenses"


def _frontmatter(path: Path) -> dict:
    m = re.match(r"---\n(.*?)\n---\n", path.read_text(encoding="utf-8"), re.S)
    assert m, f"{path} has no frontmatter"
    out = {}
    for line in m.group(1).splitlines():
        k, _, v = line.partition(":")
        out[k.strip()] = v.strip()
    return out


def test_roster_paths_install_the_same_nine_roles_on_every_path():
    data = json.loads((CORE / "roster-paths.json").read_text(encoding="utf-8"))
    assert sorted(data["universal_base"]) == ROLES
    assert data["paths"], "at least one starter path"
    for name, cfg in data["paths"].items():
        assert cfg["squad"] == [], f"{name}: squads are empty in the ten-role roster"
        assert cfg["orchestrators"] == [], f"{name}: orchestrators are lenses now"
        assert cfg["default_lenses"], f"{name}: suggests at least one lens"
        for lens in cfg["default_lenses"]:
            assert (LENS_DIR / f"{lens}.md").is_file(), f"{name}: unknown lens {lens!r}"


def test_agents_dispatch_holds_exactly_the_nine_roles():
    names = sorted(p.stem for p in (CORE / "agents-dispatch").glob("*.md"))
    assert names == ROLES


@pytest.mark.parametrize("role", ROLES)
def test_role_file_permissions_and_dispatch_line(role):
    path = CORE / "agents-dispatch" / f"{role}.md"
    fm = _frontmatter(path)
    assert fm["name"] == role
    assert fm["sandbox"] in ("read-only", "workspace-write")
    assert DISPATCHED_LINE in path.read_text(encoding="utf-8")
    tools = {t.strip() for t in fm["tools"].split(",")}
    if role in READ_ONLY_TOOL_ROLES:
        assert not tools & {"Write", "Edit"}, f"{role} must not hold Write/Edit"
    if role == "morwenna":
        assert fm["model"] == "haiku"
        assert fm["sandbox"] == "read-only"
        assert not tools & {"WebSearch", "WebFetch"}
    if role == "leah":
        assert {"WebSearch", "WebFetch"} <= tools
        assert fm["sandbox"] == "read-only"
    if role == "reid":
        assert fm["sandbox"] == "read-only"


def test_every_former_persona_is_a_lens_not_an_agent():
    lenses = sorted(p.stem for p in LENS_DIR.glob("*.md") if p.name != "README.md")
    assert len(lenses) >= 140
    assert not set(lenses) & set(ROLES), "a role must not also be a lens"
    for required in ("eva", "verity", "maialen", "lysandra", "revenue-orchestrator",
                     "founders-office-orchestrator", "athena"):
        assert required in lenses
    index = (LENS_DIR / "README.md").read_text(encoding="utf-8")
    docs_index = (REPO_ROOT / "docs" / "LENSES.md").read_text(encoding="utf-8")
    for name in lenses:
        text = (LENS_DIR / f"{name}.md").read_text(encoding="utf-8")
        assert "Lens, not an agent" in text, name
        assert f"| `{name}` |" in index, f"{name} missing from lens index"
        assert f"| `{name}` |" in docs_index, f"{name} missing from docs/LENSES.md"


def test_live_claude_agents_match_the_roles():
    live = sorted(p.stem for p in (REPO_ROOT / ".claude" / "agents").glob("*.md"))
    assert live == ROLES


# --- codex render target -----------------------------------------------------

def _root_with_roles(tmp_path: Path, roles: dict, staged=()) -> Path:
    """roles: name -> frontmatter sandbox value (None = omit the field)."""
    root = tmp_path
    d = root / ".tess" / "core" / "agents-dispatch"
    d.mkdir(parents=True)
    files = {}
    for name, sandbox in roles.items():
        fm = f"---\nname: {name}\ndescription: {name} role with \"quotes\"\nmodel: sonnet\ntools: Read\n"
        if sandbox is not None:
            fm += f"sandbox: {sandbox}\n"
        (d / f"{name}.md").write_text(fm + "---\n\nBody for " + name + " with ''' quotes.\n"
                                      if name == "q" else fm + "---\n\nBody for " + name + ".\n",
                                      encoding="utf-8")
        files[f".tess/core/agents-dispatch/{name}.md"] = {
            "status": "staged" if name in staged else "core-managed",
            "tier": "normal", "base_sha": "sha256:0", "live_path": f".claude/agents/{name}.md",
        }
    import yaml
    (root / ".tess" / "tess.lock").write_text(yaml.safe_dump({"schema": 1, "files": files}),
                                             encoding="utf-8")
    return root


def _toml(data: bytes) -> dict:
    tomllib = pytest.importorskip("tomllib")  # stdlib on 3.11+
    return tomllib.loads(data.decode("utf-8"))


def test_codex_agent_sandbox_fails_closed(engine, tmp_path):
    root = _root_with_roles(tmp_path, {"w": "workspace-write", "r": "read-only",
                                       "missing": None, "bogus": "danger-full-access"})
    got = {n: _toml(engine._render_codex_agent_bytes(root, n))["sandbox_mode"]
           for n in ("w", "r", "missing", "bogus")}
    assert got == {"w": "workspace-write", "r": "read-only",
                   "missing": "read-only", "bogus": "read-only"}


def test_codex_agent_toml_round_trips_body_and_escapes(engine, tmp_path):
    root = _root_with_roles(tmp_path, {"q": "read-only", "p": "read-only"})
    q = _toml(engine._render_codex_agent_bytes(root, "q"))
    assert q["name"] == "q"
    assert q["description"] == 'q role with "quotes"'
    assert "with ''' quotes." in q["developer_instructions"]
    p = _toml(engine._render_codex_agent_bytes(root, "p"))
    assert p["developer_instructions"] == "Body for p.\n"


def test_codex_target_emits_only_installed_roles(engine, tmp_path):
    root = _root_with_roles(tmp_path, {"a": "read-only", "b": "read-only"}, staged=("b",))
    target = engine.RENDER_TARGETS["codex"]
    paths = target.render_generated_paths(root)
    assert ".codex/agents/a.toml" in paths
    assert ".codex/agents/b.toml" not in paths
    assert target.expected_live_bytes(root, ".codex/agents/b.toml") is None
    assert target.expected_live_bytes(root, ".codex/agents/a.toml") == \
        engine._render_codex_agent_bytes(root, "a")


def test_real_repo_codex_agents_are_current(engine):
    target = engine.RENDER_TARGETS["codex"]
    live_dir = REPO_ROOT / ".codex" / "agents"
    assert sorted(p.stem for p in live_dir.glob("*.toml")) == ROLES
    for role in ROLES:
        rel = f".codex/agents/{role}.toml"
        assert (REPO_ROOT / rel).read_bytes() == target.expected_live_bytes(REPO_ROOT, rel), rel


# --- codex role mirror lifecycle (QA fix round 1) -----------------------------

def _codex_project(project):
    """A synthetic install with two real-shaped roles and codex ENABLED."""
    for name in ("alpha", "beta"):
        project.add(
            f".claude/agents/{name}.md",
            f"---\nname: {name}\ndescription: {name}\nmodel: sonnet\ntools: Read\n"
            f"sandbox: read-only\n---\n\nBody {name}.\n",
            core_key=f".tess/core/agents-dispatch/{name}.md",
            status="core-managed",
        )
    project.write()
    (project.root / ".tess" / "core" / "roster-paths.json").write_text(
        json.dumps({"universal_base": ["alpha", "beta"], "paths": {}}), encoding="utf-8")
    mpath = project.root / "tess.manifest.json"
    m = json.loads(mpath.read_text(encoding="utf-8"))
    m["render_targets"]["enabled"] = ["claude-code", "codex"]
    mpath.write_text(json.dumps(m), encoding="utf-8")
    return project


def test_codex_sync_never_deletes_user_authored_agents(engine, project, capsys):
    p = _codex_project(project)
    agents = p.root / ".codex" / "agents"
    agents.mkdir(parents=True, exist_ok=True)
    mine = agents / "mine.toml"
    mine.write_text('name = "mine"\ndescription = "my own agent"\n', encoding="utf-8")
    stale = agents / "gamma.toml"
    stale.write_text(engine.CODEX_AGENT_HEADER_PREFIX + " from x. Do not edit.\nname = \"gamma\"\n",
                     encoding="utf-8")
    roles = engine._sync_codex_role_agents(p.root)
    assert roles == ["alpha", "beta"]
    assert mine.read_text(encoding="utf-8").startswith('name = "mine"'), "user file must survive"
    assert not stale.exists(), "a generated file for an uninstalled role is removed"
    assert (agents / "alpha.toml").is_file() and (agents / "beta.toml").is_file()
    out = capsys.readouterr().out
    assert "removed   .codex/agents/gamma.toml" in out
    assert "mine.toml" not in out


def test_bench_and_recruit_keep_codex_mirror_in_step(engine, project):
    p = _codex_project(project)
    engine._sync_codex_role_agents(p.root)
    beta = p.root / ".codex" / "agents" / "beta.toml"
    assert beta.is_file()
    from conftest import ns
    engine.cmd_bench(ns(names=["beta"]), p.root)
    assert not beta.exists(), "benching a role removes its codex agent file"
    assert not (p.root / ".claude" / "agents" / "beta.md").exists()
    engine.cmd_recruit(ns(names=["beta"]), p.root)
    assert beta.is_file(), "recruiting a role restores its codex agent file"
    assert beta.read_bytes() == engine._render_codex_agent_bytes(p.root, "beta")


def test_lenses_plus_roles_equal_the_pre_v02_persona_set():
    """Every pre-v0.2 persona (agents/<name>/ spec dirs + the six outcome
    orchestrators) is either one of the nine roles or exactly one lens."""
    persona_dirs = {p.name for p in (CORE / "agents").iterdir() if p.is_dir()}
    orchestrators = {p.stem for p in (CORE / "conductor" / "outcome-orchestrators").glob("*-orchestrator.md")}
    assert len(orchestrators) == 6
    before = persona_dirs | orchestrators
    lenses = {p.stem for p in LENS_DIR.glob("*.md") if p.name != "README.md"}
    assert len(before) == 150
    assert lenses | set(ROLES) == before
    assert not lenses & set(ROLES)
    assert len(lenses) == 141


# --- doctrine never dispatches a lens as an agent (QA fix round 1) ------------

def _fold(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _doctrine_lines(path):
    """Lines of a doctrine file up to its CHANGELOG (history records what
    WAS true and is allowed to name the pre-v0.2 roster)."""
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip().upper() == "## CHANGELOG":
            return
        yield i, line


def _doctrine_files():
    roots = [CORE / "conductor", CORE / "commands", CORE / "templates"]
    for r in roots:
        for p in sorted(r.rglob("*")):
            if p.is_file() and p.suffix in (".md", ".tpl") and "lenses" not in p.parts:
                yield p


def test_doctrine_never_dispatches_a_lens_as_an_agent():
    lens_names = sorted(p.stem for p in LENS_DIR.glob("*.md") if p.name != "README.md")
    people = [n for n in lens_names if not n.endswith("-orchestrator")]
    name_alt = "|".join(re.escape(n) for n in people)
    orch_alt = "|".join(re.escape(n) for n in lens_names if n.endswith("-orchestrator"))
    verbs = (r"dispatch(?:es|ed|ing)?|invoke[sd]?|engage[sd]?|assign(?:s|ed)?|recruit(?:s|ed)?"
             r"|delegate[sd]? to|route[sd]? to|request")
    patterns = [
        # "dispatch Tamsin", "assigns Eva", "Request Eva" — a lens as a dispatch target
        re.compile(rf"\b(?:{verbs})\s+(?:\*\*)?(?:the\s+)?(?:{name_alt})\b(?!\s+lens)(?!`)", re.I),
        # an orchestrator named as something dispatched ("dispatch revenue-orchestrator")
        re.compile(rf"\b(?:{verbs})\s+(?:\*\*|`)?(?:{orch_alt})\b(?!\.md)", re.I),
        # a lens persona as the actor of crew design/recruiting
        re.compile(rf"\b(?:{name_alt})\s+(?:designs|recruits|redesigns|runs intake|owns all promotion)\b", re.I),
        re.compile(r"\bvia Eva\b|\bOwner:\*\*\s*Eva\b", re.I),
    ]
    hits = []
    for path in _doctrine_files():
        for i, line in _doctrine_lines(path):
            folded = _fold(line)
            for pat in patterns:
                m = pat.search(folded)
                if m:
                    hits.append(f"{path.relative_to(REPO_ROOT)}:{i}: {m.group(0)!r}")
    assert not hits, "doctrine dispatches a lens as an agent:\n" + "\n".join(hits)


def test_doctrine_verifier_lists_name_only_the_three_verifier_roles():
    bad = re.compile(r"\((?:Reid|Quinn|Cyra)(?:\s*/\s*\w+)*\s*/\s*(?:Verity|Maialen|Lysandra)\b")
    hits = [f"{p.relative_to(REPO_ROOT)}:{i}"
            for p in _doctrine_files()
            for i, line in _doctrine_lines(p)
            if bad.search(line)]
    assert not hits, hits
