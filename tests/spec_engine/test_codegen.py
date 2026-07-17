"""Tests for spec_engine.codegen — the spec->scaffold DIRECTION stub
continued into real, runnable code generation (Phase 1 Epic E2's
`ScaffoldPlan` consumed by the codegen slice of Phase 2 Epic E4).

Node-boot-proof tests (spawning the generated app as a real subprocess)
live in `test_codegen_app_boots.py` — this file covers everything
verifiable WITHOUT starting a Node process: file tree shape, honest
per-module manifest labeling, the plan/spec mismatch guards, determinism,
and schema validity of the two artifacts codegen writes
(`.spec-engine/scaffold-plan.json`, `.spec-engine/codegen-manifest.json`).
"""

from __future__ import annotations

import json

import _spec_engine_paths  # noqa: F401 -- sys.path bootstrap

from spec_engine.approval import record_approval
from spec_engine.codegen import (
    DEFAULT_TARGET_STACK,
    GENERATION_STATUSES,
    SUPPORTED_TARGET_STACKS,
    generate_app,
)
from spec_engine.content import (
    DataModel,
    Entity,
    EntityField,
    HowItLooks,
    HowItWorks,
    KeyFlow,
    KeyScreen,
    SpecEngineError,
    WhatItDoes,
    new_id,
    utc_now_iso,
)
from spec_engine.intake import harvest_intake
from spec_engine.plan_builder import build_plan
from spec_engine.scaffold import plan_scaffold_from_spec
from spec_engine.spec_builder import build_spec
from spec_engine.spec_check import validate
from spec_engine.types import Plan, SpecDocument


def _spec(text):
    plan = build_plan(harvest_intake(text, "structured_brief"))
    approval = record_approval(plan, approved_by="Xavier")
    return build_spec(plan, approval)


def _rich_spec() -> SpecDocument:
    """A hand-built spec exercising every ScaffoldModule kind: entities,
    screens, flows, AND integrations (the deterministic intake heuristics
    in the fixtures rarely populate all four at once — this is the same
    "purely-additive supplement" shape ModelAssistedHarvest documents,
    just constructed directly for test determinism)."""
    plan = Plan(
        plan_id=new_id("plan"),
        mission_id=None,
        created_at=utc_now_iso(),
        source_type="structured_brief",
        input_excerpt="Invoice nudge app",
        what_it_does=WhatItDoes(
            summary="Nudges clients about unpaid invoices.",
            goals=["Reduce late payments"],
            user_stories=["As an admin I can see overdue invoices"],
        ),
        how_it_looks=HowItLooks(
            description="Simple dashboard.",
            key_screens=[
                KeyScreen(name="Invoice Dashboard", description="Lists invoices with status."),
                KeyScreen(name="Client Directory", description="Lists clients."),
            ],
            design_references=[],
        ),
        how_it_works=HowItWorks(
            description="Polls invoice status and nudges.",
            key_flows=[
                KeyFlow(
                    name="Send Reminder",
                    steps=["Find overdue invoices", "Compose reminder email", "Send via provider"],
                )
            ],
            integrations=["Stripe", "SendGrid"],
        ),
        data_model=DataModel(
            entities=[
                Entity(
                    name="Invoice",
                    fields=[
                        EntityField(name="client_id"),
                        EntityField(name="amount", type="number"),
                        EntityField(name="due_date", type="date"),
                        EntityField(name="paid", type="boolean"),
                    ],
                    relationships=["belongs to Client"],
                ),
                Entity(name="Client", fields=[EntityField(name="name"), EntityField(name="email")]),
            ]
        ),
        non_goals=["No multi-currency support"],
        acceptance_criteria=[
            "Invoice dashboard lists all invoices",
            "Client can be created and appears in directory",
            "Unrelated criterion with no entity mention",
        ],
        open_questions=[],
        routing_context=None,
        summary_for_approval="summary",
    )
    approval = record_approval(plan, approved_by="Xavier")
    return build_spec(plan, approval)


