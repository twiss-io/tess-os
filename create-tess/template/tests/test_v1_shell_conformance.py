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
    gate, pristine, work = world
    # round 4b (Reid H1): the gate decides against the same home and temp
    # folder the shells use: the per-run copy (fresh_copy always reuses
    # work/run), never the pristine tree or the real OS-record home.
    run = os.path.realpath(str(work)) + "/run"
    monkeypatch.setenv("HOME", run + "/home")
    monkeypatch.setenv("TMPDIR", run + "/tmp")
    monkeypatch.setattr(gate, "_os_home", lambda: run + "/home", raising=False)
    getattr(gate, "_CONTROL_CACHE", {}).clear()
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
                     f"exit {f['exit']} changed {f['changed']}: {f['command']!r}")
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


def test_worst_case_shells_match_dot_names_and_extended_globs(gate_env):
    """1.0.0 (Cyra and Reid, f8 review): every shell also runs with the glob
    options that match the most (zsh GLOB_DOTS + EXTENDED_GLOB, bash dotglob
    + extglob), and those runs really have them on."""
    _gate, pristine, work = gate_env
    worst = [sh for sh in sc.shells() if sh.endswith(sc.WORST_SUFFIX)]
    assert {os.path.basename(sh[:-len(sc.WORST_SUFFIX)]) for sh in worst} >= {"bash", "zsh"}
    for sh in worst:
        s = sc.fresh_copy(pristine, work / "worstcheck")
        d = Path(s["T"]) / "w"
        d.mkdir()
        (d / ".hid").write_text("x")
        (d / "abc").write_text("x")
        (d / "abd").write_text("x")
        ext = "ab^c" if "zsh" in os.path.basename(sh) else "!(abc)"
        code, err = sc.run_shell(sh, f"cd '{d}' && for f in *; do touch \"$f.seen\"; done && "
                                     f"for f in {ext}; do touch \"$f.ext\"; done", s)
        assert code == 0, (sh, err)
        assert (d / ".hid.seen").exists(), sh                     # dot names match
        assert (d / "abd.ext").exists() and not (d / "abc.ext").exists(), sh  # extended glob
    sc._rmtree(work / "worstcheck")


def test_nullglob_profile_removes_a_non_matching_glob(gate_env):
    """1.0.0 (a4113f7 review, item d): the +nullglob profile really drops a
    glob that matches nothing, so the harness exercises the word-shift the
    gate must account for; the broadening options stay off."""
    _gate, pristine, work = gate_env
    null = [sh for sh in sc.shells() if sh.endswith(sc.NULLGLOB_SUFFIX)]
    assert {os.path.basename(sh[:-len(sc.NULLGLOB_SUFFIX)]) for sh in null} >= {"bash", "zsh"}
    for sh in null:
        s = sc.fresh_copy(pristine, work / "nullcheck")
        d = Path(s["T"]) / "n"
        d.mkdir()
        # `touch pre *.none post`: with nullglob, *.none vanishes -> `touch pre post`
        code, err = sc.run_shell(sh, f"cd '{d}' && touch pre *.none post", s)
        assert code == 0, (sh, err)
        assert (d / "pre").exists() and (d / "post").exists(), sh
        assert not (d / "*.none").exists(), sh    # the literal was not created: it vanished
    sc._rmtree(work / "nullcheck")


def test_worst_profile_globs_an_unquoted_value_in_zsh(gate_env):
    """item e / GLOB_SUBST: under +worst, zsh reads an unquoted variable value
    as a glob pattern."""
    _gate, pristine, work = gate_env
    zworst = [sh for sh in sc.shells() if sh.endswith(sc.WORST_SUFFIX)
              and "zsh" in os.path.basename(sh)]
    for sh in zworst:
        s = sc.fresh_copy(pristine, work / "substcheck")
        d = Path(s["T"]) / "s"
        d.mkdir()
        (d / "hit").write_text("x")
        code, err = sc.run_shell(sh, f"cd '{d}' && p='h*t'; for f in $p; do touch \"$f.seen\"; done", s)
        assert code == 0, (sh, err)
        assert (d / "hit.seen").exists(), sh      # the value h*t matched `hit`
    sc._rmtree(work / "substcheck")


