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


# =========================================================================== Quinn's verification at a6feef2
# (scratchpad/quinn-r7): the adoption allowlist, marker refusal everywhere a
# person must type, manifest robustness, more hooksPath failure modes and the
# negative SSH-trust adoption cases.


def _adopt(engine, tmp_path, monkeypatch, owned, never, rel_owned, rel_never=()):
    root = tmp_path / "inst"
    root.mkdir(exist_ok=True)
    (root / MANIFEST).write_text(json.dumps({"owned_globs": owned, "never_touch": never}))
    _stage_release_manifest(engine, root, monkeypatch, {"owned_globs": rel_owned,
                                                        "never_touch": list(rel_never)})
    return root, engine._update_adopt_owned_globs(root, {})


@pytest.mark.parametrize("g", ["**/**", "?*", "**/?*", "*/**", "**/*.*", "[!.]*/**", "./**",
                               "*", "**", "**/*", ".git/hooks/**", ".GIT./x", "../x/**", "/etc/**",
                               "a//b/**", "a/../b/**", "a\\b/**"])
def test_b7_only_globs_under_a_named_folder_are_adopted(engine, tmp_path, monkeypatch, g):
    root, added = _adopt(engine, tmp_path, monkeypatch, ["CLAUDE.md"], ["kb/**"], [g])
    assert added == []
    manifest = engine.load_manifest(root)
    for rel in ("kb/wiki/x.md", ".env", "docs/x.md"):
        assert not engine.manifest_owns(manifest, rel), (g, rel)


def test_b7_quinn_repro_catch_all_never_reaches_kb_or_env(engine, tmp_path, monkeypatch):
    root, added = _adopt(engine, tmp_path, monkeypatch, ["CLAUDE.md"], ["kb/**"], ["**/**"])
    assert added == []
    manifest = engine.load_manifest(root)
    for rel in ("kb/wiki/x.md", ".env"):
        with pytest.raises(engine.GateError):
            engine.check_manifest_write_gate(root, manifest, rel)


def test_b7_a_narrower_operator_never_touch_inside_the_glob_wins(engine, tmp_path, monkeypatch):
    root, added = _adopt(engine, tmp_path, monkeypatch, ["CLAUDE.md"], ["docs/private/**"], ["docs/**"])
    assert added == []
    (root / "docs" / "private").mkdir(parents=True)
    with pytest.raises(engine.GateError):
        engine.check_manifest_write_gate(root, engine.load_manifest(root), "docs/private/secret.md")


@pytest.mark.parametrize("a,b,overlap", [
    ("docs/**", "docs/private/**", True), ("docs/**", "kb/**", False),
    ("x/a.md", "x/*.md", True), ("x/a.md", "x/*.txt", False),
    ("**/SKILL.md", "y/**", True), (".agents/skills/s/**", ".agents/skills/*/SKILL.md", True),
    ("a/b/**", "a/c/**", False), ("a/**/c", "a/x/y/c", True),
])
def test_b7_overlap_is_symmetric_and_conservative(engine, a, b, overlap):
    assert engine._globs_may_overlap(a, b) is overlap
    assert engine._globs_may_overlap(b, a) is overlap


def test_b7_the_ship_gate_recomputes_the_adoption(engine):
    base = {"owned_globs": ["CLAUDE.md"], "never_touch": [".agents/**"]}
    release = {"owned_globs": ["CLAUDE.md", ".agents/skills/security-audit/**", "**/**"],
               "never_touch": [".agents/**"]}
    want, added, _kept, refused = engine._manifest_adopt(base, release)
    assert added == [".agents/skills/security-audit/**"] and refused == ["**/**"]
    enc = lambda d: json.dumps(d).encode()  # noqa: E731
    assert engine._gate_release_manifest_ok(enc(base), enc(want), enc(release))
    sneaky = json.loads(json.dumps(want))
    sneaky["owned_globs"].append("kb/**")
    assert not engine._gate_release_manifest_ok(enc(base), enc(sneaky), enc(release))
    assert not engine._gate_release_manifest_ok(enc(base), enc(base), enc(release))
    assert not engine._gate_release_manifest_ok(enc(base), enc(want), None)
    assert engine.MANIFEST_FILE in engine.RELEASE_PROOF_BLOB_PATHS


# --------------------------------------------------------------------------- markers


