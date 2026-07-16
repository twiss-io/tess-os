"""Offline checks for the advisory adapter-manifest v1 contract.

This contract is deliberately outside core/contracts and is not a tessctl
trust, gate, policy, signing, key, verifier, or approval input. The test uses
the repository's dependency-free schema subset directly, which reads local
JSON only and does not invoke the CLI, network, subprocesses, or trace writer.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path, PureWindowsPath

import pytest

from conftest import REPO_ROOT


SCHEMA_PATH = REPO_ROOT / "adapters" / "contracts" / "adapter-manifest.schema.json"
MANIFEST_DIR = REPO_ROOT / "adapters" / "manifests"
MANIFEST_NAMES = (
    "claude-code.adapter-manifest.json",
    "codex.adapter-manifest.json",
    "generic.adapter-manifest.json",
    "perplexity.adapter-manifest.json",
)
EXPECTED_CLAIMS = {
    "claude-code": {
        "support_level": "C3",
        "status": "preview",
        "capabilities": {"instruction-rendering", "prompt-artifacts", "config-fragment", "local-process-driver"},
        "render_target": "claude-code",
        "driver": "claude",
    },
    "codex": {
        "support_level": "C2",
        "status": "preview",
        "capabilities": {"instruction-rendering", "prompt-artifacts", "config-fragment", "local-process-driver"},
        "render_target": "codex",
        "driver": "codex",
    },
    "generic": {
        "support_level": "C2",
        "status": "preview",
        "capabilities": {"instruction-rendering", "prompt-artifacts"},
        "render_target": "generic",
        "driver": None,
    },
    "perplexity": {
        "support_level": "C0",
        "status": "not-supported",
        "capabilities": set(),
        "render_target": None,
        "driver": None,
    },
}


def _schema():
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _manifest(name: str):
    return json.loads((MANIFEST_DIR / name).read_text(encoding="utf-8"))


def _evidence_errors(data, root: Path = REPO_ROOT):
    """Validate evidence paths without following a path outside this repo."""
    errors = []
    evidence = data.get("evidence", []) if isinstance(data, dict) else []
    root = root.resolve()
    for index, item in enumerate(evidence):
        path = item.get("path") if isinstance(item, dict) else None
        if not isinstance(path, str):
            continue  # The schema validator reports the malformed shape.
        rel = Path(path)
        if rel.is_absolute() or PureWindowsPath(path).is_absolute() or ".." in rel.parts:
            errors.append(f"$.evidence[{index}].path: {path!r} must be a traversal-free repository-relative path")
            continue
        candidate = root / rel
        try:
            resolved = candidate.resolve()
            resolved.relative_to(root)
        except ValueError:
            errors.append(f"$.evidence[{index}].path: {path!r} resolves outside the repository")
            continue
        if not resolved.is_file():
            errors.append(f"$.evidence[{index}].path: {path!r} must resolve to an existing regular file")
    return errors


def _claim_parity_errors(engine, data):
    """Pin records to the source surfaces present in this checked-in tree."""
    if not isinstance(data, dict):
        return []
    adapter_id = data.get("adapter_id")
    if adapter_id not in EXPECTED_CLAIMS:
        return [f"$.adapter_id: {adapter_id!r} is not an allowlisted adapter manifest id"]
    expected = EXPECTED_CLAIMS[adapter_id]
    errors = []
    for field in ("support_level", "status"):
        if data.get(field) != expected[field]:
            errors.append(f"$.{field}: expected {expected[field]!r} for {data['adapter_id']}")
    if set(data.get("capabilities", [])) != expected["capabilities"]:
        errors.append(f"$.capabilities: do not match the checked-in {data['adapter_id']} surface")
    target = expected["render_target"]
    if target is None and data["adapter_id"] in engine.RENDER_TARGETS:
        errors.append(f"$.adapter_id: {data['adapter_id']} must not claim an absent render target")
    if target is not None and target not in engine.RENDER_TARGETS:
        errors.append(f"$.adapter_id: expected render target {target!r} is absent")
    driver = expected["driver"]
    if driver is None and data["adapter_id"] in engine.RUN_DRIVERS:
        errors.append(f"$.adapter_id: {data['adapter_id']} must not claim an absent local process driver")
    if driver is not None and driver not in engine.RUN_DRIVERS:
        errors.append(f"$.adapter_id: expected local process driver {driver!r} is absent")
    return errors


def _validate(engine, data, root: Path = REPO_ROOT):
    schema = _schema()
    return (
        engine.schema_validate(data, schema, schema, SCHEMA_PATH.parent)
        + _evidence_errors(data, root)
        + _claim_parity_errors(engine, data)
    )


def test_schema_and_shipped_manifests_validate_offline(engine, monkeypatch):
    """The advisory harness has no execution route to a network or subprocess."""
    monkeypatch.setattr(engine.subprocess, "run", lambda *args, **kwargs: pytest.fail("no subprocess"))
    monkeypatch.setattr(engine, "_trace_record", lambda *args, **kwargs: pytest.fail("no trace write"))
    for name in MANIFEST_NAMES:
        assert _validate(engine, _manifest(name)) == [], name


def test_manifest_directory_exactly_matches_the_allowlisted_records():
    assert tuple(sorted(path.name for path in MANIFEST_DIR.iterdir())) == MANIFEST_NAMES


def test_shipped_claims_match_checked_in_adapter_targets_and_drivers(engine):
    assert set(engine.RENDER_TARGETS) >= {"claude-code", "codex", "generic"}
    assert set(engine.RUN_DRIVERS) >= {"claude", "codex"}
    assert "generic" not in engine.RUN_DRIVERS
    assert "perplexity" not in engine.RENDER_TARGETS
    assert "perplexity" not in engine.RUN_DRIVERS
    for name in MANIFEST_NAMES:
        assert _claim_parity_errors(engine, _manifest(name)) == [], name


def test_status_page_retains_manifest_support_labels():
    status = (REPO_ROOT / "docs" / "STATUS.md").read_text(encoding="utf-8")
    for label in (
        "Claude Code target and driver | **C3 — Managed-adapter preview**",
        "Codex target and driver | **C2 — Manual-gated compatibility**",
        "Generic `AGENTS.md` target | **C2 — Manual-gated compatibility**",
        "Perplexity adapter/driver | **C0 — not supported**",
    ):
        assert label in status


def test_c4_and_authority_bearing_fields_are_rejected(engine):
    base = _manifest("codex.adapter-manifest.json")
    c4 = copy.deepcopy(base)
    c4["support_level"] = "C4"
    assert any("C4" in error or "support_level" in error for error in _validate(engine, c4))

    for field in (
        "authority", "access", "approval", "signing", "key", "verifier_registration",
        "protected_workflow", "protected_delivery", "trust_root", "trust_authority",
    ):
        bad = copy.deepcopy(base)
        bad[field] = "self-issued"
        assert any(field in error and "not allowed" in error for error in _validate(engine, bad)), field


def test_unknown_c3_adapter_id_is_rejected_and_cannot_evict_claim_parity(engine):
    unknown = copy.deepcopy(_manifest("claude-code.adapter-manifest.json"))
    unknown["adapter_id"] = "unknown-c3"
    errors = _validate(engine, unknown)
    assert any("not one of" in error or "not allowlisted" in error for error in errors)


def test_authority_bearing_capability_values_and_unknown_fields_are_rejected(engine):
    base = _manifest("codex.adapter-manifest.json")
    for capability in ("authority", "access", "approval", "signing", "key", "verifier-registration"):
        bad = copy.deepcopy(base)
        bad["capabilities"] = [capability]
        assert any(capability in error for error in _validate(engine, bad)), capability

    bad = copy.deepcopy(base)
    bad["undeclared_access"] = True
    assert any("undeclared_access" in error and "not allowed" in error for error in _validate(engine, bad))


def test_missing_and_malformed_required_content_is_rejected(engine):
    base = _manifest("codex.adapter-manifest.json")
    for field in ("schema_version", "adapter_id", "provider", "support_level", "status", "capabilities", "evidence", "limits"):
        bad = copy.deepcopy(base)
        del bad[field]
        assert any(field in error for error in _validate(engine, bad)), field

    malformed = copy.deepcopy(base)
    malformed["evidence"] = {"kind": "repository-source"}
    assert _validate(engine, malformed)


def test_evidence_path_escape_and_missing_file_are_rejected_offline(engine, tmp_path):
    base = _manifest("codex.adapter-manifest.json")
    missing = copy.deepcopy(base)
    missing["evidence"] = [{"kind": "repository-source", "path": "missing.md", "note": "not present"}]
    assert any("existing regular file" in error for error in _validate(engine, missing, tmp_path))

    traversal = copy.deepcopy(base)
    traversal["evidence"] = [{"kind": "repository-source", "path": "../outside.md", "note": "escape"}]
    assert any("traversal-free" in error for error in _validate(engine, traversal, tmp_path))

    absolute = copy.deepcopy(base)
    absolute["evidence"] = [{"kind": "repository-source", "path": str(tmp_path / "absolute.md"), "note": "absolute"}]
    assert any("traversal-free" in error for error in _validate(engine, absolute, tmp_path))

    outside = tmp_path.parent / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    (tmp_path / "escape.md").symlink_to(outside)
    symlink = copy.deepcopy(base)
    symlink["evidence"] = [{"kind": "repository-source", "path": "escape.md", "note": "escape"}]
    assert any("outside the repository" in error for error in _validate(engine, symlink, tmp_path))


def test_c0_cannot_advertise_preview_or_capabilities(engine):
    base = _manifest("perplexity.adapter-manifest.json")
    preview = copy.deepcopy(base)
    preview["status"] = "preview"
    assert any("not-supported" in error for error in _validate(engine, preview))

    capability = copy.deepcopy(base)
    capability["capabilities"] = ["read-only-research"]
    assert any("maxItems" in error for error in _validate(engine, capability))


def test_generic_driver_or_protected_claim_inflation_is_rejected(engine):
    generic = _manifest("generic.adapter-manifest.json")
    driver = copy.deepcopy(generic)
    driver["capabilities"].append("local-process-driver")
    assert any("checked-in generic surface" in error for error in _validate(engine, driver))

    protected = copy.deepcopy(generic)
    protected["support_level"] = "C3"
    assert any("expected 'C2'" in error for error in _validate(engine, protected))
