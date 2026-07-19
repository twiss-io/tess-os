"""
Phase 0.2 — the CROSS-HARNESS TASK STORE (`tessctl tasks new|set|claim|
release|pull|render`), a sibling of the MISSION LEDGER region's own
`tessctl mission`/`retry` (tests/test_mission_ledger.py is this file's own
rigor precedent — same fixture shape, same "real CLI via subprocess, then
re-read the file back" discipline).

Coverage:
  * `tasks new` scaffolds a schema-valid task (dogfood `tessctl validate
    task`), id pattern + uniqueness, required --harness.
  * `tasks set` mutations: status transitions, owner/assignee (including
    clearing via ''), append-only depends_on/evidence/notes, rev/updated_at
    bump, --expected-rev CAS (conflict refuses with NO mutation; success
    after reload), --heartbeat requires an active claim.
  * `tasks claim`: unclaimed -> claim; same claimant -> heartbeat refresh
    (claimed_at unchanged); different claimant while live -> refused;
    different claimant while stale (--stale-after) -> reclaimed; --force
    steals a live claim; status auto-advances backlog/ready -> in_progress.
  * `tasks release`: wrong claimant refused (then --force succeeds); not
    claimed refused; --reason classifies completed/crashed/released.
  * `tasks pull` filters (status/owner/unclaimed/limit) and `tasks render`
    (BOARD.md GENERATED marker + correct per-status groupings).
  * Real concurrent writers (two actual OS processes) racing to mutate the
    SAME task never lose an update — the per-task flock proof.
  * C1 containment on task ids (mirrors `_validate_mission_id`'s own tests).
  * Phase 0.2 hardening (PR #113 review, issue #114):
    - Reid HIGH: `tasks set --heartbeat` refuses a forged (wrong- or
      missing-identity) heartbeat as TASK_NOT_CLAIMANT; a correct-identity
      heartbeat succeeds; --force overrides.
    - Reid MEDIUM: `tasks claim` with no explicit --uuid derives a STABLE
      default from (host, pid) — a re-claim by the SAME host:pid, still
      with no explicit --uuid, is recognized as the same claimant (a clean
      heartbeat), not a stranger stealing the claim.
"""

from __future__ import annotations

import datetime
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

from conftest import REPO_ROOT, ENGINE_SRC, MANIFEST_SRC

CONTRACTS_SRC = REPO_ROOT / "core" / "contracts"


@pytest.fixture
def troot(tmp_path):
    """A minimal synthetic root: tasks/claim/release/set/pull/render never
    touch owned_globs/never_touch/tess.lock — they only need
    tess.manifest.json (find_tess_root()) and the task.schema.json contract
    (cmd_validate's + the region's own dogfood-validate load path)."""
    root = tmp_path / "os"
    contracts_dir = root / "core" / "contracts"
    contracts_dir.mkdir(parents=True)
    # `tasks new|set|claim|release` all auto-log a ledger event on success
    # (_ledger_auto_log), so the ledger-event schema must be present
    # alongside task.schema.json even though this fixture is nominally
    # "task store only."
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


# ---------------------------------------------------------------------------
# `tasks new`
# ---------------------------------------------------------------------------

def test_tasks_new_scaffolds_valid_task_default_backlog(troot):
    task_id = _new(troot, "Fix login bug")
    path = _task_path(troot, task_id)
    assert path.exists()

    v = _run(troot, "validate", "task", str(path))
    assert v.returncode == 0, v.stdout + v.stderr

    obj = json.loads(path.read_text(encoding="utf-8"))
    assert obj["status"] == "backlog"
    assert obj["rev"] == 1
    assert obj["claim"] == {"host": None, "pid": None, "uuid": None, "claimed_at": None, "heartbeat_at": None}
    assert obj["evidence"] == [] and obj["notes"] == [] and obj["depends_on"] == []
    assert obj["created_by"] == {"harness": "claude-code", "session": None}