def test_null_glob_profiles_drop_expanded_brace_and_extended_globs(gate_env):
    """1.0.0 (a769130 review, M1 and L1): the word kinds the gate now counts as
    possibly vanishing really vanish in the shells: a no-match glob from an
    unquoted variable, a command substitution or a brace (bash +nullglob and
    +worst; zsh +worst, where GLOB_SUBST is on), a brace in zsh +nullglob, and
    an EXTENDED_GLOB-only form (zsh +worst)."""
    _gate, pristine, work = gate_env
    words = {"param": "$p", "subst": "$(printf %s 'zz*.none')", "brace": "{zz,yy}*.none",
             "ext": "zznone#"}
    want = {("bash", sc.NULLGLOB_SUFFIX): {"param", "subst", "brace"},
            ("bash", sc.WORST_SUFFIX): {"param", "subst", "brace"},
            ("zsh", sc.NULLGLOB_SUFFIX): {"brace"},
            ("zsh", sc.WORST_SUFFIX): {"param", "subst", "brace", "ext"}}
    seen = set()
    for sh in sc.shells():
        prog, suf = sc._profile_of(sh)
        kind = "zsh" if "zsh" in os.path.basename(prog) else "bash"
        if (kind, suf) not in want:
            continue
        seen.add((kind, suf))
        for name, word in words.items():
            s = sc.fresh_copy(pristine, work / "nullkinds")
            d = Path(s["T"]) / "k"
            d.mkdir()
            # `touch pre WORD post`: a vanished WORD leaves exactly pre and post
            code, err = sc.run_shell(sh, f"cd '{d}' && p='zz*.none'; touch pre {word} post", s)
            assert code == 0, (sh, name, err)
            gone = sorted(os.listdir(d)) == ["post", "pre"]
            assert gone == (name in want[(kind, suf)]), (sh, name, sorted(os.listdir(d)))
            sc._rmtree(work / "nullkinds")
    assert seen == set(want), seen


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


def _instances(glob_entry: str) -> list:
    """Concrete paths one entry of the gate's protected list names."""
    base = glob_entry[:-3] if glob_entry.endswith("/**") else glob_entry
    base = base.replace("*", "x").replace("?", "x")
    return [base, base + "/x/y"] if glob_entry.endswith("/**") else [base]


