"""Resolve `how_it_works.integrations` names against the connector
registry (`connectors/registry/**`) — the PLAN-TIME half of the codegen
seam `docs/design/connectors-architecture.md` §6 designs.

    from spec_engine.connector_resolver import resolve_connectors
    resolved = resolve_connectors(["Anthropic", "Stripe"])
    # resolved[0].status == "resolved"    (connector_id="anthropic", ...)
    # resolved[1].status == "unresolved"  (registered_connector_ids=[...])

## Why THIS module reads the registry directly, rather than importing
## `connectors.manifest_validator`

Every top-level tess-os component stays independently deployable — zero
cross-component import edges (`spec_engine.spec_check` duplicates, rather
than imports, `intent_router.schema_check` for the exact same reason; see
that module's own docstring). `connectors/manifest_validator.py` is the
FULL, strict, advisory structural check (secret-value rejection, every
field's shape, cross-registry alias uniqueness) — it is what CI/tests run
to prove the registry is internally consistent. THIS module has a
narrower, independent job: read what `spec_engine.codegen` actually needs
to emit a real client, and do so defensively — a registry entry this
module cannot make sense of is treated as NOT REGISTERED (the safe
failure mode; see `resolve_connectors()`'s own docstring), never a hard
crash that would block plan-building on a malformed THIRD-PARTY-adjacent
file the strict validator (a SEPARATE, mandatory CI check) already
guards.

## Resolution rule — exact slug/alias match ONLY

Deliberately STRICTER than `codegen._match_entity_by_name()`'s substring
heuristic (design §6.2): a false negative here costs a labeled `501` stub
(safe — today's unchanged behavior); a false positive would wire a real
external call to the WRONG provider. `_slugify(integration_name)` must
equal a connector's `id` or one of its declared `aliases`, exactly — no
fuzzy/substring/case-insensitive-beyond-slugification matching.

## Determinism and the "generation-time binding, not runtime plugin
## loading" design decision (§3)

`resolve_connectors()` is a pure function of `(integrations, registry
contents on disk)` — same integration names + same registry bytes ->
byte-identical `ResolvedConnector` list, every time. It is called EXACTLY
ONCE per plan, inside `plan_builder.build_plan()`, at PLAN time — never
again at generate time. `spec_engine.codegen.generate_app()` reads only
the frozen `SpecDocument.resolved_connectors` snapshot this function
produced; it never calls this module or re-reads the registry itself.
This is what makes the resolved surface something an approval can
meaningfully bind to (`content.plan_content_hash()`): the SAME resolution
that was shown to a human at the approval gate is, byte-for-byte, what
codegen consumes — never a fresher (or staler) read of a registry that
may have moved on since.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from .content import ResolvedConnector, ResolvedConnectorOperation

PathLike = Union[str, Path]

DEFAULT_OPERATION_NAME = "generate"

_SLUG_SANITIZE_RE = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    """Same sanitize-to-slug rule `codegen._slugify()` uses (duplicated,
    not imported — this module has no import dependency on `codegen.py`;
    `codegen.py` imports FROM here, never the reverse)."""
    slug = _SLUG_SANITIZE_RE.sub("-", (name or "").strip().lower()).strip("-")
    return slug or "item"


def default_registry_root() -> Path:
    """`connectors/registry/` resolved relative to this repo's own
    checkout layout: `spec-engine/spec_engine/connector_resolver.py` ->
    `spec-engine/spec_engine/` -> `spec-engine/` -> repo root ->
    `connectors/registry/`. `connectors/**` living alongside
    `spec-engine/**` in the SAME repo is design doc §11 decision 6's
    recommendation ("the codegen seam wants atomic co-review")."""
    return Path(__file__).resolve().parent.parent.parent / "connectors" / "registry"


def _canonical_manifest_hash(manifest: Dict[str, Any]) -> str:
    """SHA-256 hex digest of `manifest`'s canonical JSON form — same
    canonicalization discipline `content.plan_content_hash()` uses (sorted
    keys, no whitespace), so the SAME manifest bytes always hash
    identically regardless of on-disk key order."""
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _read_connector_manifest(path: Path) -> Optional[Dict[str, Any]]:
    """Best-effort read of one `connector.json`. Returns `None` (never
    raises) on anything that makes the file unusable as a registered
    connector — malformed JSON, wrong top-level type, a symlink (the
    registry is data this process does not trust to point outside
    itself). This is the "safe failure mode" the module docstring
    describes: an unusable registry entry is treated as NOT REGISTERED,
    the same as if the directory didn't exist."""
    try:
        if path.is_symlink() or not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _extract_default_operation(manifest: Dict[str, Any]) -> Optional[ResolvedConnectorOperation]:
    """The operation `spec_engine.codegen` wires to the generated app's
    single POST route for this connector — `DEFAULT_OPERATION_NAME`
    ("generate") in every v1 manifest. Returns `None` (caller then treats
    the whole connector as unusable/unresolved) if the manifest does not
    declare a well-formed operation by that name — never guesses a
    different operation instead."""
    operations = manifest.get("operations")
    if not isinstance(operations, list):
        return None
    for op in operations:
        if not isinstance(op, dict) or op.get("name") != DEFAULT_OPERATION_NAME:
            continue
        side_effect = op.get("side_effect")
        http = op.get("http")
        if not isinstance(http, dict):
            return None
        method, path = http.get("method"), http.get("path")
        if not isinstance(side_effect, str) or not isinstance(method, str) or not isinstance(path, str):
            return None
        try:
            return ResolvedConnectorOperation(
                name=DEFAULT_OPERATION_NAME, side_effect=side_effect, http_method=method, http_path=path
            )
        except Exception:
            return None
    return None