def test_tasks_new_id_pattern_and_uniqueness(troot):
    import re
    id1 = _new(troot, "Same Title")
    id2 = _new(troot, "Same Title")
    assert id1 != id2
    pattern = re.compile(r"^T-[0-9]{8}-[a-z0-9]+(-[a-z0-9]+)*-[0-9a-f]{4}$")
    assert pattern.fullmatch(id1) and pattern.fullmatch(id2)


def test_tasks_new_requires_harness_argparse(troot):
    r = _run(troot, "tasks", "new", "No harness given")
    assert r.returncode == 2  # argparse required= usage error


def test_tasks_new_empty_title_refused(troot):
    r = _run(troot, "tasks", "new", "!!! ???", "--harness", "claude-code")
    assert r.returncode != 0
    assert "no usable characters" in (r.stdout + r.stderr)


def test_tasks_new_logs_task_transition_ledger_event(troot):
    task_id = _new(troot, "Ledger check", harness="claude-code")
    month = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m")
    shard = troot / ".tess" / "state" / "ledger" / f"{month}.claude-code.jsonl"
    assert shard.exists()
    line = json.loads(shard.read_text(encoding="utf-8").splitlines()[0])
    assert line["event"] == "task_transition"
    assert line["refs"]["task"] == task_id
    assert "(none) -> backlog" in line["summary"]


# ---------------------------------------------------------------------------
# `tasks set`
# ---------------------------------------------------------------------------

def test_tasks_set_status_transition_bumps_rev_and_updated_at(troot):
    task_id = _new(troot)
    before = json.loads(_task_path(troot, task_id).read_text())
    time.sleep(1.1)  # ensure a distinguishable updated_at (second resolution)

    r = _run(troot, "tasks", "set", task_id, "--status", "ready", "--harness", "claude-code")
    assert r.returncode == 0, r.stdout + r.stderr

    after = json.loads(_task_path(troot, task_id).read_text())
    assert after["status"] == "ready"
    assert after["rev"] == before["rev"] + 1
    assert after["updated_at"] != before["updated_at"]
    assert after["created_at"] == before["created_at"]


def test_tasks_set_owner_assignee_set_and_clear(troot):
    task_id = _new(troot)
    r1 = _run(troot, "tasks", "set", task_id, "--owner", "Xavier", "--assignee", "Ada", "--harness", "h")
    assert r1.returncode == 0, r1.stdout + r1.stderr
    obj = json.loads(_task_path(troot, task_id).read_text())
    assert obj["owner"] == "Xavier" and obj["assignee"] == "Ada"

    r2 = _run(troot, "tasks", "set", task_id, "--owner", "", "--harness", "h")
    assert r2.returncode == 0, r2.stdout + r2.stderr
    obj2 = json.loads(_task_path(troot, task_id).read_text())
    assert obj2["owner"] is None
    assert obj2["assignee"] == "Ada"  # untouched


def test_tasks_set_depends_evidence_notes_append_only(troot):
    task_id = _new(troot)
    r = _run(
        troot, "tasks", "set", task_id,
        "--add-depends", "T-x", "--add-depends", "T-y",
        "--add-evidence", "logs/a.txt",
        "--add-note", "investigating", "--by", "ada",
        "--harness", "h",
    )
    assert r.returncode == 0, r.stdout + r.stderr
    obj = json.loads(_task_path(troot, task_id).read_text())
    assert obj["depends_on"] == ["T-x", "T-y"]
    assert obj["evidence"] == ["logs/a.txt"]
    assert len(obj["notes"]) == 1 and obj["notes"][0]["text"] == "investigating" and obj["notes"][0]["by"] == "ada"

    # A second call APPENDS, never replaces.
    r2 = _run(troot, "tasks", "set", task_id, "--add-evidence", "logs/b.txt", "--add-note", "found it", "--harness", "h")
    assert r2.returncode == 0, r2.stdout + r2.stderr
    obj2 = json.loads(_task_path(troot, task_id).read_text())
    assert obj2["evidence"] == ["logs/a.txt", "logs/b.txt"]
    assert len(obj2["notes"]) == 2

    # Adding an already-present dependency is a no-op (no duplicate).
    r3 = _run(troot, "tasks", "set", task_id, "--add-depends", "T-x", "--harness", "h")
    assert r3.returncode == 0, r3.stdout + r3.stderr
    obj3 = json.loads(_task_path(troot, task_id).read_text())
    assert obj3["depends_on"] == ["T-x", "T-y"]


