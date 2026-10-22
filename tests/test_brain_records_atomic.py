"""brainlib.records writes are atomic and never clobber (v1.0 code review, MEDIUM).

write() used `path.exists()` then `path.write_text()`: a check-then-write race
(two writers minting the same id both pass the check; the second silently
replaces the first) and a non-atomic write (a crash mid-write leaves a
truncated record that lint then flags as tampered). update_fields() rewrote in
place with the same truncation window. Now write() publishes a fully written
temp file with os.link (fails EEXIST, like O_EXCL) and update_fields() uses
oobe.state.atomic_write (temp file + os.replace).
"""
import os
import sys
from pathlib import Path

import pytest

from fixtures.brain_learn import fxlib

sys.path.insert(0, str(Path(fxlib.REPO) / "scripts" / "brain"))
from brainlib import records  # noqa: E402
from brainlib.config import Config  # noqa: E402

RID = "D-20260924-1405-atomic"


@pytest.fixture
def inst(tmp_path):
    return Path(fxlib.make(str(tmp_path / "fx")))


def _meta():
    return {"id": RID, "type": "decision", "title": "t", "status": "accepted",
            "source_quote": "let's go with Postgres", "source_at": "2026-09-24T14:05:00+08:00",
            "source_ref": "brain/journal/2026/09/24/1405-claude-11111111.md#L1"}


def _write(inst):
    return records.write(Config(inst), "decision", inst / "brain/decisions", _meta(), {"quote": "q"})


def _temps(d: Path):
    return [p.name for p in d.iterdir() if p.name.startswith(".tmp-")]


def test_write_refuses_an_existing_record_and_leaves_it_byte_identical(inst):
    rec = _write(inst)
    before = rec.path.read_bytes()
    with pytest.raises(FileExistsError, match="record exists"):
        _write(inst)
    assert rec.path.read_bytes() == before
    assert _temps(rec.path.parent) == []


def test_write_never_clobbers_a_file_that_appears_after_the_old_existence_check(inst, monkeypatch):
    # A racing writer lands its file between any exists() check and our write.
    # Simulate that by making exists() lie; publishing must still fail, not replace.
    d = inst / "brain/decisions"
    d.mkdir(parents=True, exist_ok=True)
    (d / (RID + ".md")).write_text("other writer\n")
    monkeypatch.setattr(records.Path, "exists", lambda self: False)
    with pytest.raises(FileExistsError):
        _write(inst)
    assert (d / (RID + ".md")).read_text() == "other writer\n"
    assert _temps(d) == []


def test_update_fields_is_atomic_when_the_replace_fails(inst, monkeypatch):
    rec = _write(inst)
    before = rec.path.read_bytes()

    def boom(*_a, **_k):
        raise OSError("disk full")
    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError, match="disk full"):
        records.update_fields(rec, {"title": "changed"})
    assert rec.path.read_bytes() == before, "a failed update must leave the old record intact"
    assert _temps(rec.path.parent) == []
    monkeypatch.undo()
    new = records.update_fields(rec, {"title": "changed"})
    assert new.meta["title"] == "changed" and new.body == rec.body
