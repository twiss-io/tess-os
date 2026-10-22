"""v1.0.0 final review (GPT-6), two HIGH findings.

F1 — the anchor's view of tess.lock was a line scanner, not the YAML tree
`load_lock` uses: a second inline `framework: {...}` mapping swapped the
release upstream + key pins while the anchor digest stayed the same, and the
release key files themselves were not anchored. Now one strict reader
(`lock_strict_tree`, byte-identical in run-pinned.py and tessctl) refuses
anything outside the form Tess writes, `load_lock` checks YAML agrees with it,
the digest covers every non-volatile key, and the key files are anchored.

F2 — `self-update` never checked the anchor first and re-anchored every
current file afterwards (blessing any earlier tampering). Now it refuses while
the files differ, and after a verified update only files the release run wrote
take new hashes; any other change stops without recording.

Anchors here go to a fake OS-record home (fixtures.os_home), never ~/.config.
"""
from __future__ import annotations

import ast
import importlib.machinery
import importlib.util
import json
import subprocess

import pytest
import yaml

from conftest import ENGINE_SRC, make_upstream, ns
from fixtures.anchor import REPO
from fixtures.os_home import operator_home  # noqa: F401 — autouse: fake OS-record home
from test_v1_integration import _installed_instance, _update, needs_gpg

SHARED = ("LOCK_VOLATILE", "_LOCK_BAD_CHAR", "_LOCK_SQ", "_LOCK_DQ", "_LOCK_PLAIN", "_LOCK_NAME",
          "_lock_plain_ok", "_lock_scalar", "_lock_quote_end", "lock_strict_tree",
          "lock_projection")
EVIL_FP = "DEADBEEF" * 5


def _load(path, name):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader))
    loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def rp():
    return _load(REPO / ".claude/hooks/run-pinned.py", "rp_lock_strict")


@pytest.fixture(scope="module")
def eng():
    return _load(REPO / ".tess/bin/tessctl", "eng_lock_strict")


@pytest.fixture(scope="module")
def lock_text():
    return (REPO / ".tess/tess.lock").read_text(encoding="utf-8")


def _defs(path):
    out = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        names = [node.name] if isinstance(node, (ast.FunctionDef, ast.ClassDef)) else [
            t.id for t in getattr(node, "targets", []) if isinstance(t, ast.Name)]
        for n in names:
            if n in SHARED:
                out[n] = ast.dump(node)
    return out


def test_the_strict_reader_is_the_same_code_in_both_components():
    a, b = _defs(REPO / ".claude/hooks/run-pinned.py"), _defs(REPO / ".tess/bin/tessctl")
    assert set(a) == set(SHARED) and a == b


# --- F1: the reported exploit and every construct the strict form refuses ----

def _inline_framework(text):
    return text + (f"framework: {{upstream: 'https://evil.example/tess.git', "
                   f"trusted_key_fingerprint: {EVIL_FP}, trusted_ssh_key_fingerprint: ''}}\n")


BAD = {
    "inline duplicate framework mapping": _inline_framework,
    "duplicate top-level key": lambda t: t.replace("schema: 1\n", "schema: 1\nschema: 1\n", 1),
    "duplicate nested key": lambda t: t.replace("  channel: stable\n",
                                                "  channel: stable\n  channel: beta\n", 1),
    "block duplicate framework": lambda t: t + "framework:\n  upstream: https://evil.example/x\n",
    "merge key": lambda t: t.replace("  channel: stable\n", "  <<: {upstream: x}\n", 1),
    "anchor on a mapping + alias": lambda t: t.replace("framework:\n", "framework: &fw\n", 1)
    + "evil: *fw\n",
    "alias to an unknown anchor": lambda t: t.replace("  channel: stable\n", "  channel: *nope\n", 1),
    "tag": lambda t: t.replace("  channel: stable\n", "  channel: !!str stable\n", 1),
    "second document": lambda t: t + "---\nframework: {}\n",
    "block scalar": lambda t: t.replace("  channel: stable\n", "  channel: |\n    stable\n", 1),
    "continued plain value": lambda t: t.replace("  channel: stable\n",
                                                 "  channel: stable\n    evil\n", 1),
    "flow list": lambda t: t.replace("  channel: stable\n", "  channel: [a, b]\n", 1),
    "tab": lambda t: t.replace("  channel: stable\n", "  channel:\tstable\n", 1),
    "carriage return": lambda t: t.replace("  channel: stable\n", "  channel: stable\r\n", 1),
}


