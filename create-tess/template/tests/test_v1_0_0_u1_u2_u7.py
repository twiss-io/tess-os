r"""
1.0.0 usability softenings U1, U2, U7 (Reid, round-4 verify of 629f63d and
f66d393; approved for 1.0.0 by the operator on 22 Oct: "soften the
node_modules / recursive-delete prompts").

U1  A delete or chmod whose target is a recursive glob (`rm -rf
    **/__pycache__`) was refused from the text alone: `**` can spell a
    folder inside every protected folder. It is now decided from the files
    on disk: allowed when the listing is complete, crosses no link, and
    nothing earlier in the command changes files. Still refused: any name
    on disk that is, holds, or lies inside a protected path (looked at even
    when the listing stops early), and any listing cut short. A complete
    listing after an earlier change asks.
U2  Read-only commands over a big listing (`ls node_modules/*`, `grep x
    **/*.py`) asked "cannot tell whether it reaches its key directory".
    Inside the project, with the key directory outside it and every link
    under the pattern's folder staying inside the project, they no longer
    ask. Big write listings and `find` inside the project are checked name
    by name with a larger budget instead of asking.
U7  The same for a read-only recursive glob that crosses a link that stays
    inside the project. A write through a link is still refused (Z1).

Decisions: (claude default, claude acceptEdits, codex). The "allow" rows
fail on c80f6a3 (deny x3 or ask/ask/deny there).
"""

from __future__ import annotations

import os
import shutil

import pytest

from test_v1_n1_n3 import ALLOW, ASK, DENY, G, REPO, _all, _env  # noqa: F401 - fixtures


def _make_project(tmp, name):
    root = tmp / name
    for rel in (".tess/tess.lock", ".tess/core/pinned-scripts.sha256", "tessctl",
                "tess.manifest.json", "conductor/guardrails.md", "CLAUDE.md"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / rel, root / rel)
    for tree in (".claude/hooks", "scripts/brain", ".tess/bin", ".tess/vendor"):
        shutil.copytree(REPO / tree, root / tree, ignore=shutil.ignore_patterns("__pycache__"))
    (root / ".claude" / "settings.json").write_text("{}\n")
    for d in ("src/a/__pycache__", "src/b/__pycache__", "web/dist", "web/node_modules/x",
              "pkg/thing.egg-info", "tools"):
        (root / d).mkdir(parents=True, exist_ok=True)
    (root / "src" / "a" / "__pycache__" / "m.cpython-312.pyc").write_text("x")
    (root / "src" / "a" / "m.py").write_text("x = 1\n")
    (root / "tools" / "run.sh").write_text("echo hi\n")
    return root


@pytest.fixture(scope="module")
def proj(tmp_path_factory):
    """A small Tess project with everyday build output, and a fake HOME."""
    tmp = tmp_path_factory.mktemp("u1u2u7")
    root = _make_project(tmp, "proj")
    home = tmp / "home"
    (home / ".config").mkdir(parents=True)
    return root, home


@pytest.fixture(scope="module")
def big(proj):
    """A second project holding a dependency tree past every default limit
    (over 20,000 entries; one folder of over 1,000 names)."""
    root = _make_project(proj[0].parent, "big")
    nm = root / "node_modules"
    for i in range(1150):
        d = nm / f"pkg{i:04d}"
        d.mkdir(parents=True)
        for j in range(18):
            (d / f"f{j}.js").write_text("x")
    (root / "logs").mkdir()
    for i in range(1200):
        (root / "logs" / f"r{i}.log").write_text("x")
    (root / "src" / "a" / "b.ts").write_text("x")
    return root, proj[1]


def _ids(rows):
    return [r[0] for r in rows]


# ---------------------------------------------------------------- U1: decided from the listing
U1_ALLOW = [
    ("rm-pycache", "rm -rf **/__pycache__"),
    ("rm-pyc", "rm -f **/*.pyc"),
    ("rm-dist", "rm -rf **/dist"),
    ("rm-node-modules", "rm -rf **/node_modules"),
    ("rm-egg-info", "rm -rf **/*.egg-info"),
    ("chmod-sh", "chmod +x **/*.sh"),
    ("rm-scripts-pycache", "rm -rf scripts/**/__pycache__"),
    ("cd-then-rm", "cd src && rm -rf **/__pycache__"),
    ("triple-star", "rm -rf ***/__pycache__"),
]


