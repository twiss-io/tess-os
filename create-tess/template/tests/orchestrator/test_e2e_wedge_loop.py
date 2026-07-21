"""DoD B.9 — THE scripted "propose -> approve -> app boots -> show me the
receipt" wedge-loop end-to-end proof.

This composes three pieces that are each already separately tested
elsewhere in this repo, into ONE proof that they hold together as a
single real flow, driven entirely through the public `orchestrator.
pipeline.run_pipeline()` entry point (never a hand-assembled shortcut):

  1. `run_pipeline()`'s Hop 7 receipt emission (`orchestrator/
     mission_receipt.py`, #161) — already unit/integration-tested in
     `test_receipt_integration.py` for the "generated" path alone.
  2. `spec_engine.codegen.generate_app()`'s atomic staging (#156) —
     already exhaustively kill-tested in `tests/spec_engine/
     test_codegen_atomic_staging.py` for direct `generate_app()` calls.
  3. The generated app actually booting and serving real HTTP traffic
     (`tests/spec_engine/test_codegen_app_boots.py`) — already tested for
     `generate_app()` called directly against a hand-built spec.

None of those three files is superseded or duplicated here — each still
covers its own component in isolation, with far more edge cases than
belong in an e2e test. This file's only job is the composition: a
freeform idea, run through the REAL `run_pipeline()`, really approved by
a real (test-scoped) `LocalIdentityApprovalGate`, produces a REAL running
Node app AND a REAL, independently re-verifiable Agent Receipt — plus the
two unhappy paths a "show me the receipt" claim would be dishonest
without: a rejection must never produce codegen artifacts or a receipt,
and a kill mid-`generate_app` must never leave a partial trust artifact
(partial codegen tree OR partial/orphaned receipt) behind.

★ Node is HARD-REQUIRED for this module — deliberately NOT `pytest.mark.
skipif(not HAS_NODE, ...)` the way `test_codegen_app_boots.py` chooses to
(a reasonable, disclosed local-dev convenience for THAT file). A flagship
DoD-level "the wedge loop really works end to end" proof that silently
skips in CI is worse than useless — it would report green without ever
having run. `_require_node` below (autouse) turns a missing `node` into a
hard, loud test FAILURE, and `.github/workflows/ci.yml`'s `test` job now
sets up Node explicitly so this can never be hit on a real CI run (see
that workflow's own `Set up Node` step, added alongside this file).
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

import _orchestrator_paths  # noqa: F401 -- sys.path bootstrap
from _orchestrator_paths import EXAMPLE_ROUTING_TABLE, REPO_ROOT

from _node_server import HAS_NODE, get_json, node_server, post_json  # noqa: F401 -- node_server used as a fixture

from orchestrator.adapters.local_identity import LocalIdentityApprovalGate
from orchestrator.pipeline import run_pipeline

from spec_engine.codegen import ACCEPTANCE_TEST_REL_PATH

# tools/receipt-verify/ is already on sys.path by the time this runs --
# orchestrator/__init__.py's own sys.path bootstrap (extended by the
# wedge-loop epic) ran as a side effect of importing `orchestrator` above
# (see test_receipt_integration.py for the same, already-proven pattern).
import checks  # noqa: E402

RECEIPT_VERIFY_CLI = REPO_ROOT / "tools" / "receipt-verify" / "receipt_verify.py"

# A freeform idea, phrased the way a real user would type it -- with ONE
# literal `<Name> entity (field, field, ...)` declaration folded in
# naturally, matching spec_engine.entity_extraction's documented "never
# fabricate a data model from prose, parse only an explicit literal
# declaration" contract (spec_engine/intake.py's own module docstring).
# Without this literal shape, harvest_intake() legitimately returns ZERO
# entities (verified empirically against this exact routing table) and
# there would be nothing for the CRUD round-trip below to exercise --
# this is not a contrived test-only shortcut, it is how a real user gets
# a real generated CRUD API out of this pipeline today.
IDEA = (
    "We need a small internal tool that tracks vendor invoices and flags "
    "overdue ones. Invoice entity (vendor_name, amount, due_date, status)."
)

BOOT_TIMEOUT_SECONDS = 30


@pytest.fixture(autouse=True)
def _require_node():
    """Hard-fail (never skip) if `node` is missing -- see module docstring."""
    if not HAS_NODE:
        pytest.fail(
            "node binary is required for tests/orchestrator/test_e2e_wedge_loop.py "
            "(DoD B.9 flagship e2e) and must never be silently skipped in CI -- "
            "install Node >= 18 (see .github/workflows/ci.yml's 'test' job)."
        )


def _gate(tmp_path, *, approved=True, notes=""):
    return LocalIdentityApprovalGate(
        identity_dir=tmp_path / "identity",
        confirm_fn=lambda plan, identity: (approved, notes),
    )


def _trust_for(gate: LocalIdentityApprovalGate, identity_str: str) -> dict:
    """{approved_by: {"fingerprint", "key_bytes"}} built from the REAL
    local approval-identity key this gate actually signed with -- mirrors
    test_receipt_integration.py's `_real_trust_for`."""
    key_bytes = gate.identity.key_path.read_bytes()
    return {identity_str: {"fingerprint": gate.identity.fingerprint, "key_bytes": key_bytes}}