def test_the_reported_exploit_changes_yaml_but_is_now_refused(rp, eng, lock_text):
    bad = _inline_framework(lock_text)
    fw = yaml.safe_load(bad)["framework"]   # what PyYAML alone would have used
    assert fw["upstream"] == "https://evil.example/tess.git" and fw["trusted_key_fingerprint"] == EVIL_FP
    with pytest.raises(eng.LockFormatError, match="appears twice"):
        eng._lock_load_text(bad)
    assert rp.lock_projection(bad) != rp.lock_projection(lock_text)
    assert rp.lock_projection(bad) == eng._anchor_lock_projection(bad)


@pytest.mark.parametrize("case", sorted(BAD))
def test_unsupported_yaml_is_refused_and_both_components_agree(rp, eng, lock_text, case):
    bad = BAD[case](lock_text)
    with pytest.raises(ValueError):
        rp.lock_strict_tree(bad)
    with pytest.raises(eng.LockFormatError):
        eng._lock_load_text(bad)
    digest = rp.lock_projection(bad)
    assert digest.startswith("rejected:") and digest == eng._anchor_lock_projection(bad)
    assert digest != rp.lock_projection(lock_text)


def test_load_lock_fails_closed_with_a_plain_message(eng, lock_text, tmp_path):
    (tmp_path / ".tess").mkdir()
    (tmp_path / ".tess/tess.lock").write_text(_inline_framework(lock_text), encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        eng.load_lock(tmp_path)
    assert "not in the form Tess writes" in str(e.value) and "Nothing was changed" in str(e.value)


def test_the_real_lock_reads_the_same_both_ways(rp, eng, lock_text):
    data = eng._lock_load_text(lock_text)
    assert data == yaml.safe_load(lock_text)
    assert set(rp.lock_strict_tree(lock_text)) == set(data)


@pytest.mark.parametrize("edit,volatile", [
    (lambda t: t.replace("status: core-managed", "status: quarantined", 1), True),
    (lambda t: t.replace("  last_updated: '2026", "  last_updated: '2027", 1), True),
    (lambda t: t.replace("status: rendered", "status: captured", 1), True),
    (lambda t: t.replace("  upstream: https://github.com/twiss-io/tess-os.git",
                         "  upstream: https://evil.example/tess.git", 1), False),
    (lambda t: t.replace("  upstream_ref: v1.0.0", "  upstream_ref: v0.9.0", 1), False),
    (lambda t: t.replace("tier: security", "tier: normal", 1), False),
    (lambda t: t.replace("  channel: stable\n", "  channel: stable\n  extra: 1\n", 1), False),
])
def test_only_bookkeeping_fields_are_left_out_of_the_digest(rp, eng, lock_text, edit, volatile):
    changed = edit(lock_text)
    assert changed != lock_text
    eng._lock_load_text(changed)   # still a valid lock
    assert (rp.lock_projection(changed) == rp.lock_projection(lock_text)) is volatile
    assert rp.lock_projection(changed) == eng._anchor_lock_projection(changed)


def test_an_alias_is_read_as_the_value_it_names(rp, eng):
    base = "schema: 1\nframework:\n  version: &v 1.0.0\n  upstream_ref: *v\n"
    assert eng._lock_load_text(base)["framework"]["upstream_ref"] == "1.0.0"
    moved = "schema: 1\nframework:\n  version: &v 2.0.0\n  upstream_ref: *v\n"
    assert rp.lock_projection(base) != rp.lock_projection(moved)
    # an anchor on a bookkeeping field still pins the enforcement field aliasing it
    ent = "schema: 1\nfiles:\n  a.md:\n    last_updated: &t sha256:{}\n    base_sha: *t\n"
    assert rp.lock_projection(ent.format("aa")) != rp.lock_projection(ent.format("bb"))
    assert eng._lock_load_text(ent.format("bb"))["files"]["a.md"]["base_sha"] == "sha256:bb"


# --- F1 (c): the release key files are anchored -------------------------------

@pytest.mark.parametrize("rel", [".tess/keys/twiss-release-key.asc",
                                 ".tess/keys/twiss-release-allowed-signers"])
def test_swapping_a_release_key_file_is_an_anchor_mismatch_in_both(project, rp, rel):
    for k in (".tess/keys/twiss-release-key.asc", ".tess/keys/twiss-release-allowed-signers"):
        (project.root / k).parent.mkdir(parents=True, exist_ok=True)
        (project.root / k).write_text(f"release key {k}\n")
    project.write()
    # a root commit gives the project the id both components look the anchor up by
    git = ["git", "-C", str(project.root), "-c", "user.email=t@tess.test", "-c", "user.name=T",
           "-c", "commit.gpgsign=false"]
    subprocess.run(git + ["init", "-q", "-b", "main"], check=True)
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["commit", "-q", "--no-verify", "-m", "base"], check=True)
    project.mod._anchor_write(project.root, "test")
    assert rel in project.mod._anchor_state(project.root).doc["files"]
    assert rp.anchor_check(project.root) is not None
    (project.root / rel).write_text("attacker public key\n")
    st = project.mod._anchor_state(project.root)
    assert st.state == "mismatch" and f"{rel} has changed" in st.problems
    with pytest.raises(rp.AnchorError) as e:
        rp.anchor_check(project.root)
    assert e.value.problems == st.problems


