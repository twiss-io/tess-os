"""Acceptance L8 (caps + indexes): over a cap is an error (exit 3, file
byte-identical), never a truncation; long lists page into brain/index/."""
import hashlib
import sys
from pathlib import Path

from fixtures.brain_learn import fxlib

sys.path.insert(0, str(Path(fxlib.REPO) / "scripts" / "brain"))
from brainlib import index, records  # noqa: E402
from brainlib.config import Config  # noqa: E402

SID = "cap00001-aaaa-4bbb-8ccc-000000000001"


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _prefs(cfg, n, width=250, kind="preference"):
    for i in range(n):
        rid = "%s-20260101-%04d-pref-%d" % (records.PREFIX[kind], i, i)
        meta = {"id": rid, "type": kind, "status": "active", "statement": ("Rule %03d " % i) + "x" * width,
                "source_quote": "q", "source_ref": "turns:1", "verified_at": "2026-01-01T00:%02d:00+08:00" % (i % 60),
                "confirmed": False}
        records.write(cfg, kind, cfg.brain / "profile", meta, {"quote": "q", "statement": meta["statement"]})


def test_promote_into_full_profile_exits_3_and_leaves_it_byte_identical(tmp_path):
    inst = Path(fxlib.make(str(tmp_path / "fx")))
    cfg = Config(inst)
    n = 1
    for margin, width in ((400, 250), (120, 5)):  # fill to just under 12 KiB
        while len(index.profile_text(cfg, records.all_records(cfg)).encode()) < 12 * 1024 - margin:
            rid = "P-20260101-0000-fill-%d" % n
            meta = {"id": rid, "type": "preference", "status": "active", "source_quote": "q",
                    "statement": "Rule %03d %s" % (n, "x" * width), "source_ref": "turns:1",
                    "verified_at": "2026-01-01T00:00:00+08:00"}
            records.write(cfg, "preference", cfg.brain / "profile", meta, {"quote": "q"})
            n += 1
    assert fxlib.cli(inst, "index").returncode == 0
    prof = inst / "brain/profile.md"
    before = sha(prof)
    assert 12 * 1024 - 120 <= len(prof.read_bytes()) <= 12 * 1024
    cdir = tmp_path / "claude"
    fxlib.claude_session(cdir / (SID + ".jsonl"), SID, [
        ("user", "From now on, always write every answer as a numbered list with a one line summary on top and "
                 "a sources section at the bottom, even for very short questions.")])
    r = fxlib.sync_dir(inst, cdir)
    assert r.returncode == 3, r.stdout
    assert "consolidate: brain-review --consolidate" in r.stdout
    assert sha(prof) == before
    assert not list((inst / "brain/profile").glob("P-*numbered*.md"))
    r = fxlib.cli(inst, "remember", "--no-sync", "--kind", "preference", "--quote",
                  "always write every answer as a numbered list")
    assert r.returncode == 3 and sha(prof) == before


def test_500_clients_start_here_within_budget_with_sub_indexes(tmp_path):
    inst = Path(fxlib.make(str(tmp_path / "fx")))
    for i in range(500):
        d = inst / ("brain/clients/c%03d" % i)
        d.mkdir(parents=True)
        (d / "AGENTS.md").write_text("---\nname: Client %03d\n---\n# START HERE: Client %03d\n" % (i, i))
    r = fxlib.cli(inst, "index")
    assert r.returncode == 0, r.stdout
    text = (inst / "brain/START-HERE.md").read_text()
    assert text.count("\n") <= 150 and len(text.encode()) <= 12288
    pages = sorted((inst / "brain/index").glob("entities-clients-*.md"))
    assert len(pages) == 13
    assert "Client 499" in pages[-1].read_text()
    assert fxlib.cli(inst, "lint").returncode == 0  # every client reachable through the pages


def test_learned_keeps_100_and_archives_the_rest(tmp_path):
    inst = Path(fxlib.make(str(tmp_path / "fx")))
    cfg = Config(inst)
    _prefs(cfg, 105, width=10)
    assert fxlib.cli(inst, "index").returncode == 0
    learned = (inst / "brain/learned.md").read_text()
    assert len([l for l in learned.splitlines() if l.startswith("- 2026")]) == 100
    arch = (inst / "brain/archive/learned-2026.md").read_text()
    assert len([l for l in arch.splitlines() if l.startswith("- 2026")]) == 5
    assert "archive/learned-2026.md" in learned


def test_hand_written_start_here_over_cap_is_refused(tmp_path):
    inst = Path(fxlib.make(str(tmp_path / "fx")))
    p = inst / "brain/START-HERE.md"
    p.write_text(p.read_text() + "".join("- hand-written line %d\n" % i for i in range(200)))
    before = sha(p)
    r = fxlib.cli(inst, "index")
    assert r.returncode == 3 and "START-HERE.md" in r.stdout and sha(p) == before


def test_long_decision_register_pages(tmp_path):
    inst = Path(fxlib.make(str(tmp_path / "fx")))
    cfg = Config(inst)
    for i in range(45):
        rid = "D-20260101-%04d-choice-%d" % (i, i)
        meta = {"id": rid, "type": "decision", "title": "Choice %d" % i, "status": "accepted",
                "source_quote": "q", "source_ref": "turns:1", "source_at": "2026-01-01T00:00:00+08:00",
                "verified_at": "2026-01-01T00:00:00+08:00"}
        records.write(cfg, "decision", cfg.brain / "decisions", meta, {"quote": "q", "title": meta["title"]})
    assert fxlib.cli(inst, "index").returncode == 0
    idx = (inst / "brain/decisions/INDEX.md").read_text()
    assert idx.count("page ") == 2 and len(idx.splitlines()) < 150
    assert len(list((inst / "brain/index").glob("decisions-active-*.md"))) == 2