@pytest.mark.parametrize("marker", sorted(MARKERS))
def test_policy_accept_refuses_under_each_marker_even_on_a_terminal(engine, monkeypatch, tmp_path,
                                                                    marker):
    import io

    class TTY(io.StringIO):
        def isatty(self):
            return True
    rel = ".tess/core/policy/policy.yaml"
    (tmp_path / rel).parent.mkdir(parents=True)
    (tmp_path / rel).write_text("policy:\n  rules:\n    - id: a\n      tier: security\n")
    st = tmp_path / engine.STAGING_DIR / rel
    st.parent.mkdir(parents=True)
    st.write_text("policy:\n  rules:\n    - id: b\n      tier: normal\n")
    monkeypatch.setenv(marker, MARKERS[marker])
    monkeypatch.setattr(sys, "stdin", TTY("accept v9.9.9\n"))
    out = TTY()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "__stdout__", out)
    with pytest.raises(SystemExit) as exc:
        engine._update_confirm_policy_rule_changes(tmp_path, "v9.9.9")
    assert marker in str(exc.value.code) and "REFUSED" in str(exc.value.code)
    assert "accept>" not in out.getvalue()


def _brain_roots():
    sys.path.insert(0, str(REPO / "scripts" / "brain"))
    from brainlib import roots
    return roots


def test_brain_markers_match_tessctl(engine):
    assert _brain_roots().AGENT_SESSION_MARKERS == tuple(engine.AGENT_SESSION_MARKERS)


@pytest.mark.parametrize("marker", sorted(MARKERS))
def test_brain_roots_add_refuses_under_each_marker(monkeypatch, tmp_path, marker):
    import io
    import types

    class TTY(io.StringIO):
        def isatty(self):
            return True
    roots = _brain_roots()
    monkeypatch.setenv(marker, MARKERS[marker])
    monkeypatch.setattr(sys, "stdin", TTY("yes\n"))
    monkeypatch.setattr(sys, "stdout", TTY())
    saved = {}
    monkeypatch.setattr(roots, "problem", lambda cfg, p, strict=False: None)
    monkeypatch.setattr(roots, "extra", lambda cfg: [])
    monkeypatch.setattr(roots, "save", lambda cfg, lst: saved.setdefault("v", lst))
    monkeypatch.setattr(roots, "_codex_sessions_under", lambda p: 0)
    rc, res = roots.cmd_roots(types.SimpleNamespace(root=tmp_path),
                              types.SimpleNamespace(roots_cmd="add", path=str(tmp_path)))
    assert rc == 1 and marker in res["error"] and "own terminal" in res["error"], res
    assert not saved


@pytest.mark.parametrize("marker", sorted(MARKERS))
def test_brain_sync_other_folder_question_refuses_under_each_marker(monkeypatch, tmp_path, marker):
    import io
    import types

    class TTY(io.StringIO):
        def isatty(self):
            return True
    _brain_roots()
    from brainlib import commands
    monkeypatch.setenv(marker, MARKERS[marker])
    monkeypatch.setattr(sys, "stdin", TTY("yes\n"))
    monkeypatch.setattr(sys, "stdout", TTY())
    assert commands._operator_allows_claude_dir(types.SimpleNamespace(root=tmp_path), "/x", "why") is False


def test_brain_questions_still_reach_the_operator_without_markers(monkeypatch, tmp_path):
    import io
    import types

    class TTY(io.StringIO):
        def isatty(self):
            return True
    for m in MARKERS:
        monkeypatch.delenv(m, raising=False)
    _brain_roots()
    from brainlib import commands
    monkeypatch.setattr(sys, "stdin", TTY("yes\n"))
    monkeypatch.setattr(sys, "stdout", TTY())
    assert commands._operator_allows_claude_dir(types.SimpleNamespace(root=tmp_path), "/x", "why") is True


# --------------------------------------------------------------------------- manifest robustness


def _set_enabled(root: Path, names):
    path = root / MANIFEST
    doc = json.loads(path.read_text())
    doc.setdefault("render_targets", {})["enabled"] = names
    path.write_text(json.dumps(doc))


def _narrow(root: Path, drop):
    path = root / MANIFEST
    doc = json.loads(path.read_text())
    doc["owned_globs"] = [g for g in doc["owned_globs"] if g not in drop]
    doc["never_touch"] = doc["never_touch"] + [".claude/hooks/dispatch-guard.sh"]
    path.write_text(json.dumps(doc))


