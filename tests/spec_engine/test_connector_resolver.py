"""Tests for spec_engine.connector_resolver — the plan-time resolution of
`how_it_works.integrations` against the connector registry
(docs/design/connectors-architecture.md §6.2).
"""

from __future__ import annotations

import json

import _spec_engine_paths  # noqa: F401 -- sys.path bootstrap

from spec_engine.connector_resolver import default_registry_root, load_registry, resolve_connectors


def _write_manifest(root, connector_id, **overrides):
    manifest = {
        "manifest_version": "connector-manifest.v1",
        "id": connector_id,
        "version": "0.1.0",
        "display_name": connector_id.capitalize(),
        "aliases": [],
        "provider": {
            "base_url": "https://api.example.com",
            "api_version_pin": {"kind": "header", "name": "x-version", "value": "1"},
        },
        "auth": {"scheme": "env", "env": [f"{connector_id.upper()}_API_KEY"], "header": {"name": "x-api-key"}},
        "operations": [
            {
                "name": "generate",
                "description": "d",
                "side_effect": "spend",
                "idempotent": False,
                "http": {"method": "POST", "path": "/v1/generate"},
                "input_schema": {"fields": []},
                "output_schema": {"fields": []},
            }
        ],
        "data_flows": ["x"],
        "error_map": {"401": "ConnectorAuthError"},
        "limits": {"timeout_ms": 5000, "max_retries": 0},
        "trust": {"tier": "T0", "evidence": []},
    }
    manifest.update(overrides)
    entry_dir = root / connector_id
    entry_dir.mkdir(parents=True, exist_ok=True)
    (entry_dir / "connector.json").write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


# --------------------------------------------------------------------------
# Real registry — the exact three v1 connectors
# --------------------------------------------------------------------------


def test_default_registry_root_points_at_the_real_connectors_directory():
    root = default_registry_root()
    assert root.name == "registry"
    assert (root / "anthropic" / "connector.json").is_file()
    assert (root / "openai" / "connector.json").is_file()
    assert (root / "gemini" / "connector.json").is_file()


def test_resolves_exact_id_and_declared_alias_against_the_real_registry():
    resolved = resolve_connectors(["Anthropic", "claude", "OpenAI", "gpt", "Google Gemini", "google-gemini"])
    assert [r.status for r in resolved] == ["resolved"] * 6
    assert [r.connector_id for r in resolved] == ["anthropic", "anthropic", "openai", "openai", "gemini", "gemini"]


def test_unresolved_integration_carries_every_registered_connector_id():
    resolved = resolve_connectors(["Stripe"])
    assert len(resolved) == 1
    assert resolved[0].status == "unresolved"
    assert resolved[0].connector_id is None
    assert resolved[0].registered_connector_ids == ["anthropic", "gemini", "openai"]


def test_resolution_is_1to1_positionally_aligned_with_input_order():
    resolved = resolve_connectors(["Stripe", "Anthropic", "Notion"])
    assert [r.integration_name for r in resolved] == ["Stripe", "Anthropic", "Notion"]
    assert [r.status for r in resolved] == ["unresolved", "resolved", "unresolved"]


def test_empty_integrations_list_resolves_to_empty_list():
    assert resolve_connectors([]) == []


# --------------------------------------------------------------------------
# Match rule — EXACT slug/alias only, deliberately stricter than entity
# fuzzy-matching (design §6.2): a false negative (unresolved) is safe; a
# false positive would wire a real external call to the wrong provider.
# --------------------------------------------------------------------------


def test_match_rule_is_exact_never_fuzzy_or_substring(tmp_path):
    registry_root = tmp_path / "registry"
    _write_manifest(registry_root, "anthropic")
    # A near-miss that a substring/fuzzy matcher WOULD catch must NOT resolve.
    for near_miss in ("Anthropic AI", "Anthropic-ish", "The Anthropic Model", "anthropicx"):
        resolved = resolve_connectors([near_miss], registry_root=registry_root)
        assert resolved[0].status == "unresolved", near_miss


def test_match_is_case_and_punctuation_insensitive_via_slugification(tmp_path):
    registry_root = tmp_path / "registry"
    _write_manifest(registry_root, "anthropic")
    resolved = resolve_connectors(["ANTHROPIC", "Anthropic!", "  anthropic  "], registry_root=registry_root)
    assert [r.status for r in resolved] == ["resolved"] * 3


# --------------------------------------------------------------------------
# Defensive parsing — a malformed/incomplete registry entry never crashes
# plan-building; it is simply treated as unusable (unresolved).
# --------------------------------------------------------------------------


def test_malformed_manifest_is_treated_as_unresolved_not_a_crash(tmp_path):
    registry_root = tmp_path / "registry"
    entry = registry_root / "broken"
    entry.mkdir(parents=True)
    (entry / "connector.json").write_text("{not valid json", encoding="utf-8")
    resolved = resolve_connectors(["Broken"], registry_root=registry_root)
    assert resolved[0].status == "unresolved"


def test_manifest_with_id_mismatching_directory_is_excluded(tmp_path):
    registry_root = tmp_path / "registry"
    _write_manifest(registry_root, "anthropic", id="not-anthropic")
    resolved = resolve_connectors(["Anthropic"], registry_root=registry_root)
    assert resolved[0].status == "unresolved"
    assert resolved[0].registered_connector_ids == []


def test_unsupported_auth_scheme_cannot_be_resolved(tmp_path):
    registry_root = tmp_path / "registry"
    _write_manifest(registry_root, "vaulty", auth={"scheme": "vault-capability", "env": [], "header": {"name": "x"}})
    resolved = resolve_connectors(["Vaulty"], registry_root=registry_root)
    assert resolved[0].status == "unresolved"


def test_nonexistent_registry_root_resolves_everything_unresolved(tmp_path):
    resolved = resolve_connectors(["Anthropic"], registry_root=tmp_path / "does-not-exist")
    assert resolved[0].status == "unresolved"
    assert resolved[0].registered_connector_ids == []


# --------------------------------------------------------------------------
# Determinism — same integrations + same registry bytes -> byte-identical
# ResolvedConnector snapshots (manifest_hash in particular).
# --------------------------------------------------------------------------


def test_resolution_is_deterministic_same_registry_same_hash():
    a = resolve_connectors(["Anthropic"])
    b = resolve_connectors(["Anthropic"])
    assert a[0].manifest_hash == b[0].manifest_hash
    assert a == b


def test_manifest_hash_changes_when_manifest_content_changes(tmp_path):
    registry_root = tmp_path / "registry"
    _write_manifest(registry_root, "anthropic")
    first = resolve_connectors(["Anthropic"], registry_root=registry_root)[0]

    _write_manifest(registry_root, "anthropic", version="0.2.0")
    second = resolve_connectors(["Anthropic"], registry_root=registry_root)[0]

    assert first.manifest_hash != second.manifest_hash
    assert first.connector_version == "0.1.0"
    assert second.connector_version == "0.2.0"


def test_load_registry_only_includes_id_matching_entries(tmp_path):
    registry_root = tmp_path / "registry"
    _write_manifest(registry_root, "good")
    _write_manifest(registry_root, "bad", id="mismatched")
    registry = load_registry(registry_root)
    assert set(registry.keys()) == {"good"}