def test_tasks_set_no_changes_specified_errors(troot):
    task_id = _new(troot)
    r = _run(troot, "tasks", "set", task_id, "--harness", "h")
    assert r.returncode != 0
    assert "no changes specified" in (r.stdout + r.stderr)


def test_tasks_set_heartbeat_requires_active_claim(troot):
    task_id = _new(troot)
    r = _run(troot, "tasks", "set", task_id, "--heartbeat", "--harness", "h")
    assert r.returncode != 0
    assert "no active claim" in (r.stdout + r.stderr)


# ---------------------------------------------------------------------------
# Reid HIGH (PR #113 review, issue #114): `tasks set --heartbeat` claimant-
# identity check — a forged (wrong- or missing-identity) heartbeat is a
# forgeable liveness signal that would let anyone with the task id renew a
# DIFFERENT claimant's claim-lease, defeating `--stale-after` reclaim.
# ---------------------------------------------------------------------------

def test_tasks_set_heartbeat_forged_identity_refused(troot):
    task_id = _new(troot)
    _run(troot, "tasks", "claim", task_id, "--host", "h1", "--pid", "111", "--uuid", "u1", "--harness", "a")
    before = json.loads(_task_path(troot, task_id).read_text())

    forged = _run(
        troot, "tasks", "set", task_id, "--heartbeat",
        "--host", "h2", "--pid", "222", "--uuid", "u2", "--harness", "b",
    )
    assert forged.returncode != 0
    assert "TASK_NOT_CLAIMANT" in (forged.stdout + forged.stderr)
    unchanged = json.loads(_task_path(troot, task_id).read_text())
    assert unchanged == before, "a refused forged heartbeat must not mutate the claim at all"


def test_tasks_set_heartbeat_missing_identity_refused(troot):
    """The ORIGINAL bug: no --host/--pid/--uuid at all used to succeed
    unconditionally. It must now be refused exactly like a wrong identity —
    "no identity supplied" is not evidence of claimant-hood either."""
    task_id = _new(troot)
    _run(troot, "tasks", "claim", task_id, "--host", "h1", "--pid", "111", "--uuid", "u1", "--harness", "a")
    before = json.loads(_task_path(troot, task_id).read_text())

    r = _run(troot, "tasks", "set", task_id, "--heartbeat", "--harness", "b")
    assert r.returncode != 0
    assert "TASK_NOT_CLAIMANT" in (r.stdout + r.stderr)
    unchanged = json.loads(_task_path(troot, task_id).read_text())
    assert unchanged == before


def test_tasks_set_heartbeat_correct_identity_succeeds(troot):
    task_id = _new(troot)
    _run(troot, "tasks", "claim", task_id, "--host", "h1", "--pid", "111", "--uuid", "u1", "--harness", "a")
    before = json.loads(_task_path(troot, task_id).read_text())
    time.sleep(1.1)

    r = _run(
        troot, "tasks", "set", task_id, "--heartbeat",
        "--host", "h1", "--pid", "111", "--uuid", "u1", "--harness", "a",
    )
    assert r.returncode == 0, r.stdout + r.stderr
    after = json.loads(_task_path(troot, task_id).read_text())
    assert after["claim"]["heartbeat_at"] != before["claim"]["heartbeat_at"]
    assert after["claim"]["claimed_at"] == before["claim"]["claimed_at"]
    assert after["claim"]["host"] == "h1" and after["claim"]["uuid"] == "u1"


