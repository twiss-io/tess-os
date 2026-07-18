"""THE runnable proof: generate a real app from a real spec and boot it.

This is the acceptance test the build brief asks for directly: "Include a
test that generates from a sample spec and asserts the output is valid +
runnable (run the generated app in a throwaway dir, assert it boots)."

Every generated app + `node` subprocess in this file lives entirely under
pytest's `tmp_path` (a fresh, throwaway directory per test, deleted by
pytest's own retention policy — nothing here writes outside it). No git
operations are performed anywhere in this file or in `spec_engine.codegen`
itself (codegen only writes plain files) — the "git remote remove origin
first" constraint that applies to side-effecting tests touching a REAL git
repo is structurally inapplicable here; there is no repo to have a remote.

Requires a real `node` binary on PATH (Node >=18, for `node:test` +
built-in `fetch()` — see codegen.py's module docstring for why this
target stack was chosen). Skips cleanly (does not fail) if `node` is
unavailable in the environment running the suite.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
import urllib.error
import urllib.request
from shutil import which

import pytest

import _spec_engine_paths  # sys.path bootstrap; EVAL_FIXTURES_DIR used below

from spec_engine.gate_approval import sign_local_approval
from spec_engine.codegen import generate_app
from spec_engine.intake import harvest_intake
from spec_engine.plan_builder import build_plan
from spec_engine.spec_builder import build_spec

HAS_NODE = which("node") is not None
pytestmark = pytest.mark.skipif(not HAS_NODE, reason="node binary not found on PATH")

BOOT_TIMEOUT_SECONDS = 10
_LISTEN_RE = re.compile(r"listening on http://localhost:(\d+)")


def _spec_from_fixture(filename: str):
    """Run a REAL eval fixture through the actual E2 pipeline (intake ->
    plan -> approval -> spec) rather than hand-building a SpecDocument —
    this is the concrete proof of composition with #79 the build brief
    asks for (deliverable 5: "how it composes with #79"), not just a
    codegen-only unit test."""
    text = (_spec_engine_paths.EVAL_FIXTURES_DIR / filename).read_text(encoding="utf-8")
    plan = build_plan(harvest_intake(text, "structured_brief"))
    approval = sign_local_approval(plan, approved_by="Xavier")
    return build_spec(plan, approval)


@pytest.fixture
def node_server():
    """Yields a `start(target_dir, extra_env=None) -> (proc, base_url)`
    helper; always terminates the spawned process (and drains its pipes)
    on teardown, even if the test body raises."""
    import os

    procs = []

    def start(target_dir, extra_env=None):
        env = {**os.environ, "PORT": "0"}
        if extra_env:
            env.update(extra_env)
        proc = subprocess.Popen(
            ["node", str(target_dir / "src" / "server.js")],
            cwd=str(target_dir),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        procs.append(proc)
        deadline = time.monotonic() + BOOT_TIMEOUT_SECONDS
        port = None
        stdout_so_far = ""
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                stderr_out = proc.stderr.read()
                raise AssertionError(
                    f"generated server exited early (code {proc.returncode}) before reporting "
                    f"'listening'. stdout={stdout_so_far!r} stderr={stderr_out!r}"
                )
            line = proc.stdout.readline()
            if not line:
                time.sleep(0.05)
                continue
            stdout_so_far += line
            match = _LISTEN_RE.search(line)
            if match:
                port = int(match.group(1))
                break
        if port is None:
            proc.terminate()
            raise AssertionError(
                f"generated server did not report 'listening' within {BOOT_TIMEOUT_SECONDS}s. "
                f"stdout so far: {stdout_so_far!r}"
            )
        return proc, f"http://localhost:{port}"

    yield start

    for proc in procs:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


def _get(url, timeout=5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def _post(url, payload, timeout=5):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


# --------------------------------------------------------------------------
# THE proof: generate from a real (pipeline-produced) sample spec, boot it,
# assert it is genuinely alive and serving real traffic — then stop it.
# --------------------------------------------------------------------------


def test_generated_app_from_detailed_brief_boots_and_serves(tmp_path, node_server):
    spec = _spec_from_fixture("brief_detailed.txt")
    assert spec.data_model.entities, "sanity check: this fixture must yield at least one entity"

    result = generate_app(spec, tmp_path)
    assert result.scaffold_plan.codegen_status == "generated"

    proc, base_url = node_server(tmp_path)
    try:
        status, body = _get(f"{base_url}/health")
        assert status == 200
        assert body == {"status": "ok"}

        # The process is still alive AFTER answering a real HTTP request —
        # not a fluke single response before an immediate crash.
        assert proc.poll() is None

        first_entity_slug = re.sub(r"[^a-z0-9]+", "-", spec.data_model.entities[0].name.lower()).strip("-")
        status, body = _get(f"{base_url}/api/{first_entity_slug}s")
        assert status == 200
        assert body == []  # freshly booted — in-memory store starts empty
    finally:
        pass  # node_server fixture terminates the process on teardown

    assert proc.poll() is None, "server should still be running until the fixture tears it down"


def test_generated_app_full_crud_round_trip_over_real_http(tmp_path, node_server):
    spec = _spec_from_fixture("brief_detailed.txt")
    generate_app(spec, tmp_path)
    proc, base_url = node_server(tmp_path)

    entity = spec.data_model.entities[0]
    slug = re.sub(r"[^a-z0-9]+", "-", entity.name.lower()).strip("-")
    path = f"{base_url}/api/{slug}s"
    payload = {f.name: f"value-{i}" for i, f in enumerate(entity.fields)}

    status, created = _post(path, payload)
    assert status == 201
    assert "id" in created

    status, fetched = _get(f"{path}/{created['id']}")
    assert status == 200
    assert fetched["id"] == created["id"]

    status, listed = _get(path)
    assert status == 200
    assert any(r["id"] == created["id"] for r in listed)

    status, missing = _get(f"{path}/does-not-exist")
    assert status == 404


def test_generated_app_own_test_suite_passes_when_run_for_real(tmp_path, node_server):
    """Run the GENERATED tests/acceptance.test.js with the real `node
    --test` runner (a separate subprocess, not the boot-check server
    above) — proves the "acceptance_criteria -> generated tests"
    deliverable produces a suite that actually passes, not just files
    that merely exist on disk.

    Invokes `node --test` with the EXPLICIT file path (matching
    `spec_engine.codegen.ACCEPTANCE_TEST_REL_PATH`, and exactly what the
    generated `package.json`'s own "test" script runs), never a bare
    `tests/` directory: `node --test <directory>`'s built-in
    test-discovery is not stable across Node versions — verified
    empirically to pass on Node 20 and fail with MODULE_NOT_FOUND on Node
    22.23.1 for the identical generated tree. An explicit file path
    sidesteps that version-dependent discovery logic."""
    from spec_engine.codegen import ACCEPTANCE_TEST_REL_PATH

    spec = _spec_from_fixture("brief_voice_ramble.txt")
    generate_app(spec, tmp_path)

    result = subprocess.run(
        ["node", "--test", ACCEPTANCE_TEST_REL_PATH],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=30,
    )
    combined = result.stdout + result.stderr
    assert result.returncode == 0, f"generated test suite failed:\n{combined}"
    assert "# fail 0" in combined, combined
    assert "# pass" in combined and "# pass 0" not in combined, combined


def test_generated_app_all_route_kinds_respond_over_real_http(tmp_path, node_server):
    """A richer spec — entities, screens, flows, AND integrations all
    present — boots and every route KIND is reachable over real HTTP:
    a frontend page (HTML), an entity API (JSON CRUD), a flow endpoint
    (executes for real), and an integration stub (honest HTTP 501, not a
    silent 404 or a fake 200)."""
    from spec_engine.content import (
        DataModel,
        Entity,
        EntityField,
        HowItLooks,
        HowItWorks,
        KeyFlow,
        KeyScreen,
        WhatItDoes,
        new_id,
        utc_now_iso,
    )
    from spec_engine.connector_resolver import resolve_connectors
    from spec_engine.types import Plan

    plan = Plan(
        plan_id=new_id("plan"),
        mission_id=None,
        created_at=utc_now_iso(),
        source_type="structured_brief",
        input_excerpt="Invoice nudge app",
        what_it_does=WhatItDoes(summary="Nudges clients about unpaid invoices."),
        how_it_looks=HowItLooks(
            description="Simple dashboard.",
            key_screens=[KeyScreen(name="Invoice Dashboard", description="Lists invoices.")],
        ),
        how_it_works=HowItWorks(
            description="Polls invoice status and nudges.",
            key_flows=[KeyFlow(name="Send Reminder", steps=["Find overdue invoices", "Send reminder"])],
            integrations=["Stripe"],
        ),
        data_model=DataModel(entities=[Entity(name="Invoice", fields=[EntityField(name="amount", type="number")])]),
        acceptance_criteria=["Invoice dashboard lists all invoices"],
        summary_for_approval="summary",
        resolved_connectors=resolve_connectors(["Stripe"]),  # not registered -> unresolved, same as before
    )
    approval = sign_local_approval(plan, approved_by="Xavier")
    spec = build_spec(plan, approval)

    generate_app(spec, tmp_path)
    proc, base_url = node_server(tmp_path)

    # Frontend page — real HTML.
    req = urllib.request.Request(f"{base_url}/invoice-dashboard")
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200
        html = resp.read().decode("utf-8")
        assert "<html>" in html and "Invoice Dashboard" in html

    # Entity API — real JSON CRUD.
    status, created = _post(f"{base_url}/api/invoices", {"amount": 42})
    assert status == 201
    assert created["amount"] == 42

    # Flow endpoint — real execution (step trace), not a 404.
    status, flow_result = _post(f"{base_url}/api/flows/send-reminder", {})
    assert status == 200
    assert flow_result["flow"] == "Send Reminder"
    assert len(flow_result["steps"]) == 2

    # Integration stub — honest 501, not a silent 404 or a fake 200.
    status, integration_result = _post(f"{base_url}/api/integrations/stripe", {})
    assert status == 501
    assert integration_result["status"] == "not_implemented"

    assert proc.poll() is None