def _build_resolved_connector(integration_name: str, connector_id: str, manifest: Dict[str, Any]) -> Optional[ResolvedConnector]:
    """Build a fully-populated, `status="resolved"` `ResolvedConnector`
    snapshot from a manifest dict, or `None` if the manifest is missing
    (or malforms) anything codegen needs — the caller then falls back to
    treating this integration as unresolved rather than emitting a client
    from a partial/guessed configuration."""
    version = manifest.get("version")
    provider = manifest.get("provider")
    auth = manifest.get("auth")
    error_map = manifest.get("error_map")
    limits = manifest.get("limits")
    if not isinstance(version, str) or not isinstance(provider, dict) or not isinstance(auth, dict):
        return None
    if not isinstance(error_map, dict) or not isinstance(limits, dict):
        return None
    if auth.get("scheme") != "env":
        # v1 codegen only knows how to emit an env-scheme client — a
        # manifest declaring any other scheme (e.g. the reserved-but-
        # unimplemented "vault-capability") cannot be resolved in v1.
        return None

    env_vars = auth.get("env")
    header = auth.get("header")
    if not isinstance(env_vars, list) or not env_vars or not all(isinstance(e, str) for e in env_vars):
        return None
    if not isinstance(header, dict) or not isinstance(header.get("name"), str):
        return None

    base_url = provider.get("base_url")
    if not isinstance(base_url, str):
        return None
    base_url_override_env = provider.get("base_url_override_env")
    if base_url_override_env is not None and not isinstance(base_url_override_env, str):
        return None

    pin = provider.get("api_version_pin")
    pin_kind = pin.get("kind") if isinstance(pin, dict) else None
    pin_name = pin.get("name") if isinstance(pin, dict) else None
    pin_value = pin.get("value") if isinstance(pin, dict) else None
    if isinstance(pin, dict) and pin_kind not in ("header", "url_path"):
        return None

    operation = _extract_default_operation(manifest)
    if operation is None:
        return None

    timeout_ms = limits.get("timeout_ms")
    if not isinstance(timeout_ms, int) or isinstance(timeout_ms, bool):
        return None

    clean_error_map = {str(k): v for k, v in error_map.items() if isinstance(k, str) and isinstance(v, str)}

    try:
        return ResolvedConnector(
            integration_name=integration_name,
            status="resolved",
            connector_id=connector_id,
            connector_version=version,
            manifest_hash=_canonical_manifest_hash(manifest),
            display_name=manifest.get("display_name") if isinstance(manifest.get("display_name"), str) else connector_id,
            base_url=base_url,
            base_url_override_env=base_url_override_env,
            api_version_pin_kind=pin_kind,
            api_version_pin_name=pin_name if isinstance(pin_name, str) else None,
            api_version_pin_value=pin_value if isinstance(pin_value, str) else None,
            auth_env_vars=list(env_vars),
            auth_header_name=header.get("name"),
            auth_header_value_prefix=header.get("value_prefix") if isinstance(header.get("value_prefix"), str) else "",
            timeout_ms=timeout_ms,
            error_map=clean_error_map,
            operations=[operation],
        )
    except Exception:
        # ResolvedConnector.__post_init__ fail-loud validation caught
        # something this defensive extraction missed — treat as unusable
        # rather than propagate a raw dataclass error out of plan-building.
        return None


