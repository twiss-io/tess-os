"""
Phase 0.4 (issue #125) — the external-harness-worker TASK LANE + HANDOFF
helper, built on top of the Phase 0.2/0.3 TASK STORE + ACCOUNTABILITY
LEDGER (tests/test_task_store.py is this file's own rigor precedent — same
fixture shape, same "real CLI via subprocess, then re-read the file back"
discipline).

Coverage:
  * `tasks new --lane <codex|claude-code|any>` earmarks `target_harness`;
    omitting `--lane` defaults to `any` (byte-for-byte the pre-lane
    behavior — the CREATED record and its `task_transition` ledger event
    are unchanged from before this field existed).
  * `tasks new --lane <non-any>` additionally logs a distinct `earmarked`
    ledger event; `--lane any` (or omitted) does not.
  * `tasks set --lane` re-earmarks; classifies as `earmarked` when it is
    the ONLY change a call makes, `task_transition` when combined with any
    other field change (mirrors `--heartbeat`'s own structural
    classification).
  * `tasks pull --lane <harness>` filters to that harness's own lane PLUS
    every `any`-earmarked task; omitting `--lane` applies no lane filter at
    all (existing `pull` behavior, unchanged).
  * `tasks claim` is UNCHANGED — it still records whichever `--harness` the
    claimant supplies, regardless of the task's `target_harness` (the lane
    is advisory routing via `pull`, never claim-time enforcement).
  * `tasks handoff <id> --harness <codex|claude-code>` earmarks the lane
    (idempotent — a no-op mutation if already earmarked that way), refuses
    `--harness any` (argparse choices), refuses an unknown task id, logs a
    `handoff` ledger event, and prints a copy-pasteable invocation
    containing the `tasks claim|set|release --harness <target>` recipe.
  * `_render_handoff_invocation` is a pure function of (record, target) —
    two calls with the same inputs produce byte-identical output
    (determinism check).
  * `tasks render` (BOARD.md) surfaces `[lane: <harness>]` for an earmarked
    task and omits it entirely for an unmarked (`any`) one.
  * The full ledger hash chain (`log verify`) still verifies clean after
    `earmarked`/`handoff` events are appended — no fork of the chain
    algorithm.
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
    """Mirrors tests/test_task_store.py's own `troot` fixture exactly — a
    minimal synthetic root with just enough (tess.manifest.json, the task +
    ledger-event contracts, the real engine) for `tasks`/`log` subcommands."""
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


# ---------------------------------------------------------------------------
# `tasks new --lane`
# ---------------------------------------------------------------------------

def test_new_default_lane_is_any_and_matches_pre_lane_behavior(troot):
    task_id = _new(troot, "No lane given")
    obj = json.loads(_task_path(troot, task_id).read_text())
    assert obj["target_harness"] == "any"

    v = _run(troot, "validate", "task", str(_task_path(troot, task_id)))
    assert v.returncode == 0, v.stdout + v.stderr

    events = _events(troot, task_id)
    assert len(events) == 1, "no --lane given -> exactly ONE ledger event (task_transition), no extra earmark"
    assert events[0]["event"] == "task_transition"


@pytest.mark.parametrize("lane", ["codex", "claude-code"])
def test_new_with_lane_earmarks_and_logs_earmarked_event(troot, lane):
    task_id = _new(troot, "Earmarked at creation", lane=lane, harness="claude-code")
    obj = json.loads(_task_path(troot, task_id).read_text())
    assert obj["target_harness"] == lane

    events = _events(troot, task_id)
    assert [e["event"] for e in events] == ["task_transition", "earmarked"]
    assert events[1]["refs"]["task"] == task_id
    assert lane in events[1]["summary"]
    assert "claude-code" in events[1]["summary"]  # who earmarked it


def test_new_explicit_lane_any_logs_no_extra_earmarked_event(troot):
    """--lane any is semantically a no-op earmark (matches the default) —
    must not produce a spurious `earmarked` line just because the flag was
    typed out explicitly."""
    task_id = _new(troot, "Explicit any", lane="any")
    events = _events(troot, task_id)
    assert len(events) == 1
    assert events[0]["event"] == "task_transition"


def test_new_rejects_unknown_lane_value(troot):
    r = _run(troot, "tasks", "new", "Bad lane", "--harness", "h", "--lane", "gpt5")
    assert r.returncode == 2  # argparse choices= usage error


def test_new_lane_persists_through_full_schema_validation(troot):
    task_id = _new(troot, "Schema check", lane="codex")
    v = _run(troot, "validate", "task", str(_task_path(troot, task_id)))
    assert v.returncode == 0, v.stdout + v.stderr


# ---------------------------------------------------------------------------
# `tasks set --lane`
# ---------------------------------------------------------------------------

def test_set_lane_alone_classifies_as_earmarked_event(troot):
    task_id = _new(troot)  # target_harness: any
    r = _run(troot, "tasks", "set", task_id, "--lane", "codex", "--harness", "h")
    assert r.returncode == 0, r.stdout + r.stderr
    obj = json.loads(_task_path(troot, task_id).read_text())
    assert obj["target_harness"] == "codex"

    events = _events(troot, task_id)
    assert events[-1]["event"] == "earmarked"
    assert "any" in events[-1]["summary"] and "codex" in events[-1]["summary"]


def test_set_lane_combined_with_other_field_classifies_as_task_transition(troot):
    task_id = _new(troot)
    r = _run(troot, "tasks", "set", task_id, "--lane", "codex", "--owner", "Xavier", "--harness", "h")
    assert r.returncode == 0, r.stdout + r.stderr
    obj = json.loads(_task_path(troot, task_id).read_text())
    assert obj["target_harness"] == "codex" and obj["owner"] == "Xavier"

    events = _events(troot, task_id)
    assert events[-1]["event"] == "task_transition"


def test_set_lane_unchanged_is_a_true_no_op(troot):
    task_id = _new(troot, lane="codex")
    before = json.loads(_task_path(troot, task_id).read_text())
    r = _run(troot, "tasks", "set", task_id, "--lane", "codex", "--harness", "h")
    assert r.returncode == 0, r.stdout + r.stderr
    after = json.loads(_task_path(troot, task_id).read_text())
    assert after == before, "re-setting the SAME lane must not bump rev or write anything"
    assert "no effective change" in r.stdout


def test_set_no_changes_specified_still_errors_without_lane(troot):
    """Regression guard: --lane joining the `set` flag family must not
    accidentally satisfy the 'at least one change' guard when omitted."""
    task_id = _new(troot)
    r = _run(troot, "tasks", "set", task_id, "--harness", "h")
    assert r.returncode != 0
    assert "no changes specified" in (r.stdout + r.stderr)


def test_set_rejects_unknown_lane_value(troot):
    task_id = _new(troot)
    r = _run(troot, "tasks", "set", task_id, "--lane", "gpt5", "--harness", "h")
    assert r.returncode == 2


# ---------------------------------------------------------------------------
# `tasks pull --lane`
# ---------------------------------------------------------------------------

def test_pull_lane_filters_to_own_lane_plus_any(troot):
    codex_task = _new(troot, "Codex work", lane="codex")
    claude_task = _new(troot, "Claude work", lane="claude-code")
    any_task = _new(troot, "Unmarked work")  # lane: any

    r = _run(troot, "tasks", "pull", "--lane", "codex", "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    ids = {t["id"] for t in json.loads(r.stdout)}
    assert ids == {codex_task, any_task}, "a codex lane pull sees codex-earmarked + unmarked, never claude-code-only"


def test_pull_no_lane_filter_is_unaffected(troot):
    """Omitting --lane entirely must return EXACTLY what `pull` always
    returned before this field existed — no implicit filtering."""
    a = _new(troot, "A", lane="codex")
    b = _new(troot, "B", lane="claude-code")
    c = _new(troot, "C")

    r = _run(troot, "tasks", "pull", "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    ids = {t["id"] for t in json.loads(r.stdout)}
    assert ids == {a, b, c}


def test_pull_lane_combines_with_unclaimed(troot):
    codex_task = _new(troot, "Codex work", lane="codex")
    _run(troot, "tasks", "claim", codex_task, "--host", "h1", "--pid", "1", "--uuid", "u1", "--harness", "codex")
    any_task = _new(troot, "Unmarked work")

    r = _run(troot, "tasks", "pull", "--lane", "codex", "--unclaimed", "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    ids = {t["id"] for t in json.loads(r.stdout)}
    assert ids == {any_task}, "a claimed codex-lane task must not show up in an --unclaimed pull, lane filter or not"


def test_pull_human_output_shows_lane_column(troot):
    _new(troot, "Codex work", lane="codex")
    r = _run(troot, "tasks", "pull")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "lane=codex" in r.stdout


# ---------------------------------------------------------------------------
# `tasks claim` is UNCHANGED — lane is advisory routing, never enforcement.
# ---------------------------------------------------------------------------

def test_claim_records_actor_harness_regardless_of_lane_mismatch(troot):
    """A task earmarked for `codex` can still be claimed by a `claude-code`
    actor — `tasks claim` records WHICHEVER harness the claimant supplies;
    the lane is a pull-time filter, not a claim-time gate. (Test sequence
    from the issue: earmark -> pull filters -> claim records harness ->
    handoff emits the correct invocation -> ledger records the chain.)"""
    task_id = _new(troot, lane="codex")
    r = _run(troot, "tasks", "claim", task_id, "--host", "h1", "--pid", "1", "--uuid", "u1", "--harness", "claude-code")
    assert r.returncode == 0, r.stdout + r.stderr
    obj = json.loads(_task_path(troot, task_id).read_text())
    assert obj["target_harness"] == "codex", "claim must never mutate the lane"

    events = _events(troot, task_id)
    assert events[-1]["event"] == "claim"
    assert events[-1]["actor"]["harness"] == "claude-code"


# ---------------------------------------------------------------------------
# `tasks handoff`
# ---------------------------------------------------------------------------

def test_handoff_earmarks_and_logs_handoff_event(troot):
    task_id = _new(troot, "Needs codex work")  # lane: any
    r = _run(troot, "tasks", "handoff", task_id, "--harness", "codex", "--by-harness", "claude-code")
    assert r.returncode == 0, r.stdout + r.stderr

    obj = json.loads(_task_path(troot, task_id).read_text())
    assert obj["target_harness"] == "codex"

    events = _events(troot, task_id)
    assert events[-1]["event"] == "handoff"
    assert events[-1]["actor"]["harness"] == "claude-code"
    assert "codex" in events[-1]["summary"]
    assert "lane earmarked" in events[-1]["summary"]


def test_handoff_default_by_harness_is_orchestrator(troot):
    task_id = _new(troot)
    r = _run(troot, "tasks", "handoff", task_id, "--harness", "codex")
    assert r.returncode == 0, r.stdout + r.stderr
    events = _events(troot, task_id)
    assert events[-1]["actor"]["harness"] == "orchestrator"


def test_handoff_idempotent_when_already_earmarked(troot):
    task_id = _new(troot, lane="codex")
    before = json.loads(_task_path(troot, task_id).read_text())

    r = _run(troot, "tasks", "handoff", task_id, "--harness", "codex")
    assert r.returncode == 0, r.stdout + r.stderr
    after = json.loads(_task_path(troot, task_id).read_text())
    assert after == before, "handoff to the ALREADY-earmarked harness must not bump rev"
    assert "already earmarked" in r.stdout

    events = _events(troot, task_id)
    assert events[-1]["event"] == "handoff", "a handoff event is still logged even when the lane was a no-op"


def test_handoff_rejects_any_as_a_target(troot):
    task_id = _new(troot)
    r = _run(troot, "tasks", "handoff", task_id, "--harness", "any")
    assert r.returncode == 2  # argparse choices= usage error — TASK_HANDOFF_LANES excludes "any"


def test_handoff_unknown_task_refused(troot):
    r = _run(troot, "tasks", "handoff", "T-nope", "--harness", "codex")
    assert r.returncode != 0
    assert "no such task" in (r.stdout + r.stderr)


def test_handoff_prints_copy_pasteable_invocation(troot):
    task_id = _new(troot, "Ship the widget")
    r = _run(troot, "tasks", "handoff", task_id, "--harness", "codex")
    assert r.returncode == 0, r.stdout + r.stderr
    out = r.stdout
    assert task_id in out
    assert f"tasks claim {task_id}" in out
    assert "--harness codex" in out
    assert f"tasks set {task_id}" in out
    assert f"tasks release {task_id}" in out
    assert "does not spawn" not in out  # the printed text is the invocation, not a disclaimer dump
    assert "AGENTS.md" in out


def test_handoff_json_output_includes_task_and_invocation(troot):
    task_id = _new(troot)
    r = _run(troot, "tasks", "handoff", task_id, "--harness", "claude-code", "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    assert payload["task"]["id"] == task_id
    assert payload["task"]["target_harness"] == "claude-code"
    assert "tasks claim" in payload["invocation"]


# ---------------------------------------------------------------------------
# `_render_handoff_invocation` — pure-function determinism (engine-level).
# ---------------------------------------------------------------------------

def test_render_handoff_invocation_is_deterministic(engine):
    record = {"id": "T-20260720-x-aaaa", "title": "Determinism check"}
    out1 = engine._render_handoff_invocation(record, "codex")
    out2 = engine._render_handoff_invocation(record, "codex")
    assert out1 == out2
    assert "T-20260720-x-aaaa" in out1
    assert "codex" in out1


def test_render_handoff_invocation_differs_by_target(engine):
    record = {"id": "T-20260720-x-aaaa", "title": "Determinism check"}
    codex_out = engine._render_handoff_invocation(record, "codex")
    claude_out = engine._render_handoff_invocation(record, "claude-code")
    assert codex_out != claude_out
    assert "--harness codex" in codex_out
    assert "--harness claude-code" in claude_out


# ---------------------------------------------------------------------------
# `tasks render` (BOARD.md) surfaces the lane.
# ---------------------------------------------------------------------------

def test_render_board_shows_lane_marker_for_earmarked_task_only(troot):
    earmarked = _new(troot, "Codex-only task", lane="codex")
    unmarked = _new(troot, "Anyone's task")

    r = _run(troot, "tasks", "render")
    assert r.returncode == 0, r.stdout + r.stderr
    board = (troot / ".tess" / "state" / "tasks" / "BOARD.md").read_text(encoding="utf-8")

    earmarked_line = next(line for line in board.splitlines() if earmarked in line)
    assert "[lane: codex]" in earmarked_line

    unmarked_line = next(line for line in board.splitlines() if unmarked in line)
    assert "[lane:" not in unmarked_line


# ---------------------------------------------------------------------------
# Full ledger chain integrity — earmarked/handoff events do not break
# `log verify` (no fork of the hash-chain algorithm).
# ---------------------------------------------------------------------------

def test_log_verify_clean_after_earmark_and_handoff_events(troot):
    task_id = _new(troot, "Full lifecycle", lane="codex")
    _run(troot, "tasks", "set", task_id, "--lane", "claude-code", "--harness", "h")
    _run(troot, "tasks", "handoff", task_id, "--harness", "codex", "--by-harness", "h")
    _run(troot, "tasks", "claim", task_id, "--host", "h1", "--pid", "1", "--uuid", "u1", "--harness", "codex")
    _run(troot, "tasks", "release", task_id, "--host", "h1", "--pid", "1", "--uuid", "u1",
         "--harness", "codex", "--reason", "completed")

    r = _run(troot, "log", "verify")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "TAMPERED" not in r.stdout


# ---------------------------------------------------------------------------
# Schema/lint — the new field's shape.
# ---------------------------------------------------------------------------

def test_task_schema_target_harness_enum_rejects_unknown_value(engine):
    schema = engine.load_contract_schema(REPO_ROOT, "task")
    inst = {
        "id": "T-20260719-x-aaaa", "title": "x", "status": "backlog",
        "owner": None, "assignee": None, "target_harness": "gpt5",
        "claim": {"host": None, "pid": None, "uuid": None, "claimed_at": None, "heartbeat_at": None},
        "created_by": {"harness": "h", "session": None},
        "created_at": "2026-07-19T00:00:00Z", "updated_at": "2026-07-19T00:00:00Z",
        "rev": 1, "depends_on": [], "evidence": [], "notes": [],
    }
    base_dir = REPO_ROOT / "core" / "contracts"
    violations = engine.schema_validate(inst, schema, schema, base_dir)
    assert violations


def test_task_schema_full_valid_instance_including_target_harness_passes(engine):
    schema = engine.load_contract_schema(REPO_ROOT, "task")
    inst = {
        "id": "T-20260719-x-aaaa", "title": "x", "status": "backlog",
        "owner": None, "assignee": None, "target_harness": "any",
        "claim": {"host": None, "pid": None, "uuid": None, "claimed_at": None, "heartbeat_at": None},
        "created_by": {"harness": "h", "session": None},
        "created_at": "2026-07-19T00:00:00Z", "updated_at": "2026-07-19T00:00:00Z",
        "rev": 1, "depends_on": [], "evidence": [], "notes": [],
    }
    base_dir = REPO_ROOT / "core" / "contracts"
    violations = engine.schema_validate(inst, schema, schema, base_dir)
    assert violations == []


def test_ledger_event_schema_accepts_earmarked_and_handoff(engine):
    schema = engine.load_contract_schema(REPO_ROOT, "ledger-event")
    base_dir = REPO_ROOT / "core" / "contracts"
    for event in ("earmarked", "handoff"):
        inst = {
            "ts": "2026-07-19T00:00:00Z",
            "actor": {"harness": "h", "model": None, "session": None, "persona": None},
            "event": event,
            "refs": {"task": "T-20260719-x-aaaa", "mission": None},
            "summary": "x",
            "seq": 0,
            "prev_hash": "0" * 64,
            "hash": "a" * 64,
        }
        violations = engine.schema_validate(inst, schema, schema, base_dir)
        assert violations == [], f"{event}: {violations}"