def test_control_paths_are_the_gates_own_list_minus_what_git_writes(tmp_path):
    """round 4b (Reid H2): every path the gate protects counts in a replay,
    except the exact set git itself writes during an allowed commit, branch
    or tag. Derived from the gate module, so the two cannot drift."""
    gate = sc.load_gate()
    p = tmp_path / "proj"
    (p / ".git").mkdir(parents=True)
    (p / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    s = {"P": str(p), "H": str(tmp_path / "home")}
    for g in gate.PROTECTED_GLOBS:
        for rel in _instances(g):
            want = not sc._git_normal_write(rel, s)
            assert sc.controlled(rel, gate, s) is want, (g, rel)
    # what the round-4 filter hid: each counts now
    for rel in (".git/info/grafts", ".git/info/sparse-checkout", ".git/refs/replace/abc",
                ".git/packed-refs", ".git/worktrees/w/HEAD", ".tess/snapshots/t/.claude/settings.json",
                ".git/config", ".git/hooks/pre-commit", ".claude/settings.local.json", "CLAUDE.md",
                ".tess/tess.lock", ".github/workflows/ci.yml", "scripts/brain/x.py"):
        assert sc.controlled(rel, gate, s) is True, rel
    for rel in (".git/objects/ab/cd", ".git/index", ".git/refs/heads/main", ".git/refs/tags/v1",
                ".git/logs/HEAD", ".git/HEAD", "src/a.py", "notes.md"):
        assert sc.controlled(rel, gate, s) is False, rel
    # HEAD counts once it no longer names a local branch
    (p / ".git" / "HEAD").write_text("ref: refs/remotes/x\n")
    assert sc.controlled(".git/HEAD", gate, s) is True


def test_only_an_exact_restore_snapshot_is_not_counted():
    """`tessctl restore` writes a snapshot of the project's own files first;
    planted or changed snapshot content counts (round 4b, Reid H2)."""
    before = {"CLAUDE.md": ("file", 0o644, "h1"), ".claude": ("dir", 0o755),
              ".claude/settings.json": ("file", 0o644, "h2")}
    good = {".tess/snapshots": ("dir", 0o755), ".tess/snapshots/t1": ("dir", 0o755),
            ".tess/snapshots/t1/CLAUDE.md": ("file", 0o644, "h1"),
            ".tess/snapshots/t1/.claude": ("dir", 0o755),
            ".tess/snapshots/t1/.claude/settings.json": ("file", 0o644, "h2")}
    after = {**before, **good}
    assert not [k for k in good if not sc._true_snapshot(k, before, after)]
    planted = {**after, ".tess/snapshots/t1/.claude/settings.json": ("file", 0o644, "EVIL")}
    assert not sc._true_snapshot(".tess/snapshots/t1/.claude/settings.json", before, planted)
    extra = {**after, ".tess/snapshots/t1/scripts/brain/x.py": ("file", 0o644, "h1")}
    assert not sc._true_snapshot(".tess/snapshots/t1/scripts/brain/x.py", before, extra)
    old = {**before, ".tess/snapshots": ("dir", 0o755), ".tess/snapshots/t0": ("dir", 0o755),
           ".tess/snapshots/t0/CLAUDE.md": ("file", 0o644, "h1")}
    changed = {**old, ".tess/snapshots/t0/x": ("file", 0o644, "h1")}
    assert not sc._true_snapshot(".tess/snapshots/t0/x", old, changed)


def test_only_a_new_run_trace_file_is_not_counted():
    """`tessctl` writes its run telemetry to a new `.tess/trace/runs/<id>.jsonl`
    (local runtime state the gate does not protect); a changed or removed
    trace file, or anything else under `.tess/trace/`, still counts."""
    before = {"CLAUDE.md": ("file", 0o644, "h1")}
    new = {".tess/trace": ("dir", 0o755), ".tess/trace/runs": ("dir", 0o755),
           ".tess/trace/runs/0123abcd.jsonl": ("file", 0o644, "t1")}
    after = {**before, **new}
    assert all(sc._new_run_trace(k, before, after) for k in new)
    old = {**before, ".tess/trace": ("dir", 0o755), ".tess/trace/runs": ("dir", 0o755),
           ".tess/trace/runs/old.jsonl": ("file", 0o644, "t0")}
    assert not sc._new_run_trace(".tess/trace/runs/old.jsonl", old,
                                 {**old, ".tess/trace/runs/old.jsonl": ("file", 0o644, "t9")})
    assert not sc._new_run_trace(".tess/trace/other.json", before,
                                 {**after, ".tess/trace/other.json": ("file", 0o644, "x")})
    assert not sc._new_run_trace(".tess/trace/runs/x.sh", before,
                                 {**after, ".tess/trace/runs/x.sh": ("file", 0o755, "x")})
    assert not sc._new_run_trace(".tess/trace/runs/l.jsonl", before,
                                 {**after, ".tess/trace/runs/l.jsonl": ("link", "x")})


def test_a_restore_manifest_counts_unless_it_matches_the_project(tmp_path):
    before = {"CLAUDE.md": ("file", 0o644, "h1"), "lnk": ("link", "x")}
    rel = ".tess/snapshots/t1/manifest.json"
    after = {**before, ".tess/snapshots": ("dir", 0o755), ".tess/snapshots/t1": ("dir", 0o755),
             rel: ("file", 0o644, "m")}
    (tmp_path / ".tess/snapshots/t1").mkdir(parents=True)
    good = {"CLAUDE.md": {"existed": True, "sha256": "sha256:h1", "mode": 0o644},
            "new.md": {"existed": False},
            "lnk": {"existed": True, "is_symlink": True, "link_target": "x"},
            "out": {"out_of_tree": True}}
    for man, ok in ((good, True),
                    ({**good, "CLAUDE.md": {"existed": True, "sha256": "sha256:EVIL", "mode": 0o644}},
                     False),
                    ({**good, "CLAUDE.md": {"existed": False}}, False),  # rollback would delete it
                    ({**good, "lnk": {"existed": True, "is_symlink": True, "link_target": "y"}}, False),
                    ([1], False)):
        (tmp_path / rel).write_text(json.dumps(man))
        assert sc._true_snapshot(rel, before, after, str(tmp_path)) is ok, man
    (tmp_path / rel).write_text("{not json")
    assert sc._true_snapshot(rel, before, after, str(tmp_path)) is False


def test_home_control_files_are_the_gates_own_list(tmp_path, monkeypatch):
    """round 4b (Reid H1): user-level control files and the key folder in the
    sandbox home count, by the gate's control_file_hit and key_hit."""
    gate = sc.load_gate()
    home = str(tmp_path / "home")
    monkeypatch.setenv("HOME", home)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(gate, "_os_home", lambda: home)
    gate._CONTROL_CACHE.clear()
    s = {"P": str(tmp_path / "proj"), "H": home}
    for rel in (".gitconfig", ".config/git/config", ".claude/settings.json", ".claude.json",
                ".codex/config.toml", ".codex/rules/x", ".config/tess/operator.key") + sc.HOME_CONTROL:
        assert sc.home_controlled(rel, gate, s) is True, rel
    for rel in (".cache/pip/x", ".zsh_history", "notes.txt"):
        assert sc.home_controlled(rel, gate, s) is False, rel


@pytest.mark.skipif(not __import__("shutil").which("git"), reason="needs git to read a config file")
def test_a_home_git_config_change_counts_unless_the_gate_allows_each_key(tmp_path, monkeypatch):
    """round 4b (Reid H1): `git config --global <ordinary key>` is allowed and
    writes ~/.gitconfig; a run that changes it only that way is not a
    failure. A key the gate refuses on that route (core.hooksPath), or a file
    git cannot read, counts."""
    gate = sc.load_gate()
    base = Path(tempfile.mkdtemp(prefix="tess-conf-unit-"))
    try:
        s = sc.build_pristine(base / "pristine")
        monkeypatch.setenv("HOME", s["H"])
        monkeypatch.setenv("TMPDIR", s["T"])
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        monkeypatch.setattr(gate, "_os_home", lambda: s["H"])
        monkeypatch.setattr(gate, "_ancestry", lambda limit=40: ["python3", "zsh", "login"],
                            raising=False)
        gate._CONTROL_CACHE.clear()
        before = b"[user]\n\tname = a\n"
        cfg = Path(s["H"], ".gitconfig")
        for text, counts in ((b"[user]\n\tname = b\n", False),
                             (b"[user]\n\tname = a\n[pull]\n\trebase = true\n", False),
                             (b"[user]\n\tname = a\n# a comment\n", False),
                             (b"[user]\n\tname = a\n[core]\n\thooksPath = /x\n", True),
                             (b"[user]\n\tname = a\n[include]\n\tpath = /x\n", True),
                             (b"[user\n\tname = a\n", True)):
            cfg.write_bytes(text)
            got = sc.changed_home_controls({".gitconfig": ("file", 1)}, {".gitconfig": ("file", 2)},
                                           gate, s, {".gitconfig": before})
            assert (got == ["~/.gitconfig"]) is counts, text
    finally:
        sc._rmtree(base)
