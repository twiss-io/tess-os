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