def test_tasks_set_heartbeat_force_overrides_wrong_identity(troot):
    task_id = _new(troot)
    _run(troot, "tasks", "claim", task_id, "--host", "h1", "--pid", "111", "--uuid", "u1", "--harness", "a")
    before = json.loads(_task_path(troot, task_id).read_text())
    time.sleep(1.1)

    r = _run(
        troot, "tasks", "set", task_id, "--heartbeat", "--force",
        "--host", "h2", "--pid", "222", "--uuid", "u2", "--harness", "b",
    )
    assert r.returncode == 0, r.stdout + r.stderr
    after = json.loads(_task_path(troot, task_id).read_text())
    # --force refreshes the heartbeat but never silently reassigns the claim
    # itself — only `tasks claim --force` (an explicit steal) does that.
    assert after["claim"]["host"] == "h1" and after["claim"]["uuid"] == "u1"
    assert after["claim"]["heartbeat_at"] != before["claim"]["heartbeat_at"]


# Reid-LOW (#115 review, closed here): `_cmd_tasks_set` used to classify the
# auto-logged ledger event with exact STRING equality —
# `changes == ["heartbeat refreshed"]` — which only ever matched the
# same-claimant wording. A --force/non-claimant heartbeat's own `changes`
# entry reads "heartbeat refreshed (forced, non-claimant identity)" instead,
# so it silently fell through to the generic `task_transition` bucket,
# losing its heartbeat-ness in the accountability trail.
def test_tasks_set_heartbeat_forced_still_logs_as_heartbeat_event(troot):
    task_id = _new(troot, harness="claude-code")
    _run(troot, "tasks", "claim", task_id, "--host", "h1", "--pid", "111", "--uuid", "u1", "--harness", "claude-code")

    r = _run(
        troot, "tasks", "set", task_id, "--heartbeat", "--force",
        "--host", "h2", "--pid", "222", "--uuid", "u2", "--harness", "claude-code",
    )
    assert r.returncode == 0, r.stdout + r.stderr

    v = _run(troot, "log", "view", "--task", task_id, "--json")
    events = json.loads(v.stdout)
    assert events[-1]["event"] == "heartbeat", (
        "a forced/non-claimant heartbeat must still be logged under `heartbeat`, "
        "never silently reclassified as `task_transition`"
    )
    assert "forced" in events[-1]["summary"]


def test_tasks_set_heartbeat_clean_still_logs_as_heartbeat_event(troot):
    """Regression guard for the fix above: a same-claimant (clean) heartbeat
    must still classify as `heartbeat` too — the fix must not have narrowed
    the previously-working case while fixing the forced one."""
    task_id = _new(troot, harness="claude-code")
    _run(troot, "tasks", "claim", task_id, "--host", "h1", "--pid", "111", "--uuid", "u1", "--harness", "claude-code")
    time.sleep(1.1)

    r = _run(
        troot, "tasks", "set", task_id, "--heartbeat",
        "--host", "h1", "--pid", "111", "--uuid", "u1", "--harness", "claude-code",
    )
    assert r.returncode == 0, r.stdout + r.stderr

    v = _run(troot, "log", "view", "--task", task_id, "--json")
    events = json.loads(v.stdout)
    assert events[-1]["event"] == "heartbeat"
    assert "forced" not in events[-1]["summary"]


def test_tasks_set_unknown_task_refused(troot):
    r = _run(troot, "tasks", "set", "T-nope", "--status", "ready", "--harness", "h")
    assert r.returncode != 0
    assert "no such task" in (r.stdout + r.stderr)