# ---------------------------------------------------------------------------
# HAPPY PATH -- the full "propose -> approve -> app boots -> show me the
# receipt" loop, in one scripted run.
# ---------------------------------------------------------------------------


def test_happy_path_freeform_idea_approves_boots_and_produces_a_verifiable_receipt(tmp_path, node_server):
    gate = _gate(tmp_path)
    target_dir = tmp_path / "generated-app"
    receipt_path = tmp_path / "receipt.json"

    result = run_pipeline(
        IDEA,
        EXAMPLE_ROUTING_TABLE,
        gate,
        target_dir=target_dir,
        route_log_path=False,
        spec_log_path=False,
        receipt_path=receipt_path,
    )

    # --- it routes -----------------------------------------------------
    assert result.status == "generated"
    assert result.decision is not None and result.decision.ambiguous is False
    assert result.plan is not None

    # --- it approves (a real, authenticated decision) -------------------
    assert result.approval is not None
    assert result.approval.approved is True
    assert result.approval.approved_by.startswith("local:")
    assert gate.verify(result.approval, result.plan), (
        "the SAME gate that produced this approval must be able to independently re-verify it"
    )

    # --- codegen genuinely ran ------------------------------------------
    assert result.codegen is not None
    assert result.codegen.scaffold_plan.codegen_status == "generated"
    assert result.spec.data_model.entities, "sanity: this idea's literal entity declaration must survive to the spec"
    entity = result.spec.data_model.entities[0]
    assert entity.name == "Invoice"
    assert (target_dir / "src" / "server.js").is_file()
    manifest = json.loads((target_dir / ".spec-engine" / "codegen-manifest.json").read_text(encoding="utf-8"))
    assert manifest["codegen_status"] == "generated"
    assert manifest["spec_id"] == result.spec.spec_id

    # --- the app BOOTS and serves real HTTP traffic ----------------------
    proc, base_url = node_server(target_dir)
    try:
        status, body = get_json(f"{base_url}/health")
        assert status == 200
        assert body == {"status": "ok"}
        assert proc.poll() is None, "server must still be alive after answering a real request"

        # One real CRUD round-trip against the entity the freeform idea
        # actually declared -- create, then fetch it back by id, then
        # confirm it shows up in the list.
        slug = re.sub(r"[^a-z0-9]+", "-", entity.name.lower()).strip("-")
        collection_url = f"{base_url}/api/{slug}s"
        payload = {
            "vendor_name": "Acme Freight Co",
            "amount": "4200.00",
            "due_date": "2026-08-15",
            "status": "open",
        }
        status, created = post_json(collection_url, payload)
        assert status == 201
        assert "id" in created
        assert created["vendor_name"] == "Acme Freight Co"

        status, fetched = get_json(f"{collection_url}/{created['id']}")
        assert status == 200
        assert fetched["id"] == created["id"]

        status, listed = get_json(collection_url)
        assert status == 200
        assert any(r["id"] == created["id"] for r in listed)
    finally:
        pass  # node_server fixture terminates the process on teardown

    # --- the generated app's OWN acceptance-test suite passes for real ---
    node_test = subprocess.run(
        ["node", "--test", ACCEPTANCE_TEST_REL_PATH],
        cwd=str(target_dir),
        capture_output=True,
        text=True,
        timeout=BOOT_TIMEOUT_SECONDS,
    )
    combined = node_test.stdout + node_test.stderr
    assert node_test.returncode == 0, f"generated app's own test suite failed:\n{combined}"
    assert "# fail 0" in combined, combined
    assert "# pass" in combined and "# pass 0" not in combined, combined

    # --- a real, independently verifiable Agent Receipt was emitted -----
    assert result.receipt is not None
    assert result.receipt["decision_kind"] == "local_approval"
    assert result.receipt["receipt_signature"]["algorithm"] == "local-hmac-sha256-v1"
    assert result.receipt["decision"]["approval_id"] == result.approval.approval_id
    assert result.receipt["decision"]["approved"] is True
    assert result.receipt["policy_decision"]["rule_kind"] == "pipeline_approval_gate"
    on_disk = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert on_disk == result.receipt

    # In-process verification (checks.verify_receipt -- the exact function
    # the standalone CLI below itself calls).
    trust = _trust_for(gate, result.approval.approved_by)
    assert checks.verify_receipt(result.receipt, trust) == []

    # THE independent proof: the actual standalone `tools/receipt-verify`
    # CLI, run as a real subprocess (never imported), with a test-scoped
    # key file -- exactly what a genuinely independent third party would
    # run against this receipt, with zero knowledge of this repo's Python
    # internals beyond the receipt JSON + the key file it is handed.
    key_file = tmp_path / "trusted-key.bin"
    key_file.write_bytes(gate.identity.key_path.read_bytes())
    cli = subprocess.run(
        [
            sys.executable, str(RECEIPT_VERIFY_CLI), "verify", str(receipt_path),
            "--trust", result.approval.approved_by, gate.identity.fingerprint, str(key_file),
            "--json",
        ],
        capture_output=True, text=True, timeout=30,
    )
    assert cli.returncode == 0, f"tools/receipt-verify CLI rejected a genuinely valid receipt:\n{cli.stdout}\n{cli.stderr}"
    cli_result = json.loads(cli.stdout)
    assert cli_result["valid"] is True
    assert cli_result["reasons"] == []


