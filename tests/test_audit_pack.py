"""
Goal I1 — the exportable, independently-verifiable AUDITOR PACK
(`tessctl audit export|verify`), a sibling of the ACCOUNTABILITY LEDGER
(tests/test_accountability_ledger.py) and the CROSS-HARNESS TASK STORE
(tests/test_task_store.py) it draws on.

Coverage:
  * Scope selection: exactly one of --task / --since|--until / --all is
    required; the wrong count of selectors is refused.
  * `audit export --task ID` includes only that task's ledger events
    (interleaved with OTHER tasks' events in the same shard), marks its
    shard(s) `export_kind: partial`, and best-effort-enriches `artifacts`
    with the live task record's own `evidence` list.
  * `audit export --all` includes every shard/event unfiltered and marks
    every shard `export_kind: full`.
  * `audit export --since/--until` filters by ts bounds (a time-range
    scope).
  * `--origin` narrows to one shard, combinable with any scope.
  * Per-action attribution: every exported event still carries its own
    actor/event/refs/summary/ts verbatim — nothing is summarized away.
  * Artifact-backed: `artifacts.tasks`/`artifacts.missions` are derived from
    `refs`; `artifacts.receipt_actions` from an embedded receipt's own
    `proposed_action.repo/ref/paths`.
  * `--receipt` embeds an already-shaped Agent Receipt verbatim after
    schema-validating it against agent-receipt.schema.json; an invalid
    shape, or a missing file, is refused with NO pack written.
  * `audit verify` on a clean pack: exit 0, using ONLY the pack's own
    bytes (no live .tess/state/ledger/ access — proven by verifying
    against a COPY of the pack after the source ledger is deleted).
  * `audit verify` on a partial (task/range-scoped) pack: a seq GAP between
    two included events (because an out-of-scope event sits between them)
    is reported OK, never TAMPERED.
  * `audit verify` fails closed on: a tampered event's content (hash
    mismatch), a broken prev_hash link between seq-ADJACENT included
    events, a seq gap inside a claimed `export_kind: full` shard, a
    tampered embedded receipt envelope or decision, a missing manifest,
    and a wrong `pack_schema`.
  * `--out` refuses to silently clobber a non-empty existing directory
    without `--force`; `audit verify` accepts either the pack directory or
    a direct manifest.json path.
  * Determinism: two exports of the identical scope over unchanged ledger
    state produce identical `shards`/`events`/`artifacts` content (modulo
    the necessarily-unique `pack_id`/`exported_at`).

PR #128 review fixes (Cyra 1 MEDIUM + 2 LOW, Reid 2 LOW — honesty/
credibility, fixed pre-merge since honesty IS this brick's whole value):
  * Cyra MEDIUM — tail-truncation of a `full`-scope shard's LAST event(s)
    is now DETECTED: each `full` shard embeds its own `.tip` sidecar (the
    same {count, hash} tail anchor `tessctl log verify` cross-checks a live
    shard against), and `audit verify` asserts it — dropping the tail
    without also forging a consistent `.tip` now fails closed.
  * Cyra LOW-MED — a pre-#115 seq-absent LEGACY event pair no longer false-
    positives as a "missing event"/TAMPERED; it verifies LEGACY/OK (hash
    chain still checked), mirroring `_ledger_verify_shard`'s own handling.
  * Cyra LOW — the `trust_boundary` disclosure block is no longer
    strippable: `audit verify` asserts it is present and matches the
    canonical text this pack's own receipt count would have produced.
  * Reid LOW — `exported_by.user` (the self-reported local OS username) is
    now disclosed in `trust_boundary` as exactly that: self-reported, not
    a cryptographic identity, redact before external sharing if a concern.
  * Reid LOW — `--receipt PATH` now refuses a symlink, a non-regular file
    (directory, device), or an empty file outright, closing the asymmetry
    with `_task_path`'s/`_validate_evidence_path`'s own path hygiene.
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
SCHEMA_FILES = (
    "ledger-event.schema.json",
    "task.schema.json",
    "agent-receipt.schema.json",
    "verdict.schema.json",
)


@pytest.fixture
def aroot(tmp_path):
    root = tmp_path / "os"
    contracts_dir = root / "core" / "contracts"
    contracts_dir.mkdir(parents=True)
    for name in SCHEMA_FILES:
        shutil.copy2(CONTRACTS_SRC / name, contracts_dir / name)
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


def _run(root, *args, cwd=None):
    env = {**os.environ, "TESS_ROOT": str(root)}
    return subprocess.run(
        [sys.executable, str(root / ".tess" / "bin" / "tessctl"), *args],
        cwd=str(cwd or root), env=env, capture_output=True, text=True,
    )


def _append(root, origin="ada", event="dispatch", summary="did a thing", **kw):
    args = ["log", "append", "--origin", origin, "--event", event, "--summary", summary]
    for k, v in kw.items():
        args += [f"--{k.replace('_', '-')}", str(v)]
    r = _run(root, *args)
    assert r.returncode == 0, r.stdout + r.stderr
    return r


def _new_task(root, title="A task", harness="ada"):
    r = _run(root, "tasks", "new", title, "--harness", harness, "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout)["id"]


def _export(root, out, *scope_args, receipts=None, force=False, origin=None):
    args = ["audit", "export", "--out", str(out), *scope_args]
    if origin:
        args += ["--origin", origin]
    for rp in (receipts or []):
        args += ["--receipt", str(rp)]
    if force:
        args.append("--force")
    return _run(root, *args)


def _verify(root, pack, json_out=False):
    args = ["audit", "verify", str(pack)]
    if json_out:
        args.append("--json")
    return _run(root, *args)


def _manifest(pack_dir):
    return json.loads((Path(pack_dir) / "manifest.json").read_text(encoding="utf-8"))


def _write_manifest(pack_dir, manifest):
    (Path(pack_dir) / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


# ---------------------------------------------------------------------------
# scope selection
# ---------------------------------------------------------------------------

def test_export_refuses_when_no_scope_given(aroot, tmp_path):
    r = _export(aroot, tmp_path / "pack")
    assert r.returncode != 0
    assert "choose exactly one scope" in (r.stdout + r.stderr)
    assert not (tmp_path / "pack").exists()


def test_export_refuses_when_multiple_scopes_given(aroot, tmp_path):
    r = _export(aroot, tmp_path / "pack", "--all", "--task", "T-x")
    assert r.returncode != 0
    assert "choose exactly one scope" in (r.stdout + r.stderr)


def test_export_since_and_until_together_count_as_one_range_scope(aroot, tmp_path):
    _append(aroot, event="dispatch", summary="one", harness="ada")
    r = _export(aroot, tmp_path / "pack", "--since", "2020-01-01T00:00:00Z", "--until", "2099-01-01T00:00:00Z")
    assert r.returncode == 0, r.stdout + r.stderr


# ---------------------------------------------------------------------------
# --task scope
# ---------------------------------------------------------------------------

def test_export_task_scope_includes_only_matching_events(aroot, tmp_path):
    tid = _new_task(aroot, "Build I1")
    _append(aroot, event="task_transition", summary="status change", harness="ada", task=tid)
    other_tid = "T-other-0000-aaaa"
    _append(aroot, event="dispatch", summary="unrelated ambient dispatch", harness="ada")

    pack = tmp_path / "pack"
    r = _export(aroot, pack, "--task", tid)
    assert r.returncode == 0, r.stdout + r.stderr
    manifest = _manifest(pack)
    assert manifest["scope"] == {"kind": "task", "task": tid, "since": None, "until": None, "origin": None}
    all_events = [e for s in manifest["shards"] for e in s["events"]]
    # the task-creation event + the explicit task_transition above; the
    # ambient unrelated dispatch (refs.task=None) must NOT appear.
    assert len(all_events) == 2
    assert all(e["refs"]["task"] == tid for e in all_events)
    assert manifest["counts"]["events"] == 2


def test_export_task_scope_marks_shard_partial(aroot, tmp_path):
    tid = _new_task(aroot, "Build I1")
    pack = tmp_path / "pack"
    r = _export(aroot, pack, "--task", tid)
    assert r.returncode == 0, r.stdout + r.stderr
    manifest = _manifest(pack)
    assert all(s["export_kind"] == "partial" for s in manifest["shards"])


def test_export_task_scope_enriches_artifacts_with_live_task_evidence(aroot, tmp_path):
    tid = _new_task(aroot, "Build I1")
    r = _run(aroot, "tasks", "set", tid, "--add-evidence", "docs/AUDIT_PACK_SPEC.md", "--harness", "claude-code")
    assert r.returncode == 0, r.stdout + r.stderr

    pack = tmp_path / "pack"
    r = _export(aroot, pack, "--task", tid)
    assert r.returncode == 0, r.stdout + r.stderr
    manifest = _manifest(pack)
    assert manifest["artifacts"]["task_record_evidence"] == ["docs/AUDIT_PACK_SPEC.md"]


def test_export_task_scope_for_unknown_task_id_is_a_clean_empty_pack(aroot, tmp_path):
    _append(aroot, event="dispatch", summary="ambient", harness="ada")
    pack = tmp_path / "pack"
    r = _export(aroot, pack, "--task", "T-does-not-exist-0000")
    assert r.returncode == 0, r.stdout + r.stderr
    manifest = _manifest(pack)
    assert manifest["counts"]["events"] == 0
    assert manifest["shards"] == []
    assert manifest["artifacts"]["task_record_evidence"] == []


# ---------------------------------------------------------------------------
# --all scope
# ---------------------------------------------------------------------------

def test_export_all_scope_marks_every_shard_full(aroot, tmp_path):
    _append(aroot, origin="ada", event="dispatch", summary="a1", harness="ada")
    _append(aroot, origin="codex", event="dispatch", summary="c1", harness="codex")
    pack = tmp_path / "pack"
    r = _export(aroot, pack, "--all")
    assert r.returncode == 0, r.stdout + r.stderr
    manifest = _manifest(pack)
    assert len(manifest["shards"]) == 2
    assert all(s["export_kind"] == "full" for s in manifest["shards"])
    assert manifest["counts"]["shards"] == 2


def test_export_all_scope_includes_every_event_unfiltered(aroot, tmp_path):
    for i in range(5):
        _append(aroot, event="dispatch", summary=f"event {i}", harness="ada")
    pack = tmp_path / "pack"
    r = _export(aroot, pack, "--all")
    assert r.returncode == 0, r.stdout + r.stderr
    manifest = _manifest(pack)
    assert manifest["counts"]["events"] == 5


# ---------------------------------------------------------------------------
# --since/--until (time-range) scope
# ---------------------------------------------------------------------------

def test_export_range_scope_filters_by_since_and_until(aroot, tmp_path):
    # append three events; hand-pick a since/until window around the middle one
    _append(aroot, event="dispatch", summary="e1", harness="ada")
    _append(aroot, event="dispatch", summary="e2", harness="ada")
    _append(aroot, event="dispatch", summary="e3", harness="ada")

    manifest_all = _manifest_from_export(aroot, tmp_path / "allscope", "--all")
    events = sorted(
        (e for s in manifest_all["shards"] for e in s["events"]), key=lambda e: e["ts"]
    )
    assert len(events) == 3
    since = events[1]["ts"]
    pack = tmp_path / "pack"
    r = _export(aroot, pack, "--since", since)
    assert r.returncode == 0, r.stdout + r.stderr
    manifest = _manifest(pack)
    scoped = [e for s in manifest["shards"] for e in s["events"]]
    assert all(e["ts"] >= since for e in scoped)
    assert len(scoped) >= 1


def _manifest_from_export(root, pack, *scope_args):
    r = _export(root, pack, *scope_args)
    assert r.returncode == 0, r.stdout + r.stderr
    return _manifest(pack)


# ---------------------------------------------------------------------------
# --origin filter
# ---------------------------------------------------------------------------

def test_export_origin_filter_restricts_to_one_shard(aroot, tmp_path):
    _append(aroot, origin="ada", event="dispatch", summary="a1", harness="ada")
    _append(aroot, origin="codex", event="dispatch", summary="c1", harness="codex")
    pack = tmp_path / "pack"
    r = _export(aroot, pack, "--all", origin="ada")
    assert r.returncode == 0, r.stdout + r.stderr
    manifest = _manifest(pack)
    assert len(manifest["shards"]) == 1
    assert manifest["shards"][0]["origin"] == "ada"


# ---------------------------------------------------------------------------
# per-action attribution + artifact-backed entries
# ---------------------------------------------------------------------------

def test_exported_events_carry_full_attribution_verbatim(aroot, tmp_path):
    tid = _new_task(aroot, "Build I1")
    pack = tmp_path / "pack"
    r = _export(aroot, pack, "--task", tid)
    assert r.returncode == 0, r.stdout + r.stderr
    manifest = _manifest(pack)
    event = manifest["shards"][0]["events"][0]
    assert set(event.keys()) == {"ts", "actor", "event", "refs", "summary", "seq", "prev_hash", "hash"}
    assert event["actor"]["harness"] == "ada"
    assert event["refs"]["task"] == tid
    assert event["event"] == "task_transition"


def test_manifest_artifacts_collects_task_and_mission_refs(aroot, tmp_path):
    _append(aroot, event="dispatch", summary="m work", harness="ada", mission="M-1")
    pack = tmp_path / "pack"
    r = _export(aroot, pack, "--all")
    assert r.returncode == 0, r.stdout + r.stderr
    manifest = _manifest(pack)
    assert "M-1" in manifest["artifacts"]["missions"]


def test_trust_boundary_states_unsigned_self_reported_and_completeness_limits(aroot, tmp_path):
    _append(aroot, event="dispatch", summary="e1", harness="ada")
    pack = tmp_path / "pack"
    r = _export(aroot, pack, "--all")
    assert r.returncode == 0, r.stdout + r.stderr
    manifest = _manifest(pack)
    tb = manifest["trust_boundary"]
    assert "UNSIGNED" in tb["ledger_integrity"]
    assert "non-repudiation" in tb["ledger_integrity"]
    assert "SELF-REPORTED" in tb["actor_identity"]
    assert "does NOT prove" in tb["completeness"]
    assert "empty verifier_keys/signoff_keys" in tb["key_ceremony"]


def test_summary_md_renders_trust_boundary_and_event_table(aroot, tmp_path):
    tid = _new_task(aroot, "Build I1")
    pack = tmp_path / "pack"
    r = _export(aroot, pack, "--task", tid)
    assert r.returncode == 0, r.stdout + r.stderr
    summary = (pack / "SUMMARY.md").read_text(encoding="utf-8")
    assert "What this pack proves" in summary
    assert tid in summary
    assert "tessctl audit verify" in summary


# ---------------------------------------------------------------------------
# --receipt embedding
# ---------------------------------------------------------------------------

def _canonical_bytes(obj, exclude_key):
    payload = {k: v for k, v in obj.items() if k != exclude_key}
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _build_fixture_receipt():
    import hashlib
    decision = {
        "verifier": "Reid",
        "output_domain": "Code diff / PR",
        "primary_artifacts_read": ["docs/AUDIT_PACK_SPEC.md"],
        "findings": [],
        "severity_counts": {"critical": 0, "high": 0, "medium": 0, "low": 0},
        "summary_line": "Reviewed. Found 0 CRITICAL, 0 HIGH, 0 MEDIUM, 0 LOW. Top priority: none.",
        "disposition": "APPROVE",
    }
    decision["signature"] = {
        "algorithm": "gpg-detached-armor",
        "signed_content_sha256": hashlib.sha256(_canonical_bytes(decision, "signature")).hexdigest(),
        "signature_armored": "TEST-FIXTURE-NOT-A-REAL-SIGNATURE",
    }
    receipt = {
        "receipt_schema": "tess-os.agent-receipt/1",
        "receipt_id": "a" * 32,
        "issued_at": "2026-07-20T00:00:00.000000Z",
        "proposed_action": {
            "actor": "Ada", "summary": "Built I1 auditor pack export/verify",
            "repo": "twiss-io/tess-os", "ref": "PR#TBD", "paths": [".tess/bin/tessctl"],
        },
        "policy_decision": {
            "source": "core/policy/policy.yaml", "rule_id": "docs-review",
            "rule_kind": "path_rule", "classification": ["prod_touching"],
            "description": "Doc/backend change requires review.",
        },
        "decision_kind": "verdict",
        "decision": decision,
        "chain": {"sequence": 0, "prev_receipt_hash": "GENESIS"},
    }
    receipt["receipt_signature"] = {
        "algorithm": "gpg-detached-armor",
        "signed_by": "Reid",
        "signed_content_sha256": hashlib.sha256(_canonical_bytes(receipt, "receipt_signature")).hexdigest(),
        "signature_armored": "TEST-FIXTURE-NOT-A-REAL-SIGNATURE",
    }
    return receipt


def test_export_embeds_valid_receipt_verbatim(aroot, tmp_path):
    receipt = _build_fixture_receipt()
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    pack = tmp_path / "pack"
    r = _export(aroot, pack, "--all", receipts=[receipt_path])
    assert r.returncode == 0, r.stdout + r.stderr
    manifest = _manifest(pack)
    assert manifest["counts"]["receipts"] == 1
    assert manifest["receipts"][0] == receipt
    assert manifest["artifacts"]["receipt_actions"][0]["repo"] == "twiss-io/tess-os"
    assert manifest["artifacts"]["receipt_actions"][0]["paths"] == [".tess/bin/tessctl"]
    assert "1 Agent Receipt(s) embedded" in manifest["trust_boundary"]["receipts"]


def test_export_rejects_invalid_receipt_shape_and_writes_nothing(aroot, tmp_path):
    bad = {"receipt_schema": "tess-os.agent-receipt/1"}  # missing every other required field
    receipt_path = tmp_path / "bad_receipt.json"
    receipt_path.write_text(json.dumps(bad), encoding="utf-8")

    pack = tmp_path / "pack"
    r = _export(aroot, pack, "--all", receipts=[receipt_path])
    assert r.returncode != 0
    assert "agent-receipt.schema.json" in (r.stdout + r.stderr)
    assert not pack.exists()


def test_export_missing_receipt_file_is_refused(aroot, tmp_path):
    pack = tmp_path / "pack"
    r = _export(aroot, pack, "--all", receipts=[tmp_path / "does-not-exist.json"])
    assert r.returncode != 0
    assert "does not exist" in (r.stdout + r.stderr)
    assert not pack.exists()


# ---------------------------------------------------------------------------
# verify — clean pass, standalone (no live ledger needed)
# ---------------------------------------------------------------------------

def test_verify_passes_on_clean_all_scope_pack(aroot, tmp_path):
    for i in range(4):
        _append(aroot, event="dispatch", summary=f"e{i}", harness="ada")
    pack = tmp_path / "pack"
    _export(aroot, pack, "--all")
    r = _verify(aroot, pack)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OK" in r.stdout


def test_verify_works_standalone_after_source_ledger_is_deleted(aroot, tmp_path):
    """The pack must be independently verifiable WITHOUT the live system —
    prove it by deleting the entire source ledger after export and
    confirming `audit verify` still passes against the pack alone."""
    for i in range(3):
        _append(aroot, event="dispatch", summary=f"e{i}", harness="ada")
    pack = tmp_path / "pack"
    _export(aroot, pack, "--all")

    shutil.rmtree(aroot / ".tess" / "state" / "ledger")
    r = _verify(aroot, pack)
    assert r.returncode == 0, r.stdout + r.stderr


def test_verify_passes_on_partial_scope_pack_with_expected_seq_gap(aroot, tmp_path):
    """A task-scoped export whose OWN events are interleaved with another
    task's events in the same shard has a real seq gap between included
    events — expected for a partial scope, must never be reported as
    tamper."""
    tid = _new_task(aroot, "Build I1")
    other = "T-other-0000-bbbb"
    _append(aroot, event="task_transition", summary="other task work", harness="ada", task=other)
    _append(aroot, event="task_transition", summary="status: backlog -> in_progress", harness="ada", task=tid)

    pack = tmp_path / "pack"
    r = _export(aroot, pack, "--task", tid)
    assert r.returncode == 0, r.stdout + r.stderr
    manifest = _manifest(pack)
    seqs = [e["seq"] for e in manifest["shards"][0]["events"]]
    assert seqs[1] != seqs[0] + 1, "the gap is the whole point of this test"

    r = _verify(aroot, pack)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "TAMPERED" not in r.stdout


def test_verify_accepts_a_direct_manifest_json_path(aroot, tmp_path):
    _append(aroot, event="dispatch", summary="e1", harness="ada")
    pack = tmp_path / "pack"
    _export(aroot, pack, "--all")
    r = _verify(aroot, pack / "manifest.json")
    assert r.returncode == 0, r.stdout + r.stderr


def test_verify_json_output_shape(aroot, tmp_path):
    _append(aroot, event="dispatch", summary="e1", harness="ada")
    pack = tmp_path / "pack"
    _export(aroot, pack, "--all")
    r = _verify(aroot, pack, json_out=True)
    assert r.returncode == 0, r.stdout + r.stderr
    body = json.loads(r.stdout)
    assert body["ok"] is True
    assert body["events_checked"] == 1
    assert body["problems"] == []


# ---------------------------------------------------------------------------
# verify — fail-closed on tamper
# ---------------------------------------------------------------------------

def test_verify_fails_on_tampered_event_content(aroot, tmp_path):
    _append(aroot, event="dispatch", summary="original", harness="ada")
    pack = tmp_path / "pack"
    _export(aroot, pack, "--all")

    manifest = _manifest(pack)
    manifest["shards"][0]["events"][0]["summary"] = "TAMPERED — never happened"
    _write_manifest(pack, manifest)

    r = _verify(aroot, pack)
    assert r.returncode == 1
    assert "TAMPERED" in r.stdout
    assert "hash mismatch" in r.stdout


def test_verify_fails_on_broken_prev_hash_between_adjacent_included_events(aroot, tmp_path):
    _append(aroot, event="dispatch", summary="one", harness="ada")
    _append(aroot, event="dispatch", summary="two", harness="ada")
    pack = tmp_path / "pack"
    _export(aroot, pack, "--all")

    manifest = _manifest(pack)
    events = manifest["shards"][0]["events"]
    assert events[1]["seq"] == events[0]["seq"] + 1  # genuinely adjacent
    events[1]["prev_hash"] = "1" * 64  # break the link without touching its own hash's recompute target...
    # NOTE: mutating prev_hash changes what the recorded `hash` was computed
    # over, so this ALSO trips the hash-mismatch check below it in the
    # walk — assert on prev_hash-or-hash-mismatch language collectively.
    _write_manifest(pack, manifest)

    r = _verify(aroot, pack)
    assert r.returncode == 1
    assert "TAMPERED" in r.stdout


def test_verify_fails_on_missing_manifest(aroot, tmp_path):
    r = _verify(aroot, tmp_path / "nope")
    assert r.returncode != 0
    assert "does not exist" in (r.stdout + r.stderr)


def test_verify_fails_on_wrong_pack_schema(aroot, tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    (pack / "manifest.json").write_text(json.dumps({"pack_schema": "not-the-right-thing"}), encoding="utf-8")
    r = _verify(aroot, pack)
    assert r.returncode != 0
    assert "pack_schema" in (r.stdout + r.stderr)


def test_verify_fails_on_seq_gap_inside_a_full_export_kind_shard(aroot, tmp_path):
    """Engine-level: a hand-crafted 'full' shard group with a seq gap must
    be reported as a missing event, not silently accepted — 'full' is a
    completeness CLAIM the verifier actively checks, unlike 'partial'."""
    _append(aroot, event="dispatch", summary="one", harness="ada")
    _append(aroot, event="dispatch", summary="two", harness="ada")
    _append(aroot, event="dispatch", summary="three", harness="ada")
    pack = tmp_path / "pack"
    _export(aroot, pack, "--all")

    manifest = _manifest(pack)
    events = manifest["shards"][0]["events"]
    del events[1]  # remove the middle event, leaving a real seq gap (0, 2)
    manifest["shards"][0]["event_count"] = len(events)
    _write_manifest(pack, manifest)

    r = _verify(aroot, pack)
    assert r.returncode == 1
    assert "TAMPERED" in r.stdout
    assert "missing" in r.stdout.lower() or "gap" in r.stdout.lower()


def test_verify_fails_on_tampered_receipt_envelope(aroot, tmp_path):
    receipt = _build_fixture_receipt()
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    pack = tmp_path / "pack"
    _export(aroot, pack, "--all", receipts=[receipt_path])

    manifest = _manifest(pack)
    manifest["receipts"][0]["proposed_action"]["summary"] = "TAMPERED — not what was approved"
    _write_manifest(pack, manifest)

    r = _verify(aroot, pack)
    assert r.returncode == 1
    assert "receipt_signature.signed_content_sha256" in r.stdout


def test_verify_fails_on_tampered_receipt_decision(aroot, tmp_path):
    receipt = _build_fixture_receipt()
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    pack = tmp_path / "pack"
    _export(aroot, pack, "--all", receipts=[receipt_path])

    manifest = _manifest(pack)
    manifest["receipts"][0]["decision"]["disposition"] = "BLOCK"
    _write_manifest(pack, manifest)

    r = _verify(aroot, pack)
    assert r.returncode == 1
    assert "decision.signature.signed_content_sha256" in r.stdout


# ---------------------------------------------------------------------------
# --out handling
# ---------------------------------------------------------------------------

def test_export_refuses_nonempty_out_without_force(aroot, tmp_path):
    _append(aroot, event="dispatch", summary="e1", harness="ada")
    pack = tmp_path / "pack"
    r = _export(aroot, pack, "--all")
    assert r.returncode == 0, r.stdout + r.stderr

    r2 = _export(aroot, pack, "--all")
    assert r2.returncode != 0
    assert "already exists" in (r2.stdout + r2.stderr)


def test_export_force_overwrites_existing_out(aroot, tmp_path):
    _append(aroot, event="dispatch", summary="e1", harness="ada")
    pack = tmp_path / "pack"
    _export(aroot, pack, "--all")
    _append(aroot, event="dispatch", summary="e2", harness="ada")

    r = _export(aroot, pack, "--all", force=True)
    assert r.returncode == 0, r.stdout + r.stderr
    manifest = _manifest(pack)
    assert manifest["counts"]["events"] == 2


# ---------------------------------------------------------------------------
# determinism
# ---------------------------------------------------------------------------

def test_export_is_deterministic_modulo_pack_id_and_timestamp(aroot, tmp_path):
    tid = _new_task(aroot, "Build I1")
    _append(aroot, event="task_transition", summary="status change", harness="ada", task=tid)

    pack1 = tmp_path / "pack1"
    pack2 = tmp_path / "pack2"
    r1 = _export(aroot, pack1, "--task", tid)
    r2 = _export(aroot, pack2, "--task", tid)
    assert r1.returncode == 0 and r2.returncode == 0

    m1, m2 = _manifest(pack1), _manifest(pack2)
    for key in ("pack_id", "exported_at", "exported_by"):
        del m1[key], m2[key]
    assert m1 == m2


# ---------------------------------------------------------------------------
# PR #128 review — Cyra MEDIUM: tail anchor (.tip) makes 'full' genuinely
# complete, not just genesis-start + no-interior-gap.
# ---------------------------------------------------------------------------

def test_full_scope_shard_embeds_tip_tail_anchor(aroot, tmp_path):
    _append(aroot, event="dispatch", summary="e1", harness="ada")
    _append(aroot, event="dispatch", summary="e2", harness="ada")
    pack = tmp_path / "pack"
    r = _export(aroot, pack, "--all")
    assert r.returncode == 0, r.stdout + r.stderr
    manifest = _manifest(pack)
    shard = manifest["shards"][0]
    assert shard["export_kind"] == "full"
    assert shard["tip"]["count"] == 2
    assert shard["tip"]["hash"] == shard["events"][-1]["hash"]


def test_partial_scope_shard_does_not_embed_tip(aroot, tmp_path):
    tid = _new_task(aroot, "Build I1")
    pack = tmp_path / "pack"
    r = _export(aroot, pack, "--task", tid)
    assert r.returncode == 0, r.stdout + r.stderr
    manifest = _manifest(pack)
    assert manifest["shards"][0]["export_kind"] == "partial"
    assert manifest["shards"][0]["tip"] is None


def test_verify_fails_on_tail_truncation_of_a_full_scope_shard(aroot, tmp_path):
    """The MEDIUM fix, directly: dropping the LAST event(s) from a
    'full'-claimed shard used to still verify OK (genesis-start +
    no-interior-gap alone can't see a missing tail). The embedded tail
    anchor closes it."""
    _append(aroot, event="dispatch", summary="e1", harness="ada")
    _append(aroot, event="dispatch", summary="e2", harness="ada")
    _append(aroot, event="dispatch", summary="e3", harness="ada")
    pack = tmp_path / "pack"
    r = _export(aroot, pack, "--all")
    assert r.returncode == 0, r.stdout + r.stderr

    manifest = _manifest(pack)
    manifest["shards"][0]["events"].pop()  # drop the LAST event — tail truncation
    manifest["shards"][0]["event_count"] = len(manifest["shards"][0]["events"])
    _write_manifest(pack, manifest)

    r = _verify(aroot, pack)
    assert r.returncode == 1
    assert "TAMPERED" in r.stdout
    assert "tail anchor mismatch" in r.stdout
    assert "tail-truncation detected" in r.stdout


def test_verify_fails_on_tail_truncation_via_json_output(aroot, tmp_path):
    _append(aroot, event="dispatch", summary="e1", harness="ada")
    _append(aroot, event="dispatch", summary="e2", harness="ada")
    pack = tmp_path / "pack"
    _export(aroot, pack, "--all")
    manifest = _manifest(pack)
    manifest["shards"][0]["events"].pop()
    _write_manifest(pack, manifest)

    r = _verify(aroot, pack, json_out=True)
    assert r.returncode == 1
    body = json.loads(r.stdout)
    assert body["ok"] is False
    assert any("tail anchor mismatch" in p for p in body["problems"])


def test_verify_still_passes_when_no_events_are_dropped_from_a_tip_anchored_shard(aroot, tmp_path):
    """Sanity: the tail-anchor check must not false-positive on an
    untampered full-scope export."""
    for i in range(3):
        _append(aroot, event="dispatch", summary=f"e{i}", harness="ada")
    pack = tmp_path / "pack"
    r = _export(aroot, pack, "--all")
    assert r.returncode == 0, r.stdout + r.stderr
    r = _verify(aroot, pack)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OK" in r.stdout


# ---------------------------------------------------------------------------
# PR #128 review — Cyra LOW-MED: a pre-#115 seq-absent LEGACY shard must
# verify LEGACY/OK, never a false-positive TAMPERED.
# ---------------------------------------------------------------------------

def _hand_craft_legacy_shard(root, engine, origin="legacy"):
    """A coherent 2-line shard (valid prev_hash/hash chain, exactly as
    `_log_append_event` would have produced it before `seq` existed) with
    NO `seq` key on either line and NO `.tip` sidecar — the exact pre-#113/
    #115 on-disk shape. Mirrors tests/test_accountability_ledger.py's own
    `_hand_craft_legacy_shard` helper."""
    shard = root / ".tess" / "state" / "ledger" / f"2026-06.{origin}.jsonl"
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


def test_verify_reports_legacy_full_shard_as_legacy_not_tampered(aroot, tmp_path, engine):
    _hand_craft_legacy_shard(aroot, engine, origin="legacy")

    pack = tmp_path / "pack"
    r = _export(aroot, pack, "--all", origin="legacy")
    assert r.returncode == 0, r.stdout + r.stderr
    manifest = _manifest(pack)
    assert manifest["shards"][0]["export_kind"] == "full"
    assert "seq" not in manifest["shards"][0]["events"][0]

    r = _verify(aroot, pack)
    assert r.returncode == 0, r.stdout + r.stderr
    # the STATUS line (first line) must be LEGACY, never TAMPERED — the
    # word "TAMPERED" legitimately appears later, inside the explanatory
    # "reported as LEGACY, not TAMPERED" note text itself.
    assert r.stdout.splitlines()[0].startswith("LEGACY")
    assert "legacy (seq-absent)" in r.stdout


def test_verify_legacy_shard_still_catches_a_real_hash_tamper(aroot, tmp_path, engine):
    """Legacy handling must not become a blanket exemption — a genuinely
    tampered legacy line is still caught."""
    _hand_craft_legacy_shard(aroot, engine, origin="legacy")
    pack = tmp_path / "pack"
    r = _export(aroot, pack, "--all", origin="legacy")
    assert r.returncode == 0, r.stdout + r.stderr

    manifest = _manifest(pack)
    manifest["shards"][0]["events"][0]["summary"] = "TAMPERED"
    _write_manifest(pack, manifest)

    r = _verify(aroot, pack)
    assert r.returncode == 1
    assert "TAMPERED" in r.stdout
    assert "hash mismatch" in r.stdout


# ---------------------------------------------------------------------------
# PR #128 review — Cyra LOW: `trust_boundary` must not be strippable.
# ---------------------------------------------------------------------------

def test_verify_fails_when_trust_boundary_is_deleted(aroot, tmp_path):
    _append(aroot, event="dispatch", summary="e1", harness="ada")
    pack = tmp_path / "pack"
    _export(aroot, pack, "--all")

    manifest = _manifest(pack)
    del manifest["trust_boundary"]
    _write_manifest(pack, manifest)

    r = _verify(aroot, pack)
    assert r.returncode == 1
    assert "trust_boundary" in r.stdout
    assert "stripped or altered" in r.stdout


def test_verify_fails_when_trust_boundary_text_is_reworded(aroot, tmp_path):
    _append(aroot, event="dispatch", summary="e1", harness="ada")
    pack = tmp_path / "pack"
    _export(aroot, pack, "--all")

    manifest = _manifest(pack)
    manifest["trust_boundary"]["completeness"] = "This pack proves everything, always."
    _write_manifest(pack, manifest)

    r = _verify(aroot, pack)
    assert r.returncode == 1
    assert "trust_boundary" in r.stdout


def test_export_trust_boundary_matches_canonical_generator_for_receipt_count(aroot, tmp_path):
    """Build-time and verify-time text must be generated from the SAME
    function — proven by exporting with a receipt embedded (a different
    receipt count changes the 'receipts' field) and confirming a clean
    verify still passes."""
    receipt = _build_fixture_receipt()
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    pack = tmp_path / "pack"
    r = _export(aroot, pack, "--all", receipts=[receipt_path])
    assert r.returncode == 0, r.stdout + r.stderr
    r = _verify(aroot, pack)
    assert r.returncode == 0, r.stdout + r.stderr


# ---------------------------------------------------------------------------
# PR #128 review — Reid LOW: exported_by.user disclosure.
# ---------------------------------------------------------------------------

def test_trust_boundary_discloses_exported_by_is_self_reported(aroot, tmp_path):
    _append(aroot, event="dispatch", summary="e1", harness="ada")
    pack = tmp_path / "pack"
    r = _export(aroot, pack, "--all")
    assert r.returncode == 0, r.stdout + r.stderr
    manifest = _manifest(pack)
    assert "exported_by" in manifest["trust_boundary"]
    note = manifest["trust_boundary"]["exported_by"]
    assert "SELF-REPORTED" in note
    assert "exported_by.user" in note
    assert "EXTERNAL distribution" in note


# ---------------------------------------------------------------------------
# PR #128 review — Reid LOW: --receipt path hygiene (mirrors _task_path /
# _validate_evidence_path's own containment discipline).
# ---------------------------------------------------------------------------

def test_export_refuses_a_symlink_receipt(aroot, tmp_path):
    real = tmp_path / "receipt.json"
    real.write_text(json.dumps(_build_fixture_receipt()), encoding="utf-8")
    link = tmp_path / "receipt-link.json"
    link.symlink_to(real)

    pack = tmp_path / "pack"
    r = _export(aroot, pack, "--all", receipts=[link])
    assert r.returncode != 0
    assert "is a symlink" in (r.stdout + r.stderr)
    assert not pack.exists()


def test_export_refuses_a_directory_as_receipt(aroot, tmp_path):
    a_dir = tmp_path / "not-a-file"
    a_dir.mkdir()

    pack = tmp_path / "pack"
    r = _export(aroot, pack, "--all", receipts=[a_dir])
    assert r.returncode != 0
    assert "not a regular file" in (r.stdout + r.stderr)
    assert not pack.exists()


def test_export_refuses_an_empty_receipt_file(aroot, tmp_path):
    empty = tmp_path / "empty.json"
    empty.write_text("", encoding="utf-8")

    pack = tmp_path / "pack"
    r = _export(aroot, pack, "--all", receipts=[empty])
    assert r.returncode != 0
    assert "empty file" in (r.stdout + r.stderr)
    assert not pack.exists()


def test_export_still_accepts_a_valid_non_symlink_receipt_file(aroot, tmp_path):
    """Sanity: the new hygiene checks must not reject a perfectly normal
    receipt file."""
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(_build_fixture_receipt()), encoding="utf-8")
    pack = tmp_path / "pack"
    r = _export(aroot, pack, "--all", receipts=[receipt_path])
    assert r.returncode == 0, r.stdout + r.stderr