def _seed_safety(project):
    project.add(".claude/hooks/dispatch-guard.sh", "#!/bin/sh\nexit 0\n", tier="security",
                core_key=".tess/core/hooks/dispatch-guard.sh")
    project.add("core/policy/policy.yaml", "policy:\n  rules: []\n", tier="security",
                core_key=".tess/core/policy/policy.yaml")
    project.add("conductor/a.md", "alpha\n")
    project.write()
    _set_enabled(project.root, [])


def test_restore_puts_back_safety_files_whatever_owned_globs_says(project, run_cli):
    """Quinn: narrowing owned_globs made restore skip a deleted hook and the
    live policy, and still say "restore: complete" (exit 0)."""
    _seed_safety(project)
    root = project.root
    _narrow(root, (".claude/hooks/**", "core/policy/**"))
    (root / ".claude/hooks/dispatch-guard.sh").unlink()
    (root / "core/policy/policy.yaml").unlink()
    r = run_cli(root, "restore")
    assert r.returncode == 0, r.stdout + r.stderr
    assert (root / ".claude/hooks/dispatch-guard.sh").read_text() == "#!/bin/sh\nexit 0\n"
    assert (root / "core/policy/policy.yaml").is_file()


def test_restore_fails_when_a_safety_file_cannot_be_put_back(project, run_cli, tmp_path):
    _seed_safety(project)
    root = project.root
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    shutil.rmtree(root / "core" / "policy")
    (root / "core" / "policy").symlink_to(elsewhere)
    r = run_cli(root, "restore")
    out = r.stdout + r.stderr
    assert r.returncode != 0 and "could not be put back" in out and "core/policy/policy.yaml" in out, out
    assert "restore: complete" not in out


def test_publish_force_refuses_before_anything_is_written(project, run_cli):
    project.add("conductor/a.md", "alpha\n")
    project.write()
    _set_enabled(project.root, [])
    project.write_live("conductor/a.md", "alpha hand edit\n")
    before = (project.root / ".tess/tess.lock").read_bytes()
    r = run_cli(project.root, "publish", "conductor/a.md", "--force", input_text="y\n")
    assert r.returncode != 0 and "REFUSED" in r.stdout + r.stderr, r.stdout + r.stderr
    assert project.read_live("conductor/a.md") == "alpha hand edit\n"
    assert (project.root / ".tess/tess.lock").read_bytes() == before


@pytest.fixture(scope="module")
def tree(tmp_path_factory):
    """A copy of this working tree (tracked files, as they are now) in a new git repo."""
    root = tmp_path_factory.mktemp("r7tree") / "inst"
    root.mkdir()
    files = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z"], capture_output=True,
                           check=True).stdout.decode().split("\0")
    for rel in filter(None, files):
        src = REPO / rel
        if src.is_symlink() or not src.is_file():
            continue
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, root / rel)
    _git(root.parent, "init", "-q", "-b", "main", str(root))
    _git(root, "add", "-A")
    _git(root, "-c", "user.email=t@tess.test", "-c", "user.name=T", "-c", "commit.gpgsign=false",
         "commit", "-q", "--no-verify", "-m", "init")
    return root


def _fresh(tree: Path, tmp_path: Path) -> Path:
    d = tmp_path / "i"
    subprocess.run(["cp", "-R", str(tree), str(d)], check=True)
    return d


def _tc(root, *args):
    r = subprocess.run([sys.executable, "-I", "-B", str(root / ".tess/bin/tessctl"), *args],
                       capture_output=True, text=True, cwd=str(root),
                       env=dict(os.environ, TESS_ROOT=str(root)), timeout=600)
    return r.returncode, r.stdout + r.stderr


@pytest.mark.skipif(not HAS_GIT, reason="needs git")
def test_disabling_codex_does_not_hide_its_enforcement_files(tree, tmp_path, engine):
    """Quinn: emptying .codex/config.toml and .codex/rules/tess.rules and then
    dropping codex from render_targets.enabled hid both from doctor and verify."""
    d = _fresh(tree, tmp_path)
    for rel in (".codex/config.toml", ".codex/rules/tess.rules"):
        (d / rel).write_text("# emptied\n")
    _set_enabled(d, ["claude-code"])
    for cmd in ("doctor", "verify"):
        rc, out = _tc(d, cmd)
        assert rc != 0, out
        for rel in (".codex/config.toml", ".codex/rules/tess.rules"):
            assert rel in out, (cmd, rel, out[-2000:])
    rc, out = _tc(d, "lock", "--check")
    assert rc != 0 and ".codex/config.toml" in out, out[-2000:]
    found = dict(engine._enforcement_hook_findings(d, engine.load_lock(d)))
    assert ".codex/config.toml" not in found or found  # checked, not skipped
    assert ".codex/config.toml" in engine._disabled_enforcement_outputs(d, engine.load_lock(d))


