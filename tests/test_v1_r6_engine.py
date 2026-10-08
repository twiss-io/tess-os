"""v1.0.0 round 6 (GPT-6 final review): tessctl release path and signer custody.

  #11  verdict / sign-off signing refuses unless custody is ESTABLISHED: a
       non-empty set of signing keygrips, each reported "P" (passphrase) or
       "T" (hardware token) by gpg-agent. A failed probe, a missing
       gpg-connect-agent or a "-" answer refuse with a plain message.
  #1   `tessctl update` installs Tess's auxiliary runtime (hook launcher,
       gate, brain, boot launcher) from the verified release and checks every
       pin before it advances the version (unit level here; the 0.2.0 -> 1.0.0
       end-to-end run is tests/test_v1_r6_upgrade_e2e.py).
  #2   the release-proof gate accepts an exact signed engine transition
       (.tess/bin/tessctl equal to the proven release blob) with version and
       commit bookkeeping, also when self-update is committed on its own.
"""
from __future__ import annotations

import io
import json
import os
import shutil
from pathlib import Path

import pytest

from conftest import HAS_GIT, HAS_GPG
from test_gate_spine import gate_repo  # noqa: F401 — fixture
from test_v1_audit_policy_vault import _sign_args, _verdict_file

FPR = "A" * 40


# ===========================================================================
# #11 — signer custody must be established
# ===========================================================================

def _custody(engine, monkeypatch, grips, protection):
    monkeypatch.setattr(engine, "_signer_resolve_key", lambda cmd, root, key_id, home: (FPR, grips))
    monkeypatch.setattr(engine, "_signer_registered_fingerprint", lambda root, reg, name: FPR)
    answers = protection if isinstance(protection, dict) else {g: protection for g in grips}
    monkeypatch.setattr(engine, "_signer_key_protection", lambda grip, home: answers[grip])
    return engine._signer_check_custody("tessctl verdict sign", Path("."), "verifier_keys",
                                        "Reid", FPR, None)


@pytest.mark.parametrize("answer", ["P", "T"])
def test_custody_accepts_a_passphrase_or_a_hardware_token(engine, monkeypatch, answer):
    assert _custody(engine, monkeypatch, ["G1", "G2"], answer) == (FPR, ["G1", "G2"])


@pytest.mark.parametrize("answer", ["-", "", "D", "?"])
def test_custody_refuses_an_unknown_protection_answer(engine, monkeypatch, answer):
    with pytest.raises(SystemExit) as exc:
        _custody(engine, monkeypatch, ["G1"], answer)
    assert "could not confirm" in str(exc.value) and "Nothing was signed" in str(exc.value)


def test_custody_refuses_when_one_of_several_keys_is_unconfirmed(engine, monkeypatch):
    with pytest.raises(SystemExit) as exc:
        _custody(engine, monkeypatch, ["G1", "G2"], {"G1": "P", "G2": "-"})
    assert "could not confirm" in str(exc.value)


def test_custody_refuses_a_key_with_no_signing_keygrip(engine, monkeypatch):
    with pytest.raises(SystemExit) as exc:
        _custody(engine, monkeypatch, [], "P")
    assert "no signing key (keygrip)" in str(exc.value)


def test_custody_still_refuses_a_clear_key(engine, monkeypatch):
    with pytest.raises(SystemExit) as exc:
        _custody(engine, monkeypatch, ["G1"], "C")
    assert "has no passphrase" in str(exc.value)


def test_protection_probe_without_gpg_connect_agent_is_unknown(engine, tmp_path, monkeypatch):
    empty = tmp_path / "bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    assert engine._signer_key_protection("0" * 40, None) == "-"


def _path_with_gpg_only(tmp_path: Path) -> str:
    """PATH holding gpg (and git) but not gpg-connect-agent."""
    bindir = tmp_path / "gpg-only-bin"
    bindir.mkdir()
    for tool in ("gpg", "git", "sh", "env"):
        found = shutil.which(tool)
        if found:
            (bindir / tool).symlink_to(found)
    assert not (bindir / "gpg-connect-agent").exists()
    return str(bindir)


