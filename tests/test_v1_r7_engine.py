"""v1.0 final review, round 3 (engine writer): items C1, B6, B7 and B8 of
scratchpad/final-review/r7/review.md. Every test below that names a review
input failed at a6feef2.

  * C1  tess.manifest.json decides what doctor/verify/update inspect
        (owned_globs, never_touch, render_targets.enabled) and what the
        publish-clean gate exempts. It is now security configuration: the
        gate denies assistant edits, the security-tier policy and CODEOWNERS
        name it, and the enforcement anchor records it, so an edit made by a
        program the gate cannot see stops Tess until the operator runs
        `tessctl anchor accept` (or `tessctl restore`). A verified update's
        owned-glob adoption is the only automated writer, and re-anchors it.
  * B6  `tessctl lock --regen` (and `--only`) refuses an assistant session
        before any re-pin; without --yes it asks for the typed confirmation at
        a real terminal (the shared presence helper). `publish --force` asks
        its question only at a real terminal outside an assistant session.
  * B7  an owned glob adopted from a release never beats the operator's own
        never_touch: intersecting globs are not adopted, and the write gate
        keeps the operator's exclusion on concrete paths.
  * B8  the core.hooksPath tripwire fails closed when git cannot be run or
        queried in a project with a .git; only a project with no .git passes.
"""
from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from _presence_pty import operator_env, run_tessctl_in_pty

REPO = Path(__file__).resolve().parent.parent
HAS_GIT = shutil.which("git") is not None
MANIFEST = "tess.manifest.json"


def _load(path: Path, name: str):
    sys.dont_write_bytecode = True  # never leave __pycache__ in .claude/hooks
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader))
    loader.exec_module(mod)
    return mod


G = _load(REPO / ".claude/hooks/tess-gate.py", "tess_gate_r7_engine")
L = _load(REPO / ".claude/hooks/run-pinned.py", "run_pinned_r7_engine")


def _git(root, *args):
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


@pytest.fixture
def proj(tmp_path):
    """A Tess instance copy in a git repo with one commit."""
    root = tmp_path / "proj"
    for rel in (".tess/tess.lock", ".tess/core/pinned-scripts.sha256", "tessctl", MANIFEST,
                "conductor/guardrails.md", "CLAUDE.md", ".claude/settings.json",
                ".tess/core/policy/policy.yaml", "core/policy/policy.yaml"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / rel, root / rel)
    for tree in (".claude/hooks", "scripts/brain", ".tess/bin", ".tess/vendor"):
        shutil.copytree(REPO / tree, root / tree, ignore=shutil.ignore_patterns("__pycache__"))
    (root / "kb" / "research").mkdir(parents=True)
    (root / "README.md").write_text("readme\n")
    if HAS_GIT:
        _git(tmp_path, "init", "-b", "main", "-q", str(root))
        _git(root, "add", "-A")
        _git(root, "-c", "user.email=t@tess.test", "-c", "user.name=T", "-c", "commit.gpgsign=false",
             "commit", "-q", "--no-verify", "-m", "init")
    return root


@pytest.fixture
def anchored(proj, engine, monkeypatch):
    """`proj` with a real enforcement anchor (under the suite's fake OS home)."""
    monkeypatch.setattr(engine, "_RELEASE_WRITES", {})
    where = engine._anchor_write(proj, "test")
    yield proj
    shutil.rmtree(where.parent, ignore_errors=True)
    (engine._anchor_tess_dir() / "projects" / "by-path" / (engine._anchor_path_key(proj) + ".json")
     ).unlink(missing_ok=True)


def _level(root, tool, tin, codex=False):
    data = {"tool_name": tool, "cwd": str(root), "tool_input": tin, "permission_mode": "default"}
    if codex:
        data["turn_id"] = "t1"
    return ["allow", "ask", "deny"][G.evaluate(data, root).level]


def _edit_manifest(root: Path, change) -> None:
    """Change the manifest the way a program the gate cannot see would."""
    path = root / MANIFEST
    doc = json.loads(path.read_text(encoding="utf-8"))
    change(doc)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- C1


