"""Tests for the connectors v1 codegen seam (spec_engine.codegen) that do
NOT require booting a real Node process — see
test_codegen_connectors_boot.py for the real-HTTP round-trip proof.

Covers MANDATORY adversarial/repro test (a): an unresolved integration
still emits the labeled 501 stub, UNCHANGED — plus the honest per-module
manifest labeling, the shared runtime file's conditional presence, and the
codegen<->registry consistency guards.
"""

from __future__ import annotations

import json

import _spec_engine_paths  # noqa: F401 -- sys.path bootstrap

from spec_engine.connector_resolver import resolve_connectors
from spec_engine.content import (
    DataModel,
    HowItLooks,
    HowItWorks,
    SpecEngineError,
    WhatItDoes,
    new_id,
    utc_now_iso,
)
from spec_engine.codegen import GENERATION_STATUSES, _CONNECTOR_RUNTIME_REL_PATH, generate_app
from spec_engine.gate_approval import sign_local_approval
from spec_engine.spec_builder import build_spec
from spec_engine.spec_check import validate
from spec_engine.types import Plan


def _spec_with_integrations(integration_names):
    plan = Plan(
        plan_id=new_id("plan"),
        mission_id=None,
        created_at=utc_now_iso(),
        source_type="structured_brief",
        input_excerpt="An app with integrations",
        what_it_does=WhatItDoes(summary="An app."),
        how_it_looks=HowItLooks(),
        how_it_works=HowItWorks(integrations=list(integration_names)),
        data_model=DataModel(),
        summary_for_approval="summary",
        resolved_connectors=resolve_connectors(integration_names),
    )
    approval = sign_local_approval(plan, approved_by="Xavier")
    return build_spec(plan, approval)


# --------------------------------------------------------------------------
# MANDATORY (a) — an unresolved integration still emits the 501 stub,
# UNCHANGED from today's pre-connectors behavior.
# --------------------------------------------------------------------------


def test_unresolved_integration_still_emits_the_labeled_501_stub(tmp_path):
    spec = _spec_with_integrations(["Stripe"])
    result = generate_app(spec, tmp_path)

    stub_path = tmp_path / "src" / "integrations" / "stripe.js"
    assert stub_path.is_file()
    source = stub_path.read_text(encoding="utf-8")
    assert "IntegrationNotImplementedError" in source
    assert "async function call()" in source  # the exact unchanged no-arg stub signature

    integration_modules = [m for m in result.manifest["modules"] if m["kind"] == "integration"]
    assert len(integration_modules) == 1
    assert integration_modules[0]["generation_status"] == "stub"
    assert integration_modules[0]["connector"] is None
    assert "no registered connector matched" in integration_modules[0]["notes"]
    assert "anthropic" in integration_modules[0]["notes"]  # registered ids listed, per design §6.2


def test_unresolved_integration_never_writes_the_shared_connector_runtime(tmp_path):
    spec = _spec_with_integrations(["Stripe"])
    generate_app(spec, tmp_path)
    assert not (tmp_path / _CONNECTOR_RUNTIME_REL_PATH).exists()


def test_mixed_resolved_and_unresolved_integrations_each_get_correct_treatment(tmp_path):
    spec = _spec_with_integrations(["Anthropic", "Stripe"])
    result = generate_app(spec, tmp_path)

    assert (tmp_path / "src" / "integrations" / "anthropic.js").is_file()
    assert (tmp_path / "src" / "integrations" / "stripe.js").is_file()
    assert (tmp_path / _CONNECTOR_RUNTIME_REL_PATH).is_file()  # written because >=1 resolved

    by_slug = {m["files"][0].rsplit("/", 1)[-1]: m for m in result.manifest["modules"] if m["kind"] == "integration"}
    assert by_slug["anthropic.js"]["generation_status"] == "generated-connector"
    assert by_slug["stripe.js"]["generation_status"] == "stub"


# --------------------------------------------------------------------------
# generation_status vocabulary + honest manifest labeling for the resolved
# case
# --------------------------------------------------------------------------


def test_generated_connector_is_a_recognized_generation_status():
    assert "generated-connector" in GENERATION_STATUSES


def test_resolved_connector_manifest_entry_records_the_full_surface(tmp_path):
    spec = _spec_with_integrations(["Anthropic"])
    result = generate_app(spec, tmp_path)
    module = next(m for m in result.manifest["modules"] if m["kind"] == "integration")

    assert module["generation_status"] == "generated-connector"
    assert module["connector"]["connector_id"] == "anthropic"
    assert module["connector"]["connector_version"] == "0.1.0"
    assert len(module["connector"]["manifest_hash"]) == 64  # sha256 hex
    assert module["connector"]["operations"] == ["generate"]
    assert module["connector"]["env_vars"] == ["ANTHROPIC_API_KEY"]
    assert module["connector"]["side_effect_classes"] == ["spend"]
    assert "generation_status" != "generated"  # sanity: never silently upgraded to plain "generated"


def test_codegen_manifest_json_validates_against_schema_with_a_resolved_connector(tmp_path):
    spec = _spec_with_integrations(["Anthropic", "Stripe"])
    result = generate_app(spec, tmp_path)
    schema = json.loads(_spec_engine_paths.SCHEMA_DIR.joinpath("codegen-manifest.schema.json").read_text(encoding="utf-8"))
    validate(result.manifest, schema)  # raises on failure

    on_disk = json.loads((tmp_path / ".spec-engine" / "codegen-manifest.json").read_text(encoding="utf-8"))
    assert on_disk == result.manifest


def test_app_readme_documents_the_resolved_connector_env_var(tmp_path):
    spec = _spec_with_integrations(["Anthropic"])
    generate_app(spec, tmp_path)
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "ANTHROPIC_API_KEY" in readme
    assert "503" in readme


# --------------------------------------------------------------------------
# Fail-loud guards
# --------------------------------------------------------------------------


def test_resolved_connectors_length_mismatch_with_integrations_fails_loud(tmp_path):
    import dataclasses

    spec = _spec_with_integrations(["Anthropic"])
    tampered = dataclasses.replace(spec, resolved_connectors=[])
    try:
        generate_app(tampered, tmp_path)
        assert False, "expected SpecEngineError"
    except SpecEngineError as e:
        assert "resolved_connectors" in str(e)
    assert not (tmp_path / "src").exists()


def test_resolved_connector_id_with_no_codegen_template_fails_loud(tmp_path):
    """A registry-only 4th connector (no matching codegen.py template) must
    fail loud at generate time, never silently fall back to a stub or
    guess a client shape — design §11 non-goal."""
    import dataclasses

    from spec_engine.content import ResolvedConnector, ResolvedConnectorOperation

    spec = _spec_with_integrations(["Anthropic"])
    phantom = ResolvedConnector(
        integration_name="Anthropic",
        status="resolved",
        connector_id="totally-unregistered-4th-connector",
        connector_version="0.1.0",
        manifest_hash="a" * 64,
        auth_env_vars=["SOME_KEY"],
        auth_header_name="x-api-key",
        base_url="https://example.com",
        operations=[ResolvedConnectorOperation(name="generate", side_effect="spend", http_method="POST", http_path="/x")],
    )
    tampered = dataclasses.replace(spec, resolved_connectors=[phantom])
    try:
        generate_app(tampered, tmp_path)
        assert False, "expected SpecEngineError"
    except SpecEngineError as e:
        assert "no generated-client template" in str(e)