@pytest.mark.skipif(not (HAS_GIT and HAS_GPG), reason="git + gpg required")
def test_verdict_sign_refuses_when_gpg_connect_agent_is_missing(
        gate_repo, engine, verifier_gpg_keys, monkeypatch, tmp_path):  # noqa: F811
    """GPT-6 #11: a registered passphrase-free key, gpg present, no
    gpg-connect-agent, the confirmation typed. Before the fix the probe
    answered "-" and signing went ahead; now it is refused, unsigned."""
    key = verifier_gpg_keys["Reid"]
    path = _verdict_file(gate_repo)
    before = path.read_bytes()
    monkeypatch.setattr(engine, "_signer_is_terminal", lambda: True)
    monkeypatch.setattr(engine.sys, "stdin", io.StringIO("sign as Reid\n"))
    monkeypatch.setenv("PATH", _path_with_gpg_only(tmp_path))
    with pytest.raises(SystemExit) as exc:
        engine._cmd_verdict_sign(_sign_args(path, key), gate_repo)
    assert "could not confirm" in str(exc.value)
    assert path.read_bytes() == before
    assert "signature" not in json.loads(path.read_text())


# ===========================================================================
# #1 — update installs the auxiliary runtime from the verified release
# ===========================================================================

AUX_BRAIN = "scripts/brain/tessbrain.py"
AUX_LAUNCHER = ".claude/hooks/run-pinned.py"
PIN_KEY = ".tess/core/pinned-scripts.sha256"


def _sha(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode()).hexdigest()


def _aux_release(tmp_path, gpg_key, *, pins: dict, files: dict, tag="v2.1.0"):
    from conftest import make_upstream
    core = {
        ".tess/core/templates/CLAUDE.md.tpl": "# Tess OS\n\nRoot: {{TESS_ROOT}}\n",
        ".tess/core/settings-core.json": '{"root": "{{TESS_ROOT}}"}\n',
        PIN_KEY: "# pins\n" + "".join(f"{h}  {p}\n" for p, h in pins.items()),
    }
    core.update(files)
    return make_upstream(tmp_path / "upstream", gpg_key, tag, sign="signed", core_files=core,
                         lock_files={PIN_KEY: {"status": "core-managed", "tier": "security",
                                               "live_path": None}})


def _aux_project(project, gpg_key, up):
    project.add(None, "# Tess OS\n\nRoot: {{TESS_ROOT}}\n",
                core_key=".tess/core/templates/CLAUDE.md.tpl", render_live=False)
    project.add(None, '{"root": "{{TESS_ROOT}}"}\n',
                core_key=".tess/core/settings-core.json", render_live=False)
    project.framework["upstream"] = str(up)
    project.framework["trusted_key_fingerprint"] = gpg_key.fpr
    (project.root / ".tess/staging/.gitkeep").write_bytes(b"")
    return project.write()


@pytest.mark.skipif(not (HAS_GIT and HAS_GPG), reason="git + gpg required")
def test_update_installs_the_hook_and_brain_files_and_checks_their_pins(
        project, gpg_key, tmp_path, run_cli):
    brain, launcher = "print('brain v2')\n", "print('launcher v2')\n"
    up = _aux_release(tmp_path, gpg_key, pins={AUX_LAUNCHER: _sha(launcher), AUX_BRAIN: _sha(brain)},
                      files={AUX_LAUNCHER: launcher, AUX_BRAIN: brain,
                             "scripts/brain/templates/records/fact.md": "fact\n"})
    _aux_project(project, gpg_key, up)
    project.write_live(AUX_BRAIN, "print('brain v1')\n")   # the older release's copy
    r = run_cli(project.root, "update", "--ref", "v2.1.0")
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]
    assert project.read_live(AUX_BRAIN) == brain
    assert project.read_live(AUX_LAUNCHER) == launcher
    assert project.read_live("scripts/brain/templates/records/fact.md") == "fact\n"
    assert project.lock()["framework"]["version"] == "2.1.0"
    assert (project.root / ".tess/staging/.gitkeep").is_file()
    assert project.mod._pinned_runtime_findings(project.root) == []