# --- F2: self-update / update never re-anchor tampering ------------------------

ENF = (".claude/hooks/tess-gate.py", ".tess/core/pinned-scripts.sha256")


def _enforcement(project):
    for rel in ENF:
        (project.root / rel).parent.mkdir(parents=True, exist_ok=True)
        (project.root / rel).write_text(f"approved {rel}\n")


def _su_project(project, gpg_key, tmp_path):
    up = make_upstream(tmp_path / "up_f2", gpg_key, "v2.0.1", sign="signed",
                       core_files={".tess/core/conductor/guardrails.md": "g\n"},
                       engine_bytes=ENGINE_SRC.read_bytes() + b"\n# f2 test\n")
    project.add("conductor/a.md", "alpha\n")
    project.framework["upstream"] = str(up)
    project.framework["upstream_ref"] = "v2.0.0"
    project.framework["trusted_key_fingerprint"] = gpg_key.fpr
    project.write()
    _enforcement(project)
    return project.mod._anchor_write(project.root, "test")


def _files(where):
    return json.loads(where.read_text())["files"]


@pytest.mark.skipif(not ENGINE_SRC.is_file(), reason="engine missing")
def test_self_update_refuses_while_gate_and_pins_are_tampered(project, gpg_key, tmp_path):
    where = _su_project(project, gpg_key, tmp_path)
    before, engine = where.read_bytes(), (project.root / ".tess/bin/tessctl").read_bytes()
    for rel in ENF:
        (project.root / rel).write_text("tampered\n")
    with pytest.raises(SystemExit) as e:
        project.mod.cmd_self_update(ns(ref="v2.0.1", to=None, trust_on_first_use=False),
                                    project.root)
    assert "STOPPED" in str(e.value) and "Nothing was changed" in str(e.value)
    assert where.read_bytes() == before, "anchor unchanged"
    assert (project.root / ".tess/bin/tessctl").read_bytes() == engine, "engine unchanged"


@pytest.mark.skipif(not ENGINE_SRC.is_file(), reason="engine missing")
def test_clean_self_update_changes_only_what_the_release_wrote(project, gpg_key, tmp_path):
    where = _su_project(project, gpg_key, tmp_path)
    old = _files(where)
    project.mod.cmd_self_update(ns(ref="v2.0.1", to=None, trust_on_first_use=False), project.root)
    new = _files(where)
    changed = {rel for rel in set(old) | set(new) if old.get(rel) != new.get(rel)}
    assert ".tess/bin/tessctl" in changed
    assert changed <= {".tess/bin/tessctl", ".tess/tess.lock"}, changed   # lock: upstream_ref
    assert all(new[rel] == old[rel] for rel in ENF)
    assert project.mod._anchor_state(project.root).state == "ok"