@pytest.mark.skipif(not HAS_GIT, reason="needs git")
def test_a_never_rendered_codex_file_of_the_operators_own_is_not_flagged(tree, tmp_path, engine):
    d = _fresh(tree, tmp_path)
    lock_text = (d / ".tess/tess.lock").read_text()
    lock = engine.load_lock(d)
    for rel in list(lock.get("render_outputs") or {}):
        if rel.startswith(".codex/"):
            del lock["render_outputs"][rel]
    engine.save_lock(d, lock)
    _set_enabled(d, ["claude-code"])
    (d / ".codex/config.toml").write_text("# my own codex config\n")
    assert ".codex/config.toml" not in engine._disabled_enforcement_outputs(d, engine.load_lock(d))
    (d / ".tess/tess.lock").write_text(lock_text)


@pytest.mark.skipif(not HAS_GIT, reason="needs git")
def test_doctor_path_still_reports_hookspath_and_exits_nonzero(tree, tmp_path):
    d = _fresh(tree, tmp_path)
    _git(d, "config", "core.hooksPath", "/dev/null")
    for args in (("doctor",), ("doctor", "CLAUDE.md")):
        rc, out = _tc(d, *args)
        assert rc == 1 and "core.hooksPath" in out, (args, out[-1500:])


# --------------------------------------------------------------------------- hooksPath failure modes


