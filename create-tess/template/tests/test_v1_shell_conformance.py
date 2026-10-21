"""
v1.0.x round 4: real-shell conformance for the Tess gate.

Every command the gate ALLOWS (in Claude default, Claude acceptEdits or
Codex) from two corpora is run in real bash and zsh inside a disposable,
jailed sandbox project, and every protected control file must be unchanged
afterwards. The corpora:
  * tests/shell_conformance_corpus.json: Quinn's attack probes for d2a5707
    (G1, G2, X, NUL), everyday controls, and the zsh/bash syntax probes that
    found the round-4 shell-model classes;
  * the commands the rest of the test suite hands the gate, recorded by the
    `gate_corpus_recorder` plugin (TESS_CONFORMANCE_CORPUS: a .jsonl file or
    a folder of them; CI records it in the test job and passes it on).

Running real shells is opt-in: TESS_SHELL_CONFORMANCE=1, or
TESS_CONFORMANCE_REQUIRED=1 (CI), which also turns every "cannot run here"
skip into a failure. TESS_CONFORMANCE_REPO checks another tree's gate (used to
show the harness flags Quinn's findings on d2a5707). Safety: see
tests/shell_conformance.py.
"""

from __future__ import annotations

import glob
import json
import os
import tempfile
from pathlib import Path

import pytest

import shell_conformance as sc

REQUIRED = os.environ.get("TESS_CONFORMANCE_REQUIRED") == "1"
ENABLED = REQUIRED or os.environ.get("TESS_SHELL_CONFORMANCE") == "1"
CORPUS = Path(__file__).resolve().parent / "shell_conformance_corpus.json"
SLASHFREE = ("RANDOM", "SRANDOM", "SECONDS", "LINENO", "UID", "EUID", "PPID", "BASHPID",
             "EPOCHSECONDS", "EPOCHREALTIME", "HISTCMD", "OPTIND", "SHLVL", "COLUMNS", "LINES")


def _cannot(why: str):
    if REQUIRED:
        pytest.fail(f"shell conformance is required here but cannot run: {why}")
    pytest.skip(why)


def _repo() -> Path:
    return Path(os.environ.get("TESS_CONFORMANCE_REPO") or sc.REPO).resolve()


@pytest.fixture(scope="module")
def world():
    if not ENABLED:
        pytest.skip("real shells run only with TESS_SHELL_CONFORMANCE=1 (CI sets it)")
    if sc.jail() is None:
        _cannot("no sandbox-exec (macOS) or bwrap (Linux) to confine the shells")
    names = {os.path.basename(s) for s in sc.shells()}
    if not {"bash", "zsh"} <= names:
        _cannot(f"both bash and zsh are needed, found {sorted(names)}")
    work = Path(tempfile.mkdtemp(prefix="tess-conformance-"))
    pristine = sc.build_pristine(work / "pristine", _repo())
    sc.confinement_self_test(sc.fresh_copy(pristine, work / "selftest"))
    gate = sc.load_gate(_repo())
    yield gate, pristine, work
    sc._rmtree(work)


@pytest.fixture
def gate_env(world, monkeypatch):
    gate, pristine, _work = world
    monkeypatch.setenv("HOME", pristine["H"])
    monkeypatch.setenv("TMPDIR", pristine["T"])
    for k in ("XDG_CONFIG_HOME", "TESS_BRAIN_PROVENANCE_DIR", "GIT_DIR", "GIT_WORK_TREE",
              "TESS_CONSULT_DEPTH", "CDPATH", "TESS_HEADLESS", "TESS_DISPATCHED", *SLASHFREE):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(gate, "_ancestry", lambda limit=40: ["python3", "zsh", "login"], raising=False)
    return world


def _report(res: dict) -> str:
    lines = [f"{len(res['failures'])} run(s) changed a protected file "
             f"({res['allowed']} allowed commands, {res['ran']} shell runs):"]
    for f in res["failures"]:  # every failure, never a cut-down list
        lines.append(f"  [{f['id']}] {os.path.basename(f['shell'])} {'/'.join(f['decisions'])} "
                     f"changed {f['changed']}: {f['command']!r}")
    return "\n".join(lines)


def _stub_note(res: dict) -> str:
    return (f"{len(res['stubbed'])} run(s) called a stubbed program (network, preferences, agent "
            "CLIs, package managers); their control files were still checked: "
            + ", ".join(f"{t}:{os.path.basename(sh)}:{'+'.join(n)}" for t, sh, n in res["stubbed"]))


# ------------------------------------------------------------------ always on
def test_sandbox_is_never_built_outside_the_temp_folder(tmp_path):
    with pytest.raises(RuntimeError):
        sc.build_pristine(Path.home() / "tess-conformance-must-not-exist")
    assert not (Path.home() / "tess-conformance-must-not-exist").exists()