# ---------------------------------------------------------------------------
# REJECTION -- a human rejection must never leave codegen artifacts or a
# receipt behind, even though receipt_path was supplied.
# ---------------------------------------------------------------------------


def test_rejection_path_writes_no_codegen_artifacts_and_no_receipt(tmp_path):
    gate = _gate(tmp_path, approved=False, notes="not approved for this test")
    target_dir = tmp_path / "generated-app"
    receipt_path = tmp_path / "receipt.json"

    result = run_pipeline(
        IDEA,
        EXAMPLE_ROUTING_TABLE,
        gate,
        target_dir=target_dir,
        route_log_path=False,
        spec_log_path=False,
        receipt_path=receipt_path,
    )

    assert result.status == "rejected"
    assert result.approval is not None and result.approval.approved is False
    assert result.spec is None
    assert result.codegen is None

    # No codegen artifacts of any kind.
    assert not target_dir.exists()

    # No receipt of any kind -- a rejection has nothing honest to attach
    # a "generated a running app" receipt to (mission_receipt.py's own
    # scope: receipt is populated ONLY on "generated").
    assert result.receipt is None
    assert not receipt_path.exists()


# ---------------------------------------------------------------------------
# MID-KILL -- SIGKILL landing mid-`generate_app()`, driven through the
# FULL pipeline (routing -> plan -> real approval -> finalize -> codegen),
# not a direct generate_app() call. Reuses tests/spec_engine/
# test_codegen_atomic_staging.py's own proven instrumented-pause-then-
# SIGKILL pattern, adapted to spawn `orchestrator.pipeline.run_pipeline()`
# (with `receipt_path` set) instead of calling `generate_app()` directly.
# ---------------------------------------------------------------------------

