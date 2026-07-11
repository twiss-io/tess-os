"""
Atomic state-write mechanical fixes (Ada, framework reliability batch):

  * load_lock() surfaces a clear remediation message on corrupt/truncated
    tess.lock YAML instead of a raw traceback (previously only the
    all-whitespace/empty case was handled).
  * save_lock(), write_contract_instance_preserving_format(), and the
    mission-record FIRST-write path all now route through the same
    _atomic_write_bytes() primitive (temp sibling + os.replace) the engine
    already uses for framework->live writes (guarded_write) — instead of a
    plain Path.write_text(), which can leave a torn/truncated file on disk
    if the process dies mid-write.

Each write site is proven atomic the same way: monkeypatch os.replace to
raise partway through, then assert (a) a pre-existing file is left
byte-for-byte unchanged, (b) a brand-new target is never left half-written,
and (c) no leftover .tessctl_tmp_* temp file survives. If any of these call
sites regressed back to a raw write_text(), monkeypatching os.replace would
have NO effect and these assertions would fail — that's the point.
"""

from __future__ import annotations

import json
import os
import shutil

import pytest
import yaml

from conftest import REPO_ROOT, ENGINE_SRC, ns

CONTRACTS_SRC = REPO_ROOT / "core" / "contracts"


def _no_leftover_tmp(directory):
    return list(directory.glob(".tessctl_tmp_*")) == []


def _boom(*_a, **_kw):
    raise OSError("simulated crash mid os.replace")


# ---------------------------------------------------------------------------
# load_lock — corrupt YAML -> clear remediation, not a raw traceback
# ---------------------------------------------------------------------------

def test_load_lock_corrupt_yaml_gives_remediation_not_traceback(project):
    project.add("conductor/a.md", "alpha\n")
    project.write()
    lock_path = project.root / ".tess" / "tess.lock"
    # A torn write: valid-looking YAML up to a point, then an unterminated
    # flow sequence — yaml.safe_load raises a ParserError (YAMLError
    # subclass), distinct from the already-handled "empty file" case.
    lock_path.write_bytes(b"schema: 1\nframework:\n  track: v2\nfiles: [a, b\n")

    with pytest.raises(SystemExit) as ei:
        project.mod.load_lock(project.root)
    msg = str(ei.value)
    assert "corrupt" in msg.lower()
    assert "rollback" in msg.lower()


def test_load_lock_empty_file_still_handled_as_before(project):
    """Regression guard: the pre-existing empty-file case must still work
    (only YAMLError handling is new)."""
    project.add("conductor/a.md", "alpha\n")
    project.write()
    lock_path = project.root / ".tess" / "tess.lock"
    lock_path.write_text("", encoding="utf-8")

    with pytest.raises(SystemExit) as ei:
        project.mod.load_lock(project.root)
    assert "empty" in str(ei.value).lower()


# ---------------------------------------------------------------------------
# save_lock — atomic
# ---------------------------------------------------------------------------

def test_save_lock_routes_through_atomic_write(project, monkeypatch):
    project.add("conductor/a.md", "alpha\n")
    lock = project.write()
    lock_path = project.root / ".tess" / "tess.lock"
    original = lock_path.read_bytes()

    monkeypatch.setattr(project.mod.os, "replace", _boom)
    with pytest.raises(OSError):
        project.mod.save_lock(project.root, lock)

    # Original tess.lock survives byte-for-byte — no torn write landed.
    assert lock_path.read_bytes() == original
    assert _no_leftover_tmp(lock_path.parent)


def test_save_lock_round_trips_correctly_when_not_interrupted(project):
    project.add("conductor/a.md", "alpha\n")
    lock = project.write()
    lock["framework"]["version"] = "9.9.9"
    project.mod.save_lock(project.root, lock)
    reloaded = project.mod.load_lock(project.root)
    assert reloaded["framework"]["version"] == "9.9.9"