def test_templates_only_name_sandbox_paths():
    s = {"P": "/S/proj", "H": "/S/home", "W": "/S/W", "T": "/S/tmp"}
    assert sc.expand("cp -R @W/evil/. /tmp/x && rm @P/a ~/b @H/c", s) == \
        "cp -R /S/W/evil/. /S/tmp/x && rm /S/proj/a ~/b /S/home/c"


def test_corpus_file_holds_no_machine_paths():
    text = CORPUS.read_text(encoding="utf-8")
    for bad in ("/Users/", "/home/", "/private/var/", "/var/folders/"):
        assert bad not in text


def test_harvest_maps_recorded_folders_to_placeholders(tmp_path):
    rec = {"t": "x", "cmd": "cp -R /r/p/. /t/q && cat /h/f && ls /repo", "d": "allow",
           "root": "/r/p", "root_raw": "/r/p", "home": "/h", "tmp": "/t", "repo": "/repo"}
    f = tmp_path / "c.jsonl"
    f.write_text(json.dumps(rec) + "\n" + json.dumps({**rec, "d": "ask", "cmd": "rm x"}) + "\n"
                 + json.dumps(rec) + "\n")
    # every recorded command (whatever it was decided there) is decided again; duplicates once
    assert sc.load_harvest(str(f)) == [("harvest:x", "cp -R @P/. @T/q && cat @H/f && ls @P"),
                                       ("harvest:x", "rm x")]


# ------------------------------------------------------------------ real shells
def test_the_jail_refuses_writes_outside_the_sandbox(gate_env):
    _gate, pristine, work = gate_env
    sc.confinement_self_test(sc.fresh_copy(pristine, work / "selftest2"))


def test_attack_and_everyday_corpus_conforms(gate_env):
    gate, pristine, work = gate_env
    cases = json.loads(CORPUS.read_text(encoding="utf-8"))["cases"]
    res = sc.replay(gate, pristine, sorted(cases.items()), work)
    print(f"\ncurated corpus: {len(cases)} commands, {res['allowed']} allowed, {res['ran']} shell runs")
    print(_stub_note(res))
    assert not res["failures"], _report(res)
    assert res["ran"] > 0


def test_recorded_test_suite_corpus_conforms(gate_env):
    gate, pristine, work = gate_env
    where = os.environ.get("TESS_CONFORMANCE_CORPUS")
    if not where:
        _cannot("TESS_CONFORMANCE_CORPUS is not set (record it with -p gate_corpus_recorder)")
    files = sorted(glob.glob(os.path.join(where, "**", "*.jsonl"), recursive=True)) \
        if os.path.isdir(where) else [where]
    templates, seen = [], set()
    for f in files:
        for tid, t in sc.load_harvest(f):
            if t not in seen:
                seen.add(t)
                templates.append((tid, t))
    if not templates:
        _cannot(f"no recorded commands in {where}")
    res = sc.replay(gate, pristine, templates, work)
    print(f"\nrecorded corpus: {len(templates)} commands, {res['allowed']} allowed, {res['ran']} shell runs")
    print(_stub_note(res))
    assert not res["failures"], _report(res)


def test_a_run_that_times_out_is_a_failure_never_a_pass(tmp_path, monkeypatch):
    """A killed run may have gone on to change files: it is reported."""
    class AllowAll:
        @staticmethod
        def decide(data, root, runtime):
            return None, ""

        @staticmethod
        def protected_hit(root, cwd, path):
            return None

    base = Path(tempfile.mkdtemp(prefix="tess-conf-unit-"))
    try:
        pristine = sc.build_pristine(base / "pristine")
        monkeypatch.setattr(sc, "shells", lambda: ["/bin/sh"])
        monkeypatch.setattr(sc, "run_shell", lambda sh, cmd, s: ("timeout", ""))
        res = sc.replay(AllowAll, pristine, [("t1", "sleep 100")], base)
        assert res["failures"] and res["failures"][0]["changed"] == ["<timed out: the run did not finish>"]
    finally:
        sc._rmtree(base)


def test_control_paths_exclude_only_the_object_store_and_restore_snapshots():
    class Model:
        @staticmethod
        def protected_hit(root, cwd, path):
            return "x" if "CLAUDE" in path or "/.git/" in path else None
    s = {"P": "/S/proj"}
    assert sc.controlled(".git/objects/ab/cd", Model, s) is False
    assert sc.controlled(".tess/snapshots/t/.claude/settings.json", Model, s) is False
    assert sc.controlled(".tess/snapshots", Model, s) is False
    for rel in (".git/config", ".git/hooks/pre-commit", ".claude/settings.local.json",
                ".tess/tess.lock", ".tess/core/x", "CLAUDE.md", ".github/workflows/ci.yml"):
        assert sc.controlled(rel, Model, s) is True, rel