def load_registry(registry_root: Optional[PathLike] = None) -> Dict[str, Dict[str, Any]]:
    """Read every `connector.json` under `registry_root` (default:
    `default_registry_root()`). Returns `{connector_id: manifest_dict}` —
    ONLY entries whose `id` field is present, well-formed, and matches
    their own directory name are included (a mismatched/malformed entry
    is silently excluded here — the strict `connectors.manifest_validator`
    is the mandatory CI check that surfaces that as a loud failure; this
    reader's job is narrower and defensive, see module docstring)."""
    root = Path(registry_root) if registry_root is not None else default_registry_root()
    registry: Dict[str, Dict[str, Any]] = {}
    if not root.is_dir() or root.is_symlink():
        return registry
    for entry in sorted(root.iterdir()):
        if entry.is_symlink() or not entry.is_dir():
            continue
        manifest = _read_connector_manifest(entry / "connector.json")
        if manifest is None:
            continue
        connector_id = manifest.get("id")
        if not isinstance(connector_id, str) or connector_id != entry.name:
            continue
        registry[connector_id] = manifest
    return registry


def resolve_connectors(
    integrations: Sequence[str], *, registry_root: Optional[PathLike] = None
) -> List[ResolvedConnector]:
    """Resolve each entry of `integrations` (typically
    `spec.how_it_works.integrations` / `harvest.how_it_works.integrations`)
    against the connector registry at `registry_root`. Returns one
    `ResolvedConnector` per input entry, SAME order, SAME length — codegen
    zips this 1:1 against `how_it_works.integrations` the same way it
    already zips `ScaffoldModule`s.

    Matching is EXACT slug/alias equality only (module docstring) — never
    fuzzy. An integration name that matches no registered connector's `id`
    or `aliases` resolves to `status="unresolved"`, carrying
    `registered_connector_ids` (every id THAT WAS registered, sorted) so
    the codegen-manifest note can answer "why is this still a 501?" from
    the artifact alone (design §6.2)."""
    registry = load_registry(registry_root)
    registered_ids = sorted(registry.keys())

    # slug -> connector_id, built from id + every declared alias. A slug
    # claimed by more than one connector is a registry inconsistency the
    # strict validator (connectors.manifest_validator) rejects outright;
    # here, defensively, first-registered-wins (deterministic: registry
    # entries are iterated in sorted directory order) rather than
    # resolving ambiguously to two different providers.
    slug_to_id: Dict[str, str] = {}
    for connector_id, manifest in registry.items():
        for slug in [connector_id] + [a for a in (manifest.get("aliases") or []) if isinstance(a, str)]:
            slug_to_id.setdefault(slug, connector_id)

    resolved: List[ResolvedConnector] = []
    for integration_name in integrations:
        slug = _slugify(integration_name)
        connector_id = slug_to_id.get(slug)
        candidate = None
        if connector_id is not None:
            candidate = _build_resolved_connector(integration_name, connector_id, registry[connector_id])
        if candidate is not None:
            resolved.append(candidate)
        else:
            resolved.append(
                ResolvedConnector(
                    integration_name=integration_name,
                    status="unresolved",
                    registered_connector_ids=registered_ids,
                )
            )
    return resolved


__all__ = [
    "DEFAULT_OPERATION_NAME",
    "default_registry_root",
    "load_registry",
    "resolve_connectors",
]