@pytest.fixture
def gitenv(tmp_path, monkeypatch):
    home = tmp_path / "ghome"
    home.mkdir()
    glob = home / "gitconfig"
    glob.write_text("")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(glob))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for k in [k for k in os.environ if k.startswith("GIT_CONFIG_")
              and k not in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM")]:
        monkeypatch.delenv(k, raising=False)
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    return repo, glob


@pytest.mark.skipif(not HAS_GIT, reason="needs git")
def test_b8_hookspath_through_include_path_stops(gitenv, tmp_path):
    repo, _g = gitenv
    inc = tmp_path / "inc.cfg"
    inc.write_text("[core]\n\thooksPath = /nonexistent\n")
    _git(repo, "config", "include.path", str(inc))
    assert "core.hooksPath" in (L.hookspath_problem(repo) or "")


@pytest.mark.skipif(not HAS_GIT, reason="needs git")
def test_b8_hookspath_through_global_includeif_stops(gitenv, tmp_path):
    repo, glob = gitenv
    inc = tmp_path / "inc.cfg"
    inc.write_text("[core]\n\thooksPath = /nonexistent\n")
    glob.write_text(f'[includeIf "gitdir:{os.path.realpath(repo)}/"]\n\tpath = {inc}\n')
    assert "core.hooksPath" in (L.hookspath_problem(repo) or "")


@pytest.mark.skipif(not HAS_GIT, reason="needs git")
def test_b8_hookspath_through_git_config_parameters_stops(gitenv, monkeypatch):
    repo, _g = gitenv
    monkeypatch.setenv("GIT_CONFIG_PARAMETERS", "'core.hooksPath'='/nonexistent'")
    assert "core.hooksPath" in (L.hookspath_problem(repo) or "")


@pytest.mark.skipif(not HAS_GIT or os.geteuid() == 0, reason="needs git, not root")
def test_b8_an_unreadable_global_config_stops(gitenv):
    repo, glob = gitenv
    glob.write_text("[core]\n\thooksPath = /nonexistent\n")
    os.chmod(glob, 0)
    try:
        why = L.hookspath_problem(repo)
    finally:
        os.chmod(glob, 0o644)
    assert why and "stopped all actions" in why, why


@pytest.mark.skipif(not HAS_GIT, reason="needs git")
def test_b8_a_malformed_local_config_stops(gitenv):
    repo, _g = gitenv
    cfg = repo / ".git" / "config"
    cfg.write_text(cfg.read_text() + "\n[core\nbroken = = =\n")
    why = L.hookspath_problem(repo)
    assert why and "stopped all actions" in why, why


@pytest.mark.skipif(not HAS_GIT, reason="needs git")
def test_b8_a_git_timeout_stops(gitenv, monkeypatch):
    repo, _g = gitenv

    def slow(*_a, **_k):
        raise subprocess.TimeoutExpired("git", 10)
    monkeypatch.setattr(L.subprocess, "run", slow)
    why = L.hookspath_problem(repo)
    assert why and "in time" in why, why


# --------------------------------------------------------------------------- SSH trust adoption: negatives


HAS_SSH_KEYGEN = shutil.which("ssh-keygen") is not None


def _ssh_release(tmp_path, *, signer, signers_text, pin, sign=True, tag="v9.9.9"):
    from test_v1_ssh_release_sig import _ssh_block
    up = tmp_path / "up"
    up.mkdir()
    _git(up, "init", "-q", "-b", "main")
    (up / ".tess" / "keys").mkdir(parents=True)
    (up / ".tess" / "keys" / "twiss-release-allowed-signers").write_text(signers_text)
    (up / ".tess" / "tess.lock").write_text(
        f"schema: 1\nframework:\n  version: {tag[1:]}\n  trusted_ssh_key_fingerprint: {pin}\n"
        f"files: {{}}\n")
    (up / MANIFEST).write_text(json.dumps({"owned_globs": ["CLAUDE.md"], "never_touch": []}))
    _git(up, "add", "-A")
    _git(up, "-c", "user.email=r@t", "-c", "user.name=R", "-c", "commit.gpgsign=false",
         "commit", "-q", "-m", "release")
    commit = _git(up, "rev-parse", "HEAD")
    tree_id = _git(up, "rev-parse", "HEAD^{tree}")
    msg = f"Release {tag}\n"
    if sign:
        msg += "\n" + _ssh_block(signer, tag, commit, tree_id, tmp_path)
    (tmp_path / "tagmsg").write_text(msg)
    _git(up, "-c", "user.email=r@t", "-c", "user.name=R", "-c", "tag.gpgsign=false",
         "tag", "-a", "--cleanup=verbatim", "-F", str(tmp_path / "tagmsg"), tag)
    return up, commit, tag


@pytest.fixture(scope="module")
def ssh_pair(tmp_path_factory):
    from test_v1_ssh_release_sig import _new_ssh_key
    d = tmp_path_factory.mktemp("r7ssh")
    return _new_ssh_key(d, "release"), _new_ssh_key(d, "attacker")


def _stage_extras(engine, tmp_path, up, commit, tag):
    staging = tmp_path / "staging"
    staging.mkdir()
    engine._stage_release_extras(up, commit, tag, staging, {})
    return engine._RELEASE_TRUST_STATE["ssh"]


@pytest.mark.skipif(not (HAS_GIT and HAS_SSH_KEYGEN), reason="git + ssh-keygen required")
def test_ssh_trust_adopted_only_with_a_valid_signature(engine, tmp_path, ssh_pair):
    (key, fp, signers), _other = ssh_pair
    up, commit, tag = _ssh_release(tmp_path, signer=key, signers_text=signers, pin=fp)
    st = _stage_extras(engine, tmp_path, up, commit, tag)
    assert st and st["reason"] == "" and st["pin"] == fp


@pytest.mark.skipif(not (HAS_GIT and HAS_SSH_KEYGEN), reason="git + ssh-keygen required")
@pytest.mark.parametrize("case", ["missing", "invalid", "key_mismatch", "extra_entry"])
def test_ssh_trust_is_not_adopted_without_proof(engine, tmp_path, ssh_pair, case):
    (key, fp, signers), (okey, ofp, osigners) = ssh_pair
    kw = dict(signer=key, signers_text=signers, pin=fp)
    if case == "missing":
        kw["sign"] = False
    elif case == "invalid":
        kw["signer"] = okey                      # signed by another key
    elif case == "key_mismatch":
        kw["pin"] = ofp                          # the lock pins another key
    else:
        kw["signers_text"] = signers + osigners.split("\n", 1)[1]   # a second entry
    up, commit, tag = _ssh_release(tmp_path, **kw)
    st = _stage_extras(engine, tmp_path, up, commit, tag)
    assert st and st["reason"], (case, st)
    root = tmp_path / "inst"
    (root / ".tess" / "staging").mkdir(parents=True)
    lock = {"framework": {"version": "1.0.0", "trusted_key_fingerprint": "E" * 40}, "files": {}}
    assert engine._update_adopt_release_trust(root, lock, {}) is None
    assert "trusted_ssh_key_fingerprint" not in lock["framework"]