# --------------------------------------------------------------------------
# Basic shape / codegen_status
# --------------------------------------------------------------------------


def test_generate_app_sets_codegen_status_generated(tmp_path):
    spec = _spec("The data model needs a Widget entity (name, price).")
    result = generate_app(spec, tmp_path)
    assert result.scaffold_plan.codegen_status == "generated"


def test_generate_app_writes_scaffold_plan_json_with_generated_status(tmp_path):
    spec = _spec("The data model needs a Widget entity (name, price).")
    generate_app(spec, tmp_path)
    on_disk = json.loads((tmp_path / ".spec-engine" / "scaffold-plan.json").read_text(encoding="utf-8"))
    assert on_disk["codegen_status"] == "generated"


def test_generate_app_still_writes_spec_md_and_directive(tmp_path):
    spec = _spec("The data model needs a Widget entity (name, price).")
    generate_app(spec, tmp_path)
    assert (tmp_path / "SPEC.md").is_file()
    assert (tmp_path / "spec.json").is_file()
    for filename in ("CLAUDE.md", "AGENTS.md"):
        assert "CODE IS GENERATED FROM" in (tmp_path / filename).read_text(encoding="utf-8")


def test_generate_app_writes_one_model_file_per_entity(tmp_path):
    spec = _spec("The data model needs a Widget entity (name, price) and a Gadget entity (label).")
    result = generate_app(spec, tmp_path)
    assert (tmp_path / "src" / "models" / "widget.js").is_file()
    assert (tmp_path / "src" / "models" / "gadget.js").is_file()
    assert "src/models/widget.js" in result.written
    assert "src/models/gadget.js" in result.written


def test_generate_app_writes_infrastructure_files(tmp_path):
    spec = _spec("The data model needs a Widget entity (name, price).")
    generate_app(spec, tmp_path)
    for rel in ("src/server.js", "src/http-util.js", "package.json", "README.md", "tests/acceptance.test.js"):
        assert (tmp_path / rel).is_file(), rel


def test_generate_app_all_module_kinds_produce_files(tmp_path):
    spec = _rich_spec()
    result = generate_app(spec, tmp_path)
    assert (tmp_path / "src" / "models" / "invoice.js").is_file()
    assert (tmp_path / "src" / "models" / "client.js").is_file()
    assert (tmp_path / "src" / "pages" / "invoice-dashboard.js").is_file()
    assert (tmp_path / "src" / "pages" / "client-directory.js").is_file()
    assert (tmp_path / "src" / "flows" / "send-reminder.js").is_file()
    assert (tmp_path / "src" / "integrations" / "stripe.js").is_file()
    assert (tmp_path / "src" / "integrations" / "sendgrid.js").is_file()
    assert "src/flows/send-reminder.js" in result.written


# --------------------------------------------------------------------------
# Honest per-module labeling (the manifest)
# --------------------------------------------------------------------------


def test_manifest_labels_backend_model_and_frontend_page_and_test_suite_as_generated(tmp_path):
    spec = _rich_spec()
    result = generate_app(spec, tmp_path)
    by_kind = {}
    for m in result.manifest["modules"]:
        by_kind.setdefault(m["kind"], []).append(m)
    assert all(m["generation_status"] == "generated" for m in by_kind["backend-model"])
    assert all(m["generation_status"] == "generated" for m in by_kind["frontend-page"])
    assert all(m["generation_status"] == "generated" for m in by_kind["test-suite"])


def test_manifest_labels_service_flow_as_generated_stub_logic_not_overclaimed(tmp_path):
    spec = _rich_spec()
    result = generate_app(spec, tmp_path)
    flow_modules = [m for m in result.manifest["modules"] if m["kind"] == "service"]
    assert flow_modules
    assert all(m["generation_status"] == "generated-stub-logic" for m in flow_modules)


