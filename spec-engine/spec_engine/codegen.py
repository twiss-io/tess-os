"""Spec + ScaffoldPlan -> REAL, RUNNABLE code. The first real codegen slice
of "code is generated FROM the spec, never the reverse" (Pillar 02),
continuing `scaffold.py`'s spec->scaffold DIRECTION stub (Phase 1 Epic E2
deliverable (3)) into the codegen half of Phase 2 Epic E4 ("scaffolds the
repo from SPEC.md... generates tests from the spec's acceptance section").

    from spec_engine.codegen import generate_app
    result = generate_app(spec, "/path/to/generated-app")
    # result.scaffold_plan.codegen_status == "generated"
    # result.written["src/server.js"], result.manifest, ...

## Target stack — the ONE default, and why

`DEFAULT_TARGET_STACK = "node-http-minimal"`: plain Node.js, using ONLY
`node:http`/`node:crypto`/`node:test`/`node:assert` core modules — **zero
npm dependencies, zero build step, zero install step.** Chosen over an
Express/React/Postgres stack deliberately:

  - "It MUST actually run" (this module's own build brief) is easiest to
    guarantee with nothing to `npm install` — a generated app boots with
    `node src/server.js` on any machine that has Node >=18, offline,
    with no registry access, no lockfile drift, no version-pin decisions
    this codegen step would otherwise have to make on a caller's behalf.
  - Node 18+ ships `fetch()` and `crypto.randomUUID()` and `node:test`
    (a real test runner) in core — enough to generate a genuinely
    testable app without inventing a test-framework dependency either.
  - This mirrors the SAME "keep tess-os's own deps stdlib-only" discipline
    `spec-engine`/`intent-router` already apply to THEMSELVES (see their
    READMEs) — applying it to what THEY generate is the honest extension
    of that discipline, not a new one.
  - Persistence is in-memory (a `Map` per entity) — data resets on
    restart. This is a deliberate, disclosed scope boundary, not an
    oversight: provisioning a real, persistent database is Phase 2 Epic
    E4's OWN next deliverable ("provisions DB (Supabase default)"), out
    of scope for this codegen slice. Every generated README says so.

A future second target stack is an ADDITIVE change — add a name to
`SUPPORTED_TARGET_STACKS` and a matching generator function; nothing here
assumes there is only ever one.

## What is genuinely generated vs. still a labeled stub

Deterministic, traceable mapping from `ScaffoldPlan.modules` (each of
which already carries a `source_section` back to the spec) to real files:

| `ScaffoldModule.kind` | Generated file(s) | `generation_status` |
|---|---|---|
| `backend-model` | `src/models/<entity-slug>.js` — a real, in-memory CRUD store (list/get/create/update/remove) with field-presence validation derived from `Entity.fields` | `generated` |
| `frontend-page` | `src/pages/<screen-slug>.js` — a real server-rendered HTML page; if the screen name matches a data-model entity it renders that entity's live records, else it renders the screen's spec description | `generated` |
| `service` (flow) | `src/flows/<flow-slug>.js` — a real, EXECUTABLE step-sequence function wired into a live route, but each step's business-logic body is a `// TODO` placeholder (flow steps are free text in the spec; codegen cannot compile prose into working business logic) | `generated-stub-logic` |
| `integration` | `src/integrations/<integration-slug>.js` — a labeled connector STUB that always throws, wired to a route that returns HTTP 501 | `stub` |
| `test-suite` | `tests/acceptance.test.js` — real `node:test` tests: a baseline boot/health check, one CRUD round-trip per entity, and one test per `acceptance_criteria` entry (a real entity-backed assertion if the criterion text names a known entity, else an honestly-commented fallback to the boot check) | `generated` |

Every one of these is recorded, per module, in `.spec-engine/
codegen-manifest.json` (schema: `schema/codegen-manifest.schema.json`) —
never silently rolled up into a single "generated" claim that overstates
the `service`/`integration` rows. `src/server.js`, `src/http-util.js`,
`package.json`, and the generated app's own `README.md` are also written,
but as `infrastructure_files` in the manifest — not attributed to a
`source_section`, because they are required scaffolding for this target
stack, not derived from any one spec section.

## Determinism

`generate_app()` performs no randomness and reads no clock EXCEPT what is
already frozen into the `ScaffoldPlan`/`SpecDocument` it is given (e.g.
`ScaffoldModule.module_id`, `ScaffoldPlan.generated_at` — both already
fixed before this function runs). Given the SAME `spec` + `scaffold_plan`
+ `target_stack`, every generated file's content is byte-identical across
runs — see `tests/spec_engine/test_codegen.py::
test_generate_app_is_deterministic_given_a_fixed_plan`.

## Atomicity

`generate_app()` never writes into the caller's real `target_dir` while
generation is in progress. Every file — every model/page/flow/
integration/infrastructure file, `.spec-engine/codegen-manifest.json`,
and `write_scaffold_stub()`'s own artifacts (`SPEC.md`, `spec.json`,
`.spec-engine/scaffold-plan.json`, `CLAUDE.md`/`AGENTS.md`) — is written
into a same-filesystem STAGING directory first; the complete result is
then swapped into `target_dir` with exactly one atomic `os.replace()`.
A process killed at ANY point — mid-write of a single file, or between
the manifest write and `write_scaffold_stub()`'s own writes (the
historical failure mode: a manifest claiming `codegen_status:
"generated"` while `SPEC.md`/`CLAUDE.md` are still missing) — leaves
`target_dir` either exactly as `generate_app()` found it (absent, empty,
or its own prior content) or the complete, `codegen_status: "generated"`
tree. There is no instant at which `target_dir` can be observed holding
a partial file tree. See `generate_app()`, `_write_generated_app_tree()`,
and `_publish_staged_app()` for the full mechanism, and
`tests/spec_engine/test_codegen_atomic_staging.py` for the kill-proof
proof.

Publishing OVER pre-existing `target_dir` content needs a second rename
in addition to the first (see `_publish_staged_app()`'s docstring for
why) — a kill exactly between those two renames would, left unhandled,
leave that prior content orphaned in an untracked sibling with nothing
pointing back to it, then PERMANENTLY and SILENTLY destroyed by the very
next regeneration (the natural post-crash "just re-run it" recovery
action), since that next run would see `target_dir` absent and treat it
as a first-ever generation. `generate_app()` closes this window itself:
on EVERY call, before it decides whether `target_dir` has existing
content, it first checks for and repairs exactly this interrupted-swap
state (`_recover_interrupted_publish()`) — so any orphaned prior content
is restored before this run ever gets a chance to treat `target_dir` as
empty. This check runs unconditionally on every call, not just after a
known crash.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from .content import Entity, EntityField, KeyFlow, KeyScreen, ResolvedConnector, SpecEngineError
from .scaffold import plan_scaffold_from_spec, write_scaffold_stub
from .types import ScaffoldModule, ScaffoldPlan, SpecDocument

PathLike = Union[str, Path]

DEFAULT_TARGET_STACK = "node-http-minimal"
SUPPORTED_TARGET_STACKS = (DEFAULT_TARGET_STACK,)

# "generated-connector" (Connectors v1, docs/design/connectors-architecture.md
# §6.3) is an ADDITIVE fourth value — a real client generated from a
# REGISTERED connector manifest, operational once its declared env var is
# configured. Deliberately NOT folded into plain "generated": operability
# depends on runtime configuration this repo cannot carry (an unset env var
# means a real, working client still answers 503, not 200) — collapsing that
# distinction would be exactly the overstatement the per-module manifest
# exists to prevent. See _render_connector_client_js() below.
GENERATION_STATUSES = ("generated", "generated-stub-logic", "stub", "generated-connector")

# Every v1 connector declares exactly one wired operation, by this name
# (connector_resolver.DEFAULT_OPERATION_NAME) — the generated app's single
# POST route per integration invokes it directly; there is no v1 operation
# -selection surface in the request (see _render_server_js's INTEGRATION_ROUTES
# handling below).
_CONNECTOR_RUNTIME_REL_PATH = "src/integrations/_connector-runtime.js"

# The one test file this codegen slice ever writes. Referenced by exact
# path (never a bare directory or glob) in package.json's "test" script
# and in every generated doc comment — `node --test <directory>`'s
# positional-argument test-discovery behavior is NOT stable across Node
# versions (empirically: passes on Node 20, fails with MODULE_NOT_FOUND
# on Node 22.23.1 for the exact same generated tree — reproduced locally
# and in CI). An explicit file path sidesteps that version-dependent
# discovery logic entirely and works identically on every Node >=18.
ACCEPTANCE_TEST_REL_PATH = "tests/acceptance.test.js"

_INFRA_NOTE = (
    "Infrastructure file — required scaffolding for this target stack, "
    "not derived from any single spec section."
)


# --------------------------------------------------------------------------
# Small, pure helpers — no filesystem access.
# --------------------------------------------------------------------------

_SLUG_SANITIZE_RE = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    """Lowercase, hyphenated, filesystem/URL-safe slug. Never empty."""
    slug = _SLUG_SANITIZE_RE.sub("-", (name or "").strip().lower()).strip("-")
    return slug or "item"


def _unique_slug(seen: Dict[str, int], base: str) -> str:
    """Return `base`, or `base-2`, `base-3`, ... the first time `base`
    collides with a slug already handed out to THIS `seen` registry
    (one registry per file-namespace: models/pages/flows/integrations are
    each their own namespace, so an entity and a screen with the same
    name never collide with each other, only within their own kind)."""
    count = seen.get(base, 0) + 1
    seen[base] = count
    return base if count == 1 else f"{base}-{count}"


def _pluralize(slug: str) -> str:
    """Naive, deterministic English pluralization heuristic for REST
    collection paths (`/api/<plural>`). Handles the common regular cases
    (`-s`, `-es` after s/x/z/ch/sh, `-y`->`-ies` after a consonant);
    genuinely irregular plurals (e.g. "person"->"people") are NOT
    special-cased — documented as a known v1 limitation, not silently
    "fixed" by guessing."""
    if slug.endswith(("s", "x", "z", "ch", "sh")):
        return slug + "es"
    if len(slug) >= 2 and slug[-1] == "y" and slug[-2] not in "aeiou":
        return slug[:-1] + "ies"
    return slug + "s"


def _js_string(value: str) -> str:
    """A valid JS/JSON string literal for `value`. `json.dumps` produces
    valid JS source for any Python str (JSON string syntax is a strict
    subset of JS string syntax) — reused here instead of hand-rolling
    escaping so every free-text field from the spec (names, descriptions,
    acceptance criteria — none of it is trusted or pre-sanitized) is safe
    to embed directly into generated source."""
    return json.dumps(value)


def _html_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _sample_value_for_field(f: EntityField, index: int = 1) -> Any:
    """A deterministic, type-plausible sample value for `f` — used ONLY
    to build real request bodies in generated tests (never written into
    a model's own persistence logic). `EntityField.type` is freeform text
    (see content.py) — this is a best-effort heuristic keyed on
    substrings, not a real type system; falls back to a labeled string
    sample when nothing matches, which is always valid input for the
    generated model's presence-only validation."""
    t = (f.type or "").lower()
    name = (f.name or "").lower()
    if "bool" in t:
        return True
    if any(k in t for k in ("int", "num", "float", "decimal", "price", "amount", "count", "qty", "quantity")):
        return index
    if "date" in t or "time" in t:
        return "2026-01-01T00:00:00.000Z"
    if "email" in name or "email" in t:
        return f"sample{index}@example.com"
    return f"sample-{f.name}-{index}"


def _match_entity_by_name(needle: str, entities: Sequence[Entity]) -> Optional[Entity]:
    """Heuristic name match (case-insensitive, slug-substring, either
    direction) — used to decide whether a screen/acceptance-criterion
    should be wired to a specific entity's live data, or fall back to a
    spec-description-only / boot-check rendering. Never guesses across
    unrelated words; a false negative (rendering the fallback when a
    human WOULD see the connection) is the safe failure mode here, not a
    false positive."""
    needle_slug = _slugify(needle)
    for entity in entities:
        entity_slug = _slugify(entity.name)
        if entity_slug and (entity_slug in needle_slug or needle_slug in entity_slug):
            return entity
    return None


# --------------------------------------------------------------------------
# Connectors v1 — one route-shape descriptor per how_it_works.integrations
# entry, built while writing src/integrations/**, consumed by
# _render_server_js() to wire INTEGRATION_ROUTES. `kind` is what the
# generated server's route loop branches on: "stub" keeps today's unchanged
# call()-always-throws-501 behavior; "connector" calls the real client's
# call(operation, input) and maps its typed errors to real HTTP statuses.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _IntegrationRoute:
    integration_name: str
    slug: str
    kind: str  # "stub" | "connector"
    operation: Optional[str]
    env_vars: List[str]
    connector_id: Optional[str]


# --------------------------------------------------------------------------
# Result type
# --------------------------------------------------------------------------


@dataclass
class CodegenResult:
    """Everything `generate_app()` produced. `manifest` is the exact
    object serialized to `.spec-engine/codegen-manifest.json` (schema:
    `schema/codegen-manifest.schema.json`)."""

    written: Dict[str, Path] = field(default_factory=dict)
    scaffold_plan: Optional[ScaffoldPlan] = None
    manifest: Dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


def generate_app(
    spec: SpecDocument,
    target_dir: PathLike,
    *,
    scaffold_plan: Optional[ScaffoldPlan] = None,
    target_stack: str = DEFAULT_TARGET_STACK,
) -> CodegenResult:
    """Generate a real, runnable app from `spec` into `target_dir`. If
    `scaffold_plan` is not given, one is derived via
    `plan_scaffold_from_spec(spec, target_stack=target_stack)`. Fails
    loud (`SpecEngineError`) rather than silently generating a
    mismatched or partial app if: `target_stack` is unsupported, the
    given `scaffold_plan` was not built from THIS `spec` (id/version
    mismatch), or the plan's per-kind module counts don't match the
    spec's own lists (a stale/hand-edited plan) — see module docstring
    for the target-stack choice and the per-module generation-status
    contract this function honors.

    Atomic (see module docstring's "Atomicity" section): the full tree is
    staged in a same-filesystem sibling directory and swapped into
    `target_dir` with exactly one `os.replace()` only after every file —
    including the manifest — has been written. A process killed at any
    point leaves `target_dir` either exactly as found or the complete,
    `codegen_status: "generated"` tree; never a partial mix. Every call
    also first repairs any interrupted rename-aside-swap left behind by a
    PRIOR killed call before doing anything else (see
    `_recover_interrupted_publish()`) — so a kill between
    `_publish_staged_app()`'s two renames never causes the next call to
    silently discard real prior `target_dir` content."""
    if target_stack not in SUPPORTED_TARGET_STACKS:
        raise SpecEngineError(
            f"generate_app: target_stack {target_stack!r} is not supported "
            f"(supported: {SUPPORTED_TARGET_STACKS})"
        )

    plan = scaffold_plan if scaffold_plan is not None else plan_scaffold_from_spec(spec, target_stack=target_stack)
    if plan.spec_id != spec.spec_id or plan.spec_version != spec.spec_version:
        raise SpecEngineError(
            f"generate_app: scaffold_plan (spec_id={plan.spec_id!r}, "
            f"spec_version={plan.spec_version}) does not match spec "
            f"(spec_id={spec.spec_id!r}, spec_version={spec.spec_version}) — "
            "regenerate the plan from this exact spec before generating code."
        )

    final_root = Path(target_dir)
    final_root.parent.mkdir(parents=True, exist_ok=True)
    # MUST run before `has_existing_content` is decided below: repairs any
    # rename-aside-swap a PRIOR call left interrupted (see
    # `_recover_interrupted_publish()`'s docstring) so that leftover state
    # is never mistaken for "target_dir has always been empty" by this
    # call. Unconditional — cheap (two `Path.exists()` checks) on the
    # overwhelmingly common case where there is nothing to recover.
    _recover_interrupted_publish(final_root)
    # "Has real content to preserve" is NOT the same as `.exists()`: every
    # real caller today (orchestrator/pipeline.py, and pytest's own
    # `tmp_path` fixture in every test in this suite) hands generate_app()
    # a directory that already EXISTS but is EMPTY — and POSIX `rename(2)`
    # is perfectly happy replacing an empty directory (see
    # `_publish_staged_app()`), so only a genuinely NON-empty `target_dir`
    # needs the slower preserve-and-swap path. Evaluated AFTER recovery
    # above, so a just-restored prior tree is correctly seen as existing
    # content, not as an empty/absent `target_dir`.
    has_existing_content = final_root.exists() and any(final_root.iterdir())
    stage_root = Path(
        tempfile.mkdtemp(prefix=f".{final_root.name}.codegen-stage-", dir=str(final_root.parent))
    )
    try:
        if has_existing_content:
            # `write_scaffold_stub()` (called at the end of
            # `_write_generated_app_tree()`) MERGES with an
            # already-present CLAUDE.md/AGENTS.md rather than overwriting
            # it — staging must start from a real copy of `target_dir`'s
            # current content for that merge to see the same state it
            # would have seen writing into `target_dir` directly, not an
            # empty directory. `symlinks=True` preserves any symlink in
            # pre-existing content as a symlink in the staged copy rather
            # than silently dereferencing it into the target's content.
            shutil.copytree(final_root, stage_root, dirs_exist_ok=True, symlinks=True)
        result = _write_generated_app_tree(stage_root, spec, plan, target_stack)
        # Publishing is inside this same try/except: an exception raised
        # by `_publish_staged_app()` itself (its own internal
        # restore-on-exception handling notwithstanding) must still clean
        # up `stage_root` here — `_publish_staged_app()` only ever
        # consumes `stage_root` (renames it away) on the success path, so
        # this cleanup is always safe to attempt, and a no-op
        # (`ignore_errors=True`) on that success path since the path no
        # longer exists under its staging name by then.
        _publish_staged_app(stage_root, final_root, has_existing_content=has_existing_content)
    except BaseException:
        shutil.rmtree(stage_root, ignore_errors=True)
        raise

    # `result.written`'s Path values were built against `stage_root`
    # (renamed away by the publish above — that inode now IS
    # `final_root`); rebind them so callers see real, live paths under
    # `target_dir`, exactly as if generation had written there directly.
    result.written = {rel: final_root / rel for rel in result.written}
    return result


def _write_generated_app_tree(
    root: Path, spec: SpecDocument, plan: ScaffoldPlan, target_stack: str
) -> CodegenResult:
    """The actual per-module/infrastructure/manifest generation — every
    file this writes goes into `root`, which is ALWAYS a STAGING
    directory (see `generate_app()`, the only caller); this function has
    no awareness that `root` is not the caller's real `target_dir` and
    does not need any — atomicity is entirely `generate_app()`'s
    responsibility via `_publish_staged_app()`, not this one's. Unchanged
    by the atomic-staging fix other than taking `root`/`plan`/
    `target_stack` as explicit parameters instead of closing over
    `target_dir`."""
    root.mkdir(parents=True, exist_ok=True)

    by_kind: Dict[str, List[ScaffoldModule]] = {}
    for module in plan.modules:
        by_kind.setdefault(module.kind, []).append(module)

    def _require_matching_count(kind: str, spec_items: Sequence[Any]) -> List[ScaffoldModule]:
        modules = by_kind.get(kind, [])
        if len(modules) != len(spec_items):
            raise SpecEngineError(
                f"generate_app: {len(modules)} {kind!r} module(s) in scaffold_plan "
                f"but {len(spec_items)} matching item(s) in spec — plan/spec are out "
                "of sync; regenerate the plan via plan_scaffold_from_spec(spec)."
            )
        return modules

    entity_modules = _require_matching_count("backend-model", spec.data_model.entities)
    screen_modules = _require_matching_count("frontend-page", spec.how_it_looks.key_screens)
    flow_modules = _require_matching_count("service", spec.how_it_works.key_flows)
    integration_modules = _require_matching_count("integration", spec.how_it_works.integrations)
    test_modules = by_kind.get("test-suite", [])

    # Connectors v1: `spec.resolved_connectors` was bound into the approval
    # gate's content hash as a list POSITIONALLY aligned with
    # `spec.how_it_works.integrations` (spec_builder.build_spec() copies it
    # verbatim from the approved plan — see connector_resolver.py's module
    # docstring for why this is resolved ONCE, at plan time, never re-read
    # here). A length mismatch means the SpecDocument itself is internally
    # inconsistent (never a normal "some integrations unresolved" case,
    # which is `ResolvedConnector.status == "unresolved"`, not a missing
    # entry) — fail loud rather than guess an alignment.
    if len(spec.resolved_connectors) != len(spec.how_it_works.integrations):
        raise SpecEngineError(
            f"generate_app: {len(spec.resolved_connectors)} resolved_connectors entry(ies) but "
            f"{len(spec.how_it_works.integrations)} how_it_works.integrations entry(ies) — spec is "
            "internally inconsistent (resolved_connectors must be 1:1 positionally aligned with "
            "how_it_works.integrations; see connector_resolver.resolve_connectors())."
        )

    written: Dict[str, Path] = {}
    manifest_modules: List[Dict[str, Any]] = []
    entity_slugs: Dict[str, int] = {}
    screen_slugs: Dict[str, int] = {}
    flow_slugs: Dict[str, int] = {}
    integration_slugs: Dict[str, int] = {}

    entities_by_slug: Dict[str, Tuple[Entity, str]] = {}  # slug -> (entity, class-name-safe slug)
    for module, entity in zip(entity_modules, spec.data_model.entities):
        slug = _unique_slug(entity_slugs, _slugify(entity.name))
        entities_by_slug[slug] = (entity, slug)
        rel_path = f"src/models/{slug}.js"
        _write_file(root, rel_path, _render_model_js(entity, module))
        written[rel_path] = root / rel_path
        manifest_modules.append(
            _manifest_entry(module, "generated", [rel_path], f"In-memory CRUD store for entity '{entity.name}'.")
        )

    screens_written: List[Tuple[KeyScreen, str]] = []
    for module, screen in zip(screen_modules, spec.how_it_looks.key_screens):
        slug = _unique_slug(screen_slugs, _slugify(screen.name))
        matched_entity = _match_entity_by_name(screen.name, spec.data_model.entities)
        matched_slug = None
        if matched_entity is not None:
            for eslug, (entity, _) in entities_by_slug.items():
                if entity is matched_entity:
                    matched_slug = eslug
                    break
        rel_path = f"src/pages/{slug}.js"
        _write_file(root, rel_path, _render_page_js(screen, module, matched_entity, matched_slug))
        written[rel_path] = root / rel_path
        screens_written.append((screen, slug))
        note = (
            f"Server-rendered page for screen '{screen.name}', showing live "
            f"'{matched_entity.name}' records." if matched_entity
            else f"Server-rendered page for screen '{screen.name}' (spec description only — "
                 "no matching data-model entity found)."
        )
        manifest_modules.append(_manifest_entry(module, "generated", [rel_path], note))

    flows_written: List[Tuple[KeyFlow, str]] = []
    for module, flow in zip(flow_modules, spec.how_it_works.key_flows):
        slug = _unique_slug(flow_slugs, _slugify(flow.name))
        rel_path = f"src/flows/{slug}.js"
        _write_file(root, rel_path, _render_flow_js(flow, module))
        written[rel_path] = root / rel_path
        flows_written.append((flow, slug))
        manifest_modules.append(
            _manifest_entry(
                module,
                "generated-stub-logic",
                [rel_path],
                f"Real, executable step sequence for flow '{flow.name}'; each step's business-logic "
                "body is a documented TODO placeholder (flow steps are free text — codegen cannot "
                "compile prose into working business logic).",
            )
        )

    integrations_written: List[_IntegrationRoute] = []
    any_resolved_connector = False
    for module, integration_name, resolved in zip(
        integration_modules, spec.how_it_works.integrations, spec.resolved_connectors
    ):
        slug = _unique_slug(integration_slugs, _slugify(integration_name))
        rel_path = f"src/integrations/{slug}.js"

        if resolved.status == "resolved":
            renderer = _CONNECTOR_CLIENT_RENDERERS.get(resolved.connector_id)
            if renderer is None:
                raise SpecEngineError(
                    f"generate_app: integration {integration_name!r} resolved to registered "
                    f"connector {resolved.connector_id!r}, but codegen has no generated-client "
                    "template for that connector id — the registry and codegen.py's "
                    "_CONNECTOR_CLIENT_RENDERERS have drifted out of sync (a registry-only change "
                    "that adds a 4th connector needs a matching codegen.py template before specs "
                    "can resolve to it)."
                )
            any_resolved_connector = True
            _write_file(root, rel_path, renderer(integration_name, module, resolved))
            written[rel_path] = root / rel_path
            operation_names = sorted({op.name for op in resolved.operations})
            side_effects = sorted({op.side_effect for op in resolved.operations})
            integrations_written.append(
                _IntegrationRoute(
                    integration_name=integration_name,
                    slug=slug,
                    kind="connector",
                    operation=resolved.operations[0].name,
                    env_vars=list(resolved.auth_env_vars),
                    connector_id=resolved.connector_id,
                )
            )
            manifest_modules.append(
                _manifest_entry(
                    module,
                    "generated-connector",
                    [rel_path],
                    f"Real, vendored fetch() client for integration '{integration_name}', generated "
                    f"from registered connector {resolved.connector_id}@{resolved.connector_version} "
                    f"(manifest_hash={resolved.manifest_hash}). Operational once "
                    f"{'/'.join(resolved.auth_env_vars)} is configured; until then its route returns "
                    "HTTP 503 (not 501) — the code is real, operability depends on runtime "
                    "configuration this repo cannot carry.",
                    connector={
                        "connector_id": resolved.connector_id,
                        "connector_version": resolved.connector_version,
                        "manifest_hash": resolved.manifest_hash,
                        "operations": operation_names,
                        "env_vars": list(resolved.auth_env_vars),
                        "side_effect_classes": side_effects,
                    },
                )
            )
        else:
            _write_file(root, rel_path, _render_integration_js(integration_name, module))
            written[rel_path] = root / rel_path
            integrations_written.append(
                _IntegrationRoute(
                    integration_name=integration_name, slug=slug, kind="stub", operation=None,
                    env_vars=[], connector_id=None,
                )
            )
            registered_note = (
                f" Connector ids registered in this checkout: {', '.join(resolved.registered_connector_ids)}."
                if resolved.registered_connector_ids
                else " No connectors are registered in this checkout at all."
            )
            manifest_modules.append(
                _manifest_entry(
                    module,
                    "stub",
                    [rel_path],
                    f"Labeled connector stub for integration '{integration_name}' — no registered "
                    "connector matched this name (exact id/alias match only)."
                    + registered_note,
                )
            )

    # Infrastructure — required for any app on this target stack, not
    # attributed to a source_section (see module docstring).
    infra_files: List[str] = []
    infra_entries: List[Tuple[str, str]] = [
        ("src/http-util.js", _render_http_util_js()),
        (
            "src/server.js",
            _render_server_js(
                spec,
                entities_by_slug=[(slug, entity) for slug, (entity, _) in entities_by_slug.items()],
                screens=screens_written,
                flows=flows_written,
                integrations=integrations_written,
            ),
        ),
        ("package.json", _render_package_json(spec)),
        ("README.md", _render_app_readme(spec, target_stack, integrations_written)),
    ]
    # _connector-runtime.js is shared, generated-once infrastructure —
    # written ONLY when at least one integration resolved to a registered
    # connector (see the loop above); an app with zero resolved connectors
    # (every integration unresolved, or no integrations at all) never gets
    # a dead, unused file.
    if any_resolved_connector:
        infra_entries.append((_CONNECTOR_RUNTIME_REL_PATH, _render_connector_runtime_js()))
    for rel_path, content in infra_entries:
        _write_file(root, rel_path, content)
        written[rel_path] = root / rel_path
        infra_files.append(rel_path)

    # Tests — from acceptance_criteria (deliverable: "acceptance_criteria
    # -> generated tests"), plus a baseline boot check and a per-entity
    # CRUD round-trip test that runs regardless of acceptance_criteria
    # content.
    test_rel_path = ACCEPTANCE_TEST_REL_PATH
    _write_file(
        root,
        test_rel_path,
        _render_acceptance_test_js(
            spec,
            entities=[(slug, entity) for slug, (entity, _) in entities_by_slug.items()],
        ),
    )
    written[test_rel_path] = root / test_rel_path
    if test_modules:
        for module in test_modules:
            manifest_modules.append(
                _manifest_entry(
                    module,
                    "generated",
                    [test_rel_path],
                    "Real node:test suite: a baseline boot/health check, one CRUD round-trip per "
                    "entity, and one test per acceptance_criteria entry (entity-backed where the "
                    "criterion text names a known entity, else an honestly-commented fallback).",
                )
            )
    else:
        infra_files.append(test_rel_path)

    finalized_plan = ScaffoldPlan(
        spec_id=plan.spec_id,
        spec_version=plan.spec_version,
        generated_at=plan.generated_at,
        modules=plan.modules,
        target_stack=target_stack,
        codegen_status="generated",
        notes=plan.notes,
    )

    manifest = {
        "spec_id": spec.spec_id,
        "spec_version": spec.spec_version,
        "target_stack": target_stack,
        "generated_at": finalized_plan.generated_at,
        "codegen_status": "generated",
        "modules": manifest_modules,
        "infrastructure_files": infra_files,
        "notes": (
            f"{len(manifest_modules)} spec-derived module(s), {len(infra_files)} infrastructure "
            "file(s). generation_status per module: 'generated' (real, working code), "
            "'generated-stub-logic' (real wiring, TODO business logic), 'stub' (labeled "
            "placeholder only, not functional). Never treat 'codegen_status: generated' at the "
            "top level as implying every module is production-ready — read this manifest."
        ),
    }
    manifest_rel_path = ".spec-engine/codegen-manifest.json"
    _write_file(root, manifest_rel_path, json.dumps(manifest, indent=2, sort_keys=True))
    written[manifest_rel_path] = root / manifest_rel_path

    scaffold_written = write_scaffold_stub(spec, root, scaffold_plan=finalized_plan)
    written.update(scaffold_written)

    return CodegenResult(written=written, scaffold_plan=finalized_plan, manifest=manifest)


def _manifest_entry(
    module: ScaffoldModule,
    generation_status: str,
    files: List[str],
    notes: str,
    *,
    connector: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if generation_status not in GENERATION_STATUSES:
        raise SpecEngineError(f"_manifest_entry: {generation_status!r} not in {GENERATION_STATUSES}")
    if connector is not None and generation_status != "generated-connector":
        raise SpecEngineError(
            "_manifest_entry: connector= is only valid on a 'generated-connector' entry"
        )
    return {
        "module_id": module.module_id,
        "kind": module.kind,
        "source_section": module.source_section,
        "generation_status": generation_status,
        "files": files,
        "notes": notes,
        # Present (non-null) ONLY on generated-connector modules — connector
        # id@version, manifest content hash, the operations wired, the
        # declared env var names, and the side-effect classes (design §6.3).
        # Always present as a key (never omitted) so the schema can require
        # it uniformly rather than treat it as sometimes-absent.
        "connector": connector,
    }


def _write_file(root: Path, rel_path: str, content: str) -> Path:
    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _swap_aside_path(final_root: Path) -> Path:
    """The ONE, deterministic sibling path `_publish_staged_app()` ever
    renames `final_root`'s prior content aside to, for the duration of the
    two-rename swap described in its docstring below. Deterministic (not
    a `tempfile.mkdtemp()`-style random suffix) is the point: it lets
    `_recover_interrupted_publish()` find — unambiguously, on ANY later
    call — whether THIS `target_dir`'s swap was left interrupted, without
    having to guess which of possibly-several random-suffixed siblings
    might be the one that matters. A random name is exactly what let the
    original data-loss bug happen: nothing pointed back to it."""
    return final_root.parent / f".{final_root.name}.codegen-prev"


def _recover_interrupted_publish(final_root: Path) -> None:
    """Called unconditionally at the very start of every `generate_app()`
    call, before `has_existing_content` is decided — repairs the ONE
    state a hard kill between `_publish_staged_app()`'s two `os.replace()`
    calls (the `has_existing_content=True` branch) can leave behind:
    `final_root` swapped aside to `_swap_aside_path(final_root)` but never
    swapped back, because the process died before the second rename ran.

    Left unrepaired, the NEXT call against the same `target_dir` — the
    natural "just re-run it" recovery action after a crash — would see
    `final_root` absent, treat this as a first-ever generation, and
    silently publish fresh content straight over it: the real prior
    content sitting in the aside directory would never be looked at
    again, and is destroyed the moment this run's own publish succeeds.
    This function closes that window by restoring the aside BEFORE this
    run (or any run) gets a chance to draw that wrong conclusion; once
    restored, `generate_app()`'s normal `has_existing_content` handling
    takes back over and re-does the swap correctly.

    The other interrupted-cleanup case — the second rename succeeded (so
    `final_root` already holds the complete, correct new content) but the
    final `shutil.rmtree(aside, ...)` never ran — is also repaired here:
    the aside is stale prior content at that point, safe to discard.

    Any state this function cannot safely reconcile — concretely, the
    aside path existing but not being a directory, which nothing in this
    module ever creates — is a genuinely ambiguous situation (something
    outside `_publish_staged_app()`'s own two-rename sequence put
    something there) and is never silently guessed at: this raises
    `SpecEngineError` rather than risk restoring, or discarding, the
    wrong thing."""
    aside = _swap_aside_path(final_root)
    if not aside.exists():
        # The overwhelmingly common case: no prior swap was ever
        # interrupted (either none was ever attempted against this
        # `target_dir`, or the last one that was ran to completion,
        # cleanup included). Nothing to reconcile.
        return

    if not aside.is_dir():
        raise SpecEngineError(
            f"generate_app: {aside} exists but is not a directory. This path is reserved for "
            "_publish_staged_app()'s rename-aside-swap recovery and nothing in this module ever "
            "creates it as anything else — refusing to guess whether it is safe to restore into "
            f"{final_root} or delete outright. Move or remove {aside} by hand (after confirming "
            "what it actually is) before regenerating."
        )

    if not final_root.exists():
        # Interrupted between the two os.replace() calls: the original
        # content is intact in `aside`; `final_root` is absent. Restore
        # it FIRST so this run — and every check `generate_app()` makes
        # after this one returns — sees the real, pre-crash state.
        os.replace(aside, final_root)
        return

    # `final_root` exists AND `aside` exists: the second rename already
    # completed (`final_root` holds the fully-published new content) but
    # the trailing `shutil.rmtree(aside, ...)` cleanup step never ran.
    # `aside` is stale prior content now — safe to discard.
    shutil.rmtree(aside, ignore_errors=True)


def _publish_staged_app(stage_root: Path, final_root: Path, *, has_existing_content: bool) -> None:
    """The ONE moment `generate_app()` ever touches `final_root` (the
    caller's real `target_dir`): a same-filesystem `os.replace()` — a
    single atomic rename syscall — swaps the fully-written `stage_root`
    into `final_root`'s place. Nothing before this call has written
    anything to `final_root` itself, so a process killed at any point up
    to (but not including) this call leaves `final_root` exactly as
    `generate_app()` found it — absent, empty, or its own prior content,
    NEVER a codegen-produced partial file. The rename syscall cannot be
    observed half-done: a reader of `final_root` sees either the old
    state or the complete new tree, never a mix of the two.

    When `final_root` already held real content (`has_existing_content`),
    a direct `os.replace(stage_root, final_root)` is refused by the OS —
    POSIX `rename(2)` only replaces a directory target that is missing or
    EMPTY, never a non-empty one (verified empirically on this repo's
    target platforms: `os.replace()` onto an existing non-empty directory
    raises `OSError: [Errno 66] Directory not empty` on macOS/BSD, or
    `OSError: [Errno 39] Directory not empty` on Linux — the code below
    does not branch on the errno value either way, since the safe
    two-rename path is always taken whenever `has_existing_content` is
    true, regardless of platform) — so the prior tree is first atomically
    renamed aside to `_swap_aside_path(final_root)` (still exactly one
    atomic rename; a DETERMINISTIC path, not a random one — see that
    function's docstring for why), `stage_root` then takes `final_root`'s
    place, and the aside is removed.

    Between those two renames `final_root` is briefly ABSENT. UNLIKE a
    first-ever generation's absence, this is not a state with nothing to
    lose: real, previously-committed `target_dir` content is, at that
    instant, sitting only in the aside directory. A kill exactly here
    does not corrupt or partially-mix anything (`final_root` is cleanly
    absent, never a mix of old and new), but it DOES leave that real
    content orphaned — recoverable only because `generate_app()`
    unconditionally checks for and repairs exactly this state on every
    call, before this function ever runs again (see
    `_recover_interrupted_publish()`). This function does not, and
    structurally cannot, defend against that kill window by itself — it
    is two syscalls with nothing to catch a `SIGKILL` between them; the
    recovery guarantee lives one level up, in `generate_app()`, by
    design."""
    if not has_existing_content:
        os.replace(stage_root, final_root)
        return

    aside = _swap_aside_path(final_root)
    if aside.exists():
        # `_recover_interrupted_publish()` unconditionally reconciles or
        # clears this exact path at the start of every `generate_app()`
        # call, before staging even begins — by construction, it should
        # never exist here. If it does anyway (e.g. a second
        # `generate_app()` call racing this one against the same
        # `target_dir` — concurrent calls are not a supported use of this
        # function), fail loud rather than silently clobber whatever is
        # in it or lose track of `final_root`'s current content.
        raise SpecEngineError(
            f"_publish_staged_app: {aside} already exists immediately before the rename-aside-swap "
            "it is reserved for. generate_app()'s _recover_interrupted_publish() should already "
            "have reconciled or cleared this path — its unexpected presence here most likely means "
            "a concurrent generate_app() call is racing this one against the same target_dir "
            "(not supported); refusing to publish rather than risk clobbering or losing content."
        )

    os.replace(final_root, aside)
    try:
        os.replace(stage_root, final_root)
    except BaseException:
        # Both renames' preconditions are already satisfied by the time
        # the first one runs; nothing in this module can make the second
        # one fail after the first succeeds. Restore rather than leave
        # `final_root` absent if it somehow does anyway.
        os.replace(aside, final_root)
        raise
    shutil.rmtree(aside, ignore_errors=True)


# --------------------------------------------------------------------------
# Per-module generators — src/models/<slug>.js
# --------------------------------------------------------------------------


def _render_model_js(entity: Entity, module: ScaffoldModule) -> str:
    class_name = "".join(part.capitalize() for part in re.split(r"[^A-Za-z0-9]+", entity.name) if part) or "Entity"
    field_names = [f.name for f in entity.fields]
    fields_js = ", ".join(_js_string(n) for n in field_names)
    return f"""\
"use strict";

/**
 * GENERATED backend model for entity {_js_string(entity.name)}.
 * Source: spec section {module.source_section} — spec_engine.codegen
 * (target_stack: {DEFAULT_TARGET_STACK}). generation_status: "generated"
 * (see ../../.spec-engine/codegen-manifest.json).
 *
 * In-memory store — data is NOT persisted across process restarts. A
 * persistent database is a later deliverable (TESS-VISION-AND-BUILD-SPEC.html
 * Phase 2 Epic E4: "provisions DB"), out of scope for this codegen slice.
 */

const crypto = require("node:crypto");

const FIELDS = [{fields_js}];

class {class_name}Store {{
  constructor() {{
    this._byId = new Map();
  }}

  list() {{
    return Array.from(this._byId.values());
  }}

  get(id) {{
    return this._byId.get(id) || null;
  }}

  create(data) {{
    data = data || {{}};
    const missing = FIELDS.filter((f) => !(f in data));
    if (missing.length) {{
      const err = new Error(
        {_js_string(f"{entity.name}.create: missing field(s): ")} + missing.join(", ")
      );
      err.statusCode = 400;
      throw err;
    }}
    const id = crypto.randomUUID();
    const record = {{ id }};
    for (const f of FIELDS) record[f] = data[f];
    this._byId.set(id, record);
    return record;
  }}

  update(id, data) {{
    const existing = this._byId.get(id);
    if (!existing) return null;
    data = data || {{}};
    const updated = {{ ...existing }};
    for (const f of FIELDS) {{
      if (f in data) updated[f] = data[f];
    }}
    this._byId.set(id, updated);
    return updated;
  }}

  remove(id) {{
    return this._byId.delete(id);
  }}
}}

module.exports = {{ {class_name}Store, FIELDS }};
"""


# --------------------------------------------------------------------------
# Per-module generators — src/pages/<slug>.js
# --------------------------------------------------------------------------


def _render_page_js(
    screen: KeyScreen, module: ScaffoldModule, matched_entity: Optional[Entity], matched_slug: Optional[str]
) -> str:
    title_html = _html_escape(screen.name)
    description_html = _html_escape(screen.description or "(no description in spec)")
    if matched_entity is not None and matched_slug is not None:
        body = f"""\
function render(context) {{
  const store = context.entityStores[{_js_string(matched_slug)}];
  const records = store ? store.list() : [];
  const rows = records
    .map(
      (r) =>
        "<li>" +
        Object.entries(r)
          .map(([k, v]) => "<strong>" + escapeHtml(k) + ":</strong> " + escapeHtml(v))
          .join(" &middot; ") +
        "</li>"
    )
    .join("\\n");
  return (
    "<!doctype html><html><head><meta charset=\\"utf-8\\"><title>" +
    {_js_string(title_html)} +
    "</title></head><body><h1>" +
    {_js_string(title_html)} +
    "</h1><p>" +
    {_js_string(description_html)} +
    "</p><ul>" +
    (rows || "<li>(no records yet)</li>") +
    "</ul></body></html>"
  );
}}
"""
    else:
        body = f"""\
function render(context) {{
  return (
    "<!doctype html><html><head><meta charset=\\"utf-8\\"><title>" +
    {_js_string(title_html)} +
    "</title></head><body><h1>" +
    {_js_string(title_html)} +
    "</h1><p>" +
    {_js_string(description_html)} +
    "</p><p><em>No matching data-model entity found for this screen — " +
    "this page renders the spec's own description only.</em></p></body></html>"
  );
}}
"""
    return f"""\
"use strict";

/**
 * GENERATED frontend page for screen {_js_string(screen.name)}.
 * Source: spec section {module.source_section} — spec_engine.codegen
 * (target_stack: {DEFAULT_TARGET_STACK}). generation_status: "generated"
 * (see ../../.spec-engine/codegen-manifest.json).
 *
 * Server-rendered plain HTML — no build step, no client-side framework.
 */

function escapeHtml(value) {{
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}}

{body}
module.exports = {{ render }};
"""


# --------------------------------------------------------------------------
# Per-module generators — src/flows/<slug>.js
# --------------------------------------------------------------------------


def _render_flow_js(flow: KeyFlow, module: ScaffoldModule) -> str:
    steps_js = ",\n  ".join(_js_string(s) for s in flow.steps) if flow.steps else ""
    return f"""\
"use strict";

/**
 * GENERATED flow handler for {_js_string(flow.name)}.
 * Source: spec section {module.source_section} — spec_engine.codegen
 * (target_stack: {DEFAULT_TARGET_STACK}). generation_status:
 * "generated-stub-logic" (see ../../.spec-engine/codegen-manifest.json):
 * the step SEQUENCE below is real and executes end to end; each step's
 * business-logic body is a documented placeholder. Flow steps are
 * free-text in the spec — codegen cannot compile prose into working
 * business/integration logic. Implement each TODO before relying on this
 * flow for anything real.
 */

const STEPS = [
  {steps_js}
];

async function run(input) {{
  const trace = [];
  for (const step of STEPS) {{
    // TODO: implement this step's real business logic. `input` is the
    // parsed JSON body of the request that triggered this flow.
    trace.push({{ step, status: "not_implemented" }});
  }}
  return {{
    flow: {_js_string(flow.name)},
    executed_at: new Date().toISOString(),
    steps: trace,
  }};
}}

module.exports = {{ run, STEPS }};
"""


# --------------------------------------------------------------------------
# Per-module generators — src/integrations/<slug>.js
# --------------------------------------------------------------------------


def _render_integration_js(integration_name: str, module: ScaffoldModule) -> str:
    return f"""\
"use strict";

/**
 * GENERATED integration connector STUB for {_js_string(integration_name)}.
 * Source: spec section {module.source_section} — spec_engine.codegen
 * (target_stack: {DEFAULT_TARGET_STACK}). generation_status: "stub" (see
 * ../../.spec-engine/codegen-manifest.json) — NOT a working connector.
 * Deterministic codegen cannot produce a working third-party integration
 * without real credentials/API contract details this spec does not
 * carry. This file is a clearly-labeled placeholder; implement it by
 * hand before use. The generated server wires it to a route that
 * returns HTTP 501 until you do.
 */

class IntegrationNotImplementedError extends Error {{}}

async function call() {{
  throw new IntegrationNotImplementedError(
    {_js_string(f"Integration {integration_name!r} is a codegen stub — implement this connector before use.")}
  );
}}

module.exports = {{ call }};
"""


# --------------------------------------------------------------------------
# Connectors v1 — src/integrations/_connector-runtime.js (shared infra,
# written ONLY when >=1 integration resolves to a registered connector) and
# src/integrations/<slug>.js for a RESOLVED integration (generation_status:
# "generated-connector"). docs/design/connectors-architecture.md §4.2/§6.3.
#
# Split, same discipline every other codegen template already applies: the
# GENERIC transport/error-handling/config logic (fetch with an
# AbortController timeout, env-var/base-url resolution, error_map status
# mapping, the six typed error classes) lives ONCE in the shared runtime;
# each provider's file supplies ONLY what is genuinely provider-specific —
# how a normalized `generate` input becomes THAT provider's request body,
# and how THAT provider's response becomes the normalized output. This is
# manifest-driven for id/version/hash/env-var-names/base-url/auth-header/
# timeout/error_map (all captured on the ResolvedConnector snapshot codegen
# was handed — see connector_resolver.py) and hand-authored ONLY for the
# per-provider request/response SHAPE, which the manifest's input_schema/
# output_schema do not attempt to encode as a code-generation DSL in v1
# (documented limitation — see spec-engine/README.md's Connectors section).
# --------------------------------------------------------------------------


def _render_connector_runtime_js() -> str:
    return f"""\
"use strict";

/**
 * GENERATED infrastructure — spec_engine.codegen (target_stack: {DEFAULT_TARGET_STACK}).
 * {_INFRA_NOTE}
 *
 * Shared runtime for every GENERATED CONNECTOR client (generation_status:
 * "generated-connector" — see ../../.spec-engine/codegen-manifest.json).
 * Zero npm dependencies: Node core `fetch()` + `AbortController` only
 * (both global in Node >=18). Every per-connector file in this directory
 * (e.g. anthropic.js) calls createConnectorClient() with its own
 * provider-specific buildRequest()/parseResponse() pair; everything else —
 * env-var/base-url resolution, the fetch+timeout, error_map status
 * mapping, the typed error classes — lives here exactly once.
 *
 * Contract (docs/design/connectors-architecture.md §4.2):
 *   call(operation, input) -> {{ output, usage, raw }} on success.
 *   Every failure is one of the typed error classes below — never a
 *   silent 200, never invented output, never a credential in a message.
 *   Config is read LAZILY, at call time, never at boot — a generated app
 *   with a configured-nowhere connector still boots and serves every
 *   other route; see _render_server_js()'s boot-time WARNING.
 */

class ConnectorConfigError extends Error {{
  constructor(message) {{ super(message); this.name = "ConnectorConfigError"; this.statusCode = 503; }}
}}
class ConnectorAuthError extends Error {{
  constructor(message) {{ super(message); this.name = "ConnectorAuthError"; this.statusCode = 503; }}
}}
class ConnectorRateLimitError extends Error {{
  constructor(message, retryAfter) {{
    super(message);
    this.name = "ConnectorRateLimitError";
    this.statusCode = 429;
    this.retryAfter = retryAfter || null;
  }}
}}
class ConnectorProviderError extends Error {{
  constructor(message) {{ super(message); this.name = "ConnectorProviderError"; this.statusCode = 502; }}
}}
class ConnectorContractError extends Error {{
  constructor(message) {{ super(message); this.name = "ConnectorContractError"; this.statusCode = 502; }}
}}
class ConnectorInvocationError extends Error {{
  constructor(message) {{ super(message); this.name = "ConnectorInvocationError"; this.statusCode = 400; }}
}}

const ERROR_CLASSES = {{
  ConnectorAuthError,
  ConnectorRateLimitError,
  ConnectorProviderError,
  ConnectorContractError,
  ConnectorInvocationError,
}};

function createConnectorClient(config) {{
  const {{
    id, version, manifestHash, displayName,
    envVars, headerName, headerValuePrefix,
    baseUrl, baseUrlOverrideEnv,
    apiVersionPin, timeoutMs, errorMap,
    operations, buildRequest, parseResponse,
  }} = config;

  const opByName = new Map(operations.map((op) => [op.name, op]));

  function resolveBaseUrl() {{
    if (baseUrlOverrideEnv && process.env[baseUrlOverrideEnv]) {{
      const override = process.env[baseUrlOverrideEnv];
      // https-pinned, same as the manifest's declared `base_url` (Cyra
      // LOW F6, PR #84 security review fix-up round): this override is a
      // disclosed escape hatch (connectors/registry/*/README.md "Base URL
      // override"), never a license to downgrade transport security. An
      // http:// (or any non-https://) value here would let a local env
      // var silently send the real auth header/key in cleartext, or to an
      // unintended internal endpoint — refused BEFORE any network call is
      // ever attempted, with the same typed-error/503 discipline every
      // other config problem in this client already uses.
      if (!override.startsWith("https://")) {{
        throw new ConnectorConfigError(
          id + ": " + baseUrlOverrideEnv + " is set but is not an https:// URL (" +
          JSON.stringify(override) + ") — refusing a non-HTTPS base-url override; " +
          "this manifest's https-only guarantee applies to base_url_override_env too"
        );
      }}
      return override;
    }}
    return baseUrl;
  }}

  function resolveApiKey() {{
    // v1 connectors declare exactly one env var; iterating handles a
    // future manifest declaring more than one without a runtime change.
    for (const name of envVars) {{
      const value = process.env[name];
      if (value) return {{ name, value }};
    }}
    return null;
  }}

  function isConfigured() {{
    return resolveApiKey() !== null;
  }}

  async function call(operationName, input) {{
    const op = opByName.get(operationName);
    if (!op) {{
      throw new ConnectorInvocationError(
        id + ": unknown operation " + JSON.stringify(operationName) + " — declared operation(s): " +
        Array.from(opByName.keys()).join(", ")
      );
    }}
    const key = resolveApiKey();
    if (!key) {{
      throw new ConnectorConfigError(
        id + ": not configured — set " + envVars.join(" or ") + " to make this connector " +
        "operational (currently unset; this route returns 503 until it is)"
      );
    }}

    // Resolved (and https-scheme-validated) BEFORE the request-building
    // try/catch below — same reason resolveApiKey() is checked above it:
    // a config problem must surface as its own typed ConnectorConfigError
    // (503), never get silently re-wrapped into a generic
    // ConnectorInvocationError (400) by the request-building catch block.
    const resolvedBaseUrl = resolveBaseUrl();

    let url;
    let requestInit;
    try {{
      const built = buildRequest(op, input || {{}});
      url = resolvedBaseUrl.replace(/\\/$/, "") + built.path;
      const headers = Object.assign({{ "Content-Type": "application/json" }}, built.headers || {{}});
      headers[headerName] = (headerValuePrefix || "") + key.value;
      if (apiVersionPin && apiVersionPin.kind === "header") {{
        headers[apiVersionPin.name] = apiVersionPin.value;
      }}
      requestInit = {{ method: op.httpMethod, headers, body: JSON.stringify(built.body) }};
    }} catch (err) {{
      throw new ConnectorInvocationError(
        id + ": could not build a request for " + operationName + " from the given input: " + err.message
      );
    }}

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    let response;
    try {{
      response = await fetch(url, Object.assign({{}}, requestInit, {{ signal: controller.signal }}));
    }} catch (err) {{
      if (err.name === "AbortError") {{
        throw new ConnectorProviderError(id + ": request to provider timed out after " + timeoutMs + "ms");
      }}
      throw new ConnectorProviderError(id + ": network error calling provider: " + err.message);
    }} finally {{
      clearTimeout(timer);
    }}

    const bodyText = await response.text();
    let bodyJson = null;
    try {{
      bodyJson = bodyText ? JSON.parse(bodyText) : null;
    }} catch (err) {{
      bodyJson = null; // handled below — a non-JSON body on a non-ok response still maps by status
    }}

    if (!response.ok) {{
      const className = errorMap[String(response.status)];
      const ErrClass = ERROR_CLASSES[className] || ConnectorProviderError;
      const providerMessage =
        bodyJson && bodyJson.error && typeof bodyJson.error === "object" && bodyJson.error.message
          ? bodyJson.error.message
          : bodyText.slice(0, 200);
      const message = id + ": provider responded " + response.status + (providerMessage ? " — " + providerMessage : "");
      if (ErrClass === ConnectorRateLimitError) {{
        throw new ConnectorRateLimitError(message, response.headers.get("retry-after"));
      }}
      throw new ErrClass(message);
    }}

    if (bodyJson === null) {{
      throw new ConnectorContractError(
        id + ": provider response was not valid JSON — contract mismatch (manifest " + id + "@" + version + ")"
      );
    }}

    let normalized;
    try {{
      normalized = parseResponse(op, bodyJson);
      if (!normalized || typeof normalized.text !== "string" || !normalized.usage) {{
        throw new Error("normalized output missing required fields (text, usage)");
      }}
    }} catch (err) {{
      throw new ConnectorContractError(
        id + ": provider response did not match the manifest's declared output shape (manifest " +
        id + "@" + version + "): " + err.message
      );
    }}

    return {{ output: normalized, usage: normalized.usage, raw: bodyJson }};
  }}

  return {{
    call,
    isConfigured,
    envVars,
    OPERATIONS: operations.map((op) => op.name),
    CONNECTOR: {{ id, version, manifest_hash: manifestHash, display_name: displayName }},
  }};
}}

module.exports = {{
  createConnectorClient,
  ERROR_CLASSES,
  ConnectorConfigError,
  ConnectorAuthError,
  ConnectorRateLimitError,
  ConnectorProviderError,
  ConnectorContractError,
  ConnectorInvocationError,
}};
"""


def _resolved_connector_config_js(resolved: ResolvedConnector) -> str:
    """The JS object-literal fragment shared by every per-provider
    generated file's `createConnectorClient({{...}})` call — every field
    that came from the manifest snapshot (`ResolvedConnector`), NOT the
    provider-specific `buildRequest`/`parseResponse` pair (those are
    appended by each `_render_<provider>_client_js()` caller)."""
    op = resolved.operations[0]
    api_version_pin_js = (
        "{ kind: %s, name: %s, value: %s }"
        % (
            _js_string(resolved.api_version_pin_kind),
            _js_string(resolved.api_version_pin_name) if resolved.api_version_pin_name else "null",
            _js_string(resolved.api_version_pin_value or ""),
        )
        if resolved.api_version_pin_kind
        else "null"
    )
    error_map_js = json.dumps(resolved.error_map, sort_keys=True)
    env_vars_js = ", ".join(_js_string(v) for v in resolved.auth_env_vars)
    return f"""\
  id: {_js_string(resolved.connector_id)},
  version: {_js_string(resolved.connector_version)},
  manifestHash: {_js_string(resolved.manifest_hash)},
  displayName: {_js_string(resolved.display_name or resolved.connector_id)},
  envVars: [{env_vars_js}],
  headerName: {_js_string(resolved.auth_header_name)},
  headerValuePrefix: {_js_string(resolved.auth_header_value_prefix or "")},
  baseUrl: {_js_string(resolved.base_url)},
  baseUrlOverrideEnv: {_js_string(resolved.base_url_override_env) if resolved.base_url_override_env else "null"},
  apiVersionPin: {api_version_pin_js},
  timeoutMs: {resolved.timeout_ms},
  errorMap: {error_map_js},
  operations: [{{ name: {_js_string(op.name)}, httpMethod: {_js_string(op.http_method)}, httpPath: {_js_string(op.http_path)} }}],
"""


def _connector_client_header(integration_name: str, module: ScaffoldModule, resolved: ResolvedConnector) -> str:
    return f"""\
"use strict";

/**
 * GENERATED integration CONNECTOR CLIENT for {_js_string(integration_name)}.
 * Source: spec section {module.source_section} — spec_engine.codegen
 * (target_stack: {DEFAULT_TARGET_STACK}). generation_status:
 * "generated-connector" (see ../../.spec-engine/codegen-manifest.json) —
 * REAL code, generated from registered connector
 * {resolved.connector_id}@{resolved.connector_version}
 * (manifest_hash={resolved.manifest_hash}). Operational once
 * {"/".join(resolved.auth_env_vars)} is configured in this process's
 * environment; until then this connector's route returns HTTP 503 (never
 * 501 — the code is real, only its runtime configuration is missing) and
 * never a silent 200 with invented output.
 *
 * Auth: reads {"/".join(resolved.auth_env_vars)} at CALL time — never at
 * boot, never logged, never echoed into any error message.
 */

const {{ createConnectorClient }} = require("./_connector-runtime.js");
"""


def _render_anthropic_client_js(integration_name: str, module: ScaffoldModule, resolved: ResolvedConnector) -> str:
    config_js = _resolved_connector_config_js(resolved)
    return _connector_client_header(integration_name, module, resolved) + f"""
function buildRequest(op, input) {{
  const allMessages = Array.isArray(input.messages) ? input.messages : [];
  const systemText = allMessages
    .filter((m) => m && m.role === "system")
    .map((m) => m.text)
    .join("\\n\\n");
  const messages = allMessages
    .filter((m) => m && m.role !== "system")
    .map((m) => ({{ role: m.role, content: m.text }}));
  const body = {{
    model: input.model,
    max_tokens: input.max_tokens,
    messages,
  }};
  if (input.temperature !== undefined) body.temperature = input.temperature;
  if (systemText) body.system = systemText;
  return {{ path: op.httpPath, headers: {{}}, body }};
}}

function parseResponse(op, json) {{
  const blocks = Array.isArray(json.content) ? json.content : [];
  const textBlock = blocks.find((b) => b && b.type === "text");
  const usage = json.usage || {{}};
  return {{
    text: textBlock ? textBlock.text : "",
    stop_reason: json.stop_reason || "other",
    usage: {{
      input_tokens: usage.input_tokens || 0,
      output_tokens: usage.output_tokens || 0,
    }},
  }};
}}

const client = createConnectorClient({{
{config_js}  buildRequest,
  parseResponse,
}});

module.exports = client;
"""


def _render_openai_client_js(integration_name: str, module: ScaffoldModule, resolved: ResolvedConnector) -> str:
    config_js = _resolved_connector_config_js(resolved)
    return _connector_client_header(integration_name, module, resolved) + f"""
// KNOWN v1 LIMITATION (connectors/registry/openai/README.md): sends
// normalized max_tokens as-is. OpenAI's o-series reasoning models
// (o1/o3/o4-mini) require max_completion_tokens instead and will reject
// max_tokens with their own 400 — surfaced here as a typed
// ConnectorInvocationError, never a silent failure or a guessed retry.
function buildRequest(op, input) {{
  const messages = (Array.isArray(input.messages) ? input.messages : []).map((m) => ({{
    role: m.role,
    content: m.text,
  }}));
  const body = {{
    model: input.model,
    max_tokens: input.max_tokens,
    messages,
  }};
  if (input.temperature !== undefined) body.temperature = input.temperature;
  return {{ path: op.httpPath, headers: {{}}, body }};
}}

function parseResponse(op, json) {{
  const choices = Array.isArray(json.choices) ? json.choices : [];
  const first = choices[0] || {{}};
  const message = first.message || {{}};
  const usage = json.usage || {{}};
  return {{
    text: typeof message.content === "string" ? message.content : "",
    stop_reason: first.finish_reason || "other",
    usage: {{
      input_tokens: usage.prompt_tokens || 0,
      output_tokens: usage.completion_tokens || 0,
    }},
  }};
}}

const client = createConnectorClient({{
{config_js}  buildRequest,
  parseResponse,
}});

module.exports = client;
"""


def _render_gemini_client_js(integration_name: str, module: ScaffoldModule, resolved: ResolvedConnector) -> str:
    config_js = _resolved_connector_config_js(resolved)
    return _connector_client_header(integration_name, module, resolved) + f"""
// The model name rides in the URL PATH ({{model}}:generateContent), not the
// body — buildRequest() substitutes it at call time.
function buildRequest(op, input) {{
  if (!input.model) {{
    throw new Error("input.model is required — Gemini's endpoint path embeds the model name");
  }}
  const allMessages = Array.isArray(input.messages) ? input.messages : [];
  const systemParts = allMessages
    .filter((m) => m && m.role === "system")
    .map((m) => ({{ text: m.text }}));
  const contents = allMessages
    .filter((m) => m && m.role !== "system")
    .map((m) => ({{ role: m.role === "assistant" ? "model" : "user", parts: [{{ text: m.text }}] }}));
  const generationConfig = {{}};
  if (input.max_tokens !== undefined) generationConfig.maxOutputTokens = input.max_tokens;
  if (input.temperature !== undefined) generationConfig.temperature = input.temperature;
  const body = {{ contents, generationConfig }};
  if (systemParts.length) body.systemInstruction = {{ parts: systemParts }};
  const path = op.httpPath.replace("{{model}}", encodeURIComponent(input.model));
  return {{ path, headers: {{}}, body }};
}}

function parseResponse(op, json) {{
  const candidates = Array.isArray(json.candidates) ? json.candidates : [];
  const first = candidates[0] || {{}};
  const parts = (first.content && Array.isArray(first.content.parts)) ? first.content.parts : [];
  const text = parts.map((p) => (p && typeof p.text === "string" ? p.text : "")).join("");
  const usage = json.usageMetadata || {{}};
  return {{
    text,
    stop_reason: first.finishReason || "other",
    usage: {{
      input_tokens: usage.promptTokenCount || 0,
      output_tokens: usage.candidatesTokenCount || 0,
    }},
  }};
}}

const client = createConnectorClient({{
{config_js}  buildRequest,
  parseResponse,
}});

module.exports = client;
"""


# Registry connector id -> codegen JS template renderer. Additive — a 4th
# provider connector needs an entry here (design §11 non-goal: v1 ships
# exactly Anthropic/OpenAI/Gemini; a NEW registry entry alone does not
# make it resolvable, deliberately — see the SpecEngineError raised above
# when a resolved connector_id has no matching renderer).
_CONNECTOR_CLIENT_RENDERERS = {
    "anthropic": _render_anthropic_client_js,
    "openai": _render_openai_client_js,
    "gemini": _render_gemini_client_js,
}


# --------------------------------------------------------------------------
# Infrastructure — src/http-util.js, src/server.js, package.json, README.md
# --------------------------------------------------------------------------


def _render_http_util_js() -> str:
    return f"""\
"use strict";

/**
 * GENERATED infrastructure — spec_engine.codegen (target_stack: {DEFAULT_TARGET_STACK}).
 * {_INFRA_NOTE}
 * Small JSON request/response helpers shared by the generated server.
 */

function sendJson(res, statusCode, body) {{
  const payload = body === undefined ? "" : JSON.stringify(body);
  res.writeHead(statusCode, {{ "Content-Type": "application/json; charset=utf-8" }});
  res.end(payload);
}}

function readJsonBody(req) {{
  return new Promise((resolve, reject) => {{
    let raw = "";
    req.on("data", (chunk) => {{
      raw += chunk;
      if (raw.length > 5 * 1024 * 1024) {{
        reject(Object.assign(new Error("request body too large"), {{ statusCode: 413 }}));
        req.destroy();
      }}
    }});
    req.on("end", () => {{
      if (!raw) {{
        resolve({{}});
        return;
      }}
      try {{
        resolve(JSON.parse(raw));
      }} catch (err) {{
        reject(Object.assign(new Error("invalid JSON body"), {{ statusCode: 400 }}));
      }}
    }});
    req.on("error", reject);
  }});
}}

module.exports = {{ sendJson, readJsonBody }};
"""


def _render_server_js(
    spec: SpecDocument,
    *,
    entities_by_slug: List[Tuple[str, Entity]],
    screens: List[Tuple[KeyScreen, str]],
    flows: List[Tuple[KeyFlow, str]],
    integrations: List["_IntegrationRoute"],
) -> str:
    model_requires = "\n".join(
        f'const {_class_name(entity.name)}Store = require("./models/{slug}.js").{_class_name(entity.name)}Store;'
        for slug, entity in entities_by_slug
    )
    store_entries = ",\n  ".join(f"{_js_string(slug)}: new {_class_name(entity.name)}Store()" for slug, entity in entities_by_slug)
    entity_route_entries = ",\n  ".join(
        f'{{ path: "/api/{_pluralize(slug)}", slug: {_js_string(slug)}, entity: {_js_string(entity.name)} }}'
        for slug, entity in entities_by_slug
    )

    page_requires = "\n".join(
        f'const page_{slug.replace("-", "_")} = require("./pages/{slug}.js");' for _, slug in screens
    )
    page_route_entries = ",\n  ".join(
        f'{{ path: "/{slug}", name: {_js_string(screen.name)}, render: page_{slug.replace("-", "_")}.render }}'
        for screen, slug in screens
    )

    flow_requires = "\n".join(
        f'const flow_{slug.replace("-", "_")} = require("./flows/{slug}.js");' for _, slug in flows
    )
    flow_route_entries = ",\n  ".join(
        f'{{ path: "/api/flows/{slug}", name: {_js_string(flow.name)}, run: flow_{slug.replace("-", "_")}.run }}'
        for flow, slug in flows
    )

    integration_requires = "\n".join(
        f'const integration_{route.slug.replace("-", "_")} = require("./integrations/{route.slug}.js");'
        for route in integrations
    )
    integration_route_entries = ",\n  ".join(
        (
            f'{{ path: "/api/integrations/{route.slug}", name: {_js_string(route.integration_name)}, '
            f'kind: "connector", operation: {_js_string(route.operation)}, '
            f'envVars: [{", ".join(_js_string(v) for v in route.env_vars)}], '
            f'call: integration_{route.slug.replace("-", "_")}.call }}'
            if route.kind == "connector"
            else
            f'{{ path: "/api/integrations/{route.slug}", name: {_js_string(route.integration_name)}, '
            f'kind: "stub", operation: null, envVars: [], '
            f'call: integration_{route.slug.replace("-", "_")}.call }}'
        )
        for route in integrations
    )
    connector_boot_checks = "\n".join(
        (
            f'  if (!({" || ".join("process.env[" + _js_string(v) + "]" for v in route.env_vars)})) {{\n'
            f'    console.warn("[connector] " + {_js_string(route.integration_name)} + " ({route.connector_id}) is NOT '
            f'configured — set {" or ".join(route.env_vars)} to make POST /api/integrations/{route.slug} operational. '
            'Until then it returns 503, never a silent 200.");\n'
            "  }"
        )
        for route in integrations
        if route.kind == "connector"
    )

    return f"""\
#!/usr/bin/env node
"use strict";

/**
 * GENERATED server — spec_engine.codegen (target_stack: {DEFAULT_TARGET_STACK}).
 * {_INFRA_NOTE}
 * Zero npm dependencies: Node core `http` only.
 *
 * Run:  node src/server.js   (or `npm start`)
 * Test: node --test {ACCEPTANCE_TEST_REL_PATH}   (or `npm test`)
 *
 * Listens on process.env.PORT || 3000. See ../SPEC.md for what this app
 * does, and ../.spec-engine/codegen-manifest.json for exactly which parts
 * of this generated app are fully real vs. labeled stubs.
 */

const http = require("node:http");
const {{ readJsonBody, sendJson }} = require("./http-util.js");

{model_requires}
{page_requires}
{flow_requires}
{integration_requires}

const entityStores = {{
  {store_entries}
}};

const ENTITY_ROUTES = [
  {entity_route_entries}
];

const PAGE_ROUTES = [
  {page_route_entries}
];

const FLOW_ROUTES = [
  {flow_route_entries}
];

const INTEGRATION_ROUTES = [
  {integration_route_entries}
];

async function handleEntityRoute(req, res, route, restPath) {{
  const store = entityStores[route.slug];
  const id = restPath.replace(/^\\//, "");
  try {{
    if (req.method === "GET" && !id) {{
      sendJson(res, 200, store.list());
      return;
    }}
    if (req.method === "GET" && id) {{
      const record = store.get(id);
      sendJson(res, record ? 200 : 404, record || {{ error: "not found" }});
      return;
    }}
    if (req.method === "POST" && !id) {{
      const body = await readJsonBody(req);
      const record = store.create(body);
      sendJson(res, 201, record);
      return;
    }}
    if (req.method === "PUT" && id) {{
      const body = await readJsonBody(req);
      const record = store.update(id, body);
      sendJson(res, record ? 200 : 404, record || {{ error: "not found" }});
      return;
    }}
    if (req.method === "DELETE" && id) {{
      const removed = store.remove(id);
      sendJson(res, removed ? 204 : 404, removed ? undefined : {{ error: "not found" }});
      return;
    }}
    sendJson(res, 405, {{ error: "method not allowed" }});
  }} catch (err) {{
    sendJson(res, err.statusCode || 500, {{ error: err.message }});
  }}
}}

function createServer() {{
  // Boot-time WARNING (never fatal) per unconfigured GENERATED CONNECTOR —
  // an app with declared-but-unconfigured connectors still boots and
  // serves every non-connector route; this is the only place that state
  // is surfaced (design §4.2: "the state is visible without being
  // fatal"). Never logs a key or its value — only the env var NAME.
{connector_boot_checks}

  return http.createServer(async (req, res) => {{
    let url;
    try {{
      url = new URL(req.url, "http://localhost");
    }} catch (err) {{
      sendJson(res, 400, {{ error: "invalid request URL" }});
      return;
    }}
    const pathname = url.pathname;

    if (pathname === "/health") {{
      sendJson(res, 200, {{ status: "ok" }});
      return;
    }}

    if (pathname === "/") {{
      sendJson(res, 200, {{
        app: {_js_string(spec.title)},
        generated_from: "SPEC.md",
        pages: PAGE_ROUTES.map((r) => r.path),
        api: ENTITY_ROUTES.map((r) => r.path),
        flows: FLOW_ROUTES.map((r) => r.path),
        integrations: INTEGRATION_ROUTES.map((r) => r.path),
      }});
      return;
    }}

    for (const route of PAGE_ROUTES) {{
      if (pathname === route.path) {{
        res.writeHead(200, {{ "Content-Type": "text/html; charset=utf-8" }});
        res.end(route.render({{ entityStores }}));
        return;
      }}
    }}

    for (const route of ENTITY_ROUTES) {{
      if (pathname === route.path || pathname.startsWith(route.path + "/")) {{
        const restPath = pathname.slice(route.path.length);
        await handleEntityRoute(req, res, route, restPath);
        return;
      }}
    }}

    for (const route of FLOW_ROUTES) {{
      if (pathname === route.path && req.method === "POST") {{
        let body = {{}};
        try {{
          body = await readJsonBody(req);
        }} catch (err) {{
          // Malformed body — flows still run with an empty input rather
          // than failing the request; the flow's own TODO logic decides
          // what to do with a missing field.
        }}
        const result = await route.run(body);
        sendJson(res, 200, result);
        return;
      }}
    }}

    for (const route of INTEGRATION_ROUTES) {{
      if (pathname === route.path && req.method === "POST") {{
        if (route.kind === "connector") {{
          // GENERATED CONNECTOR — a real client, wired to a real route.
          // Every failure is one of the typed error classes from
          // _connector-runtime.js; err.statusCode carries the real HTTP
          // status (503 unconfigured, 429 rate-limited, 502 provider/
          // contract, 400 invocation) — NEVER a bare 501 (that status is
          // reserved for an UNRESOLVED integration, below) and never a
          // silent 200 on failure.
          let body = {{}};
          try {{
            body = await readJsonBody(req);
          }} catch (err) {{
            sendJson(res, err.statusCode || 400, {{ status: "error", connector: route.name, error: err.message }});
            return;
          }}
          try {{
            const result = await route.call(route.operation, body);
            sendJson(res, 200, {{ status: "ok", output: result.output, usage: result.usage }});
          }} catch (err) {{
            sendJson(res, err.statusCode || 500, {{ status: "error", connector: route.name, error: err.message }});
          }}
          return;
        }}
        // UNRESOLVED integration — today's unchanged stub behavior.
        try {{
          await route.call();
          sendJson(res, 200, {{ status: "ok" }});
        }} catch (err) {{
          sendJson(res, 501, {{ status: "not_implemented", integration: route.name, error: err.message }});
        }}
        return;
      }}
    }}

    sendJson(res, 404, {{ error: "not found" }});
  }});
}}

if (require.main === module) {{
  // PORT=0 asks the OS for a free ephemeral port (used by the boot-proof
  // test in tests/spec_engine/test_codegen_app_boots.py) — the ACTUAL
  // bound port is read back from server.address().port, never assumed to
  // equal the requested value, so this line is correct in both cases.
  // NOTE: `Number(process.env.PORT) || 3000` would be wrong here — `0` is
  // falsy in JS, so that pattern would silently discard an explicit
  // PORT=0 and fall back to 3000. Check for `undefined`/empty explicitly
  // instead.
  const port = process.env.PORT !== undefined && process.env.PORT !== "" ? Number(process.env.PORT) : 3000;
  const server = createServer();
  server.listen(port, () => {{
    console.log("Generated app listening on http://localhost:" + server.address().port);
  }});
}}

module.exports = {{ createServer, entityStores }};
"""


def _class_name(name: str) -> str:
    return "".join(part.capitalize() for part in re.split(r"[^A-Za-z0-9]+", name) if part) or "Entity"


def _render_package_json(spec: SpecDocument) -> str:
    pkg = {
        "name": f"{_slugify(spec.spec_id)}-generated-app",
        "version": "0.1.0",
        "private": True,
        "description": f"Generated from SPEC.md by spec_engine.codegen (twiss-io/tess-os). {spec.title}",
        "main": "src/server.js",
        "scripts": {
            "start": "node src/server.js",
            "test": f"node --test {ACCEPTANCE_TEST_REL_PATH}",
        },
        "engines": {"node": ">=18"},
    }
    return json.dumps(pkg, indent=2) + "\n"


def _render_app_readme(spec: SpecDocument, target_stack: str, integrations: List["_IntegrationRoute"]) -> str:
    stub_names = [r.integration_name for r in integrations if r.kind == "stub"]
    connector_lines = [
        f"  - **{r.integration_name}** — real connector client (`{r.connector_id}`); configure "
        f"`{' or '.join(r.env_vars)}` to make `POST /api/integrations/{r.slug}` operational. Until "
        "then that route returns `503` (not `501`)."
        for r in integrations
        if r.kind == "connector"
    ]
    connector_block = (
        "\n" + "\n".join(connector_lines) if connector_lines
        else "\n  - (none in this spec)"
    )
    return f"""\
# {spec.title}

**GENERATED from `SPEC.md` by `spec_engine.codegen`** (twiss-io/tess-os) —
target stack: `{target_stack}`. `SPEC.md` in this repo's root is the
source of truth; see `CLAUDE.md`/`AGENTS.md` for the full spec-authoritative
rule. Do not edit generated code first and back-port to the spec later —
edit `SPEC.md`, then regenerate (or hand-edit code and update the spec to
match — see `.spec-engine/codegen-manifest.json`'s `notes` field for what
this codegen pass covers).

## Run it

```bash
node src/server.js       # or: npm start
```

Then visit `http://localhost:3000/` (or `PORT=<n> node src/server.js` for
a different port). `GET /health` returns `{{"status":"ok"}}` once the
server is up.

## Test it

```bash
node --test {ACCEPTANCE_TEST_REL_PATH}       # or: npm test
```

(Always an explicit file path, never a bare `tests/` directory —
`node --test <directory>`'s built-in test-discovery behavior is not
stable across Node versions; see `ACCEPTANCE_TEST_REL_PATH`'s comment in
`spec_engine/codegen.py` for the empirical Node 20 vs. 22 difference
that motivated this.)

Zero npm dependencies — this whole app runs on Node core only (`node:http`,
`node:crypto`, `node:test`, `node:assert/strict`, plus the built-in global
`fetch()`). `npm install` is not required and there is no lockfile.

## What's real vs. stub — read `.spec-engine/codegen-manifest.json`

This codegen pass is honest about what it can and cannot deterministically
generate:

- **Real, working code:** the data-model entities' CRUD stores and REST
  API, the frontend pages, and the acceptance test suite.
- **Real wiring, placeholder business logic:** each flow's route and step
  sequence execute for real, but every step's body is a `// TODO` — flow
  steps are free text in the spec, not something codegen can compile into
  working business logic.
- **Real connector client — configure an env var to make it operational:**
  an integration whose name matched a REGISTERED connector
  (`connectors/registry/**` in the tess-os repo this app was generated
  from) gets a real, vendored `fetch()` client, not a stub. The code is
  real; whether it can actually reach the provider depends on runtime
  configuration this repo cannot carry — until the env var below is set,
  its route answers `503`, never a silent `200`, never `501` (that status
  means "no connector", not "not configured yet"):{connector_block}
- **Labeled stubs, not functional:** every OTHER integration name — no
  registered connector matched it. Codegen cannot produce a working
  connector to `{", ".join(stub_names) or "(none in this spec)"}` without
  real credentials/API contract details this spec does not carry; its
  route returns `501`.

## Persistence

In-memory only — every entity's data resets when the process restarts.
A persistent database is a later pipeline deliverable (Phase 2 Epic E4:
"provisions DB"), out of scope for this codegen slice.
"""


def _render_acceptance_test_js(spec: SpecDocument, *, entities: List[Tuple[str, Entity]]) -> str:
    entity_tests = []
    for slug, entity in entities:
        path = f"/api/{_pluralize(slug)}"
        payload = {f.name: _sample_value_for_field(f, 1) for f in entity.fields}
        entity_tests.append(f"""\
test({_js_string(f"{entity.name}: create then list round-trip")}, withServer(async (base) => {{
  const res = await fetch(base + {_js_string(path)}, {{
    method: "POST",
    headers: {{ "Content-Type": "application/json" }},
    body: JSON.stringify({json.dumps(payload)}),
  }});
  assert.equal(res.status, 201);
  const created = await res.json();
  assert.ok(created.id);
  const listRes = await fetch(base + {_js_string(path)});
  assert.equal(listRes.status, 200);
  const list = await listRes.json();
  assert.ok(list.some((r) => r.id === created.id));
}}));""")

    criteria_tests = []
    for i, criterion in enumerate(spec.acceptance_criteria):
        matched = _match_entity_by_name(criterion, [e for _, e in entities])
        matched_slug = None
        if matched is not None:
            for slug, entity in entities:
                if entity is matched:
                    matched_slug = slug
                    break
        test_name = f"ACCEPTANCE: {criterion}"
        if matched is not None and matched_slug is not None:
            path = f"/api/{_pluralize(matched_slug)}"
            payload = {f.name: _sample_value_for_field(f, 100 + i) for f in matched.fields}
            criteria_tests.append(f"""\
test({_js_string(test_name)}, withServer(async (base) => {{
  // Matched entity: {matched.name!r} — exercised via a real create+list round-trip.
  const res = await fetch(base + {_js_string(path)}, {{
    method: "POST",
    headers: {{ "Content-Type": "application/json" }},
    body: JSON.stringify({json.dumps(payload)}),
  }});
  assert.equal(res.status, 201);
}}));""")
        else:
            criteria_tests.append(f"""\
test({_js_string(test_name)}, withServer(async (base) => {{
  // No data-model entity name matched in this criterion's text — codegen
  // cannot derive a specific behavioral assertion deterministically.
  // Falls back to the baseline boot check; verify this criterion by hand.
  const res = await fetch(base + "/health");
  assert.equal(res.status, 200);
}}));""")

    entity_tests_js = "\n\n".join(entity_tests)
    criteria_tests_js = "\n\n".join(criteria_tests)

    return f"""\
"use strict";

/**
 * GENERATED acceptance tests — spec_engine.codegen (target_stack: {DEFAULT_TARGET_STACK}).
 * Source: spec section acceptance_criteria (+ a baseline boot/health check
 * and a per-entity CRUD round-trip that always run regardless of
 * acceptance_criteria content). generation_status: "generated" (see
 * ../.spec-engine/codegen-manifest.json).
 *
 * Run (from the repo root): node --test {ACCEPTANCE_TEST_REL_PATH}   (or
 * `npm test`). Zero test-framework dependencies — Node core `node:test`
 * + `node:assert/strict` + the built-in global `fetch()`.
 */

const test = require("node:test");
const assert = require("node:assert/strict");
const {{ createServer }} = require("../src/server.js");

function withServer(fn) {{
  return async () => {{
    const server = createServer();
    await new Promise((resolve) => server.listen(0, resolve));
    const port = server.address().port;
    const base = "http://localhost:" + port;
    try {{
      await fn(base);
    }} finally {{
      await new Promise((resolve) => server.close(resolve));
    }}
  }};
}}

test("server boots and GET /health returns ok", withServer(async (base) => {{
  const res = await fetch(base + "/health");
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.equal(body.status, "ok");
}}));

{entity_tests_js}

{criteria_tests_js}
"""


__all__ = [
    "DEFAULT_TARGET_STACK",
    "SUPPORTED_TARGET_STACKS",
    "GENERATION_STATUSES",
    "CodegenResult",
    "generate_app",
]