@pytest.mark.parametrize("cmd", [c for _i, c in U1_ALLOW], ids=_ids(U1_ALLOW))
def test_u1_recursive_cleanup_allows(proj, cmd):
    assert _all(proj, cmd) == ALLOW


U1_STILL_DENY = [
    ("everything", "rm -rf **"),
    ("everything-below", "rm -rf ./**/*"),
    ("names-protected-folder", "rm -rf **/brain"),
    ("names-parent-of-protected", "chmod -R 777 **/scripts"),
    ("names-protected-file", "rm -rf **/tessctl"),
    ("names-protected-doc", "rm -rf **/guardrails.md"),
    ("names-claude-folder", "rm -rf **/.claude"),
    ("names-hooks", "rm -rf **/.claude/hooks"),
    ("fixed-protected-prefix", "rm -rf scripts/brain/**/x"),
    ("real-md-match", "sed -i '' s/a/b/ **/*.md"),
    ("real-py-match", "rm -f **/*.py"),
    ("climbs-out", "rm -rf **/../**/hooks"),
]


@pytest.mark.parametrize("cmd", [c for _i, c in U1_STILL_DENY], ids=_ids(U1_STILL_DENY))
def test_u1_real_protected_match_still_denies(proj, cmd):
    assert _all(proj, cmd) == DENY


def test_u1_real_match_inside_scripts_brain_denies(proj):
    """A real __pycache__ inside scripts/brain/ stays a deny, for the
    recursive form and for the find form."""
    pyc = proj[0] / "scripts" / "brain" / "brainlib" / "__pycache__"
    pyc.mkdir(parents=True, exist_ok=True)
    try:
        for cmd in ("rm -rf **/__pycache__", "rm -rf scripts/**/__pycache__", "rm -rf **/brainlib",
                    "find . -name __pycache__ -prune -exec rm -rf {} +"):
            assert _all(proj, cmd) == DENY, cmd
    finally:
        pyc.rmdir()


def test_u1_scripts_module_still_denies(proj):
    """scripts/<pkg>/__init__.py is protected (imported at session start)."""
    pkg = proj[0] / "scripts" / "zzpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    try:
        assert _all(proj, "rm -f **/__init__.py") == DENY
    finally:
        shutil.rmtree(pkg)


U1_ASK = [
    ("after-touch", "touch new.txt && rm -rf **/dist"),
    ("after-program", "python3 build.py; rm -rf **/dist"),
    ("in-loop", "for i in 1 2; do rm -rf **/dist; done"),
    ("in-function", "f() { rm -rf **/dist; }; f"),
]


@pytest.mark.parametrize("cmd", [c for _i, c in U1_ASK], ids=_ids(U1_ASK))
def test_u1_after_a_change_asks_and_names_find(proj, cmd):
    assert _all(proj, cmd) == ASK
    reason = G.decide({"tool_name": "Bash", "cwd": str(proj[0]), "permission_mode": "default",
                       "tool_input": {"command": cmd}}, proj[0], "claude")[1]
    assert "find . -name <name> -prune -exec rm -rf {} +" in reason


def test_u1_through_links_inside_the_project(proj):
    """A link inside the project to a protected folder: the recursive write
    still asks, as on c80f6a3 (Z1: the listing crosses the link); a read-only recursive glob
    through it is allowed (U7: the link stays inside the project)."""
    sub = proj[0] / "lk1"
    sub.mkdir()
    os.symlink(str(proj[0] / ".claude"), str(sub / "lk"))
    try:
        assert _all(proj, "rm -rf lk1/***/hooks") == ASK
        assert _all(proj, "rm -rf lk1/**/hooks") == ASK  # bash: `*/hooks` enters the link
        assert _all(proj, "ls lk1/***/*.json") == ALLOW
        assert _all(proj, "cat lk1/***/settings.json") == ALLOW
    finally:
        shutil.rmtree(sub)