@pytest.mark.skipif(not (HAS_GIT and HAS_GPG), reason="git + gpg required")
def test_update_rolls_back_when_a_release_file_does_not_match_its_pin(
        project, gpg_key, tmp_path, run_cli):
    brain = "print('brain v2')\n"
    up = _aux_release(tmp_path, gpg_key, pins={AUX_BRAIN: _sha("something else\n")},
                      files={AUX_BRAIN: brain})
    _aux_project(project, gpg_key, up)
    project.write_live(AUX_BRAIN, "print('brain v1')\n")
    r = run_cli(project.root, "update", "--ref", "v2.1.0")
    assert r.returncode != 0
    assert "do not match the release's pins" in r.stdout + r.stderr
    assert project.read_live(AUX_BRAIN) == "print('brain v1')\n"   # rolled back
    assert project.lock()["framework"]["version"] == "2.0.0"
    assert not (project.root / PIN_KEY).exists()


@pytest.mark.skipif(not (HAS_GIT and HAS_GPG), reason="git + gpg required")
def test_update_refuses_a_pinned_hook_file_it_cannot_install(project, gpg_key, tmp_path, run_cli):
    new_hook = ".claude/hooks/new-hook.py"
    up = _aux_release(tmp_path, gpg_key, pins={new_hook: _sha("x\n")}, files={new_hook: "x\n"})
    _aux_project(project, gpg_key, up)
    r = run_cli(project.root, "update", "--ref", "v2.1.0")
    assert r.returncode != 0
    out = r.stdout + r.stderr
    assert "does not know how to install it" in out and "self-update" in out
    assert not (project.root / new_hook).exists()
    assert project.lock()["framework"]["version"] == "2.0.0"


@pytest.mark.skipif(not (HAS_GIT and HAS_GPG), reason="git + gpg required")
def test_update_refuses_a_symlinked_runtime_folder(project, gpg_key, tmp_path, run_cli):
    brain = "print('brain v2')\n"
    up = _aux_release(tmp_path, gpg_key, pins={AUX_BRAIN: _sha(brain)}, files={AUX_BRAIN: brain})
    _aux_project(project, gpg_key, up)
    outside = tmp_path / "outside"
    outside.mkdir()
    (project.root / "scripts").mkdir()
    (project.root / "scripts" / "brain").symlink_to(outside)
    r = run_cli(project.root, "update", "--ref", "v2.1.0")
    assert r.returncode != 0 and "is a symlink" in r.stdout + r.stderr
    assert not (outside / "tessbrain.py").exists()


def test_verify_reports_a_missing_or_changed_pinned_hook_file(engine, tmp_path):
    (tmp_path / ".tess/core").mkdir(parents=True)
    (tmp_path / PIN_KEY).write_text(f"{_sha('a')}  {AUX_LAUNCHER}\n{_sha('b')}  {AUX_BRAIN}\n")
    (tmp_path / "scripts/brain").mkdir(parents=True)
    (tmp_path / AUX_BRAIN).write_text("changed")
    got = dict(engine._pinned_runtime_findings(tmp_path))
    assert "is missing" in got[AUX_LAUNCHER] and "differs from its pin" in got[AUX_BRAIN]


def test_every_pinned_script_is_covered_by_the_runtime_manifest(engine):
    """The manifest update installs from must cover every path this release
    pins, or `update` to it would stop (and ask for self-update)."""
    from conftest import REPO_ROOT
    pins = engine._pinned_scripts_parse((REPO_ROOT / PIN_KEY).read_text())
    assert pins and all(engine._aux_runtime_rel(p) for p in pins), \
        [p for p in pins if not engine._aux_runtime_rel(p)]


# ===========================================================================
# #2 — the release-proof gate and an exact signed engine transition
# ===========================================================================

