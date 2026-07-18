"""Tests for the advisory connector-manifest validator
(`connectors/manifest_validator.py`), including the MANDATORY adversarial
proof (d) required by the Connectors v1 build brief:

    (d) the manifest validator REJECTS a manifest containing a secret
        value (only env-var names allowed).

Mirrors `tests/test_adapter_manifest_validator.py`'s fixture-copy pattern.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from conftest import REPO_ROOT
from connectors import manifest_validator as validator
from connectors.validate_connector_manifests import main as cli_main


def _copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(source.read_bytes())


def _fixture_repository(tmp_path: Path) -> Path:
    """A throwaway checkout carrying only what the validator reads: the
    schema + the three real connector manifests (+ their fixtures/README,
    harmless but not required by the validator itself)."""
    root = tmp_path / "repository"
    _copy_file(REPO_ROOT / validator.SCHEMA_PATH, root / validator.SCHEMA_PATH)
    for connector_id in ("anthropic", "openai", "gemini"):
        rel = Path("connectors/registry") / connector_id / "connector.json"
        _copy_file(REPO_ROOT / rel, root / rel)
    return root


def _read_manifest(root: Path, connector_id: str) -> Dict[str, Any]:
    path = root / validator.MANIFEST_DIRECTORY / connector_id / "connector.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _write_manifest(root: Path, connector_id: str, data: Dict[str, Any]) -> None:
    path = root / validator.MANIFEST_DIRECTORY / connector_id / "connector.json"
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------
# The real, checked-in registry is clean
# --------------------------------------------------------------------------


def test_real_registry_is_valid_and_the_validator_is_advisory_only():
    findings = validator.validate_repository(REPO_ROOT)
    assert findings == [], findings


def test_cli_and_api_have_deterministic_advisory_parity(tmp_path, capsys):
    root = _fixture_repository(tmp_path)
    expected = validator.validate_repository(root)
    assert expected == []

    assert cli_main(["--root", str(root), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"advisory": True, "findings": expected, "valid": True}


# --------------------------------------------------------------------------
# MANDATORY adversarial proof (d) — secret VALUES are rejected, not just
# malformed names. Two independent angles: the env-var-NAME-shape check,
# and the whole-manifest secret-shaped-string scan (a value smuggled into
# ANY field, not only auth.env).
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fake_secret",
    [
        "sk-ant-api03-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789AbCdEfGhIjKlMnOpQrSt",
        "sk-proj-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789",
        "AIzaSyAbCdEfGhIjKlMnOpQrStUvWxYz012345678",
        "ghp_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789AB",
    ],
)
def test_secret_value_in_auth_env_is_rejected(tmp_path, fake_secret):
    root = _fixture_repository(tmp_path)
    data = _read_manifest(root, "anthropic")
    data["auth"]["env"] = [fake_secret]
    _write_manifest(root, "anthropic", data)

    findings = validator.validate_repository(root)
    assert findings, "a manifest carrying a secret VALUE in auth.env must fail validation"
    assert any("not an env-var NAME" in f for f in findings)
    assert any("shaped like a real credential" in f for f in findings)
    # And the fake secret's literal bytes never appear in a finding —
    # findings must not themselves leak the offending value verbatim.
    assert not any(fake_secret in f for f in findings)


def test_secret_value_smuggled_into_an_unrelated_field_is_still_rejected(tmp_path):
    """The offending value does NOT have to be in auth.env to be caught —
    the whole-manifest scan (connectors/README.md's "Secret-shaped
    values, rejected — heuristic, not a guarantee") catches a value
    shaped like a real credential no matter where it hides, e.g.
    mistakenly pasted into a free-text description field."""
    root = _fixture_repository(tmp_path)
    data = _read_manifest(root, "openai")
    data["operations"][0]["description"] += (
        " Debug note: my test key is sk-proj-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789."
    )
    _write_manifest(root, "openai", data)

    findings = validator.validate_repository(root)
    assert any("shaped like a real credential" in f for f in findings), findings


def test_env_var_name_shape_is_enforced_even_without_a_known_prefix(tmp_path):
    """An env var name must be SCREAMING_SNAKE_CASE — a lowercase or
    mixed-case string fails even if it happens not to match one of the
    known provider-key prefixes (defense in depth: the shape check does
    not depend on knowing every possible provider's key format)."""
    root = _fixture_repository(tmp_path)
    data = _read_manifest(root, "gemini")
    data["auth"]["env"] = ["not-a-valid-env-var-name"]
    _write_manifest(root, "gemini", data)

    findings = validator.validate_repository(root)
    assert any("not an env-var NAME" in f for f in findings)


def test_validate_manifest_dict_rejects_secret_value_without_any_filesystem(tmp_path):
    """The pure, in-memory entry point (no registry directory needed) —
    proves the check is a property of the manifest CONTENT, not of how it
    was discovered on disk."""
    data = json.loads((REPO_ROOT / "connectors/registry/anthropic/connector.json").read_text())
    data["auth"]["env"] = ["sk-ant-api03-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789AbCdEfGh"]
    findings = validator.validate_manifest_dict(data, expected_id="anthropic")
    assert findings
    assert any("shaped like a real credential" in f for f in findings)


def test_legitimate_env_names_and_error_class_literals_are_never_false_positives():
    """The generic secret-shape heuristic must not flag this schema's OWN
    fixed vocabulary (PascalCase error-class names are exactly the kind of
    mixed-case unbroken 20+ char string a naive heuristic would wrongly
    flag) — regression guard for the false-positive bug caught during
    development of this validator."""
    for connector_id in ("anthropic", "openai", "gemini"):
        data = json.loads((REPO_ROOT / f"connectors/registry/{connector_id}/connector.json").read_text())
        findings = validator.validate_manifest_dict(data, expected_id=connector_id)
        assert findings == [], (connector_id, findings)


# --------------------------------------------------------------------------
# Cyra LOW F2 (PR #84 security review, fix-up round) — the strengthened
# heuristic closes three shapes the original one missed: a lowercase/
# uppercase hex run, an all-uppercase+digit run with no separator, and a
# short (12-19 char) key. Each is proven both directly (unit-level, against
# `_token_is_secret_shaped`) and end-to-end (embedded mid-sentence in a
# free-text manifest field, matching the existing mid-sentence-smuggling
# pattern above).
# --------------------------------------------------------------------------


# Deterministic (seeded) synthetic tokens — never real credentials, and
# never committed anywhere a real secret scanner would need to special-case
# them; chosen purely for their SHAPE.
_HEX40_LOWER_SHAPE = "3a37dfe702393e0fa6c8bbc2a299e490bbed2cf3"
_HEX64_LOWER_SHAPE = "dfc8df07413df4f73ef8c9fcd698014efb68fefd19ae3e8e5df28fb36d4e020e"
_UPPER_DIGIT_NO_SEP_SHAPE = "8FMPHC8RWJAU5I8O4I6S"
_SHORT_LOWER_DIGIT_SHAPE = "f0kit60yj7myag"
_LONG_PURE_ALPHA_HIGH_ENTROPY_SHAPE = "mcblulyaaqpkvjokdpostzfesqgn"


@pytest.mark.parametrize(
    "newly_caught_token",
    [
        pytest.param(_HEX40_LOWER_SHAPE, id="lowercase-hex-40 (GitHub-OAuth-v1-style)"),
        pytest.param(_HEX64_LOWER_SHAPE, id="lowercase-hex-64 (SHA-256-style)"),
        pytest.param(_UPPER_DIGIT_NO_SEP_SHAPE, id="all-uppercase+digit-no-separator"),
        pytest.param(_SHORT_LOWER_DIGIT_SHAPE, id="short (14-char) lowercase+digit-no-separator"),
        pytest.param(_LONG_PURE_ALPHA_HIGH_ENTROPY_SHAPE, id="long (28-char) pure-alpha high-entropy"),
    ],
)
def test_previously_missed_secret_shapes_are_now_caught(newly_caught_token):
    """Direct, unit-level proof each shape Cyra's finding named is now
    flagged by `_token_is_secret_shaped` — independent of where in a
    manifest it might appear."""
    assert validator._token_is_secret_shaped(newly_caught_token), newly_caught_token


@pytest.mark.parametrize(
    "newly_caught_token",
    [
        pytest.param(_HEX40_LOWER_SHAPE, id="lowercase-hex-40 (GitHub-OAuth-v1-style)"),
        pytest.param(_HEX64_LOWER_SHAPE, id="lowercase-hex-64 (SHA-256-style)"),
        pytest.param(_UPPER_DIGIT_NO_SEP_SHAPE, id="all-uppercase+digit-no-separator"),
        pytest.param(_SHORT_LOWER_DIGIT_SHAPE, id="short (14-char) lowercase+digit-no-separator"),
        pytest.param(_LONG_PURE_ALPHA_HIGH_ENTROPY_SHAPE, id="long (28-char) pure-alpha high-entropy"),
    ],
)
def test_previously_missed_secret_shapes_are_caught_when_smuggled_mid_sentence(tmp_path, newly_caught_token):
    """End-to-end proof for each newly-caught shape: pasted mid-sentence
    into a free-text description field (not a bare value, not auth.env) —
    the exact "smuggled past the scan" scenario Cyra's finding describes."""
    root = _fixture_repository(tmp_path)
    data = _read_manifest(root, "openai")
    data["operations"][0]["description"] += (
        f" Debug note: my test key is {newly_caught_token}."
    )
    _write_manifest(root, "openai", data)

    findings = validator.validate_repository(root)
    assert any("shaped like a real credential" in f for f in findings), (newly_caught_token, findings)
    assert not any(newly_caught_token in f for f in findings)


def test_short_single_case_digit_free_token_is_a_disclosed_residual_gap():
    """Honest limitation, locked so it can't silently regress further: a
    SHORT (12-19 char), single-case, digit-free random token — e.g. a
    lowercase-only key with no digits and no separator — is NOT reliably
    caught by this heuristic (Shannon entropy is too noisy to trust below
    the 20-char floor, and it has no digit for the deterministic
    same-case+digit rule to key on). This is the disclosed gap
    connectors/README.md's corrected claim ("secret-SHAPED", not "any
    secret VALUE") exists to be honest about — this test pins the
    behavior so a future change doesn't silently claim more than the
    heuristic actually delivers."""
    short_pure_alpha_token = "qwsxertyplokinjuh"  # 17 chars, single-case, no digit
    assert len(short_pure_alpha_token) < 20
    assert not any(c.isdigit() for c in short_pure_alpha_token)
    assert not validator._token_is_secret_shaped(short_pure_alpha_token)


def test_entropy_threshold_does_not_false_positive_on_real_manifest_identifiers():
    """Calibration proof: every 20+ char unbroken token that actually
    appears anywhere in the three real, checked-in connector manifests
    scores BELOW the entropy threshold — the margin the threshold was
    picked with. Fails loud if a future edit to the real manifests (or to
    the threshold) closes that margin."""
    import re

    token_re = re.compile(r"[A-Za-z0-9_-]{20,}")
    max_observed = 0.0
    for connector_id in ("anthropic", "openai", "gemini"):
        data = json.loads((REPO_ROOT / f"connectors/registry/{connector_id}/connector.json").read_text())
        for value in validator._walk_strings(data):
            for match in token_re.finditer(value):
                token = match.group(0)
                if token in validator._KNOWN_SAFE_LITERALS:
                    continue
                entropy = validator._shannon_entropy_bits_per_char(token)
                max_observed = max(max_observed, entropy)
                assert entropy < validator._ENTROPY_BITS_PER_CHAR_THRESHOLD, (token, entropy)
    assert max_observed > 0.0  # sanity: the corpus actually exercised the check


# --------------------------------------------------------------------------
# Other structural invariants
# --------------------------------------------------------------------------


def test_max_retries_must_be_exactly_zero(tmp_path):
    root = _fixture_repository(tmp_path)
    data = _read_manifest(root, "anthropic")
    data["limits"]["max_retries"] = 2
    _write_manifest(root, "anthropic", data)
    findings = validator.validate_repository(root)
    assert any("MUST be exactly 0" in f for f in findings)


def test_trust_tier_t3_is_unconditionally_rejected(tmp_path):
    root = _fixture_repository(tmp_path)
    data = _read_manifest(root, "anthropic")
    data["trust"]["tier"] = "T3"
    _write_manifest(root, "anthropic", data)
    findings = validator.validate_repository(root)
    assert any("UNREACHABLE" in f for f in findings)


def test_trust_tier_t2_requires_evidence(tmp_path):
    root = _fixture_repository(tmp_path)
    data = _read_manifest(root, "anthropic")
    data["trust"]["tier"] = "T2"
    data["trust"]["evidence"] = []
    _write_manifest(root, "anthropic", data)
    findings = validator.validate_repository(root)
    assert any("requires a non-empty, dated 'evidence' array" in f for f in findings)


def test_vault_capability_scheme_is_reserved_not_implemented(tmp_path):
    root = _fixture_repository(tmp_path)
    data = _read_manifest(root, "anthropic")
    data["auth"]["scheme"] = "vault-capability"
    _write_manifest(root, "anthropic", data)
    findings = validator.validate_repository(root)
    assert any("RESERVED" in f for f in findings)


def test_id_must_match_registry_directory_name(tmp_path):
    root = _fixture_repository(tmp_path)
    data = _read_manifest(root, "anthropic")
    data["id"] = "not-anthropic"
    _write_manifest(root, "anthropic", data)
    findings = validator.validate_repository(root)
    assert any("does not match registry directory" in f for f in findings)


def test_alias_collision_across_connectors_is_rejected(tmp_path):
    root = _fixture_repository(tmp_path)
    data = _read_manifest(root, "openai")
    data["aliases"] = ["claude"]  # already anthropic's alias
    _write_manifest(root, "openai", data)
    findings = validator.validate_repository(root)
    assert any("claimed by both" in f for f in findings)


def test_http_base_url_must_be_https(tmp_path):
    root = _fixture_repository(tmp_path)
    data = _read_manifest(root, "anthropic")
    data["provider"]["base_url"] = "http://api.anthropic.com"
    _write_manifest(root, "anthropic", data)
    findings = validator.validate_repository(root)
    assert any("must be an https:// URL" in f for f in findings)


def test_strict_json_rejects_duplicate_keys(tmp_path):
    root = _fixture_repository(tmp_path)
    path = root / validator.MANIFEST_DIRECTORY / "anthropic" / "connector.json"
    path.write_text('{"id":"anthropic","id":"anthropic"}', encoding="utf-8")
    findings = validator.validate_repository(root)
    assert any("duplicate object key 'id'" in f for f in findings)


def test_missing_manifest_is_a_findable_advisory_failure_not_a_crash(tmp_path):
    root = _fixture_repository(tmp_path)
    (root / validator.MANIFEST_DIRECTORY / "gemini" / "connector.json").unlink()
    findings = validator.validate_repository(root)
    assert any("missing connector.json" in f for f in findings)


def test_symlinked_manifest_is_rejected(tmp_path):
    root = _fixture_repository(tmp_path)
    real = root / validator.MANIFEST_DIRECTORY / "anthropic" / "connector.json"
    real.unlink()
    (root / validator.MANIFEST_DIRECTORY / "openai" / "connector.json").symlink_to
    try:
        real.symlink_to(root / validator.MANIFEST_DIRECTORY / "openai" / "connector.json")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported on this filesystem/platform")
    findings = validator.validate_repository(root)
    assert any("must not be a symlink" in f for f in findings)


def test_valid_run_is_read_only(tmp_path, monkeypatch):
    root = _fixture_repository(tmp_path)

    def forbidden(*args, **kwargs):
        pytest.fail("validator attempted a filesystem mutation")

    for method in ("write_bytes", "write_text", "mkdir", "unlink", "rename", "replace", "chmod"):
        monkeypatch.setattr(Path, method, forbidden)
    assert validator.validate_repository(root) == []
