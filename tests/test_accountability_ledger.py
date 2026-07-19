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


# ---------------------------------------------------------------------------
# append + hash chain
# ---------------------------------------------------------------------------

def test_append_first_event_has_genesis_prev_hash(lroot):
    r = _append(lroot, origin="ada", event="dispatch", summary="dispatched Ada", harness="tess")
    assert r.returncode == 0, r.stdout + r.stderr
    shard = _shard_path(lroot, "ada")
    line = json.loads(shard.read_text(encoding="utf-8").splitlines()[0])
    assert line["prev_hash"] == "0" * 64
    assert len(line["hash"]) == 64 and all(c in "0123456789abcdef" for c in line["hash"])


def test_append_chains_prev_hash_to_prior_events_hash(lroot):
    _append(lroot, origin="ada", event="dispatch", summary="first", harness="tess")
    _append(lroot, origin="ada", event="dispatch", summary="second", harness="tess")
    lines = [json.loads(l) for l in _shard_path(lroot, "ada").read_text().splitlines()]
    assert len(lines) == 2
    assert lines[1]["prev_hash"] == lines[0]["hash"]
    assert lines[0]["hash"] != lines[1]["hash"]


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