def test_reanchor_after_a_release_never_blesses_a_change_it_did_not_write(project):
    _enforcement(project)
    project.write()
    where = project.mod._anchor_write(project.root, "test")
    before = where.read_bytes()
    engine = project.root / ".tess/bin/tessctl"
    project.mod._RELEASE_WRITES.clear()
    engine.write_bytes(engine.read_bytes() + b"\n# verified release\n")
    project.mod._release_write_note(engine, engine.read_bytes())
    (project.root / ENF[0]).write_text("tampered mid-run\n")
    for verb in ("update", "self-update"):
        with pytest.raises(SystemExit) as e:
            project.mod._anchor_after_release(project.root, verb, engine=engine)
        assert "did NOT record" in str(e.value) and ENF[0] in str(e.value)
        assert where.read_bytes() == before
    (project.root / ENF[0]).write_text(f"approved {ENF[0]}\n")   # put back: only the engine changed
    project.mod._anchor_after_release(project.root, "update")
    new, old = _files(where), json.loads(before)["files"]
    assert new[".tess/bin/tessctl"] != old[".tess/bin/tessctl"]
    assert {r: v for r, v in new.items() if r != ".tess/bin/tessctl"} == \
        {r: v for r, v in old.items() if r != ".tess/bin/tessctl"}


@needs_gpg
def test_update_with_an_anchor_carries_forward_what_it_did_not_write(project, gpg_key, tmp_path,
                                                                     run_cli):
    _installed_instance(project, gpg_key, tmp_path, run_cli)
    (project.root / ENF[0]).parent.mkdir(parents=True, exist_ok=True)
    (project.root / ENF[0]).write_text("approved gate, not part of this release\n")
    where = project.mod._anchor_write(project.root, "test")
    old = _files(where)
    _update(project, run_cli)
    st = project.mod._anchor_state(project.root)
    assert st.state == "ok" and st.doc["source"] == "update", st.problems
    assert st.doc["files"][ENF[0]] == old[ENF[0]]


def test_multi_line_quoted_text_as_save_lock_writes_it_is_read_like_yaml(rp, eng, tmp_path):
    diff = "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-\told  \n+new ' \" \\ line " + "long " * 40 + "\n"
    lock = {"schema": 1, "framework": {"version": "1.0.0", "upstream": "u"},
            "files": {"a.md": {"status": "patch-override", "base_sha": "sha256:aa",
                               "override_diff": diff, "note": "x\ny " + "z " * 70}}}
    (tmp_path / ".tess").mkdir()
    eng.save_lock(tmp_path, lock)
    text = (tmp_path / ".tess/tess.lock").read_text(encoding="utf-8")
    assert "\n      " in text, "the long values really span lines"
    assert eng._lock_load_text(text) == yaml.safe_load(text) == lock
    lock["files"]["a.md"]["override_diff"] = diff + "+more\n"      # bookkeeping: same digest
    eng.save_lock(tmp_path, lock)
    text2 = (tmp_path / ".tess/tess.lock").read_text(encoding="utf-8")
    assert rp.lock_projection(text2) == rp.lock_projection(text) == eng._anchor_lock_projection(text2)
    lock["files"]["a.md"]["note"] = "x\ny " + "w " * 70                # not bookkeeping
    eng.save_lock(tmp_path, lock)
    text3 = (tmp_path / ".tess/tess.lock").read_text(encoding="utf-8")
    assert rp.lock_projection(text3) != rp.lock_projection(text)
    # a quoted value that swallows the next lines is one value, never a new key
    swallow = "schema: 1\nframework:\n  channel: 'stable\nframework: x'\n"
    assert eng._lock_load_text(swallow) == yaml.safe_load(swallow)
    assert set(rp.lock_strict_tree(swallow)) == {"schema", "framework"}