def test_tasks_set_expected_rev_conflict_no_mutation_then_reload_and_retry(troot):
    task_id = _new(troot)  # rev 1
    r1 = _run(troot, "tasks", "set", task_id, "--status", "ready", "--harness", "h")
    assert r1.returncode == 0  # now rev 2
    before = json.loads(_task_path(troot, task_id).read_text())
    assert before["rev"] == 2

    # A caller that read rev=1 earlier tries to CAS against a now-stale rev.
    conflict = _run(troot, "tasks", "set", task_id, "--status", "in_progress",
                     "--expected-rev", "1", "--harness", "h")
    assert conflict.returncode != 0
    assert "TASK_CAS_CONFLICT" in (conflict.stdout + conflict.stderr)
    unchanged = json.loads(_task_path(troot, task_id).read_text())
    assert unchanged == before, "a CAS conflict must not mutate the file at all"

    # Reload (rev=2) and retry with the correct expectation -> succeeds.
    retry = _run(troot, "tasks", "set", task_id, "--status", "in_progress",
                 "--expected-rev", "2", "--harness", "h")
    assert retry.returncode == 0, retry.stdout + retry.stderr
    final = json.loads(_task_path(troot, task_id).read_text())
    assert final["status"] == "in_progress" and final["rev"] == 3


# ---------------------------------------------------------------------------
# `tasks claim` / `tasks release`
# ---------------------------------------------------------------------------

def test_tasks_claim_then_heartbeat_reclaim_by_same_claimant(troot):
    task_id = _new(troot)
    r1 = _run(troot, "tasks", "claim", task_id, "--host", "h1", "--pid", "111",
              "--uuid", "u1", "--harness", "claude-code")
    assert r1.returncode == 0, r1.stdout + r1.stderr
    obj = json.loads(_task_path(troot, task_id).read_text())
    assert obj["status"] == "in_progress"
    assert obj["claim"] == {
        "host": "h1", "pid": 111, "uuid": "u1",
        "claimed_at": obj["claim"]["claimed_at"], "heartbeat_at": obj["claim"]["heartbeat_at"],
    }
    claimed_at_1 = obj["claim"]["claimed_at"]

    time.sleep(1.1)
    r2 = _run(troot, "tasks", "claim", task_id, "--host", "h1", "--pid", "111",
              "--uuid", "u1", "--harness", "claude-code")
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert "heartbeat" in r2.stdout
    obj2 = json.loads(_task_path(troot, task_id).read_text())
    assert obj2["claim"]["claimed_at"] == claimed_at_1, "re-claim by the SAME claimant must not reset claimed_at"
    assert obj2["claim"]["heartbeat_at"] != obj["claim"]["heartbeat_at"]


# ---------------------------------------------------------------------------
# Reid MEDIUM (PR #113 review, issue #114): `tasks claim`'s default --uuid
# is now a STABLE uuid5 derived from (host, pid), not a fresh uuid4() per
# call — a same-process re-claim (no explicit --uuid, twice) must be
# recognized as the SAME claimant.
# ---------------------------------------------------------------------------

def test_tasks_claim_no_explicit_uuid_reclaim_by_same_host_pid_is_same_claimant(troot):
    task_id = _new(troot)
    r1 = _run(troot, "tasks", "claim", task_id, "--host", "h1", "--pid", "111", "--harness", "claude-code")
    assert r1.returncode == 0, r1.stdout + r1.stderr
    obj = json.loads(_task_path(troot, task_id).read_text())
    uuid_1 = obj["claim"]["uuid"]
    assert uuid_1  # a default was assigned
    claimed_at_1 = obj["claim"]["claimed_at"]

    time.sleep(1.1)
    r2 = _run(troot, "tasks", "claim", task_id, "--host", "h1", "--pid", "111", "--harness", "claude-code")
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert "heartbeat" in r2.stdout, (
        "a re-claim by the SAME host:pid, with no explicit --uuid, must be "
        "recognized as the same claimant (a clean heartbeat), not a stranger"
    )
    obj2 = json.loads(_task_path(troot, task_id).read_text())
    assert obj2["claim"]["uuid"] == uuid_1, "the default uuid must be STABLE across calls, not a fresh uuid4 each time"
    assert obj2["claim"]["claimed_at"] == claimed_at_1


