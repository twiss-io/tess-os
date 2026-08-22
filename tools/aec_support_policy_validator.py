"""Offline validation for the advisory AEC support-policy template.

This module validates documentation contracts only.  It has no provider,
credential, network, subprocess, write, gate, approval, or ``--fix`` path.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple


SCHEMA_PATH = Path("adapters/contracts/aec-support-policy.schema.json")
POLICY_PATH = Path("adapters/support-policy/aec-support-policy.template.json")
ADR_PATH = Path("docs/AEC_GOVERNANCE_DEFAULTS.md")

_TOP_FIELDS = {
    "schema_version",
    "document_status",
    "runtime_enforcement_status",
    "default_assurance",
    "security_tiers",
    "trust_boundary",
    "data_defaults",
    "retention",
    "provider_execution",
    "credentials",
    "cost",
    "products",
}
_STATUS_LABELS = {"available", "preview", "planned", "unsupported"}
_COMPLETENESS = {"AEC-C0", "AEC-C1", "AEC-C2", "AEC-C3", "AEC-C4"}
_TRUST = {"T0", "T1", "T2", "T3"}

_TIER_DEFAULTS: Dict[str, Tuple[str, str]] = {
    "local-informational": ("AEC-C1", "T0"),
    "auditable-non-protected": ("AEC-C2", "T1"),
    "protected-repository": ("AEC-C3", "T2"),
    "release-high-security": ("AEC-C4", "T3"),
}
_HIGH_ASSURANCE_EVIDENCE: Dict[str, Set[str]] = {
    "protected-repository": {
        "runtime-identity",
        "workspace-before-after",
        "tool-call-outcomes",
        "independent-execution-receipt",
        "immutable-artifact-binding",
    },
    "release-high-security": {
        "runtime-identity",
        "workspace-before-after",
        "tool-call-outcomes",
        "independent-execution-receipt",
        "immutable-artifact-binding",
        "independent-conformance",
        "human-owned-trust-anchor",
        "vcs-required-check",
        "candidate-cannot-self-authorize",
        "published-audit-summary",
    },
}
_SENSITIVE_PATHS = {
    "clients/**",
    "kb/**",
    ".tess/state/**",
    "operator/**",
    "**/vault/**",
    ".tess/keys/**",
    ".tess/gate/signoffs/**",
}
_SENSITIVE_CATEGORIES = {
    "raw-prompt",
    "raw-tool-result",
    "secret-value",
    "credential-material",
    "private-key",
    "access-token",
    "refresh-token",
    "session-cookie",
    "unredacted-client-content",
}
_PROVIDER_DECLARATIONS = {"endpoint", "region", "provider-retention-mode", "tool-profile"}
_NONZERO_BUDGET_DECLARATIONS = {"explicit-owner", "per-run-budget", "cost-scope"}
_PRODUCT_CONTROLS: Dict[str, Set[str]] = {
    "advanced_memory": {
        "classification",
        "tenant-isolation",
        "retention",
        "verified-deletion",
        "retrieval-scope",
        "incident-response",
    },
    "tess_cloud": {
        "tenancy",
        "encryption-custody",
        "classification",
        "residency",
        "retention",
        "verified-deletion",
        "incident-response",
        "export",
    },
    "tess_vault": {
        "tenancy",
        "custody",
        "recovery",
        "rotation",
        "revocation",
        "scoped-reference-resolution",
        "audit",
        "verified-deletion",
        "incident-response",
    },
}

_DOC_MARKERS: Dict[Path, Tuple[str, ...]] = {
    Path("README.md"): (
        "| Agent Execution Contract governance defaults | **Planned** |",
        "| Tess Cloud | **Planned** |",
        "| Tess Vault | **Planned** |",
    ),
    Path("docs/STATUS.md"): (
        "| AEC runtime assurance grading and enforcement | **Planned** |",
        "| Advanced retrieval memory | **Planned** |",
        "| Tess Cloud | **Planned** |",
        "| Tess Vault | **Planned** |",
    ),
    ADR_PATH: (
        "**Decision status: accepted. Implementation status: planned.**",
        "Both products remain **planned and disabled**.",
    ),
}
_PLANNED_ONLY_TABLE_SUBJECTS = {
    "Agent Execution Contract governance defaults",
    "AEC runtime assurance grading and enforcement",
    "Advanced retrieval memory",
    "Tess Cloud",
    "Tess Vault",
}


class _StrictJsonError(ValueError):
    pass


def _reject_duplicates(pairs: Sequence[Tuple[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _StrictJsonError("duplicate object key {!r}".format(key))
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise _StrictJsonError("non-finite JSON constant {!r}".format(value))


def _read_regular(root: Path, relative: Path, findings: List[str]) -> Optional[str]:
    path = root / relative
    label = relative.as_posix()
    try:
        root_resolved = root.resolve(strict=True)
        path_resolved = path.resolve(strict=True)
    except OSError as exc:
        findings.append("{}: cannot resolve required input: {}".format(label, exc))
        return None
    if path.is_symlink():
        findings.append("{}: symlinks are not allowed".format(label))
        return None
    try:
        path_resolved.relative_to(root_resolved)
    except ValueError:
        findings.append("{}: resolved outside repository root".format(label))
        return None
    if not path_resolved.is_file():
        findings.append("{}: must be an existing regular file".format(label))
        return None
    try:
        return path_resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        findings.append("{}: cannot read UTF-8 input: {}".format(label, exc))
        return None


def _read_json(root: Path, relative: Path, findings: List[str]) -> Any:
    text = _read_regular(root, relative, findings)
    if text is None:
        return None
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicates,
            parse_constant=_reject_nonfinite,
        )
    except (json.JSONDecodeError, _StrictJsonError) as exc:
        findings.append("{}: strict JSON parse failed: {}".format(relative.as_posix(), exc))
        return None


def _string_set(value: Any, label: str, findings: List[str]) -> Set[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        findings.append("{}: must be an array of non-empty strings".format(label))
        return set()
    if len(set(value)) != len(value):
        findings.append("{}: duplicate entries are not allowed".format(label))
    return set(value)


def _require_fields(value: Any, fields: Set[str], label: str, findings: List[str]) -> bool:
    if not isinstance(value, dict):
        findings.append("{}: must be an object".format(label))
        return False
    for field in sorted(fields - set(value)):
        findings.append("{}: missing required field {!r}".format(label, field))
    for field in sorted(set(value) - fields):
        findings.append("{}: field {!r} is not allowed".format(label, field))
    return not (fields - set(value))


def _validate_assurance(
    value: Any, label: str, findings: List[str]
) -> Tuple[Optional[str], Optional[str]]:
    if not _require_fields(value, {"completeness", "trust"}, label, findings):
        return None, None
    completeness = value.get("completeness")
    trust = value.get("trust")
    if completeness not in _COMPLETENESS:
        findings.append("{}.completeness: must be AEC-C0 through AEC-C4".format(label))
    if trust not in _TRUST:
        findings.append("{}.trust: must be T0 through T3".format(label))
    return completeness, trust


def _validate_schema(data: Any, findings: List[str]) -> None:
    label = SCHEMA_PATH.as_posix()
    if not isinstance(data, dict):
        findings.append("{}: top-level JSON value must be an object".format(label))
        return
    if data.get("$id") != "urn:twiss-io:tess-os:aec-support-policy:v1":
        findings.append("{}.$id: unexpected schema identifier".format(label))
    if data.get("type") != "object" or data.get("additionalProperties") is not False:
        findings.append("{}: schema must define a closed top-level object".format(label))
    if set(data.get("required", [])) != _TOP_FIELDS:
        findings.append("{}.required: does not match the canonical contract fields".format(label))
    properties = data.get("properties")
    if not isinstance(properties, dict) or set(properties) != _TOP_FIELDS:
        findings.append("{}.properties: does not match the canonical contract fields".format(label))


def _validate_tiers(value: Any, findings: List[str]) -> None:
    if not isinstance(value, list):
        findings.append("security_tiers: must be an array")
        return
    seen: Set[str] = set()
    for index, item in enumerate(value):
        label = "security_tiers[{}]".format(index)
        fields = {"tier", "minimum", "implementation_status", "required_evidence"}
        if not _require_fields(item, fields, label, findings):
            continue
        tier = item.get("tier")
        if tier not in _TIER_DEFAULTS:
            findings.append("{}.tier: unknown tier {!r}".format(label, tier))
            continue
        if tier in seen:
            findings.append("{}.tier: duplicate tier {!r}".format(label, tier))
        seen.add(tier)
        actual = _validate_assurance(item.get("minimum"), label + ".minimum", findings)
        if actual != _TIER_DEFAULTS[tier]:
            findings.append("{}.minimum: must equal {}/{}".format(label, *_TIER_DEFAULTS[tier]))
        status = item.get("implementation_status")
        if status not in _STATUS_LABELS:
            findings.append("{}.implementation_status: unknown support label".format(label))
        evidence = _string_set(item.get("required_evidence"), label + ".required_evidence", findings)
        required = _HIGH_ASSURANCE_EVIDENCE.get(tier, set())
        missing = sorted(required - evidence)
        if missing:
            findings.append("{}.required_evidence: high-assurance claim lacks {}".format(label, missing))
        if status != "planned":
            findings.append(
                "{}.implementation_status: all AEC-C1 through AEC-C4 runtime tiers remain 'planned' while runtime enforcement is planned".format(label)
            )
    if seen != set(_TIER_DEFAULTS):
        findings.append("security_tiers: must contain each canonical tier exactly once")


def _validate_products(value: Any, findings: List[str]) -> None:
    if not _require_fields(value, set(_PRODUCT_CONTROLS), "products", findings):
        return
    for product, required_controls in _PRODUCT_CONTROLS.items():
        item = value.get(product)
        label = "products.{}".format(product)
        if not _require_fields(item, {"status", "enabled", "required_controls"}, label, findings):
            continue
        if item.get("status") != "planned" or item.get("enabled") is not False:
            findings.append("{}: must remain planned and disabled".format(label))
        controls = _string_set(item.get("required_controls"), label + ".required_controls", findings)
        missing = sorted(required_controls - controls)
        if missing:
            findings.append("{}.required_controls: missing {}".format(label, missing))


def _validate_policy(data: Any, findings: List[str]) -> None:
    if not _require_fields(data, _TOP_FIELDS, POLICY_PATH.as_posix(), findings):
        return
    if data.get("schema_version") != "tess.aec-support-policy.v1":
        findings.append("schema_version: must equal 'tess.aec-support-policy.v1'")
    if data.get("document_status") != "available":
        findings.append("document_status: the documentation template is available")
    if data.get("runtime_enforcement_status") != "planned":
        findings.append("runtime_enforcement_status: must remain 'planned'")
    if _validate_assurance(data.get("default_assurance"), "default_assurance", findings) != ("AEC-C0", "T0"):
        findings.append("default_assurance: must fail closed to AEC-C0/T0")

    _validate_tiers(data.get("security_tiers"), findings)

    trust_boundary = data.get("trust_boundary")
    trust_fields = {
        "same_user_ceiling",
        "above_t1_requires",
        "adapter_capability_levels_do_not_satisfy_aec",
    }
    if _require_fields(trust_boundary, trust_fields, "trust_boundary", findings):
        if trust_boundary.get("same_user_ceiling") != "T1":
            findings.append("trust_boundary.same_user_ceiling: must be T1")
        above = _string_set(trust_boundary.get("above_t1_requires"), "trust_boundary.above_t1_requires", findings)
        required_above_t1 = {"independent-execution-receipt", "immutable-artifact-binding"}
        if not required_above_t1 <= above:
            findings.append(
                "trust_boundary.above_t1_requires: independent receipt and immutable artifact binding are both required"
            )
        if trust_boundary.get("adapter_capability_levels_do_not_satisfy_aec") is not True:
            findings.append(
                "trust_boundary.adapter_capability_levels_do_not_satisfy_aec: adapter C-levels cannot imply AEC assurance"
            )

    data_defaults = data.get("data_defaults")
    data_fields = {
        "storage_scope",
        "cloud_sync",
        "automatic_external_model_routing",
        "automatic_indexing",
        "excluded_index_paths",
        "excluded_durable_categories",
    }
    if _require_fields(data_defaults, data_fields, "data_defaults", findings):
        expected = {
            "storage_scope": "local-only",
            "cloud_sync": "disabled",
            "automatic_external_model_routing": "disabled",
            "automatic_indexing": "disabled",
        }
        for field, wanted in expected.items():
            if data_defaults.get(field) != wanted:
                findings.append("data_defaults.{}: must equal {!r}".format(field, wanted))
        paths = _string_set(data_defaults.get("excluded_index_paths"), "data_defaults.excluded_index_paths", findings)
        categories = _string_set(data_defaults.get("excluded_durable_categories"), "data_defaults.excluded_durable_categories", findings)
        if not _SENSITIVE_PATHS <= paths:
            findings.append("data_defaults.excluded_index_paths: sensitive path exclusions cannot be weakened")
        if not _SENSITIVE_CATEGORIES <= categories:
            findings.append("data_defaults.excluded_durable_categories: secret/raw exclusions cannot be weakened")

    retention = data.get("retention")
    retention_fields = {"raw_aec_content", "minimal_redacted_metadata_days", "permanent_artifacts", "implementation_status"}
    if _require_fields(retention, retention_fields, "retention", findings):
        if retention != {
            "raw_aec_content": "denied",
            "minimal_redacted_metadata_days": 7,
            "permanent_artifacts": "explicit-operator-setting-required",
            "implementation_status": "planned",
        }:
            findings.append("retention: must deny raw content and retain only planned seven-day redacted metadata by default")

    provider = data.get("provider_execution")
    if _require_fields(provider, {"default", "required_per_run_declarations"}, "provider_execution", findings):
        if provider.get("default") != "disabled":
            findings.append("provider_execution.default: must be disabled")
        declarations = _string_set(provider.get("required_per_run_declarations"), "provider_execution.required_per_run_declarations", findings)
        if not _PROVIDER_DECLARATIONS <= declarations:
            findings.append("provider_execution.required_per_run_declarations: endpoint, region, retention, and tool profile are required")

    credentials = data.get("credentials")
    credentials_expected = {
        "ambient_environment_inheritance": "denied",
        "allowlist": "explicit-name-and-class",
        "reference_lifetime": "short-lived-and-scoped",
        "secret_material_in_context": "denied",
    }
    if _require_fields(credentials, set(credentials_expected), "credentials", findings):
        if credentials != credentials_expected:
            findings.append("credentials: must deny ambient/secret context and require scoped allowlisted references")

    cost = data.get("cost")
    if _require_fields(cost, {"default_budget_usd", "default_hard_stop", "nonzero_requires"}, "cost", findings):
        budget = cost.get("default_budget_usd")
        if isinstance(budget, bool) or not isinstance(budget, (int, float)) or not math.isfinite(float(budget)) or budget != 0:
            findings.append("cost.default_budget_usd: must be numeric zero")
        if cost.get("default_hard_stop") is not True:
            findings.append("cost.default_hard_stop: must be true")
        nonzero = _string_set(cost.get("nonzero_requires"), "cost.nonzero_requires", findings)
        if not _NONZERO_BUDGET_DECLARATIONS <= nonzero:
            findings.append("cost.nonzero_requires: explicit owner, per-run budget, and cost scope are required")

    _validate_products(data.get("products"), findings)


def _validate_docs(root: Path, findings: List[str]) -> None:
    for relative, markers in _DOC_MARKERS.items():
        text = _read_regular(root, relative, findings)
        if text is None:
            continue
        for marker in markers:
            if marker not in text:
                findings.append("{}: missing claim-status marker {!r}".format(relative.as_posix(), marker))
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.lstrip().startswith("|"):
                continue
            if not any(subject in line for subject in _PLANNED_ONLY_TABLE_SUBJECTS):
                continue
            if "**Available**" in line or "**Preview**" in line:
                findings.append(
                    "{}:{}: planned-only AEC/Cloud/Memory/Vault claim cannot be Available or Preview".format(
                        relative.as_posix(), line_number
                    )
                )


def validate_repository(root: Path) -> List[str]:
    """Return stable findings; an empty list means the advisory contract is consistent."""
    findings: List[str] = []
    try:
        if root.is_symlink():
            return ["root: repository root must not be a symlink"]
        if not root.resolve(strict=True).is_dir():
            return ["root: repository root must be an existing directory"]
    except OSError as exc:
        return ["root: cannot resolve repository root: {}".format(exc)]

    schema = _read_json(root, SCHEMA_PATH, findings)
    policy = _read_json(root, POLICY_PATH, findings)
    if schema is not None:
        _validate_schema(schema, findings)
    if policy is not None:
        _validate_policy(policy, findings)
    _validate_docs(root, findings)
    return sorted(set(findings))