def test_manifest_labels_integration_as_stub_never_generated(tmp_path):
    spec = _rich_spec()
    result = generate_app(spec, tmp_path)
    integration_modules = [m for m in result.manifest["modules"] if m["kind"] == "integration"]
    assert len(integration_modules) == 2
    assert all(m["generation_status"] == "stub" for m in integration_modules)
    # No overclaiming: never "generated" for a module codegen cannot make real.
    assert all(m["generation_status"] != "generated" for m in integration_modules)


def test_manifest_every_module_generation_status_is_a_recognized_value(tmp_path):
    spec = _rich_spec()
    result = generate_app(spec, tmp_path)
    for m in result.manifest["modules"]:
        assert m["generation_status"] in GENERATION_STATUSES


def test_manifest_infrastructure_files_are_not_attributed_to_a_source_section(tmp_path):
    spec = _spec("The data model needs a Widget entity (name, price).")
    result = generate_app(spec, tmp_path)
    assert "src/server.js" in result.manifest["infrastructure_files"]
    assert "src/http-util.js" in result.manifest["infrastructure_files"]
    module_files = {f for m in result.manifest["modules"] for f in m["files"]}
    assert "src/server.js" not in module_files


def test_manifest_written_to_disk_matches_returned_manifest(tmp_path):
    spec = _rich_spec()
    result = generate_app(spec, tmp_path)
    on_disk = json.loads((tmp_path / ".spec-engine" / "codegen-manifest.json").read_text(encoding="utf-8"))
    assert on_disk == result.manifest


# --------------------------------------------------------------------------
# Schema validity of both artifacts
# --------------------------------------------------------------------------


def test_scaffold_plan_json_validates_against_schema(tmp_path):
    schema = json.loads(_spec_engine_paths.SCHEMA_DIR.joinpath("scaffold-plan.schema.json").read_text(encoding="utf-8"))
    spec = _rich_spec()
    result = generate_app(spec, tmp_path)
    validate(result.scaffold_plan.to_log_record(), schema)  # raises on failure


def test_codegen_manifest_json_validates_against_schema(tmp_path):
    schema = json.loads(_spec_engine_paths.SCHEMA_DIR.joinpath("codegen-manifest.schema.json").read_text(encoding="utf-8"))
    spec = _rich_spec()
    result = generate_app(spec, tmp_path)
    validate(result.manifest, schema)  # raises on failure


# --------------------------------------------------------------------------
# Fail-loud guards
# --------------------------------------------------------------------------


def test_generate_app_rejects_unsupported_target_stack(tmp_path):
    spec = _spec("The data model needs a Widget entity (name, price).")
    try:
        generate_app(spec, tmp_path, target_stack="rails-postgres")
        assert False, "expected SpecEngineError"
    except SpecEngineError as e:
        assert "target_stack" in str(e)


def test_generate_app_rejects_scaffold_plan_from_a_different_spec(tmp_path):
    spec_a = _spec("The data model needs a Widget entity (name, price).")
    spec_b = _spec("The data model needs a Gadget entity (label).")
    plan_for_b = plan_scaffold_from_spec(spec_b)
    try:
        generate_app(spec_a, tmp_path, scaffold_plan=plan_for_b)
        assert False, "expected SpecEngineError"
    except SpecEngineError as e:
        assert "does not match spec" in str(e)


def test_generate_app_default_target_stack_is_supported():
    assert DEFAULT_TARGET_STACK in SUPPORTED_TARGET_STACKS


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------


def test_generate_app_is_deterministic_given_a_fixed_plan(tmp_path):
    spec = _rich_spec()
    plan = plan_scaffold_from_spec(spec, target_stack=DEFAULT_TARGET_STACK)
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    generate_app(spec, dir_a, scaffold_plan=plan)
    generate_app(spec, dir_b, scaffold_plan=plan)

    files_a = sorted(p.relative_to(dir_a).as_posix() for p in dir_a.rglob("*") if p.is_file())
    files_b = sorted(p.relative_to(dir_b).as_posix() for p in dir_b.rglob("*") if p.is_file())
    assert files_a == files_b
    for rel in files_a:
        assert (dir_a / rel).read_text(encoding="utf-8") == (dir_b / rel).read_text(encoding="utf-8"), rel