@pytest.mark.parametrize("tool,tin", [
    ("Edit", {"file_path": MANIFEST, "old_string": '".agents/skills/tess-*/**",', "new_string": ""}),
    ("Write", {"file_path": MANIFEST, "content": "{}"}),
    ("Bash", {"command": "sed -i '' 's/\"codex\", //' tess.manifest.json"}),
    ("Bash", {"command": "python3 -c 'print(1)' > tess.manifest.json"}),
    ("Bash", {"command": "rm tess.manifest.json"}),
    ("Bash", {"command": "mv tess.manifest.json /tmp/m.json"}),
])
def test_the_gate_denies_assistant_edits_of_the_manifest(proj, tool, tin):
    if tool in ("Edit", "Write"):
        tin = dict(tin, file_path=str(proj / tin["file_path"]))
    assert _level(proj, tool, tin) == "deny"
    assert _level(proj, tool, tin, codex=True) == "deny"


def test_reading_the_manifest_stays_allowed(proj):
    assert _level(proj, "Bash", {"command": "cat tess.manifest.json"}) == "allow"
    assert _level(proj, "Read", {"file_path": str(proj / MANIFEST)}) == "allow"


def test_manifest_is_security_tier_in_gate_policy_codeowners_and_anchor(engine):
    assert MANIFEST in G.PROTECTED_GLOBS
    for rel in ("core/policy/policy.yaml", ".tess/core/policy/policy.yaml"):
        text = (REPO / rel).read_text(encoding="utf-8")
        rule = text[text.index("id: tess-os-security-tier-doctrine"):]
        rule = rule[:rule.index("\n    - id:")]
        assert f"- {MANIFEST}\n" in rule, rel
    owners = (REPO / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
    assert f"/{MANIFEST} " in owners
    assert MANIFEST in L.ANCHOR_FILES and MANIFEST in engine.ANCHOR_FILES
    assert tuple(L.ANCHOR_FILES) == tuple(engine.ANCHOR_FILES)


def _assert_detected(engine, root):
    problems = L.anchor_problems(root, L.anchor_locate(root)[0])
    assert f"{MANIFEST} has changed" in problems, problems
    with pytest.raises(L.AnchorError):
        L.anchor_check(root)
    findings = engine._anchor_findings(root)
    assert findings and f"  - {MANIFEST} has changed" in findings, findings
    assert engine._anchor_state(root).state == "mismatch"


@pytest.mark.skipif(not HAS_GIT, reason="needs git")
def test_c1_removing_an_owned_glob_is_refused_and_detected(anchored, engine):
    """Review C1 input 1: drop `.agents/skills/tess-*/**` from owned_globs,
    then edit a Tess skill: the untracked-render drift check no longer sees it."""
    root = anchored
    edit = {"file_path": str(root / MANIFEST), "old_string": '    ".agents/skills/tess-*/**",\n',
            "new_string": ""}
    assert _level(root, "Edit", edit) == "deny"
    _edit_manifest(root, lambda d: d["owned_globs"].remove(".agents/skills/tess-*/**"))
    assert not engine.path_matches_globs(".agents/skills/tess-help/SKILL.md",
                                         engine.load_manifest(root)["owned_globs"])
    _assert_detected(engine, root)


@pytest.mark.skipif(not HAS_GIT, reason="needs git")
def test_c1_disabling_a_render_target_is_refused_and_detected(anchored, engine):
    """Review C1 input 2: `enabled` loses codex and gemini, so their artifacts
    drop out of the render and drift checks."""
    root = anchored
    assert _level(root, "Write", {"file_path": str(root / MANIFEST), "content": "{}"}) == "deny"
    before = set(engine.enabled_render_targets(root))
    _edit_manifest(root, lambda d: d["render_targets"].__setitem__("enabled", ["claude-code"]))
    assert {"codex", "gemini"} <= before - set(engine.enabled_render_targets(root))
    _assert_detected(engine, root)


@pytest.mark.skipif(not HAS_GIT, reason="needs git")
def test_c1_owning_kb_is_refused_and_detected(anchored, engine):
    """Review C1 input 3: adding `kb/**` to owned_globs exempts a staged
    kb/research note from the publish-clean finding."""
    root = anchored
    (root / "kb" / "research" / "note.md").write_text("private\n")
    _git(root, "add", "kb/research/note.md")
    assert engine._publish_clean_violations(root, engine.load_manifest(root))
    cmd = "python3 - <<'EOF'\nimport json\np='tess.manifest.json'\nd=json.load(open(p))\n" \
          "d['owned_globs'].append('kb/**')\njson.dump(d, open(p,'w'))\nEOF"
    assert _level(root, "Bash", {"command": cmd}) != "allow"
    _edit_manifest(root, lambda d: d["owned_globs"].append("kb/**"))
    assert engine._publish_clean_violations(root, engine.load_manifest(root)) == []
    _assert_detected(engine, root)


@pytest.mark.skipif(not HAS_GIT, reason="needs git")
def test_restore_puts_the_approved_manifest_back(anchored, engine):
    root = anchored
    approved = (root / MANIFEST).read_bytes()
    _edit_manifest(root, lambda d: d["owned_globs"].append("kb/**"))
    assert engine._anchor_restore(root) == []
    assert (root / MANIFEST).read_bytes() == approved
    assert engine._anchor_state(root).state == "ok"


def _stage_release_manifest(engine, root, monkeypatch, doc):
    data = json.dumps(doc).encode()
    path = root / ".tess" / "staging" / engine.STAGED_RELEASE_MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    table = {engine.STAGED_RELEASE_MANIFEST: "sha256:" + hashlib.sha256(data).hexdigest()}
    monkeypatch.setitem(engine._STAGING_STATE, "verified", table)
    monkeypatch.setitem(engine._STAGING_STATE, "root", str(Path(root).resolve()))


@pytest.mark.skipif(not HAS_GIT, reason="needs git")
def test_update_adoption_reanchors_the_manifest(anchored, engine, monkeypatch):
    """Step 6.7 is the only automated writer: what it writes is re-anchored."""
    root = anchored
    release = json.loads((REPO / MANIFEST).read_text(encoding="utf-8"))
    release["owned_globs"] = release["owned_globs"] + ["new/release/path/**"]
    _stage_release_manifest(engine, root, monkeypatch, release)
    assert engine._update_adopt_owned_globs(root, {}) == ["new/release/path/**"]
    engine._anchor_after_release(root, "update")
    assert engine._anchor_state(root).state == "ok"
    rec = engine._anchor_state(root).doc["files"][MANIFEST]
    assert rec["sha256"] == hashlib.sha256((root / MANIFEST).read_bytes()).hexdigest()


@pytest.mark.skipif(not HAS_GIT, reason="needs git")
def test_update_never_reblesses_a_manifest_edit_it_did_not_make(anchored, engine, monkeypatch):
    root = anchored
    _edit_manifest(root, lambda d: d["owned_globs"].append("kb/**"))
    with pytest.raises(SystemExit) as exc:
        engine._anchor_after_release(root, "update")
    assert MANIFEST in str(exc.value.code) and "did NOT record" in str(exc.value.code)
    with pytest.raises(SystemExit):
        engine._anchor_refuse_unless_clean(root, "update")


@pytest.mark.skipif(not HAS_GIT, reason="needs git")
def test_an_older_anchor_records_the_manifest_on_the_next_verified_update(anchored, engine):
    """An anchor written before the manifest was anchored lacks it: the next
    verified update records the manifest as it is, and says so."""
    root = anchored
    st = engine._anchor_state(root)
    doc = dict(st.doc)
    doc["files"] = {k: v for k, v in doc["files"].items() if k != MANIFEST}
    engine._anchor_write_private(Path(st.where), (json.dumps(doc) + "\n").encode())
    assert engine._anchor_state(root).state == "ok"
    engine._anchor_after_release(root, "update")
    assert MANIFEST in engine._anchor_state(root).doc["files"]
    _edit_manifest(root, lambda d: d["owned_globs"].append("kb/**"))
    assert engine._anchor_state(root).state == "mismatch"


def test_engine_notes_tell_the_operator_how_to_change_the_manifest():
    text = (REPO / ".tess/bin/tessctl").read_text(encoding="utf-8")
    for start in ("output(s) not written — outside owned_globs", "outside owned_globs are not rendered"):
        i = text.index(start)
        assert "anchor accept" in text[i:i + 500], start
    sec = (REPO / "SECURITY.md").read_text(encoding="utf-8")
    assert "tess.manifest.json" in sec and "anchor accept" in sec


# --------------------------------------------------------------------------- B6


def _seed(project):
    project.add("conductor/a.md", "alpha\n")
    project.add("agents/leah/README.md", "leah\n")
    project.write()
    root = project.root
    core_a = root / ".tess" / "core" / "conductor" / "a.md"
    core_a.write_text("alpha v2\n")
    project.write_live("conductor/a.md", "alpha v2\n")
    return root


MARKERS = {"CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "cli", "CODEX_THREAD_ID": "t-1",
           "CODEX_SANDBOX": "seatbelt", "CODEX_SANDBOX_NETWORK_DISABLED": "1"}


@pytest.mark.parametrize("marker", sorted(MARKERS))
@pytest.mark.parametrize("args", [
    ("lock", "--regen", "--yes"),
    ("lock", "--regen", "--yes", "--only", "conductor/a.md"),
    ("lock", "--regen", "--only", ".tess/core/conductor/a.md", "--yes"),
])
def test_b6_lock_regen_refuses_an_assistant_session_before_any_repin(project, run_cli, marker, args):
    root = _seed(project)
    before = (root / ".tess" / "tess.lock").read_bytes()
    r = run_cli(root, *args, extra_env={marker: MARKERS[marker]})
    assert r.returncode != 0
    out = r.stdout + r.stderr
    assert "REFUSED" in out and marker in out and "your own terminal" in out, out
    assert (root / ".tess" / "tess.lock").read_bytes() == before


def test_b6_maintainer_and_ci_regen_with_yes_still_works(project, run_cli):
    """Outside an assistant session (a maintainer's shell, CI, this suite's
    scrubbed env) `--yes` stays the non-interactive form."""
    root = _seed(project)
    r = run_cli(root, "lock", "--regen", "--yes", "--only", "conductor/a.md")
    assert r.returncode == 0 and "re-baselined 1 entry" in r.stdout, r.stdout + r.stderr


def test_b6_interactive_regen_needs_the_typed_confirmation(project):
    root = _seed(project)
    before = (root / ".tess" / "tess.lock").read_bytes()
    rc, out = run_tessctl_in_pty(root, "lock", "--regen", "--only", "conductor/a.md",
                                 answer="y", prompt=b"lock> ", timeout=60)
    assert rc != 0 and "re-baseline tess.lock" in out, out
    assert (root / ".tess" / "tess.lock").read_bytes() == before
    rc, out = run_tessctl_in_pty(root, "lock", "--regen", "--only", "conductor/a.md",
                                 answer="re-baseline tess.lock", prompt=b"lock> ", timeout=60)
    assert rc == 0 and "re-baselined 1 entry" in out, out


def test_b6_interactive_regen_in_a_real_terminal_inside_a_session_is_refused(project):
    root = _seed(project)
    env = operator_env(TESS_ROOT=str(root), CLAUDECODE="1")
    rc, out = run_tessctl_in_pty(root, "lock", "--regen", answer="re-baseline tess.lock",
                                 prompt=b"lock> ", env=env, timeout=60)
    assert rc != 0 and "REFUSED" in out and "lock>" not in out, out


@pytest.mark.parametrize("marker", sorted(MARKERS))
def test_b6_publish_force_question_refuses_an_assistant_session(engine, monkeypatch, marker):
    monkeypatch.setenv(marker, MARKERS[marker])
    with pytest.raises(SystemExit) as exc:
        engine._confirm_at_terminal("publish --force", "Re-seed CLAUDE.md from latest core?",
                                    "CLAUDE.md is as it was.")
    assert "REFUSED" in str(exc.value.code) and marker in str(exc.value.code)


def test_b6_publish_force_question_needs_a_terminal(engine, monkeypatch):
    for m in MARKERS:
        monkeypatch.delenv(m, raising=False)
    monkeypatch.setattr("builtins.input", lambda *_a: "y")  # a fed "y" must not be read
    with pytest.raises(SystemExit) as exc:   # pytest's stdin is not a terminal
        engine._confirm_at_terminal("publish --force", "Re-seed CLAUDE.md from latest core?",
                                    "CLAUDE.md is as it was.")
    assert "interactive terminal" in str(exc.value.code)


def test_b6_every_direct_prompt_in_tessctl_is_audited():
    """Each input() / getpass() site is either behind the shared presence
    helpers or listed here with the reason it carries no security decision."""
    text = (REPO / ".tess/bin/tessctl").read_text(encoding="utf-8")
    sites = [ln.strip() for ln in text.splitlines()
             if ("input(" in ln or "getpass.getpass(" in ln) and not ln.lstrip().startswith("#")]
    allowed = {
        'typed = input(f"  {prompt}")',          # _require_human_presence
        'typed = input("  path> ")',             # _approve_require_human_presence
        'typed = input("  accept> ")',           # anchor accept (marker + TTY checked first)
        'reply = input(f"  {question} [y/N] ").strip().lower()',  # _confirm_at_terminal
        'value = getpass.getpass(f"Value for {ref}: ")',      # vault set: the operator's secret
        'value = getpass.getpass(f"New value for {ref}: ")',  # vault rotate: same
    }
    assert set(sites) <= allowed, set(sites) - allowed


# --------------------------------------------------------------------------- B7


def test_b7_review_manifests_keep_the_operators_exclusion(engine, tmp_path, monkeypatch):
    """The exact manifests of review B7."""
    root = tmp_path / "inst"
    root.mkdir()
    (root / MANIFEST).write_text(json.dumps({
        "owned_globs": ["CLAUDE.md"],
        "never_touch": [".agents/skills/security-audit/SKILL.md"]}))
    _stage_release_manifest(engine, root, monkeypatch, {
        "owned_globs": [".agents/skills/security-audit/**"], "never_touch": []})
    assert engine._update_adopt_owned_globs(root, {}) == []
    manifest = engine.load_manifest(root)
    assert manifest["owned_globs"] == ["CLAUDE.md"]
    with pytest.raises(engine.GateError):
        engine.check_manifest_write_gate(root, manifest, ".agents/skills/security-audit/SKILL.md")


@pytest.mark.parametrize("never", [
    ".agents/skills/security-audit/SKILL.md",       # a file inside the new glob
    ".agents/skills/security-audit/*.md",           # a narrower glob inside it
    ".agents/skills/*/SKILL.md",                    # crosses it through a wildcard
    "**/SKILL.md",                                  # a pattern with no fixed folder
    ".agents/skills/**",                            # a broader one (the old check)
])
def test_b7_intersecting_globs_are_not_adopted(engine, tmp_path, monkeypatch, never):
    root = tmp_path / "inst"
    root.mkdir()
    (root / MANIFEST).write_text(json.dumps({"owned_globs": ["CLAUDE.md"], "never_touch": [never]}))
    _stage_release_manifest(engine, root, monkeypatch, {
        "owned_globs": [".agents/skills/security-audit/**", "unrelated/notes.txt"],
        "never_touch": []})
    assert engine._update_adopt_owned_globs(root, {}) == ["unrelated/notes.txt"]


def test_b7_the_releases_own_never_touch_is_still_beaten(engine, tmp_path, monkeypatch):
    """The point of adoption: `.agents/skills/security-audit/**` beats the
    release-shipped `.agents/**`, on the concrete write too."""
    root = tmp_path / "inst"
    root.mkdir()
    (root / MANIFEST).write_text(json.dumps({"owned_globs": ["CLAUDE.md"], "never_touch": [".agents/**"]}))
    _stage_release_manifest(engine, root, monkeypatch, {
        "owned_globs": [".agents/skills/security-audit/**"], "never_touch": [".agents/**"]})
    assert engine._update_adopt_owned_globs(root, {}) == [".agents/skills/security-audit/**"]
    manifest = engine.load_manifest(root)
    assert engine.check_manifest_write_gate(root, manifest, ".agents/skills/security-audit/SKILL.md")
    with pytest.raises(engine.GateError):
        engine.check_manifest_write_gate(root, manifest, ".agents/skills/mine/SKILL.md")


def test_b7_a_later_operator_exclusion_wins_over_an_adopted_glob_at_write_time(
        engine, tmp_path, monkeypatch):
    root = tmp_path / "inst"
    root.mkdir()
    (root / MANIFEST).write_text(json.dumps({"owned_globs": ["CLAUDE.md"], "never_touch": [".agents/**"]}))
    _stage_release_manifest(engine, root, monkeypatch, {
        "owned_globs": [".agents/skills/security-audit/**"], "never_touch": [".agents/**"]})
    engine._update_adopt_owned_globs(root, {})
    doc = json.loads((root / MANIFEST).read_text())
    doc["never_touch"].append(".agents/skills/security-audit/SKILL.md")
    (root / MANIFEST).write_text(json.dumps(doc))
    manifest = engine.load_manifest(root)
    with pytest.raises(engine.GateError) as exc:
        engine.check_manifest_write_gate(root, manifest, ".agents/skills/security-audit/SKILL.md")
    assert "never_touch" in str(exc.value)
    assert engine.check_manifest_write_gate(root, manifest, ".agents/skills/security-audit/README.md")
    assert not engine.manifest_owns(manifest, ".agents/skills/security-audit/SKILL.md")
    # a glob the install owned from the start keeps owned_globs > never_touch
    assert engine.manifest_owns({"owned_globs": ["clients/_template/**"],
                                 "never_touch": ["clients/*/**"]}, "clients/_template/x.md")


# --------------------------------------------------------------------------- B8


@pytest.mark.skipif(not HAS_GIT, reason="needs git")
def test_b8_git_missing_from_path_stops_every_hook(proj, tmp_path, monkeypatch):
    """Review B8: an anchored repo with core.hooksPath=/dev/null, launcher run
    with a PATH that holds python but no git."""
    _git(proj, "config", "core.hooksPath", "/dev/null")
    empty = tmp_path / "nogit"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    why = L.hookspath_problem(proj)
    assert why and "git" in why and "stopped all actions" in why, why
    payload = json.dumps({"tool_name": "Bash", "cwd": str(proj), "tool_input": {"command": "echo ok"},
                          "permission_mode": "default"})
    r = subprocess.run([sys.executable, "-I", "-B", str(proj / ".claude/hooks/run-pinned.py"),
                        "--on-fail", "block", "--", ".claude/hooks/tess-gate.py", "--runtime", "claude"],
                       input=payload, capture_output=True, text=True, cwd=str(proj), timeout=120,
                       env=dict(os.environ, PATH=str(empty), CLAUDE_PROJECT_DIR=str(proj)))
    assert r.returncode == 2 and "TESS STOPPED" in r.stderr and "git" in r.stderr, r.stderr


@pytest.mark.parametrize("exc", [OSError("exec format error"), PermissionError("denied"),
                                 subprocess.TimeoutExpired(["git"], 10)])
def test_b8_git_that_cannot_be_run_stops(proj, monkeypatch, exc):
    (proj / ".git").mkdir(exist_ok=True)

    def boom(*_a, **_k):
        raise exc
    monkeypatch.setattr(L.subprocess, "run", boom)
    why = L.hookspath_problem(proj)
    assert why and "stopped all actions" in why, why


def _fake_git(tmp_path, rc: int, out: str = "", err: str = "") -> str:
    d = tmp_path / "fakegit"
    d.mkdir(exist_ok=True)
    g = d / "git"
    g.write_text(f"#!/bin/sh\nprintf '%s' '{out}'\nprintf '%s' '{err}' >&2\nexit {rc}\n")
    g.chmod(g.stat().st_mode | stat.S_IXUSR)
    return str(d)


@pytest.mark.parametrize("rc,err", [(1, "xcrun: error: invalid active developer path"), (2, ""),
                                    (128, "fatal: bad config line 1"), (127, "")])
def test_b8_an_unexpected_git_exit_stops(proj, tmp_path, monkeypatch, rc, err):
    (proj / ".git").mkdir(exist_ok=True)
    monkeypatch.setenv("PATH", _fake_git(tmp_path, rc, err=err))
    why = L.hookspath_problem(proj)
    assert why and "stopped all actions" in why, why


def test_b8_unset_key_still_passes(proj, tmp_path, monkeypatch):
    (proj / ".git").mkdir(exist_ok=True)
    monkeypatch.setenv("PATH", _fake_git(tmp_path, 1))
    assert L.hookspath_problem(proj) is None


def test_b8_an_unreadable_git_file_stops(tmp_path, monkeypatch):
    root = tmp_path / "wt"
    root.mkdir()
    (root / ".git").write_text("not a gitdir line\n")
    assert L.hookspath_problem(root) and "stopped all actions" in L.hookspath_problem(root)


def test_b8_a_project_with_no_git_folder_is_exempt_even_without_git(tmp_path, monkeypatch):
    root = tmp_path / "plain"
    root.mkdir()
    empty = tmp_path / "nogit"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    assert L.hookspath_problem(root) is None
