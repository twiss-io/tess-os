"""Read-only, offline, dependency-free structural validator for the
advisory `connector-manifest.v1` records under `connectors/registry/**`.

Same harness pattern and posture as `tools/adapter_manifest_validator.py`:
this module does not import `spec_engine`, does not touch the network, and
its findings are advisory only — never a gate, approval, or conformance
certificate (`connectors/README.md`, `docs/design/connectors-architecture.md`
§4.1/§7.1). A clean run proves LOCAL structural consistency (schema shape,
cross-registry alias/id uniqueness, no secret-shaped values anywhere in the
manifest) — never that a provider's real API matches what a manifest
declares, and never that any code path was reviewed.

Two entry points:

    validate_manifest_dict(data, *, expected_id=None) -> List[str]
        Pure, in-memory check of ONE already-parsed manifest dict. Used by
        both `validate_repository()` below and by tests that construct a
        manifest dict directly (e.g. the adversarial "secret value in the
        manifest is rejected" proof — no filesystem needed).

    validate_repository(root: Path) -> List[str]
        Walks `connectors/registry/*/connector.json`, parses each as
        strict JSON (rejects duplicate keys — same discipline
        `tools/adapter_manifest_validator.py` applies), validates every
        manifest, and checks cross-registry invariants (every connector's
        `id` matches its directory name; no two connectors share an `id`
        or `alias`).

Both return `[]` on a clean pass (never raise on a malformed manifest —
findings are collected and returned, fail-loud is the CALLER's choice, matching
`tools.adapter_manifest_validator.validate_repository()`'s own contract).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Sequence, Set, Tuple

MANIFEST_DIRECTORY = Path("connectors/registry")
SCHEMA_PATH = Path("connectors/contracts/connector-manifest.schema.json")
SCHEMA_ID = "urn:twiss-io:tess-os:connector-manifest:v1"
MANIFEST_FILENAME = "connector.json"

_MANIFEST_VERSION = "connector-manifest.v1"

_ID_RE = re.compile(r"^[a-z][a-z0-9-]*$")
_SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_HEADER_NAME_RE = re.compile(r"^[a-zA-Z0-9-]+$")
_HTTP_PATH_RE = re.compile(r"^/.*$")
_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_OP_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_STATUS_CODE_RE = re.compile(r"^[1-5][0-9]{2}$")

_ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
_ALLOWED_SIDE_EFFECTS = {"read", "write", "spend"}
_ALLOWED_AUTH_SCHEMES = {"env"}  # "vault-capability" is reserved, NOT implemented — see schema.
_ALLOWED_API_VERSION_PIN_KINDS = {"header", "url_path"}
_ALLOWED_ERROR_CLASSES = {
    "ConnectorAuthError",
    "ConnectorRateLimitError",
    "ConnectorProviderError",
    "ConnectorContractError",
    "ConnectorInvocationError",
}
_ALLOWED_TRUST_TIERS = {"T0", "T1", "T2", "T3"}
_SELF_ASSERTABLE_TIERS = {"T0", "T1"}

_TOP_LEVEL_REQUIRED = {
    "manifest_version", "id", "version", "display_name", "aliases",
    "provider", "auth", "operations", "data_flows", "error_map", "limits", "trust",
}
_PROVIDER_REQUIRED = {"base_url", "api_version_pin"}
_PROVIDER_OPTIONAL = {"base_url_override_env"}
_AUTH_REQUIRED = {"scheme", "env", "header"}
_OPERATION_REQUIRED = {
    "name", "description", "side_effect", "idempotent", "http", "input_schema", "output_schema",
}
_LIMITS_REQUIRED = {"timeout_ms", "max_retries"}
_TRUST_REQUIRED = {"tier", "evidence"}


# ---------------------------------------------------------------------------
# Secret-shaped string detection — applied to EVERY string value anywhere in
# a manifest, not merely inside `auth`. Defense in depth: `auth.env` entries
# additionally get their own env-var-NAME-shape check (below), and a real
# secret value essentially never satisfies BOTH "is a valid identifier for
# some other manifest field" and "is not secret-shaped" at once.
# ---------------------------------------------------------------------------

_KNOWN_KEY_PREFIXES = (
    "sk-ant-", "sk-proj-", "sk-", "AIza", "ghp_", "gho_", "ghu_", "ghs_", "ghr_",
    "glpat-", "xoxb-", "xoxa-", "xoxp-", "xoxr-", "xoxs-", "AKIA", "ASIA", "ya29.",
)
# Matches a KNOWN key prefix followed by 8+ more token characters, ANYWHERE
# in a string (not anchored to the start) — catches a secret embedded mid-
# sentence (e.g. "my test key is sk-proj-..."), not just a bare value.
_KNOWN_PREFIX_RE = re.compile(
    "(?:" + "|".join(re.escape(p) for p in sorted(_KNOWN_KEY_PREFIXES, key=len, reverse=True)) + r")[A-Za-z0-9_-]{8,}"
)
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._-]{10,}")
# A candidate "unbroken token" anywhere in the string: 20+ chars of
# alnum/underscore/hyphen with no whitespace boundary — matched via
# re.finditer (not anchored), so a token embedded in longer prose is found
# the same way a bare value is.
_UNBROKEN_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{20,}")

# Every FIXED-VOCABULARY string this schema itself defines (enum/const
# values) — excluded from the generic secret-shape heuristic below so this
# schema's own PascalCase error-class names (e.g. "ConnectorInvocationError",
# 24 chars, upper+lower mixed) never false-positive as a credential. This is
# an EXACT-match exclusion list, not a wildcard: any TOKEN not identical to
# one of these still goes through the full heuristic, so a real secret typo'd
# into any field — including one of these fields — is still caught.
_KNOWN_SAFE_LITERALS: Set[str] = {
    _MANIFEST_VERSION,
    "env", "vault-capability",
    "header", "url_path",
    "read", "write", "spend",
    "GET", "POST", "PUT", "PATCH", "DELETE",
    "T0", "T1", "T2", "T3",
    "live-smoke",
} | _ALLOWED_ERROR_CLASSES


def _token_is_secret_shaped(token: str) -> bool:
    if token in _KNOWN_SAFE_LITERALS:
        return False
    has_lower = any(c.islower() for c in token)
    has_upper = any(c.isupper() for c in token)
    has_digit = any(c.isdigit() for c in token)
    # A legitimate manifest identifier/slug in this schema is EITHER
    # all-lowercase-with-hyphens (ids/aliases/op names) OR
    # SCREAMING_SNAKE_CASE (env var names) — never a mix of upper AND
    # lower case letters. Real API keys/tokens routinely mix case (and/or
    # digits) inside one unbroken 20+ char run; that specific combination
    # is what this flags.
    if has_lower and has_upper:
        return True
    if (has_lower or has_upper) and has_digit and ("-" in token or "_" in token):
        return True
    return False


def _looks_like_secret_value(value: str) -> bool:
    """True if `value` CONTAINS (not just wholly IS) a substring that
    structurally resembles a real credential rather than a name/label/URL/
    prose string — catches both a bare secret value AND one embedded mid-
    sentence (e.g. a debug note someone pasted a key into). Never claims
    certainty — this is a heuristic tripwire, not a secret-scanning
    service; see `.gitleaks.toml` at the repo root for the repo-wide
    equivalent this deliberately overlaps with, not replaces."""
    if not isinstance(value, str) or not value:
        return False
    if value in _KNOWN_SAFE_LITERALS:
        return False
    if _KNOWN_PREFIX_RE.search(value):
        return True
    if _BEARER_RE.search(value):
        return True
    for match in _UNBROKEN_TOKEN_RE.finditer(value):
        if _token_is_secret_shaped(match.group(0)):
            return True
    return False


def _walk_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _walk_strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _walk_strings(v)


def _scan_for_secret_values(data: Any, label: str, findings: List[str]) -> None:
    for value in _walk_strings(data):
        if _looks_like_secret_value(value):
            findings.append(
                f"{label}: a value in this manifest is shaped like a real credential, not a "
                "name/label/URL — manifests may declare env var NAMES only, never secret VALUES "
                f"(offending value redacted from this finding; length={len(value)})"
            )


# ---------------------------------------------------------------------------
# Strict JSON (reject duplicate keys) — same discipline
# tools/adapter_manifest_validator.py applies.
# ---------------------------------------------------------------------------


class _StrictJsonError(ValueError):
    pass


def _reject_duplicates(pairs: Sequence[Tuple[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _StrictJsonError(f"duplicate object key {key!r}")
        result[key] = value
    return result


def _strict_json_loads(text: str, label: str, findings: List[str]) -> Any:
    try:
        return json.loads(text, object_pairs_hook=_reject_duplicates)
    except (json.JSONDecodeError, _StrictJsonError) as exc:
        findings.append(f"{label}: strict JSON parse failed: {exc}")
        return None


# ---------------------------------------------------------------------------
# Per-manifest structural validation
# ---------------------------------------------------------------------------


def validate_manifest_dict(data: Any, *, expected_id: str = None, label: str = "connector.json") -> List[str]:
    """Validate ONE already-parsed manifest dict against the
    `connector-manifest.v1` shape. Pure — no filesystem access. Returns a
    list of findings (empty = clean). `expected_id` (if given) is checked
    against the manifest's own `id` field — used by `validate_repository()`
    to enforce "id matches registry directory name"."""
    findings: List[str] = []
    if not isinstance(data, dict):
        return [f"{label}: top-level JSON value must be an object"]

    unknown = sorted(set(data) - _TOP_LEVEL_REQUIRED)
    missing = sorted(_TOP_LEVEL_REQUIRED - set(data))
    for f in missing:
        findings.append(f"{label}: missing required field {f!r}")
    for f in unknown:
        findings.append(f"{label}: field {f!r} is not allowed")

    if data.get("manifest_version") != _MANIFEST_VERSION:
        findings.append(f"{label}.manifest_version: must equal {_MANIFEST_VERSION!r}")

    connector_id = data.get("id")
    if not isinstance(connector_id, str) or not _ID_RE.match(connector_id):
        findings.append(f"{label}.id: must match {_ID_RE.pattern!r}")
    elif expected_id is not None and connector_id != expected_id:
        findings.append(f"{label}.id: {connector_id!r} does not match registry directory {expected_id!r}")

    version = data.get("version")
    if not isinstance(version, str) or not _SEMVER_RE.match(version):
        findings.append(f"{label}.version: must be semver (x.y.z)")

    display_name = data.get("display_name")
    if not isinstance(display_name, str) or not display_name.strip():
        findings.append(f"{label}.display_name: must be a non-empty string")

    aliases = data.get("aliases")
    if not isinstance(aliases, list):
        findings.append(f"{label}.aliases: must be an array")
    else:
        for alias in aliases:
            if not isinstance(alias, str) or not _ID_RE.match(alias):
                findings.append(f"{label}.aliases: {alias!r} must match {_ID_RE.pattern!r}")
        if len(set(aliases)) != len(aliases):
            findings.append(f"{label}.aliases: duplicate entries are not allowed")
        if isinstance(connector_id, str) and connector_id in (aliases or []):
            findings.append(f"{label}.aliases: must not repeat the connector's own id")

    _validate_provider(data.get("provider"), label, findings)
    _validate_auth(data.get("auth"), label, findings)
    _validate_operations(data.get("operations"), label, findings)

    data_flows = data.get("data_flows")
    if not isinstance(data_flows, list) or not data_flows:
        findings.append(f"{label}.data_flows: must be a non-empty array")
    elif any(not isinstance(x, str) or not x.strip() for x in data_flows):
        findings.append(f"{label}.data_flows: every entry must be a non-empty string")

    _validate_error_map(data.get("error_map"), label, findings)
    _validate_limits(data.get("limits"), label, findings)
    _validate_trust(data.get("trust"), label, findings)

    _scan_for_secret_values(data, label, findings)

    return findings


def _validate_provider(provider: Any, label: str, findings: List[str]) -> None:
    if not isinstance(provider, dict):
        findings.append(f"{label}.provider: must be an object")
        return
    allowed = _PROVIDER_REQUIRED | _PROVIDER_OPTIONAL
    unknown = sorted(set(provider) - allowed)
    missing = sorted(_PROVIDER_REQUIRED - set(provider))
    for f in missing:
        findings.append(f"{label}.provider: missing required field {f!r}")
    for f in unknown:
        findings.append(f"{label}.provider: field {f!r} is not allowed")

    base_url = provider.get("base_url")
    if not isinstance(base_url, str) or not base_url.startswith("https://"):
        findings.append(f"{label}.provider.base_url: must be an https:// URL")

    override_env = provider.get("base_url_override_env")
    if override_env is not None and (not isinstance(override_env, str) or not _ENV_NAME_RE.match(override_env)):
        findings.append(f"{label}.provider.base_url_override_env: must be an env-var NAME ({_ENV_NAME_RE.pattern!r})")

    pin = provider.get("api_version_pin")
    if not isinstance(pin, dict):
        findings.append(f"{label}.provider.api_version_pin: must be an object")
        return
    pin_allowed = {"kind", "name", "value"}
    unknown = sorted(set(pin) - pin_allowed)
    for f in unknown:
        findings.append(f"{label}.provider.api_version_pin: field {f!r} is not allowed")
    kind = pin.get("kind")
    if kind not in _ALLOWED_API_VERSION_PIN_KINDS:
        findings.append(f"{label}.provider.api_version_pin.kind: must be one of {sorted(_ALLOWED_API_VERSION_PIN_KINDS)}")
    value = pin.get("value")
    if not isinstance(value, str) or not value:
        findings.append(f"{label}.provider.api_version_pin.value: must be a non-empty string")
    name = pin.get("name")
    if kind == "header":
        if not isinstance(name, str) or not _HEADER_NAME_RE.match(name):
            findings.append(f"{label}.provider.api_version_pin.name: required and must match {_HEADER_NAME_RE.pattern!r} when kind == 'header'")
    elif kind == "url_path" and name is not None:
        findings.append(f"{label}.provider.api_version_pin.name: must be absent when kind == 'url_path'")


def _validate_auth(auth: Any, label: str, findings: List[str]) -> None:
    if not isinstance(auth, dict):
        findings.append(f"{label}.auth: must be an object")
        return
    unknown = sorted(set(auth) - _AUTH_REQUIRED)
    missing = sorted(_AUTH_REQUIRED - set(auth))
    for f in missing:
        findings.append(f"{label}.auth: missing required field {f!r}")
    for f in unknown:
        findings.append(f"{label}.auth: field {f!r} is not allowed")

    scheme = auth.get("scheme")
    if scheme not in _ALLOWED_AUTH_SCHEMES:
        if scheme == "vault-capability":
            findings.append(
                f"{label}.auth.scheme: 'vault-capability' is RESERVED (design doc §4.1/§11) but not "
                "implemented in v1 — this manifest cannot use it yet"
            )
        else:
            findings.append(f"{label}.auth.scheme: must be one of {sorted(_ALLOWED_AUTH_SCHEMES)}")

    env = auth.get("env")
    if not isinstance(env, list) or not env:
        findings.append(f"{label}.auth.env: must be a non-empty array")
    else:
        for entry in env:
            if not isinstance(entry, str) or not _ENV_NAME_RE.match(entry):
                # Redact the offending value from the finding text itself
                # when it looks secret-shaped — a validation FINDING must
                # never become a second place a leaked credential's bytes
                # get echoed (into CI logs, terminal output, etc). A
                # non-secret-shaped malformed name (a genuine typo) is
                # still shown verbatim — that's the useful, safe case.
                shown = (
                    f"(redacted — value is shaped like a credential, length={len(entry)})"
                    if isinstance(entry, str) and _looks_like_secret_value(entry)
                    else repr(entry)
                )
                findings.append(
                    f"{label}.auth.env: {shown} is not an env-var NAME ({_ENV_NAME_RE.pattern!r}) — "
                    "manifests declare env var names only, NEVER secret values"
                )
        if len(set(env)) != len(env):
            findings.append(f"{label}.auth.env: duplicate entries are not allowed")

    header = auth.get("header")
    if not isinstance(header, dict):
        findings.append(f"{label}.auth.header: must be an object")
    else:
        unknown = sorted(set(header) - {"name", "value_prefix"})
        for f in unknown:
            findings.append(f"{label}.auth.header: field {f!r} is not allowed")
        name = header.get("name")
        if not isinstance(name, str) or not _HEADER_NAME_RE.match(name):
            findings.append(f"{label}.auth.header.name: required, must match {_HEADER_NAME_RE.pattern!r}")
        prefix = header.get("value_prefix")
        if prefix is not None and not isinstance(prefix, str):
            findings.append(f"{label}.auth.header.value_prefix: must be a string when present")


def _validate_operations(operations: Any, label: str, findings: List[str]) -> None:
    if not isinstance(operations, list) or not operations:
        findings.append(f"{label}.operations: must be a non-empty array")
        return
    names_seen: Set[str] = set()
    for i, op in enumerate(operations):
        op_label = f"{label}.operations[{i}]"
        if not isinstance(op, dict):
            findings.append(f"{op_label}: must be an object")
            continue
        unknown = sorted(set(op) - _OPERATION_REQUIRED)
        missing = sorted(_OPERATION_REQUIRED - set(op))
        for f in missing:
            findings.append(f"{op_label}: missing required field {f!r}")
        for f in unknown:
            findings.append(f"{op_label}: field {f!r} is not allowed")

        name = op.get("name")
        if not isinstance(name, str) or not _OP_NAME_RE.match(name):
            findings.append(f"{op_label}.name: must match {_OP_NAME_RE.pattern!r}")
        elif name in names_seen:
            findings.append(f"{op_label}.name: duplicate operation name {name!r}")
        else:
            names_seen.add(name)

        description = op.get("description")
        if not isinstance(description, str) or not description.strip():
            findings.append(f"{op_label}.description: must be a non-empty string")

        side_effect = op.get("side_effect")
        if side_effect not in _ALLOWED_SIDE_EFFECTS:
            findings.append(f"{op_label}.side_effect: must be one of {sorted(_ALLOWED_SIDE_EFFECTS)}")

        if not isinstance(op.get("idempotent"), bool):
            findings.append(f"{op_label}.idempotent: must be a boolean")

        http = op.get("http")
        if not isinstance(http, dict):
            findings.append(f"{op_label}.http: must be an object")
        else:
            unknown = sorted(set(http) - {"method", "path"})
            for f in unknown:
                findings.append(f"{op_label}.http: field {f!r} is not allowed")
            if http.get("method") not in _ALLOWED_METHODS:
                findings.append(f"{op_label}.http.method: must be one of {sorted(_ALLOWED_METHODS)}")
            path = http.get("path")
            if not isinstance(path, str) or not _HTTP_PATH_RE.match(path):
                findings.append(f"{op_label}.http.path: must start with '/'")

        for schema_field in ("input_schema", "output_schema"):
            schema = op.get(schema_field)
            if not isinstance(schema, dict) or set(schema) != {"fields"}:
                findings.append(f"{op_label}.{schema_field}: must be an object with exactly one key 'fields'")
                continue
            fields = schema.get("fields")
            if not isinstance(fields, list):
                findings.append(f"{op_label}.{schema_field}.fields: must be an array")
                continue
            for j, item in enumerate(fields):
                item_label = f"{op_label}.{schema_field}.fields[{j}]"
                if not isinstance(item, dict) or set(item) != {"name", "type"}:
                    findings.append(f"{item_label}: must be an object with exactly keys 'name','type'")
                    continue
                if not isinstance(item.get("name"), str) or not item["name"].strip():
                    findings.append(f"{item_label}.name: must be a non-empty string")
                if not isinstance(item.get("type"), str) or not item["type"].strip():
                    findings.append(f"{item_label}.type: must be a non-empty string")


def _validate_error_map(error_map: Any, label: str, findings: List[str]) -> None:
    if not isinstance(error_map, dict):
        findings.append(f"{label}.error_map: must be an object")
        return
    for status, error_class in error_map.items():
        if not _STATUS_CODE_RE.match(status):
            findings.append(f"{label}.error_map: key {status!r} is not a 3-digit HTTP status code")
        if error_class not in _ALLOWED_ERROR_CLASSES:
            findings.append(f"{label}.error_map[{status!r}]: {error_class!r} must be one of {sorted(_ALLOWED_ERROR_CLASSES)}")


def _validate_limits(limits: Any, label: str, findings: List[str]) -> None:
    if not isinstance(limits, dict):
        findings.append(f"{label}.limits: must be an object")
        return
    unknown = sorted(set(limits) - _LIMITS_REQUIRED)
    missing = sorted(_LIMITS_REQUIRED - set(limits))
    for f in missing:
        findings.append(f"{label}.limits: missing required field {f!r}")
    for f in unknown:
        findings.append(f"{label}.limits: field {f!r} is not allowed")

    timeout_ms = limits.get("timeout_ms")
    if not isinstance(timeout_ms, int) or isinstance(timeout_ms, bool) or not (1 <= timeout_ms <= 120000):
        findings.append(f"{label}.limits.timeout_ms: must be an integer in [1, 120000]")

    max_retries = limits.get("max_retries")
    if max_retries != 0 or isinstance(max_retries, bool):
        findings.append(
            f"{label}.limits.max_retries: MUST be exactly 0 in v1 (design §4.3 — retrying a "
            "non-idempotent spend/write call is how you double-bill or double-post)"
        )


def _validate_trust(trust: Any, label: str, findings: List[str]) -> None:
    if not isinstance(trust, dict):
        findings.append(f"{label}.trust: must be an object")
        return
    unknown = sorted(set(trust) - _TRUST_REQUIRED)
    missing = sorted(_TRUST_REQUIRED - set(trust))
    for f in missing:
        findings.append(f"{label}.trust: missing required field {f!r}")
    for f in unknown:
        findings.append(f"{label}.trust: field {f!r} is not allowed")

    tier = trust.get("tier")
    if tier not in _ALLOWED_TRUST_TIERS:
        findings.append(f"{label}.trust.tier: must be one of {sorted(_ALLOWED_TRUST_TIERS)}")
    elif tier == "T3":
        findings.append(
            f"{label}.trust.tier: 'T3' is UNREACHABLE — core/policy/policy.yaml's verifier_keys "
            "ships empty and no agent may self-provision one; the honest ceiling today is 'T2' "
            "(design doc §7.2)"
        )
    elif tier == "T2":
        evidence = trust.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            findings.append(f"{label}.trust: tier 'T2' requires a non-empty, dated 'evidence' array")
    elif tier in _SELF_ASSERTABLE_TIERS:
        pass  # T0/T1 self-assertion needs no evidence array content

    evidence = trust.get("evidence")
    if isinstance(evidence, list):
        for i, item in enumerate(evidence):
            item_label = f"{label}.trust.evidence[{i}]"
            if not isinstance(item, dict):
                findings.append(f"{item_label}: must be an object")
                continue
            required = {"kind", "date", "run_by", "note"}
            unknown = sorted(set(item) - required)
            missing = sorted(required - set(item))
            for f in missing:
                findings.append(f"{item_label}: missing required field {f!r}")
            for f in unknown:
                findings.append(f"{item_label}: field {f!r} is not allowed")
            if item.get("kind") != "live-smoke":
                findings.append(f"{item_label}.kind: must equal 'live-smoke'")
            date = item.get("date")
            if not isinstance(date, str) or not _DATE_RE.match(date):
                findings.append(f"{item_label}.date: must be YYYY-MM-DD")
    elif evidence is not None:
        findings.append(f"{label}.trust.evidence: must be an array")


# ---------------------------------------------------------------------------
# Whole-registry validation — filesystem entry point
# ---------------------------------------------------------------------------


def validate_repository(root: Path) -> List[str]:
    """Validate every `connectors/registry/<id>/connector.json` under
    `root`, plus cross-registry invariants (id/alias uniqueness). Returns
    deterministic, sorted findings — `[]` means a clean pass. Read-only,
    offline: reads the schema file (checked only for its `$id`, never
    interpreted as a general JSON-Schema engine — this validator IS the
    check) and every manifest under the registry directory; touches
    nothing else, follows no symlinks."""
    findings: List[str] = []
    root = Path(root)

    schema_path = root / SCHEMA_PATH
    if schema_path.is_symlink():
        findings.append(f"{SCHEMA_PATH}: must not be a symlink")
    elif not schema_path.is_file():
        findings.append(f"{SCHEMA_PATH}: missing")
    else:
        schema_data = _strict_json_loads(schema_path.read_text(encoding="utf-8"), str(SCHEMA_PATH), findings)
        if isinstance(schema_data, dict) and schema_data.get("$id") != SCHEMA_ID:
            findings.append(f"{SCHEMA_PATH}: must be the advisory connector-manifest v1 schema")

    registry_dir = root / MANIFEST_DIRECTORY
    if registry_dir.is_symlink():
        findings.append(f"{MANIFEST_DIRECTORY}: must not be a symlink")
        return sorted(set(findings))
    if not registry_dir.is_dir():
        findings.append(f"{MANIFEST_DIRECTORY}: missing")
        return sorted(set(findings))

    all_ids: Dict[str, str] = {}  # id/alias -> owning connector_id

    for entry in sorted(registry_dir.iterdir()):
        if entry.is_symlink():
            findings.append(f"{MANIFEST_DIRECTORY}/{entry.name}: must not be a symlink")
            continue
        if not entry.is_dir():
            findings.append(f"{MANIFEST_DIRECTORY}/{entry.name}: unexpected non-directory entry in the registry")
            continue

        manifest_path = entry / MANIFEST_FILENAME
        label = f"{MANIFEST_DIRECTORY}/{entry.name}/{MANIFEST_FILENAME}"
        if manifest_path.is_symlink():
            findings.append(f"{label}: must not be a symlink")
            continue
        if not manifest_path.is_file():
            findings.append(f"{label}: missing {MANIFEST_FILENAME}")
            continue

        data = _strict_json_loads(manifest_path.read_text(encoding="utf-8"), label, findings)
        if data is None:
            continue

        manifest_findings = validate_manifest_dict(data, expected_id=entry.name, label=label)
        findings.extend(manifest_findings)

        if isinstance(data, dict):
            connector_id = data.get("id")
            aliases = data.get("aliases") if isinstance(data.get("aliases"), list) else []
            if isinstance(connector_id, str):
                for slug in [connector_id] + [a for a in aliases if isinstance(a, str)]:
                    if slug in all_ids and all_ids[slug] != connector_id:
                        findings.append(
                            f"{MANIFEST_DIRECTORY}: id/alias {slug!r} is claimed by both "
                            f"{all_ids[slug]!r} and {connector_id!r} — the resolver requires "
                            "every id/alias to be globally unique across the registry"
                        )
                    else:
                        all_ids[slug] = connector_id

    return sorted(set(findings))


__all__ = [
    "MANIFEST_DIRECTORY",
    "SCHEMA_PATH",
    "SCHEMA_ID",
    "MANIFEST_FILENAME",
    "validate_manifest_dict",
    "validate_repository",
]