# ---------------------------------------------------------------- U2: big listings inside the project
U2_BIG_ALLOW = [
    ("ls-node-modules", "ls node_modules/*"),
    ("du-node-modules", "du -sh node_modules/*"),
    ("ls-starstar-js", "ls **/*.js"),
    ("wc-starstar-ts", "wc -l **/*.ts"),
    ("grep-starstar", "grep -n TODO **/*.py"),
    ("cat-logs", "cat logs/*.log"),
    ("rm-logs", "rm -f logs/*.log"),
    ("rm-node-modules", "rm -rf **/node_modules"),
    ("rm-pycache", "rm -rf **/__pycache__"),
    ("find-prune-exec", "find . -name __pycache__ -prune -exec rm -rf {} +"),
]


@pytest.mark.parametrize("cmd", [c for _i, c in U2_BIG_ALLOW], ids=_ids(U2_BIG_ALLOW))
def test_u2_big_tree_inside_project_allows(big, cmd):
    assert _all(big, cmd) == ALLOW


def test_u2_big_tree_write_still_checks_every_name(big):
    """A big listing is checked name by name: a real protected match in it
    is still refused."""
    for cmd in ("rm -f **/*.py", "find . -name '*.py' -delete", "chmod 777 **/*.js **/*.py"):
        assert _all(big, cmd) == DENY, cmd


def test_u2_link_out_of_project_still_asks(big):
    """A link under the pattern's folder that leaves the project: the names
    Tess did not list may reach the key directory, so it asks."""
    out = big[0] / "node_modules" / "zz-out"
    os.symlink(str(big[1]), str(out))
    try:
        assert _all(big, "ls node_modules/*") == ASK
        assert _all(big, "grep -rn x node_modules/*") == ASK
    finally:
        out.unlink()


@pytest.mark.parametrize("cmd", ["ls node_modules/*/../*", "cat node_modules/*/../../logs/*"])
def test_u2_a_step_that_climbs_out_still_asks(big, cmd):
    assert _all(big, cmd) == ASK


def test_u2_link_on_the_fixed_folder_still_asks(big):
    lnk = big[0] / "nm-link"
    os.symlink(str(big[0] / "node_modules"), str(lnk))
    try:
        assert _all(big, "ls nm-link/*") == ASK
    finally:
        lnk.unlink()


def test_u2_key_dir_inside_project_still_asks(big, monkeypatch):
    """When the key directory lies inside the project, nothing is softened."""
    cfg = big[0] / "cfg"
    (cfg / "tess").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(cfg))
    try:
        assert _all(big, "ls node_modules/*") == ASK
    finally:
        shutil.rmtree(cfg)


def test_u2_outside_project_keeps_the_old_limits(big, tmp_path):
    """A big listing outside the project still asks."""
    d = tmp_path / "many"
    d.mkdir()
    for i in range(1100):
        (d / f"f{i}").write_text("x")
    assert _all(big, f"ls {d}/*") == ASK
    assert _all(big, f"rm -f {d}/*") == ASK


# ---------------------------------------------------------------- helpers
def test_fast_clear_never_clears_what_protected_hit_flags(big):
    root = big[0]
    fast = G._fast_cache(root)
    base = os.path.realpath(str(root))
    for rel in ("CLAUDE.md", "tessctl", "scripts/brain/tessbrain.py", "scripts/x.py",
                "scripts/pkg/__init__.py", ".claude/hooks/tess-gate.py", ".claude/settings.local.json",
                "conductor/guardrails.md", ".tess/tess.lock", "core/contracts/a.json", "scripts",
                ".git/config", "a/etc/gitconfig"):
        assert not G._fast_clear(fast, os.path.join(base, rel)), rel
    assert G._fast_clear(fast, os.path.join(base, "node_modules", "pkg0001", "f1.js"))
    assert G._fast_clear(fast, os.path.join(base, "logs", "r1.log"))
    lnk = root / "logs" / "lnk"
    os.symlink(str(root / "CLAUDE.md"), str(lnk))
    try:
        assert not G._fast_clear(fast, str(lnk))
    finally:
        lnk.unlink()


def test_glob_reports_why_a_listing_was_cut(big, tmp_path):
    assert G._glob(str(big[0]), "logs/*").cause == "limit"
    assert G._glob(str(big[0]), "logs/*", G._BIG_GLOB_LIMIT, G._BIG_WALK_LIMIT).truncated is False
    w = tmp_path / "w"
    (w / "d").mkdir(parents=True)
    os.symlink(str(tmp_path), str(w / "d" / "l"))
    assert G._glob(str(w), "***/x").cause == "link"
