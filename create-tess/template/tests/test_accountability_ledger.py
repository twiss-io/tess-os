"""
Phase 0.2 — the hash-chained, append-only ACCOUNTABILITY LEDGER
(`tessctl log append|view|verify`), a sibling of the TASK STORE
(tests/test_task_store.py) and of the MISSION LEDGER region's typed-retry
ledger (tests/test_mission_ledger.py).

Coverage:
  * `log append`: genesis prev_hash for a shard's first event, chaining
    (event N's prev_hash == event N-1's hash), unknown event/empty summary
    refused, task-scoped events require a non-null --task (lint), a
    task-independent event (dispatch/session_open/session_close) does not.
  * Sharding: per calendar month AND per origin — two origins never share a
    shard file; corrupting one shard never affects another's `log verify`.
  * `log view`: filters (task/mission/since) and returns events sorted by ts
    across shards.
  * `log verify`: OK on a clean chain; detects a hash-content tamper; detects
    a prev_hash break (line removed/reordered).
  * Schema-level: ledger-event.schema.json rejects a malformed hash/prev_hash
    pattern; `_lint_ledger_event` is exercised directly (engine-level).
  * Phase 0.2 hardening (Cyra M1, PR #113 review — issue #114): per-event
    `seq` is monotonic/gapless per shard; every append writes a co-located
    `.tip` sidecar and upserts the ledger-wide `.registry.json`; `log
    verify` cross-checks the tail it finds against both, so a removed TAIL
    line (undetectable by a pure prev_hash walk) and a deleted WHOLE shard
    (undiscoverable by directory-globbing alone) are both DETECTED, not
    silently reported OK. A dedicated engine-level test also proves the
    `seq` check itself catches a gap a self-consistent (recomputed) hash
    chain alone would not.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO_ROOT, ENGINE_SRC

CONTRACTS_SRC = REPO_ROOT / "core" / "contracts"


@pytest.fixture
def lroot(tmp_path):
    root = tmp_path / "os"
    contracts_dir = root / "core" / "contracts"
    contracts_dir.mkdir(parents=True)
    shutil.copy2(CONTRACTS_SRC / "ledger-event.schema.json", contracts_dir / "ledger-event.schema.json")
    (root / "tess.manifest.json").write_text(
        json.dumps({"schema": 1, "owned_globs": [], "never_touch": [".tess/state/**"]}),
        encoding="utf-8",
    )
    bin_dir = root / ".tess" / "bin"
    bin_dir.mkdir(parents=True)
    dst_engine = bin_dir / "tessctl"
    shutil.copy2(ENGINE_SRC, dst_engine)
    os.chmod(dst_engine, 0o755)
    return root


def _run(root, *args, input_text=None):
    env = {**os.environ, "TESS_ROOT": str(root)}
    return subprocess.run(
        [sys.executable, str(root / ".tess" / "bin" / "tessctl"), *args],
        cwd=str(root), env=env, capture_output=True, text=True, input=input_text,
    )


def _append(root, origin="ada", event="dispatch", summary="did a thing", **kw):
    args = ["log", "append", "--origin", origin, "--event", event, "--summary", summary]
    for k, v in kw.items():
        args += [f"--{k.replace('_', '-')}", str(v)]
    return _run(root, *args)


def _shard_path(root, origin, when=None):
    import datetime
    when = when or datetime.datetime.now(datetime.timezone.utc)
    return root / ".tess" / "state" / "ledger" / f"{when.strftime('%Y-%m')}.{origin}.jsonl"


def _tip_path(root, origin, when=None):
    return _shard_path(root, origin, when).with_name(_shard_path(root, origin, when).name + ".tip")


def _registry_path(root):
    return root / ".tess" / "state" / "ledger" / ".registry.json"


# ---------------------------------------------------------------------------
# append + hash chain
# ---------------------------------------------------------------------------

def test_append_first_event_has_genesis_prev_hash(lroot):
    r = _append(lroot, origin="ada", event="dispatch", summary="dispatched Ada", harness="tess")
    assert r.returncode == 0, r.stdout + r.stderr
    shard = _shard_path(lroot, "ada")
    line = json.loads(shard.read_text(encoding="utf-8").splitlines()[0])
    assert line["prev_hash"] == "0" * 64
    assert line["seq"] == 0
    assert len(line["hash"]) == 64 and all(c in "0123456789abcdef" for c in line["hash"])


def test_append_chains_prev_hash_to_prior_events_hash(lroot):
    _append(lroot, origin="ada", event="dispatch", summary="first", harness="tess")
    _append(lroot, origin="ada", event="dispatch", summary="second", harness="tess")
    lines = [json.loads(l) for l in _shard_path(lroot, "ada").read_text().splitlines()]
    assert len(lines) == 2
    assert lines[1]["prev_hash"] == lines[0]["hash"]
    assert lines[0]["hash"] != lines[1]["hash"]
    assert [l["seq"] for l in lines] == [0, 1]


# ---------------------------------------------------------------------------
# Phase 0.2 hardening (Cyra M1, PR #113 review) — seq + .tip sidecar +
# ledger-wide .registry.json, and the tail-truncation / whole-shard-deletion
# detection they exist to enable.
# ---------------------------------------------------------------------------

def test_append_writes_tip_sidecar_matching_last_event(lroot):
    _append(lroot, origin="ada", event="dispatch", summary="first", harness="tess")
    _append(lroot, origin="ada", event="dispatch", summary="second", harness="tess")
    lines = [json.loads(l) for l in _shard_path(lroot, "ada").read_text().splitlines()]
    tip = json.loads(_tip_path(lroot, "ada").read_text(encoding="utf-8"))
    assert tip == {"seq": 1, "count": 2, "hash": lines[-1]["hash"]}


def test_append_upserts_ledger_wide_registry(lroot):
    _append(lroot, origin="ada", event="dispatch", summary="a1", harness="ada")
    _append(lroot, origin="codex", event="dispatch", summary="c1", harness="codex")
    _append(lroot, origin="ada", event="dispatch", summary="a2", harness="ada")
    registry = json.loads(_registry_path(lroot).read_text(encoding="utf-8"))
    ada_lines = [json.loads(l) for l in _shard_path(lroot, "ada").read_text().splitlines()]
    codex_lines = [json.loads(l) for l in _shard_path(lroot, "codex").read_text().splitlines()]
    assert registry["shards"][_shard_path(lroot, "ada").name] == {
        "seq": 1, "count": 2, "hash": ada_lines[-1]["hash"],
    }
    assert registry["shards"][_shard_path(lroot, "codex").name] == {
        "seq": 0, "count": 1, "hash": codex_lines[-1]["hash"],
    }


def test_verify_detects_tail_truncation_of_last_line(lroot):
    """Removing the LAST line leaves every REMAINING line's own prev_hash
    link to its predecessor perfectly intact — a pure hash-chain walk alone
    would report this shard OK. The .tip sidecar + registry cross-check is
    what actually catches it (Cyra M1)."""
    _append(lroot, origin="ada", event="dispatch", summary="one", harness="ada")
    _append(lroot, origin="ada", event="dispatch", summary="two", harness="ada")
    _append(lroot, origin="ada", event="dispatch", summary="three", harness="ada")
    shard = _shard_path(lroot, "ada")
    lines = shard.read_text().splitlines()
    shard.write_text("\n".join(lines[:-1]) + "\n")  # drop the TAIL line only

    r = _run(lroot, "log", "verify")
    assert r.returncode == 1
    assert "TAMPERED" in r.stdout
    assert "tail line" in r.stdout or "whole shard" in r.stdout


def test_verify_detects_whole_shard_emptied(lroot):
    """The file still exists (an empty stub) but every line was removed —
    same detection path as tail-truncation, just count 0 vs. the registered
    count."""
    _append(lroot, origin="ada", event="dispatch", summary="one", harness="ada")
    _append(lroot, origin="ada", event="dispatch", summary="two", harness="ada")
    shard = _shard_path(lroot, "ada")
    shard.write_text("")

    r = _run(lroot, "log", "verify")
    assert r.returncode == 1
    assert "TAMPERED" in r.stdout


def test_verify_detects_whole_shard_deletion(lroot):
    """The shard file (AND its .tip sidecar) are deleted outright — a
    directory glob of `*.jsonl` can never discover a file that simply is
    not there anymore. Only the ledger-wide registry (which is NOT
    co-located with any single shard) can still recall the shard existed."""
    _append(lroot, origin="ada", event="dispatch", summary="one", harness="ada")
    _append(lroot, origin="codex", event="dispatch", summary="c1", harness="codex")
    shard = _shard_path(lroot, "ada")
    shard.unlink()
    _tip_path(lroot, "ada").unlink()

    r = _run(lroot, "log", "verify")
    assert r.returncode == 1
    assert "MISSING" in r.stdout
    assert shard.name in r.stdout
    # the untouched origin is unaffected
    codex_line = next(l for l in r.stdout.splitlines() if _shard_path(lroot, "codex").name in l)
    assert codex_line.startswith("OK")


def test_verify_scoped_to_origin_still_reports_other_origins_missing_shard(lroot):
    _append(lroot, origin="ada", event="dispatch", summary="one", harness="ada")
    _append(lroot, origin="codex", event="dispatch", summary="c1", harness="codex")
    _shard_path(lroot, "codex").unlink()
    _tip_path(lroot, "codex").unlink()

    r_ada_only = _run(lroot, "log", "verify", "--origin", "ada")
    assert r_ada_only.returncode == 0, r_ada_only.stdout + r_ada_only.stderr

    r_codex_only = _run(lroot, "log", "verify", "--origin", "codex")
    assert r_codex_only.returncode == 1
    assert "MISSING" in r_codex_only.stdout


def test_ledger_verify_shard_seq_gap_detected_independently_of_hash_chain(lroot, engine):
    """A coherently-forged 2-line shard: prev_hash chain and every line's
    own hash are BOTH internally self-consistent (recomputed exactly as
    `_log_append_event` would), and no line was removed/reordered — the
    ONLY thing wrong is that `seq` jumps 0 -> 5 instead of 0 -> 1. Proves
    the `seq` contiguity check catches something the pre-existing
    prev_hash/hash checks alone would not (Cyra M1)."""
    shard = lroot / ".tess" / "state" / "ledger" / "2026-07.forge.jsonl"
    shard.parent.mkdir(parents=True, exist_ok=True)

    ev0 = {
        "ts": "2026-07-19T00:00:00Z",
        "actor": {"harness": "h", "model": None, "session": None, "persona": None},
        "event": "dispatch", "refs": {"task": None, "mission": None},
        "summary": "one", "seq": 0, "prev_hash": "0" * 64,
    }
    ev0["hash"] = engine._ledger_event_hash(ev0)
    ev1 = {
        "ts": "2026-07-19T00:00:01Z",
        "actor": {"harness": "h", "model": None, "session": None, "persona": None},
        "event": "dispatch", "refs": {"task": None, "mission": None},
        "summary": "two", "seq": 5, "prev_hash": ev0["hash"],  # gap: should be 1
    }
    ev1["hash"] = engine._ledger_event_hash(ev1)
    shard.write_text(json.dumps(ev0) + "\n" + json.dumps(ev1) + "\n", encoding="utf-8")

    ok, problems = engine._ledger_verify_shard(lroot, shard)
    assert ok is False
    assert any("seq mismatch" in p for p in problems)


# ---------------------------------------------------------------------------
# Legacy (seq-absent) shards — Cyra-LOW / Reid-MED (#115 review, closed in a
# later consolidated PR): a shard written before Phase 0.2's `seq` field
# existed has NO `seq` key on ANY of its lines at all — the exact on-disk
# shape a pre-#115 `log append` produced. That is an older shape THIS SAME
# engine wrote honestly, not tampering, and `log append` to it must not
# hard-refuse either.
# ---------------------------------------------------------------------------

def _hand_craft_legacy_shard(lroot, engine, origin="legacy"):
    """A coherent 2-line shard (valid prev_hash/hash chain, exactly as
    `_log_append_event` would have produced it before `seq` existed) with NO
    `seq` key on either line."""
    shard = _shard_path(lroot, origin)
    shard.parent.mkdir(parents=True, exist_ok=True)
    ev0 = {
        "ts": "2026-06-01T00:00:00Z",
        "actor": {"harness": "h", "model": None, "session": None, "persona": None},
        "event": "dispatch", "refs": {"task": None, "mission": None},
        "summary": "pre-#115 event one", "prev_hash": "0" * 64,
    }
    ev0["hash"] = engine._ledger_event_hash(ev0)
    ev1 = {
        "ts": "2026-06-01T00:00:01Z",
        "actor": {"harness": "h", "model": None, "session": None, "persona": None},
        "event": "dispatch", "refs": {"task": None, "mission": None},
        "summary": "pre-#115 event two", "prev_hash": ev0["hash"],
    }
    ev1["hash"] = engine._ledger_event_hash(ev1)
    shard.write_text(json.dumps(ev0) + "\n" + json.dumps(ev1) + "\n", encoding="utf-8")
    return shard


def test_verify_reports_legacy_seq_absent_shard_not_tampered(lroot, engine):
    shard = _hand_craft_legacy_shard(lroot, engine, origin="legacy")

    r = _run(lroot, "log", "verify")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "TAMPERED" not in r.stdout
    assert "LEGACY" in r.stdout
    assert shard.name in r.stdout


def test_append_to_legacy_shard_backfills_seq_instead_of_erroring(lroot, engine):
    shard = _hand_craft_legacy_shard(lroot, engine, origin="legacy")

    r = _append(lroot, origin="legacy", event="dispatch", summary="first seq-aware append", harness="h")
    assert r.returncode == 0, r.stdout + r.stderr

    lines = [json.loads(l) for l in shard.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 3
    assert "seq" not in lines[0] and "seq" not in lines[1], "pre-existing legacy lines are never rewritten"
    assert lines[2]["seq"] == 2, "backfilled from the shard's own line count (2 legacy lines already on disk)"
    assert lines[2]["prev_hash"] == lines[1]["hash"], (
        "the hash chain still links correctly across the legacy/versioned boundary"
    )

    # The now-mixed shard (2 legacy lines + 1 newly-versioned line) still
    # verifies clean — reported LEGACY (informational), never TAMPERED.
    v = _run(lroot, "log", "verify")
    assert v.returncode == 0, v.stdout + v.stderr
    assert "TAMPERED" not in v.stdout
    assert "LEGACY" in v.stdout


def test_append_unknown_event_rejected(lroot):
    r = _run(lroot, "log", "append", "--origin", "ada", "--event", "not-a-real-event", "--summary", "x")
    assert r.returncode == 2  # argparse choices= usage error


def test_append_empty_summary_rejected(lroot):
    r = _run(lroot, "log", "append", "--origin", "ada", "--event", "dispatch", "--summary", "   ")
    assert r.returncode != 0
    assert "must not be empty" in (r.stdout + r.stderr)


def test_append_task_scoped_event_without_task_ref_rejected(lroot):
    r = _append(lroot, origin="ada", event="claim", summary="claimed something", harness="tess")
    assert r.returncode != 0
    assert "task-scoped" in (r.stdout + r.stderr)


def test_append_task_scoped_event_with_task_ref_accepted(lroot):
    r = _append(lroot, origin="ada", event="claim", summary="claimed T-x", harness="tess", task="T-x")
    assert r.returncode == 0, r.stdout + r.stderr


def test_append_dispatch_event_task_ref_optional(lroot):
    r = _append(lroot, origin="ada", event="dispatch", summary="dispatched work", harness="tess")
    assert r.returncode == 0, r.stdout + r.stderr


def test_append_harness_defaults_to_origin(lroot):
    r = _append(lroot, origin="codex-runner", event="session_open", summary="session started")
    assert r.returncode == 0, r.stdout + r.stderr
    line = json.loads(_shard_path(lroot, "codex-runner").read_text().splitlines()[0])
    assert line["actor"]["harness"] == "codex-runner"


# ---------------------------------------------------------------------------
# sharding — per calendar month AND per origin
# ---------------------------------------------------------------------------

def test_two_origins_never_share_a_shard_file(lroot):
    _append(lroot, origin="ada", event="dispatch", summary="a1", harness="ada")
    _append(lroot, origin="codex", event="dispatch", summary="c1", harness="codex")
    assert _shard_path(lroot, "ada").exists()
    assert _shard_path(lroot, "codex").exists()
    assert _shard_path(lroot, "ada") != _shard_path(lroot, "codex")
    assert len(_shard_path(lroot, "ada").read_text().splitlines()) == 1
    assert len(_shard_path(lroot, "codex").read_text().splitlines()) == 1


def test_origin_is_slugified_for_the_shard_filename(lroot):
    r = _append(lroot, origin="Claude Code!!", event="dispatch", summary="x", harness="h")
    assert r.returncode == 0, r.stdout + r.stderr
    assert _shard_path(lroot, "claude-code").exists()


def test_corrupting_one_shard_does_not_affect_another(lroot):
    _append(lroot, origin="ada", event="dispatch", summary="a1", harness="ada")
    _append(lroot, origin="codex", event="dispatch", summary="c1", harness="codex")
    shard = _shard_path(lroot, "ada")
    obj = json.loads(shard.read_text().splitlines()[0])
    obj["summary"] = "TAMPERED"
    shard.write_text(json.dumps(obj) + "\n")

    r = _run(lroot, "log", "verify")
    assert r.returncode == 1
    lines = r.stdout.splitlines()
    ada_line = next(l for l in lines if l.split()[-1].startswith(_shard_path(lroot, "ada").name))
    codex_line = next(l for l in lines if l.split()[-1].startswith(_shard_path(lroot, "codex").name))
    assert ada_line.startswith("TAMPERED")
    assert codex_line.startswith("OK")


# ---------------------------------------------------------------------------
# view — filters + cross-shard sort
# ---------------------------------------------------------------------------

def test_view_filters_by_task_and_sorts_across_shards(lroot):
    _append(lroot, origin="a", event="claim", summary="claim x", harness="a", task="T-x")
    _append(lroot, origin="b", event="claim", summary="claim y", harness="b", task="T-y")
    _append(lroot, origin="a", event="release", summary="release x", harness="a", task="T-x")

    r = _run(lroot, "log", "view", "--task", "T-x", "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    events = json.loads(r.stdout)
    assert [e["event"] for e in events] == ["claim", "release"]
    assert all(e["refs"]["task"] == "T-x" for e in events)
    # sorted by ts (ascending)
    assert events[0]["ts"] <= events[1]["ts"]


def test_view_filters_by_mission(lroot):
    _append(lroot, origin="a", event="dispatch", summary="m1 work", harness="a", mission="M-1")
    _append(lroot, origin="a", event="dispatch", summary="m2 work", harness="a", mission="M-2")
    r = _run(lroot, "log", "view", "--mission", "M-1", "--json")
    events = json.loads(r.stdout)
    assert len(events) == 1 and events[0]["refs"]["mission"] == "M-1"


def test_view_no_matches_prints_friendly_message(lroot):
    r = _run(lroot, "log", "view", "--task", "T-does-not-exist")
    assert r.returncode == 0
    assert "no matching events" in r.stdout


# ---------------------------------------------------------------------------
# verify — clean chain OK, tamper + reordering both detected
# ---------------------------------------------------------------------------

def test_verify_ok_on_clean_chain(lroot):
    for i in range(5):
        _append(lroot, origin="ada", event="dispatch", summary=f"event {i}", harness="ada")
    r = _run(lroot, "log", "verify")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OK" in r.stdout


def test_verify_no_shards_is_a_clean_noop(lroot):
    r = _run(lroot, "log", "verify")
    assert r.returncode == 0
    assert "no ledger shards found" in r.stdout


def test_verify_detects_hash_content_tamper(lroot):
    _append(lroot, origin="ada", event="dispatch", summary="one", harness="ada")
    _append(lroot, origin="ada", event="dispatch", summary="two", harness="ada")
    shard = _shard_path(lroot, "ada")
    lines = shard.read_text().splitlines()
    obj = json.loads(lines[0])
    obj["summary"] = "TAMPERED"
    lines[0] = json.dumps(obj)
    shard.write_text("\n".join(lines) + "\n")

    r = _run(lroot, "log", "verify")
    assert r.returncode == 1
    assert "TAMPERED" in r.stdout
    assert "hash mismatch" in r.stdout


def test_verify_detects_prev_hash_break_from_line_removal(lroot):
    _append(lroot, origin="ada", event="dispatch", summary="one", harness="ada")
    _append(lroot, origin="ada", event="dispatch", summary="two", harness="ada")
    _append(lroot, origin="ada", event="dispatch", summary="three", harness="ada")
    shard = _shard_path(lroot, "ada")
    lines = shard.read_text().splitlines()
    del lines[1]  # remove the middle event — breaks the chain link
    shard.write_text("\n".join(lines) + "\n")

    r = _run(lroot, "log", "verify")
    assert r.returncode == 1
    assert "prev_hash mismatch" in r.stdout


def test_verify_scoped_to_origin(lroot):
    _append(lroot, origin="ada", event="dispatch", summary="a1", harness="ada")
    _append(lroot, origin="codex", event="dispatch", summary="c1", harness="codex")
    shard = _shard_path(lroot, "codex")
    obj = json.loads(shard.read_text().splitlines()[0])
    obj["summary"] = "TAMPERED"
    shard.write_text(json.dumps(obj) + "\n")

    r_ada_only = _run(lroot, "log", "verify", "--origin", "ada")
    assert r_ada_only.returncode == 0, r_ada_only.stdout + r_ada_only.stderr

    r_codex_only = _run(lroot, "log", "verify", "--origin", "codex")
    assert r_codex_only.returncode == 1


# ---------------------------------------------------------------------------
# Schema + lint (engine-level, no subprocess)
# ---------------------------------------------------------------------------

def _valid_ledger_event():
    return {
        "ts": "2026-07-19T00:00:00Z",
        "actor": {"harness": "ada", "model": None, "session": None, "persona": None},
        "event": "dispatch",
        "refs": {"task": None, "mission": None},
        "summary": "did a thing",
        "seq": 0,
        "prev_hash": "0" * 64,
        "hash": "1" * 64,
    }


def test_lint_ledger_event_valid_instance_passes(engine):
    assert engine._lint_ledger_event(_valid_ledger_event()) == []


def test_lint_ledger_event_task_scoped_without_ref_flagged(engine):
    inst = _valid_ledger_event()
    inst["event"] = "claim"
    violations = engine._lint_ledger_event(inst)
    assert any("task-scoped" in v for v in violations)


def test_ledger_event_schema_rejects_bad_hash_pattern(engine):
    schema = engine.load_contract_schema(REPO_ROOT, "ledger-event")
    inst = _valid_ledger_event()
    inst["hash"] = "not-hex"
    base_dir = REPO_ROOT / "core" / "contracts"
    violations = engine.schema_validate(inst, schema, schema, base_dir)
    assert violations


def test_ledger_event_schema_rejects_bad_event_enum(engine):
    schema = engine.load_contract_schema(REPO_ROOT, "ledger-event")
    inst = _valid_ledger_event()
    inst["event"] = "not-a-real-event"
    base_dir = REPO_ROOT / "core" / "contracts"
    violations = engine.schema_validate(inst, schema, schema, base_dir)
    assert violations


def test_ledger_event_schema_requires_seq(engine):
    schema = engine.load_contract_schema(REPO_ROOT, "ledger-event")
    inst = _valid_ledger_event()
    del inst["seq"]
    base_dir = REPO_ROOT / "core" / "contracts"
    violations = engine.schema_validate(inst, schema, schema, base_dir)
    assert violations


def test_ledger_event_schema_rejects_negative_seq(engine):
    schema = engine.load_contract_schema(REPO_ROOT, "ledger-event")
    inst = _valid_ledger_event()
    inst["seq"] = -1
    base_dir = REPO_ROOT / "core" / "contracts"
    violations = engine.schema_validate(inst, schema, schema, base_dir)
    assert violations


def test_ledger_event_hash_function_is_deterministic_and_prev_hash_sensitive(engine):
    a = {"ts": "x", "actor": {"harness": "h"}, "event": "dispatch", "refs": {}, "summary": "s", "prev_hash": "0" * 64}
    b = dict(a, prev_hash="1" * 64)
    assert engine._ledger_event_hash(a) == engine._ledger_event_hash(dict(a))
    assert engine._ledger_event_hash(a) != engine._ledger_event_hash(b)


def test_validate_ledger_event_cli(lroot, tmp_path):
    ev = _valid_ledger_event()
    ev["hash"] = "a" * 64
    p = tmp_path / "event.json"
    p.write_text(json.dumps(ev), encoding="utf-8")
    r = _run(lroot, "validate", "ledger-event", str(p))
    assert r.returncode == 0, r.stdout + r.stderr
