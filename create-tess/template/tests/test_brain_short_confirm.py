"""v1.0.0 release integration, item b: friendly confirmations.

Every listing shows a short id and a ready-to-say reply ('Reply "confirm
D-0929-approve" to accept ...'). The operator may confirm with that short id;
the confirmation is still bound to the exact record, its shown content, the
operator's authenticated words and freshness. A short id that stops being
unique no longer counts.
"""
from __future__ import annotations

import sys
from pathlib import Path

from test_brain_provenance_adversarial import _cli, _material, _meta, _say

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "brain"))
from brainlib import confirm  # noqa: E402


def _review_item(inst, rid):
    rc, items = _cli(inst, "review")
    assert rc == 0
    return next(it for it in items if it["id"] == rid)


def test_review_shows_a_short_id_and_a_ready_to_say_reply(tmp_path):
    inst, _, _, _, rid = _material(tmp_path)
    it = _review_item(inst, rid)
    short = it["short_id"]
    assert short != rid and len(short) < len(rid) and short.startswith("D-" + rid[6:10] + "-")
    assert it["reply"].startswith('Reply "confirm %s" to accept' % short)


def test_short_id_confirms_the_shown_record(tmp_path):
    inst, cdir, path, rec, rid = _material(tmp_path)
    short = _review_item(inst, rid)["short_id"]
    _say(inst, cdir, path, "confirm %s" % short)
    rc, out = _cli(inst, "confirm", rid, "--quote", "confirm %s" % short)
    assert rc == 0 and out["status"] == "accepted", out
    assert _meta(rec)["status"] == "accepted"


def test_short_id_still_needs_fresh_unchanged_unreplayed_words(tmp_path):
    inst, cdir, path, rec, rid = _material(tmp_path)
    short = _review_item(inst, rid)["short_id"]
    rc, out = _cli(inst, "confirm", rid, "--quote", "confirm %s" % short)   # never said
    assert rc == 1 and _meta(rec)["status"] == "proposed", out
    _say(inst, cdir, path, "don't confirm %s" % short)
    rc, out = _cli(inst, "confirm", rid, "--quote", "don't confirm %s" % short)
    assert rc == 1 and _meta(rec)["status"] == "proposed", out
    _say(inst, cdir, path, "confirm %s" % short)
    text = rec.read_text()
    rec.write_text(text.replace("S$900", "S$9000", 1))
    rc, out = _cli(inst, "confirm", rid, "--quote", "confirm %s" % short)
    assert rc == 1 and "changed since it was shown" in out["error"], out
    rec.write_text(text)
    assert _cli(inst, "confirm", rid, "--quote", "confirm %s" % short)[0] == 0
    rc, out = _cli(inst, "confirm", rid, "--quote", "confirm %s" % short)
    assert rc == 1 and "replay" in out["error"], out


def test_a_short_id_that_became_ambiguous_no_longer_counts(tmp_path):
    inst, cdir, path, rec, rid = _material(tmp_path)
    short = _review_item(inst, rid)["short_id"]
    twin = rec.with_name(rec.name.replace(rid, rid[:11] + "2359" + rid[15:]))   # same day, same slug
    twin.write_text(rec.read_text().replace(rid, twin.stem))
    assert confirm.short_id(None, rid, [rid, twin.stem]) != short
    _say(inst, cdir, path, "confirm %s" % short)
    rc, out = _cli(inst, "confirm", rid, "--quote", "confirm %s" % short)
    assert rc == 1 and "naming %s exactly" % rid in out["error"], out
    assert _meta(rec)["status"] == "proposed"


def test_short_forms_pick_the_shortest_unique_spelling():
    a, b = "D-20260929-1412-pricing", "D-20260929-1500-pricing-model"
    assert confirm.short_id(None, a, [a, b]) == "D-0929-1412-pricing"
    # v1.0.0 item c: a single meaningful word first; "pricing" names both, so b is known by "model"
    assert confirm.short_id(None, b, [a, b]) == "D-0929-model"
    assert confirm.short_id(None, a, [a]) == "D-0929-pricing"
    assert confirm.short_id(None, "C-20260929-1200-01", ["C-20260929-1200-01"]) == "C-0929-01"
    # slug words inside a short id are never read as the operator's intent
    assert confirm.intent("confirm D-0929-do-not-use", "D-20260929-1412-do-not-use", "confirm",
                          "D-0929-do-not-use") == ""


def test_skills_tell_the_agent_to_relay_the_reply_line():
    root = Path(__file__).resolve().parents[1]
    for base in (".agents", ".claude"):
        review = (root / base / "skills/brain-review/SKILL.md").read_text(encoding="utf-8")
        assert "`reply` line word for word" in review and "short id" in review
        assert "FULL id" in review          # the tool is still called with the full id
        for skill in ("brain-decide", "brain-remember"):
            text = (root / base / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
            assert "`reply` line word for word" in text, (base, skill)