_CHILD_SCRIPT = r'''
import os
import sys
import tempfile
import time

target_dir = sys.argv[1]
receipt_path = sys.argv[2]
routing_table_path = sys.argv[3]
identity_dir = sys.argv[4]

# Same defense-in-depth env-var safety net tests/orchestrator/
# _orchestrator_paths.py and tests/spec_engine/test_codegen_atomic_staging.py's
# own child script both apply -- this child has NO pytest/conftest
# machinery at all, so it sets up its own isolation before importing
# anything real.
os.environ.setdefault("TESS_OS_APPROVAL_IDENTITY_DIR", tempfile.mkdtemp(prefix="e2e-kill-test-identity-"))
os.environ.setdefault("TESS_OS_TELEMETRY_DIR", tempfile.mkdtemp(prefix="e2e-kill-test-telemetry-"))

sys.path.insert(0, "__REPO_ROOT__")

# Importing orchestrator.* runs orchestrator/__init__.py's own sys.path
# bootstrap (adds intent-router/, spec-engine/, tools/receipt-verify/) --
# spec_engine.codegen only becomes importable AFTER this line.
from orchestrator.adapters.local_identity import LocalIdentityApprovalGate
from orchestrator.pipeline import run_pipeline

import spec_engine.codegen as codegen_module

gate = LocalIdentityApprovalGate(
    identity_dir=identity_dir,
    confirm_fn=lambda plan, identity: (True, ""),
)

_orig_write_file = codegen_module._write_file


def _instrumented_write_file(root, rel_path, content):
    result = _orig_write_file(root, rel_path, content)
    print("REACHED:" + rel_path, flush=True)
    # SIGKILL from the parent lands somewhere in here -- unblockable,
    # un-catchable, no Python-level cleanup (including Hop 6/7) ever runs.
    time.sleep(30)
    return result


codegen_module._write_file = _instrumented_write_file

run_pipeline(
    "We need a small internal tool that tracks vendor invoices and flags overdue ones. "
    "Invoice entity (vendor_name, amount, due_date, status).",
    routing_table_path,
    gate,
    target_dir=target_dir,
    route_log_path=False,
    spec_log_path=False,
    receipt_path=receipt_path,
)
print("COMPLETED", flush=True)
'''


def test_sigkill_mid_generate_app_leaves_zero_partial_trust_artifacts(tmp_path):
    target_dir = tmp_path / "generated-app"
    receipt_path = tmp_path / "receipt.json"
    identity_dir = tmp_path / "identity"
    assert not target_dir.exists(), "sanity: target_dir must not pre-exist for this test"

    script_path = tmp_path / "_child_e2e_kill.py"
    script_path.write_text(
        _CHILD_SCRIPT.replace("__REPO_ROOT__", str(REPO_ROOT)),
        encoding="utf-8",
    )
    proc = subprocess.Popen(
        [
            sys.executable, str(script_path),
            str(target_dir), str(receipt_path), str(EXAMPLE_ROUTING_TABLE), str(identity_dir),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    deadline = time.monotonic() + BOOT_TIMEOUT_SECONDS
    marker = None
    try:
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                out = proc.stdout.read()
                err = proc.stderr.read()
                raise AssertionError(
                    f"child exited early (code {proc.returncode}) before reaching the write it "
                    f"was instrumented to pause at.\nstdout={out!r}\nstderr={err!r}"
                )
            line = proc.stdout.readline()
            if not line:
                time.sleep(0.02)
                continue
            if line.startswith("REACHED:"):
                marker = line.strip()[len("REACHED:"):]
                break
        if marker is None:
            raise AssertionError("child never reached the instrumented write within the deadline")

        os.kill(proc.pid, signal.SIGKILL)
        proc.wait(timeout=10)
        assert proc.returncode != 0, "child should have been killed, not exited cleanly"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)

    # --- ZERO partial codegen tree ---------------------------------------
    # The kill landed right after the FIRST generated file was written --
    # target_dir must remain fully absent (atomic staging's own guarantee,
    # #156, now proven to hold when driven through the full pipeline, not
    # just a direct generate_app() call).
    assert not target_dir.exists(), (
        "target_dir must remain absent -- the write the child was killed mid-sleep-after went "
        "into a STAGING sibling directory, never into target_dir itself, exactly like "
        "tests/spec_engine/test_codegen_atomic_staging.py's own direct generate_app() kill test"
    )
    stage_dirs = [
        p for p in tmp_path.iterdir()
        if p.is_dir() and p.name.startswith(f".{target_dir.name}.codegen-stage-")
    ]
    assert len(stage_dirs) == 1, f"expected exactly one leftover staging dir, found {stage_dirs}"
    written_files = [p for p in stage_dirs[0].rglob("*") if p.is_file()]
    assert len(written_files) == 1, (
        f"expected exactly the one file the child was killed right after writing, found {written_files}"
    )
    assert written_files[0].relative_to(stage_dirs[0]).as_posix() == marker

    # --- ZERO partial receipt ---------------------------------------------
    # Hop 7 (_emit_governed_mission_receipt) only runs AFTER generate_app()
    # RETURNS -- a kill inside generate_app() means that code was never
    # reached at all in this process's lifetime, so there is nothing
    # partial to clean up; assert the stronger, directly-observable fact:
    # no receipt file exists anywhere this run could have written one.
    assert not receipt_path.exists(), (
        "a mid-generate_app() kill must never leave a receipt behind -- Hop 7 only runs after "
        "codegen already fully succeeded and returned"
    )