def test_tasks_claim_default_uuid_differs_across_different_pids(troot):
    a = _new(troot, "Task A")
    b = _new(troot, "Task B")
    ra = _run(troot, "tasks", "claim", a, "--host", "h1", "--pid", "111", "--harness", "x")
    rb = _run(troot, "tasks", "claim", b, "--host", "h1", "--pid", "222", "--harness", "x")
    assert ra.returncode == 0 and rb.returncode == 0
    uuid_a = json.loads(_task_path(troot, a).read_text())["claim"]["uuid"]
    uuid_b = json.loads(_task_path(troot, b).read_text())["claim"]["uuid"]
    assert uuid_a != uuid_b


def test_tasks_claim_refused_when_live_claim_held_by_another(troot):
    task_id = _new(troot)
    _run(troot, "tasks", "claim", task_id, "--host", "h1", "--pid", "111", "--uuid", "u1", "--harness", "a")
    r = _run(troot, "tasks", "claim", task_id, "--host", "h2", "--pid", "222", "--uuid", "u2", "--harness", "b")
    assert r.returncode != 0
    assert "TASK_ALREADY_CLAIMED" in (r.stdout + r.stderr)
    obj = json.loads(_task_path(troot, task_id).read_text())
    assert obj["claim"]["host"] == "h1", "a refused claim attempt must not mutate the existing claim"


def test_tasks_claim_force_steals_a_live_claim(troot):
    task_id = _new(troot)
    _run(troot, "tasks", "claim", task_id, "--host", "h1", "--pid", "111", "--uuid", "u1", "--harness", "a")
    r = _run(troot, "tasks", "claim", task_id, "--host", "h2", "--pid", "222", "--uuid", "u2",
              "--harness", "b", "--force")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "reclaimed" in r.stdout
    obj = json.loads(_task_path(troot, task_id).read_text())
    assert obj["claim"]["host"] == "h2"


def test_tasks_claim_reclaims_after_stale_after_elapsed(troot):
    task_id = _new(troot)
    _run(troot, "tasks", "claim", task_id, "--host", "h1", "--pid", "111", "--uuid", "u1", "--harness", "a")
    r = _run(troot, "tasks", "claim", task_id, "--host", "h2", "--pid", "222", "--uuid", "u2",
              "--harness", "b", "--stale-after", "0")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "reclaimed" in r.stdout and "stale heartbeat" in r.stdout
    obj = json.loads(_task_path(troot, task_id).read_text())
    assert obj["claim"]["host"] == "h2"


def test_tasks_claim_auto_advances_status_only_from_backlog_or_ready(troot):
    task_id = _new(troot)
    _run(troot, "tasks", "set", task_id, "--status", "blocked", "--harness", "h")
    r = _run(troot, "tasks", "claim", task_id, "--host", "h1", "--pid", "1", "--uuid", "u1", "--harness", "a")
    assert r.returncode == 0, r.stdout + r.stderr
    obj = json.loads(_task_path(troot, task_id).read_text())
    assert obj["status"] == "blocked", "claiming a blocked task must not silently un-block it"


def test_tasks_release_wrong_claimant_refused_then_force_succeeds(troot):
    task_id = _new(troot)
    _run(troot, "tasks", "claim", task_id, "--host", "h1", "--pid", "111", "--uuid", "u1", "--harness", "a")

    refused = _run(troot, "tasks", "release", task_id, "--host", "h2", "--pid", "222", "--uuid", "u2", "--harness", "b")
    assert refused.returncode != 0
    assert "pass --force" in (refused.stdout + refused.stderr)

    forced = _run(troot, "tasks", "release", task_id, "--host", "h2", "--pid", "222", "--uuid", "u2",
                  "--harness", "b", "--force")
    assert forced.returncode == 0, forced.stdout + forced.stderr
    obj = json.loads(_task_path(troot, task_id).read_text())
    assert obj["claim"]["host"] is None