# ---------------------------------------------------------------------------
# write_contract_instance_preserving_format — atomic, all 3 formats
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("suffix,dump", [
    (".json", lambda d: json.dumps(d)),
    (".yaml", lambda d: yaml.safe_dump(d)),
])
def test_write_contract_instance_atomic_json_yaml(engine, tmp_path, monkeypatch, suffix, dump):
    path = tmp_path / f"instance{suffix}"
    original = {"id": "x", "name": "original"}
    path.write_text(dump(original), encoding="utf-8")
    original_bytes = path.read_bytes()

    monkeypatch.setattr(engine.os, "replace", _boom)
    with pytest.raises(OSError):
        engine.write_contract_instance_preserving_format(path, {"id": "x", "name": "tampered"})

    assert path.read_bytes() == original_bytes
    assert _no_leftover_tmp(tmp_path)


def test_write_contract_instance_atomic_md(engine, tmp_path, monkeypatch):
    path = tmp_path / "instance.md"
    original_text = "---\nid: x\nname: original\n---\n\nbody text\n"
    path.write_text(original_text, encoding="utf-8")

    monkeypatch.setattr(engine.os, "replace", _boom)
    with pytest.raises(OSError):
        engine.write_contract_instance_preserving_format(path, {"id": "x", "name": "tampered"})

    assert path.read_text(encoding="utf-8") == original_text
    assert _no_leftover_tmp(tmp_path)


def test_write_contract_instance_correct_when_not_interrupted(engine, tmp_path):
    path = tmp_path / "instance.json"
    engine.write_contract_instance_preserving_format(path, {"id": "x", "name": "v1"})
    assert json.loads(path.read_text(encoding="utf-8")) == {"id": "x", "name": "v1"}


# ---------------------------------------------------------------------------
# Mission-record FIRST write — atomic
# ---------------------------------------------------------------------------

@pytest.fixture
def mroot(tmp_path, engine):
    """Minimal synthetic root for mission-record commands (mirrors
    test_mission_ledger.py's mroot fixture)."""
    root = tmp_path / "os"
    contracts_dir = root / "core" / "contracts"
    contracts_dir.mkdir(parents=True)
    for fname in ("mission.schema.json", "retry.schema.json"):
        shutil.copy2(CONTRACTS_SRC / fname, contracts_dir / fname)
    (root / "tess.manifest.json").write_text(
        json.dumps({"schema": 1, "owned_globs": [], "never_touch": ["missions/**"]}),
        encoding="utf-8",
    )
    bin_dir = root / ".tess" / "bin"
    bin_dir.mkdir(parents=True)
    dst_engine = bin_dir / "tessctl"
    shutil.copy2(ENGINE_SRC, dst_engine)
    os.chmod(dst_engine, 0o755)
    return root


def test_mission_record_first_write_routes_through_atomic_write(mroot, engine, monkeypatch):
    """Regression: mission.md's FIRST write (brand-new mission) used to call
    Path.write_text() directly, bypassing atomicity. If it still did,
    monkeypatching os.replace to raise would have NO effect — the file
    would land on disk anyway. This proves the write now genuinely goes
    through os.replace: when replace fails, nothing is left on disk."""
    monkeypatch.setattr(engine.os, "replace", _boom)
    with pytest.raises(OSError):
        engine._cmd_mission_new(ns(name="Atomic Test Mission", by=None, outcome_type=None), mroot)

    mission_dirs = list((mroot / "missions").iterdir()) if (mroot / "missions").exists() else []
    assert len(mission_dirs) == 1, "mission dir may exist (mkdir happens first) but must hold no records"
    mission_dir = mission_dirs[0]
    assert not (mission_dir / "mission.md").exists()
    assert not (mission_dir / "mission.json").exists()
    assert _no_leftover_tmp(mission_dir)


def test_mission_record_first_write_correct_when_not_interrupted(mroot, engine):
    engine._cmd_mission_new(ns(name="Clean Mission", by=None, outcome_type=None), mroot)
    mission_dirs = list((mroot / "missions").iterdir())
    assert len(mission_dirs) == 1
    mission_dir = mission_dirs[0]
    md = mission_dir / "mission.md"
    js = mission_dir / "mission.json"
    assert md.exists() and js.exists()

    v_md = engine.load_contract_instance(md)
    v_js = engine.load_contract_instance(js)
    assert v_md == v_js
    assert v_md["name"] == "Clean Mission"