OLD_ENGINE = b"#!/usr/bin/env python3\n# engine 2.0.0\n"
NEW_ENGINE = b"#!/usr/bin/env python3\n# engine 2.1.0\n"
ENGINE, BAK, LOCK = ".tess/bin/tessctl", ".tess/bin/tessctl.bak", ".tess/tess.lock"


def _g(root, *a):
    import subprocess
    r = subprocess.run(["git", "-C", str(root), *a], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def _lock_text(engine, fw: dict) -> str:
    import yaml
    return engine.LOCK_HEADER + yaml.safe_dump({"schema": 1, "framework": fw, "files": {}},
                                               sort_keys=False)


@pytest.fixture
def engine_release(tmp_path, gpg_key, engine):
    """A signed upstream v2.1.0 carrying NEW_ENGINE, its self-update proof, and
    a project repo whose base commit pins the key and holds OLD_ENGINE."""
    import subprocess
    from conftest import make_upstream
    up = make_upstream(tmp_path / "up", gpg_key, "v2.1.0", sign="signed", engine_bytes=NEW_ENGINE)
    commit = _g(up, "rev-parse", "v2.1.0^{commit}")
    proof = engine._release_proof_build(up, "refs/tags/v2.1.0", "v2.1.0", commit, {"files": {}})
    root = tmp_path / "proj"
    (root / ".tess/bin").mkdir(parents=True)
    (root / ".tess/keys").mkdir(parents=True)
    _g(tmp_path, "init", "-q", "-b", "main", str(root))
    _g(root, "config", "user.email", "t@tess.test")
    _g(root, "config", "user.name", "T")
    _g(root, "config", "commit.gpgsign", "false")
    key = subprocess.run(["gpg", "--armor", "--export", gpg_key.fpr], capture_output=True,
                         env={**os.environ, "GNUPGHOME": gpg_key.home}).stdout
    (root / ".tess/keys/twiss-release-key.asc").write_bytes(key)
    base_fw = {"track": "v2", "version": "2.0.0", "upstream": str(up), "upstream_ref": "v2.0.0",
               "upstream_commit": None, "upstream_digest": None,
               "trusted_key_fingerprint": gpg_key.fpr, "last_updated": "2026-01-01T00:00:00Z"}
    (root / LOCK).write_text(_lock_text(engine, base_fw))
    (root / ENGINE).write_bytes(OLD_ENGINE)
    _g(root, "add", "-A")
    _g(root, "commit", "-q", "-m", "base")
    return types_ns(root=root, base=_g(root, "rev-parse", "HEAD"), proof=proof, commit=commit,
                    base_fw=base_fw)


def types_ns(**kw):
    import types
    return types.SimpleNamespace(**kw)


def _self_update_commit(engine, rel, *, engine_bytes=NEW_ENGINE, bak=OLD_ENGINE, fw_extra=None,
                        record=True):
    root = rel.root
    (root / ENGINE).write_bytes(engine_bytes)
    if bak is not None:
        (root / BAK).write_bytes(bak)
    fw = dict(rel.base_fw, upstream_ref="v2.1.0", last_updated="2026-02-02T00:00:00Z")
    if record:
        fw.update(engine_ref="v2.1.0", engine_commit=rel.commit)
    fw.update(fw_extra or {})
    (root / LOCK).write_text(_lock_text(engine, fw))
    engine._release_proof_write(root, rel.proof)
    _g(root, "add", "-A")
    _g(root, "commit", "-q", "-m", "self-update")
    head = _g(root, "rev-parse", "HEAD")
    changed = _g(root, "diff", "--name-only", rel.base, head).split("\n")
    cands = [p for p in changed if p in (ENGINE, BAK, LOCK)]
    return engine._gate_release_update_accepted(root, cands, [head], [rel.base], changed_paths=changed)


@pytest.mark.skipif(not (HAS_GIT and HAS_GPG), reason="git + gpg required")
def test_a_self_update_committed_alone_is_accepted(engine, engine_release):
    accepted, info = _self_update_commit(engine, engine_release)
    assert accepted == {ENGINE, BAK, LOCK}, info
    assert info["status"] == "accepted" and info["engine_only"] is True


@pytest.mark.skipif(not (HAS_GIT and HAS_GPG), reason="git + gpg required")
def test_an_engine_that_is_not_the_release_blob_is_refused(engine, engine_release):
    accepted, info = _self_update_commit(engine, engine_release,
                                         engine_bytes=NEW_ENGINE + b"# evil\n")
    assert accepted == set() and info["status"] == "rejected", info


@pytest.mark.skipif(not (HAS_GIT and HAS_GPG), reason="git + gpg required")
def test_a_self_update_without_engine_bookkeeping_is_refused(engine, engine_release):
    accepted, info = _self_update_commit(engine, engine_release, record=False)
    assert accepted == set(), info


@pytest.mark.skipif(not (HAS_GIT and HAS_GPG), reason="git + gpg required")
@pytest.mark.parametrize("extra", [
    {"trusted_key_fingerprint": "B" * 40},
    {"version": "2.1.0"},
    {"upstream": "https://evil.invalid/tess.git"},
    {"engine_commit": "0" * 40},
])
def test_a_self_update_lock_with_other_changes_is_refused(engine, engine_release, extra):
    accepted, info = _self_update_commit(engine, engine_release, fw_extra=extra)
    assert accepted == set(), info


@pytest.mark.skipif(not (HAS_GIT and HAS_GPG), reason="git + gpg required")
def test_an_older_engine_proof_cannot_replace_a_newer_engine(engine, engine_release):
    """Replay: the base already records engine v2.2.0; the v2.1.0 proof is
    genuine but older, so putting the 2.1.0 engine back needs a verdict."""
    rel = engine_release
    rel.base_fw = dict(rel.base_fw, engine_ref="v2.2.0", engine_commit="1" * 40)
    (rel.root / LOCK).write_text(_lock_text(engine, rel.base_fw))
    _g(rel.root, "commit", "-qam", "engine 2.2.0 recorded")
    rel.base = _g(rel.root, "rev-parse", "HEAD")
    accepted, info = _self_update_commit(engine, rel)
    assert accepted == set(), info


@pytest.mark.skipif(not (HAS_GIT and HAS_GPG), reason="git + gpg required")
def test_a_backup_that_is_not_the_base_engine_is_not_accepted(engine, engine_release):
    accepted, info = _self_update_commit(engine, engine_release, bak=b"# anything\n")
    assert accepted == {ENGINE, LOCK}, info


def test_runtime_paths_pass_only_as_the_release_blob(engine):
    resolve = {"scripts/brain/a.py": ("100644", "a" * 40), ENGINE: ("100755", "e" * 40),
               "scripts/other.py": ("100644", "c" * 40), "conductor/x.md": ("100644", "d" * 40)}.get
    head = {"scripts/brain/a.py": "a" * 40, ENGINE: "e" * 40, "scripts/other.py": "c" * 40,
            "conductor/x.md": "d" * 40, "scripts/brain/b.py": "b" * 40}
    base_lock = {"files": {".tess/core/conductor/x.md": {"live_path": "conductor/x.md",
                                                         "status": "user-published"}}}
    got = engine._gate_release_runtime_accepted(Path("."), "HEAD", base_lock, resolve, head,
                                                sorted(head))
    assert got == {"scripts/brain/a.py", ENGINE}


def test_lock_change_must_name_the_proven_engine(engine):
    base = {"framework": {"version": "2.0.0", "upstream_ref": "v2.0.0"}, "files": {}}
    head = {"framework": {"version": "2.1.0", "upstream_ref": "v2.1.0", "upstream_commit": "c" * 40,
                          "engine_ref": "v2.1.0", "engine_commit": "c" * 40}, "files": {}}
    ok = engine._gate_release_lock_change_ok(base, head, "v2.1.0", "c" * 40, lambda r: None,
                                             lambda r: None, lambda r: None)
    assert ok is None
    head["framework"]["engine_ref"] = "v9.9.9"
    assert "engine_ref" in engine._gate_release_lock_change_ok(
        base, head, "v2.1.0", "c" * 40, lambda r: None, lambda r: None, lambda r: None)