def test_tasks_release_not_claimed_refused(troot):
    task_id = _new(troot)
    r = _run(troot, "tasks", "release", task_id, "--host", "h1", "--pid", "1", "--uuid", "u1", "--harness", "a")
    assert r.returncode != 0
    assert "is not currently claimed" in (r.stdout + r.stderr)


@pytest.mark.parametrize("reason,expected_event", [
    ("completed", "completed"), ("crashed", "crashed"), (None, "release"),
])
def test_tasks_release_reason_classifies_ledger_event(troot, reason, expected_event):
    task_id = _new(troot, harness="claude-code")
    _run(troot, "tasks", "claim", task_id, "--host", "h1", "--pid", "1", "--uuid", "u1", "--harness", "claude-code")
    args = ["tasks", "release", task_id, "--host", "h1", "--pid", "1", "--uuid", "u1", "--harness", "claude-code"]
    if reason:
        args += ["--reason", reason]
    r = _run(troot, *args)
    assert r.returncode == 0, r.stdout + r.stderr

    v = _run(troot, "log", "view", "--task", task_id, "--json")
    events = json.loads(v.stdout)
    assert events[-1]["event"] == expected_event


# ---------------------------------------------------------------------------
# `tasks pull` / `tasks render`
# ---------------------------------------------------------------------------

def test_tasks_pull_filters(troot):
    a = _new(troot, "Task A", owner="Xavier")
    b = _new(troot, "Task B", owner="Jo")
    _run(troot, "tasks", "set", b, "--status", "ready", "--harness", "h")

    r_owner = _run(troot, "tasks", "pull", "--owner", "Xavier", "--json")
    ids = {t["id"] for t in json.loads(r_owner.stdout)}
    assert ids == {a}

    r_status = _run(troot, "tasks", "pull", "--status", "ready", "--json")
    ids2 = {t["id"] for t in json.loads(r_status.stdout)}
    assert ids2 == {b}

    r_unclaimed = _run(troot, "tasks", "pull", "--unclaimed", "--json")
    ids3 = {t["id"] for t in json.loads(r_unclaimed.stdout)}
    assert ids3 == {a, b}

    _run(troot, "tasks", "claim", a, "--host", "h1", "--pid", "1", "--uuid", "u1", "--harness", "x")
    r_unclaimed2 = _run(troot, "tasks", "pull", "--unclaimed", "--json")
    ids4 = {t["id"] for t in json.loads(r_unclaimed2.stdout)}
    assert ids4 == {b}


def test_tasks_render_board_generated_marker_and_groupings(troot):
    a = _new(troot, "Backlog task")
    b = _new(troot, "Done task")
    _run(troot, "tasks", "set", b, "--status", "done", "--harness", "h")

    r = _run(troot, "tasks", "render")
    assert r.returncode == 0, r.stdout + r.stderr
    board = (troot / ".tess" / "state" / "tasks" / "BOARD.md").read_text(encoding="utf-8")
    assert "GENERATED by `tessctl tasks render`" in board
    assert "do not hand-edit" in board
    assert f"`{a}`" in board.split("## Backlog")[1].split("## Ready")[0]
    assert f"`{b}`" in board.split("## Done")[1].split("## Cancelled")[0]


# ---------------------------------------------------------------------------
# Real concurrency — two ACTUAL OS processes racing to mutate the same task.
# ---------------------------------------------------------------------------

