"""
Phase 0.5 (issue #129) — the STRUCTURED STUCK-PACKET (`tessctl tasks block`),
built on top of the Phase 0.2 TASK STORE + ACCOUNTABILITY LEDGER
(tests/test_task_store.py / tests/test_task_lane_handoff.py are this file's
own rigor precedent — same fixture shape, same "real CLI via subprocess,
then re-read the file back" discipline).

`tasks block` is `tasks handoff`'s sibling: `handoff` = "here's a task, go
do it" (routes work forward); `block` = "I got stuck, here's everything you
need to continue" (captures a resumability packet at the point of failure).

Coverage:
  * `tasks block <id> --reason ... --summary ... --progress ... --needed
    ...` transitions status to `blocked` and records a structured packet
    (`reason`/`summary`/`progress`/`attempted`/`needed`/`blocked_at`/
    `blocked_by`); `--attempted` is repeatable and optional (defaults to
    an empty list); every one of `--reason`/`--summary`/`--progress`/
    `--needed` is required (argparse usage error otherwise); `--reason`
    is enum-constrained (argparse choices=).
  * A `blocked` ledger event is logged via the EXISTING `_ledger_auto_log`
    append path (task-scoped, correct actor/summary) — no fork of the
    chain algorithm.
  * Re-blocking an already-blocked task records a FRESH packet (a genuine
    new event, not a heartbeat) — `blocked_at` and the packet content are
    replaced, not merged, and a second `blocked` ledger line is appended.
  * Resumability: `tasks pull --status blocked` surfaces a stuck task
    (the accountability-list visibility Xavier's re-aimed vision calls
    for); `tasks claim` on a blocked task does NOT clear the packet
    (mirrors the pre-existing "claiming a blocked task does not silently
    un-block it" precedent); `tasks set|release --status
    <away-from-blocked>` DOES clear it, as an explicit side effect of that
    same write — logged under the SAME `task_transition` (or `earmarked`)
    event the status change itself produces, never a separate `unblocked`
    class.
  * Backward compatibility: a bare `tessctl tasks set --status blocked`
    (pre-#129, still fully supported) leaves `blocked: null` — the new
    `blocked` schema field/lint does not retroactively require a packet
    for every `blocked`-status task.
  * Legacy-record healing: a task record written before `blocked` existed
    (`.tess/state/tasks/**` is gitignored instance data, so a real
    deployed install can genuinely have these) has no such key at all;
    `_task_read` heals it to `null` in memory (mirrors the #126
    `target_harness` legacy-healing precedent), and `tasks block`/`set`
    against such a record succeeds and heals + logs correctly — no
    state/ledger divergence.
  * Schema/lint coverage: `task.schema.json`'s `blocked` field (null vs. a
    full BlockedPacket, `additionalProperties: false`, enum-constrained
    `reason`); `ledger-event.schema.json` accepts the new `blocked` event
    class; `_lint_task`'s new one-directional invariant (a packet implies
    `status == "blocked"`; the reverse is NOT required).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO_ROOT, ENGINE_SRC, MANIFEST_SRC

CONTRACTS_SRC = REPO_ROOT / "core" / "contracts"


@pytest.fixture
def troot(tmp_path):
    """Mirrors tests/test_task_store.py's / tests/test_task_lane_handoff.py's
    own `troot` fixture exactly — a minimal synthetic root with just enough
    (tess.manifest.json, the task + ledger-event contracts, the real engine)
    for `tasks`/`log` subcommands."""
    root = tmp_path / "os"
    contracts_dir = root / "core" / "contracts"
    contracts_dir.mkdir(parents=True)
    shutil.copy2(CONTRACTS_SRC / "task.schema.json", contracts_dir / "task.schema.json")
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


def _task_path(root, task_id):
    return root / ".tess" / "state" / "tasks" / f"{task_id}.json"


def _new(root, title="Fix login bug", **kw):
    args = ["tasks", "new", title, "--harness", kw.pop("harness", "claude-code")]
    for k, v in kw.items():
        args += [f"--{k.replace('_', '-')}", str(v)]
    r = _run(root, *args)
    assert r.returncode == 0, r.stdout + r.stderr
    task_id = r.stdout.splitlines()[0].split("—")[1].strip()
    return task_id


def _events(root, task_id):
    v = _run(root, "log", "view", "--task", task_id, "--json")
    assert v.returncode == 0, v.stdout + v.stderr
    return json.loads(v.stdout)


def _block(root, task_id, **kw):
    args = [
        "tasks", "block", task_id,
        "--reason", kw.pop("reason", "required_input"),
        "--summary", kw.pop("summary", "waiting on API credentials"),
        "--progress", kw.pop("progress", "endpoint wired, auth still 401s"),
        "--needed", kw.pop("needed", "a valid API key from the vendor"),
        "--harness", kw.pop("harness", "claude-code"),
    ]
    for attempt in kw.pop("attempted", None) or []:
        args += ["--attempted", attempt]
    for k, v in kw.items():
        args += [f"--{k.replace('_', '-')}", str(v)]
    return _run(root, *args)


# ---------------------------------------------------------------------------
# `tasks block` basics
# ---------------------------------------------------------------------------

def test_block_transitions_status_and_writes_packet(troot):
    task_id = _new(troot)
    r = _block(
        troot, task_id,
        reason="failed_dependency", summary="upstream service is down",
        progress="wrote the client, integration test fails on connect",
        needed="ops to restore the upstream service",
        attempted=["retried 3x", "checked DNS"],
    )
    assert r.returncode == 0, r.stdout + r.stderr

    obj = json.loads(_task_path(troot, task_id).read_text())
    assert obj["status"] == "blocked"
    packet = obj["blocked"]
    assert packet["reason"] == "failed_dependency"
    assert packet["summary"] == "upstream service is down"
    assert packet["progress"] == "wrote the client, integration test fails on connect"
    assert packet["needed"] == "ops to restore the upstream service"
    assert packet["attempted"] == ["retried 3x", "checked DNS"]
    assert packet["blocked_at"]
    assert packet["blocked_by"] == {"harness": "claude-code", "session": None}

    v = _run(troot, "validate", "task", str(_task_path(troot, task_id)))
    assert v.returncode == 0, v.stdout + v.stderr


def test_block_attempted_optional_defaults_to_empty_list(troot):
    task_id = _new(troot)
    r = _block(troot, task_id)
    assert r.returncode == 0, r.stdout + r.stderr
    obj = json.loads(_task_path(troot, task_id).read_text())
    assert obj["blocked"]["attempted"] == []


def test_block_records_session_and_persona(troot):
    task_id = _new(troot)
    r = _block(troot, task_id, session="sess-1", persona="Ada")
    assert r.returncode == 0, r.stdout + r.stderr
    obj = json.loads(_task_path(troot, task_id).read_text())
    assert obj["blocked"]["blocked_by"] == {"harness": "claude-code", "session": "sess-1"}
    events = _events(troot, task_id)
    assert events[-1]["actor"]["persona"] == "Ada"


@pytest.mark.parametrize("missing", ["--reason", "--summary", "--progress", "--needed"])
def test_block_requires_every_core_field(troot, missing):
    task_id = _new(troot)
    args = [
        "tasks", "block", task_id,
        "--reason", "required_input", "--summary", "s", "--progress", "p",
        "--needed", "n", "--harness", "claude-code",
    ]
    # Strip the flag under test (and its value) to prove it is required.
    idx = args.index(missing)
    args = args[:idx] + args[idx + 2:]
    r = _run(troot, *args)
    assert r.returncode == 2  # argparse required= usage error


def test_block_rejects_unknown_reason_value(troot):
    task_id = _new(troot)
    r = _block(troot, task_id, reason="not-a-real-reason")
    assert r.returncode == 2  # argparse choices= usage error


def test_block_json_output_includes_full_record(troot):
    task_id = _new(troot)
    r = _block(troot, task_id)
    assert r.returncode == 0, r.stdout + r.stderr
    r2 = _run(
        troot, "tasks", "block", task_id, "--reason", "gate", "--summary", "s2",
        "--progress", "p2", "--needed", "n2", "--harness", "h", "--json",
    )
    assert r2.returncode == 0, r2.stdout + r2.stderr
    payload = json.loads(r2.stdout)
    assert payload["id"] == task_id
    assert payload["blocked"]["reason"] == "gate"


def test_block_human_output_shows_reason_and_resume_hint(troot):
    task_id = _new(troot, "Ship the widget")
    r = _block(troot, task_id, needed="a signed-off design doc")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "required_input" in r.stdout
    assert "a signed-off design doc" in r.stdout
    assert "tasks pull --status blocked" in r.stdout
    assert f"tasks claim {task_id}" in r.stdout


def test_block_from_in_progress_records_status_transition_in_summary(troot):
    task_id = _new(troot)
    _run(troot, "tasks", "claim", task_id, "--host", "h1", "--pid", "1", "--uuid", "u1", "--harness", "a")
    obj = json.loads(_task_path(troot, task_id).read_text())
    assert obj["status"] == "in_progress"

    r = _block(troot, task_id)
    assert r.returncode == 0, r.stdout + r.stderr
    events = _events(troot, task_id)
    assert events[-1]["event"] == "blocked"
    assert "in_progress -> blocked" in events[-1]["summary"]


def test_block_unknown_task_refused(troot):
    r = _block(troot, "T-nope")
    assert r.returncode != 0
    assert "no such task" in (r.stdout + r.stderr)


def test_block_does_not_disturb_an_existing_claim(troot):
    """A claimed task can be blocked in place — `block` never touches
    `claim` (mirrors `tasks handoff`'s own claim-independence)."""
    task_id = _new(troot)
    _run(troot, "tasks", "claim", task_id, "--host", "h1", "--pid", "1", "--uuid", "u1", "--harness", "a")
    r = _block(troot, task_id)
    assert r.returncode == 0, r.stdout + r.stderr
    obj = json.loads(_task_path(troot, task_id).read_text())
    assert obj["claim"]["host"] == "h1", "block must not release an existing claim"


# ---------------------------------------------------------------------------
# Re-blocking — a genuinely NEW event, not a heartbeat/merge.
# ---------------------------------------------------------------------------

def test_reblock_replaces_the_packet_and_logs_a_second_event(troot):
    task_id = _new(troot)
    r1 = _block(troot, task_id, summary="first blocker", attempted=["tried A"])
    assert r1.returncode == 0, r1.stdout + r1.stderr
    rev_after_first = json.loads(_task_path(troot, task_id).read_text())["rev"]

    r2 = _block(
        troot, task_id, reason="gate", summary="second, different blocker",
        attempted=["tried A", "tried B"],
    )
    assert r2.returncode == 0, r2.stdout + r2.stderr

    obj = json.loads(_task_path(troot, task_id).read_text())
    assert obj["rev"] > rev_after_first, "a re-block with different content must be a real write, not a no-op"
    assert obj["blocked"]["reason"] == "gate"
    assert obj["blocked"]["summary"] == "second, different blocker"
    assert obj["blocked"]["attempted"] == ["tried A", "tried B"], "re-blocking REPLACES the packet, it does not merge/append"

    events = _events(troot, task_id)
    blocked_events = [e for e in events if e["event"] == "blocked"]
    assert len(blocked_events) == 2, "each `tasks block` call logs its OWN ledger event"


# ---------------------------------------------------------------------------
# Resumability — visibility (`pull --status blocked`), claim does not
# silently un-block, an explicit status departure clears the packet.
# ---------------------------------------------------------------------------

def test_pull_status_blocked_surfaces_stuck_work(troot):
    stuck = _new(troot, "Stuck task")
    fine = _new(troot, "Fine task")
    _block(troot, stuck)

    r = _run(troot, "tasks", "pull", "--status", "blocked", "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    ids = {t["id"] for t in json.loads(r.stdout)}
    assert ids == {stuck}, "pull --status blocked must surface exactly the blocked task(s)"
    assert fine not in ids


def test_claim_on_blocked_task_does_not_clear_the_packet(troot):
    task_id = _new(troot)
    _block(troot, task_id)
    r = _run(troot, "tasks", "claim", task_id, "--host", "h1", "--pid", "1", "--uuid", "u1", "--harness", "a")
    assert r.returncode == 0, r.stdout + r.stderr
    obj = json.loads(_task_path(troot, task_id).read_text())
    assert obj["status"] == "blocked", "claiming a blocked task must not silently un-block it (pre-existing precedent)"
    assert obj["blocked"] is not None, "claiming must not clear the stuck-packet either — that is an explicit `set --status` decision"


def test_set_status_away_from_blocked_clears_the_packet(troot):
    task_id = _new(troot)
    _block(troot, task_id)

    r = _run(troot, "tasks", "set", task_id, "--status", "in_progress", "--harness", "h")
    assert r.returncode == 0, r.stdout + r.stderr
    obj = json.loads(_task_path(troot, task_id).read_text())
    assert obj["status"] == "in_progress"
    assert obj["blocked"] is None, "moving status away from blocked must clear the stuck-packet as a side effect"
    assert "blocked: cleared" in r.stdout

    events = _events(troot, task_id)
    assert events[-1]["event"] == "task_transition", "clearing rides along in the SAME task_transition event, no separate 'unblocked' class"


def test_set_status_to_blocked_again_is_not_a_clear(troot):
    """Regression guard: the clearing logic must only fire when LEAVING
    `blocked`, never when the target status IS `blocked` (a no-op re-set)."""
    task_id = _new(troot)
    _block(troot, task_id)
    r = _run(troot, "tasks", "set", task_id, "--status", "blocked", "--harness", "h")
    assert r.returncode == 0, r.stdout + r.stderr
    obj = json.loads(_task_path(troot, task_id).read_text())
    assert obj["blocked"] is not None, "re-setting status to the SAME blocked value must not touch the packet"


def test_release_status_away_from_blocked_clears_the_packet(troot):
    task_id = _new(troot)
    _run(troot, "tasks", "claim", task_id, "--host", "h1", "--pid", "1", "--uuid", "u1", "--harness", "a")
    _block(troot, task_id)

    r = _run(
        troot, "tasks", "release", task_id, "--host", "h1", "--pid", "1", "--uuid", "u1",
        "--harness", "a", "--status", "review",
    )
    assert r.returncode == 0, r.stdout + r.stderr
    obj = json.loads(_task_path(troot, task_id).read_text())
    assert obj["status"] == "review"
    assert obj["blocked"] is None, "release --status away-from-blocked must clear the packet too (second write path, same invariant)"


def test_set_status_away_when_no_packet_present_is_a_plain_transition(troot):
    """A task in `blocked` status via the BARE pre-#129 path (no packet) —
    moving it away must behave exactly as it always did: no spurious
    'blocked: cleared' entry, since there was nothing to clear."""
    task_id = _new(troot)
    r0 = _run(troot, "tasks", "set", task_id, "--status", "blocked", "--harness", "h")
    assert r0.returncode == 0, r0.stdout + r0.stderr
    obj0 = json.loads(_task_path(troot, task_id).read_text())
    assert obj0["blocked"] is None

    r = _run(troot, "tasks", "set", task_id, "--status", "ready", "--harness", "h")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "blocked: cleared" not in r.stdout


# ---------------------------------------------------------------------------
# Backward compatibility — the bare pre-#129 `set --status blocked` path is
# untouched (mirrors tests/test_task_store.py's own coverage of this exact
# call, proven again here since this PR adds a schema/lint constraint that
# could plausibly have broken it).
# ---------------------------------------------------------------------------

def test_bare_set_status_blocked_leaves_packet_null(troot):
    task_id = _new(troot)
    r = _run(troot, "tasks", "set", task_id, "--status", "blocked", "--harness", "h")
    assert r.returncode == 0, r.stdout + r.stderr
    obj = json.loads(_task_path(troot, task_id).read_text())
    assert obj["status"] == "blocked"
    assert obj["blocked"] is None

    v = _run(troot, "validate", "task", str(_task_path(troot, task_id)))
    assert v.returncode == 0, v.stdout + v.stderr


# ---------------------------------------------------------------------------
# Legacy-record backward compatibility (mirrors #126's own dedicated
# section in tests/test_task_lane_handoff.py) — a task record written
# before `blocked` existed (`.tess/state/tasks/**` is gitignored instance
# data; a real deployed install genuinely has these).
# ---------------------------------------------------------------------------

def _legacy_task_record(task_id="T-20260601-legacy-task-abcd", **overrides) -> dict:
    """The exact post-#125/pre-#129 on-disk shape: has `target_harness`,
    does NOT have `blocked`."""
    record = {
        "id": task_id, "title": "Pre-existing legacy task", "status": "ready",
        "owner": "Xavier", "assignee": None, "target_harness": "any",
        "claim": {"host": None, "pid": None, "uuid": None, "claimed_at": None, "heartbeat_at": None},
        "created_by": {"harness": "claude-code", "session": None},
        "created_at": "2026-06-01T00:00:00Z", "updated_at": "2026-06-01T00:00:00Z",
        "rev": 1, "depends_on": [], "evidence": [], "notes": [],
    }
    record.update(overrides)
    return record


def _write_legacy_task(troot, task_id="T-20260601-legacy-task-abcd", **overrides) -> str:
    path = _task_path(troot, task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = _legacy_task_record(task_id, **overrides)
    assert "blocked" not in record, "fixture bug: this must be the PRE-#129 shape"
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return task_id


def test_legacy_record_on_disk_has_no_blocked_key(troot):
    task_id = _write_legacy_task(troot)
    raw = json.loads(_task_path(troot, task_id).read_text())
    assert "blocked" not in raw


def test_legacy_record_set_heals_blocked_field_and_logs_ledger_event(troot):
    task_id = _write_legacy_task(troot)
    r = _run(troot, "tasks", "set", task_id, "--status", "in_progress", "--harness", "h")
    assert r.returncode == 0, r.stdout + r.stderr

    obj = json.loads(_task_path(troot, task_id).read_text())
    assert obj["blocked"] is None, "legacy record must heal to a null packet"
    assert obj["status"] == "in_progress"

    events = _events(troot, task_id)
    assert len(events) == 1, "the mutation must be logged — no state/ledger divergence"


def test_legacy_record_block_heals_and_logs(troot):
    task_id = _write_legacy_task(troot)
    r = _block(troot, task_id)
    assert r.returncode == 0, r.stdout + r.stderr

    obj = json.loads(_task_path(troot, task_id).read_text())
    assert obj["target_harness"] == "any", "healed target_harness must survive the block write too"
    assert obj["blocked"]["reason"] == "required_input"
    assert obj["status"] == "blocked"

    events = _events(troot, task_id)
    assert len(events) == 1
    assert events[0]["event"] == "blocked"


def test_legacy_record_pull_heals_in_memory_without_writing_back(troot):
    task_id = _write_legacy_task(troot)
    before = _task_path(troot, task_id).read_text()

    r = _run(troot, "tasks", "pull", "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    ids = {t["id"] for t in json.loads(r.stdout)}
    assert task_id in ids

    after = _task_path(troot, task_id).read_text()
    assert after == before, "pull must never write back to a task record"


def test_write_locked_validate_before_write_leaves_disk_untouched_on_failure(engine, troot):
    """Engine-level proof (mirrors test_task_lane_handoff.py's own
    identically-named test): a mutate_fn producing an invalid `blocked`
    value must be refused with NOTHING persisted to disk."""
    task_id = _new(troot, "Ordering check")
    path = _task_path(troot, task_id)
    before_bytes = path.read_bytes()

    def bad_mutate(record):
        record["blocked"] = {"reason": "not-a-real-reason"}  # missing required subfields too
        return record

    with pytest.raises(engine.TaskError):
        engine._tasks_write_locked(troot, task_id, bad_mutate)

    after_bytes = path.read_bytes()
    assert after_bytes == before_bytes

    events = _events(troot, task_id)
    assert len(events) == 1 and events[0]["event"] == "task_transition"


# ---------------------------------------------------------------------------
# Schema/lint — the new field's shape (engine-level, no subprocess).
# ---------------------------------------------------------------------------

def _valid_task_instance(task_id="T-20260719-x-aaaa", blocked=None):
    return {
        "id": task_id, "title": "x", "status": "blocked" if blocked else "backlog",
        "owner": None, "assignee": None, "target_harness": "any",
        "claim": {"host": None, "pid": None, "uuid": None, "claimed_at": None, "heartbeat_at": None},
        "created_by": {"harness": "h", "session": None},
        "created_at": "2026-07-19T00:00:00Z", "updated_at": "2026-07-19T00:00:00Z",
        "rev": 1, "depends_on": [], "evidence": [], "notes": [], "blocked": blocked,
    }


def _valid_packet(**overrides):
    packet = {
        "reason": "required_input", "summary": "s", "progress": "p", "attempted": [],
        "needed": "n", "blocked_at": "2026-07-19T00:00:00Z",
        "blocked_by": {"harness": "h", "session": None},
    }
    packet.update(overrides)
    return packet


def test_task_schema_null_blocked_passes(engine):
    schema = engine.load_contract_schema(REPO_ROOT, "task")
    base_dir = REPO_ROOT / "core" / "contracts"
    violations = engine.schema_validate(_valid_task_instance(), schema, schema, base_dir)
    assert violations == []


def test_task_schema_full_blocked_packet_passes(engine):
    schema = engine.load_contract_schema(REPO_ROOT, "task")
    base_dir = REPO_ROOT / "core" / "contracts"
    inst = _valid_task_instance(blocked=_valid_packet())
    violations = engine.schema_validate(inst, schema, schema, base_dir)
    assert violations == []


def test_task_schema_missing_blocked_key_entirely_rejected(engine):
    schema = engine.load_contract_schema(REPO_ROOT, "task")
    base_dir = REPO_ROOT / "core" / "contracts"
    inst = _valid_task_instance()
    del inst["blocked"]
    violations = engine.schema_validate(inst, schema, schema, base_dir)
    assert violations


def test_task_schema_blocked_packet_rejects_unknown_reason(engine):
    schema = engine.load_contract_schema(REPO_ROOT, "task")
    base_dir = REPO_ROOT / "core" / "contracts"
    inst = _valid_task_instance(blocked=_valid_packet(reason="not-a-real-reason"))
    violations = engine.schema_validate(inst, schema, schema, base_dir)
    assert violations


def test_task_schema_blocked_packet_rejects_missing_subfield(engine):
    schema = engine.load_contract_schema(REPO_ROOT, "task")
    base_dir = REPO_ROOT / "core" / "contracts"
    packet = _valid_packet()
    del packet["needed"]
    inst = _valid_task_instance(blocked=packet)
    violations = engine.schema_validate(inst, schema, schema, base_dir)
    assert violations


def test_task_schema_blocked_packet_rejects_additional_property(engine):
    schema = engine.load_contract_schema(REPO_ROOT, "task")
    base_dir = REPO_ROOT / "core" / "contracts"
    inst = _valid_task_instance(blocked=_valid_packet(extra="nope"))
    violations = engine.schema_validate(inst, schema, schema, base_dir)
    assert violations


def test_ledger_event_schema_accepts_blocked(engine):
    schema = engine.load_contract_schema(REPO_ROOT, "ledger-event")
    base_dir = REPO_ROOT / "core" / "contracts"
    inst = {
        "ts": "2026-07-19T00:00:00Z",
        "actor": {"harness": "h", "model": None, "session": None, "persona": None},
        "event": "blocked",
        "refs": {"task": "T-20260719-x-aaaa", "mission": None},
        "summary": "x",
        "seq": 0,
        "prev_hash": "0" * 64,
        "hash": "a" * 64,
    }
    violations = engine.schema_validate(inst, schema, schema, base_dir)
    assert violations == []


def test_lint_task_packet_without_blocked_status_flagged(engine):
    """The new ONE-DIRECTIONAL invariant: a packet present implies
    status == 'blocked'. Catches a hand-edited/inconsistent record —
    normal engine writes (`tasks block`, and the clear-on-departure logic)
    never produce this combination themselves."""
    inst = _valid_task_instance(blocked=_valid_packet())
    inst["status"] = "in_progress"
    violations = engine._lint_task(inst)
    assert any("stuck-packet is set but status is" in v for v in violations)


def test_lint_task_blocked_status_without_packet_is_valid(engine):
    """The REVERSE is explicitly allowed — the pre-existing bare `set
    --status blocked` path (no packet) must not be flagged."""
    inst = _valid_task_instance()  # status backlog, blocked None
    inst["status"] = "blocked"
    assert engine._lint_task(inst) == []


def test_lint_task_full_blocked_instance_passes(engine):
    inst = _valid_task_instance(blocked=_valid_packet())
    assert engine._lint_task(inst) == []
