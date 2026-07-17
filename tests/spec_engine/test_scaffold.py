"""Tests for spec_engine.scaffold — the spec->scaffold DIRECTION stub."""

from __future__ import annotations

import json

import _spec_engine_paths  # noqa: F401 -- sys.path bootstrap

from spec_engine.approval import record_approval
from spec_engine.intake import harvest_intake
from spec_engine.plan_builder import build_plan
from spec_engine.scaffold import SPEC_DIRECTIVE_MARKER, plan_scaffold_from_spec, write_scaffold_stub
from spec_engine.spec_builder import build_spec


def _spec(text):
    plan = build_plan(harvest_intake(text, "structured_brief"))
    approval = record_approval(plan, approved_by="Xavier")
    return build_spec(plan, approval)


def test_plan_scaffold_pins_codegen_status_not_started():
    spec = _spec("The data model needs a Widget entity (name, price).")
    sp = plan_scaffold_from_spec(spec)
    assert sp.codegen_status == "not_started"


def test_plan_scaffold_derives_one_backend_model_module_per_entity():
    spec = _spec("The data model needs a Widget entity (name, price) and a Gadget entity (label).")
    sp = plan_scaffold_from_spec(spec)
    backend_modules = [m for m in sp.modules if m.kind == "backend-model"]
    assert len(backend_modules) == 2
    assert any("Widget" in m.source_section for m in backend_modules)
    assert any("Gadget" in m.source_section for m in backend_modules)


def test_plan_scaffold_test_suite_module_depends_on_every_other_module():
    spec = _spec(
        "The data model needs a Widget entity (name, price). The app should be able to list widgets."
    )
    sp = plan_scaffold_from_spec(spec)
    test_modules = [m for m in sp.modules if m.kind == "test-suite"]
    assert len(test_modules) == 1
    non_test_ids = {m.module_id for m in sp.modules if m.kind != "test-suite"}
    assert set(test_modules[0].depends_on) == non_test_ids


def test_plan_scaffold_every_module_traces_to_a_real_source_section():
    spec = _spec("The data model needs a Widget entity (name, price).")
    sp = plan_scaffold_from_spec(spec)
    for m in sp.modules:
        assert m.source_section.strip() != ""


def test_write_scaffold_stub_writes_spec_md_and_spec_json_and_scaffold_plan(tmp_path):
    spec = _spec("The data model needs a Widget entity (name, price).")
    written = write_scaffold_stub(spec, tmp_path)

    assert (tmp_path / "SPEC.md").is_file()
    assert (tmp_path / "spec.json").is_file()
    assert (tmp_path / ".spec-engine" / "scaffold-plan.json").is_file()
    assert written["SPEC.md"] == tmp_path / "SPEC.md"

    spec_json = json.loads((tmp_path / "spec.json").read_text(encoding="utf-8"))
    assert spec_json["spec_id"] == spec.spec_id


def test_write_scaffold_stub_writes_the_directive_into_claude_md_and_agents_md(tmp_path):
    spec = _spec("An app that tracks invoices.")
    write_scaffold_stub(spec, tmp_path)
    for filename in ("CLAUDE.md", "AGENTS.md"):
        content = (tmp_path / filename).read_text(encoding="utf-8")
        assert SPEC_DIRECTIVE_MARKER in content
        assert "CODE IS GENERATED FROM" in content


def test_write_scaffold_stub_is_idempotent_and_never_duplicates_the_directive(tmp_path):
    spec = _spec("An app that tracks invoices.")
    write_scaffold_stub(spec, tmp_path)
    write_scaffold_stub(spec, tmp_path)
    content = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert content.count(SPEC_DIRECTIVE_MARKER) == 1


def test_write_scaffold_stub_appends_to_an_existing_claude_md_without_clobbering_it(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# Existing project doctrine\n\nDo not delete this.\n", encoding="utf-8")
    spec = _spec("An app that tracks invoices.")
    write_scaffold_stub(spec, tmp_path)
    content = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Do not delete this." in content
    assert SPEC_DIRECTIVE_MARKER in content