def test_concurrent_set_calls_never_lose_an_update(troot):
    task_id = _new(troot)
    p1 = subprocess.Popen(
        [sys.executable, str(troot / ".tess" / "bin" / "tessctl"), "tasks", "set", task_id,
         "--add-note", "note from writer A", "--harness", "a"],
        cwd=str(troot), env={**os.environ, "TESS_ROOT": str(troot)},
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    p2 = subprocess.Popen(
        [sys.executable, str(troot / ".tess" / "bin" / "tessctl"), "tasks", "set", task_id,
         "--add-note", "note from writer B", "--harness", "b"],
        cwd=str(troot), env={**os.environ, "TESS_ROOT": str(troot)},
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    out1, err1 = p1.communicate(timeout=30)
    out2, err2 = p2.communicate(timeout=30)
    assert p1.returncode == 0, out1 + err1
    assert p2.returncode == 0, out2 + err2

    obj = json.loads(_task_path(troot, task_id).read_text())
    texts = {n["text"] for n in obj["notes"]}
    assert texts == {"note from writer A", "note from writer B"}, (
        "both concurrent writers' notes must survive — a lost update means "
        "the per-task flock failed to serialize the two read-modify-writes"
    )
    assert obj["rev"] == 3  # 1 (new) + 2 successful set calls, none lost


# ---------------------------------------------------------------------------
# C1 containment — mirrors _validate_mission_id's own test coverage.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_id", ["../escape", "/etc/passwd", "..", "."])
def test_task_id_containment_rejects_traversal(troot, bad_id):
    r = _run(troot, "tasks", "set", bad_id, "--status", "ready", "--harness", "h")
    assert r.returncode != 0
    assert "C1 containment" in (r.stdout + r.stderr) or "must be a single path component" in (r.stdout + r.stderr) or "absolute paths are not allowed" in (r.stdout + r.stderr)


# ---------------------------------------------------------------------------
# Lint (engine-level, no subprocess) — _lint_task
# ---------------------------------------------------------------------------

def _valid_task_instance(task_id="T-20260719-x-aaaa"):
    return {
        "id": task_id, "title": "x", "status": "backlog", "owner": None, "assignee": None,
        "claim": {"host": None, "pid": None, "uuid": None, "claimed_at": None, "heartbeat_at": None},
        "created_by": {"harness": "h", "session": None},
        "created_at": "2026-07-19T00:00:00Z", "updated_at": "2026-07-19T00:00:00Z",
        "rev": 1, "depends_on": [], "evidence": [], "notes": [],
    }


def test_lint_task_valid_instance_passes(engine):
    assert engine._lint_task(_valid_task_instance()) == []


def test_lint_task_partial_claim_flagged(engine):
    inst = _valid_task_instance()
    inst["claim"] = {"host": "h1", "pid": None, "uuid": None, "claimed_at": None, "heartbeat_at": None}
    violations = engine._lint_task(inst)
    assert any("partially-set claim" in v for v in violations)


def test_lint_task_self_dependency_flagged(engine):
    inst = _valid_task_instance("T-20260719-x-aaaa")
    inst["depends_on"] = ["T-20260719-x-aaaa"]
    violations = engine._lint_task(inst)
    assert any("lists itself as a dependency" in v for v in violations)


def test_lint_task_duplicate_dependency_flagged(engine):
    inst = _valid_task_instance()
    inst["depends_on"] = ["T-a", "T-a"]
    violations = engine._lint_task(inst)
    assert any("duplicate dependency" in v for v in violations)


def test_lint_task_empty_note_text_flagged(engine):
    inst = _valid_task_instance()
    inst["notes"] = [{"at": "2026-07-19T00:00:00Z", "by": "ada", "text": "   "}]
    violations = engine._lint_task(inst)
    assert any("empty note text" in v for v in violations)


def test_task_schema_rejects_missing_required_field(engine):
    schema = engine.load_contract_schema(REPO_ROOT, "task")
    inst = _valid_task_instance()
    del inst["claim"]
    base_dir = REPO_ROOT / "core" / "contracts"
    violations = engine.schema_validate(inst, schema, schema, base_dir)
    assert violations


def test_task_schema_rejects_bad_id_pattern(engine):
    schema = engine.load_contract_schema(REPO_ROOT, "task")
    inst = _valid_task_instance()
    inst["id"] = "not-a-valid-id"
    base_dir = REPO_ROOT / "core" / "contracts"
    violations = engine.schema_validate(inst, schema, schema, base_dir)
    assert violations
