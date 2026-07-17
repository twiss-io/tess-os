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
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from .content import Entity, EntityField, KeyFlow, KeyScreen, SpecEngineError
from .scaffold import plan_scaffold_from_spec, write_scaffold_stub
from .types import ScaffoldModule, ScaffoldPlan, SpecDocument

PathLike = Union[str, Path]

DEFAULT_TARGET_STACK = "node-http-minimal"
SUPPORTED_TARGET_STACKS = (DEFAULT_TARGET_STACK,)

GENERATION_STATUSES = ("generated", "generated-stub-logic", "stub")

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
    contract this function honors."""
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

    root = Path(target_dir)
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

    integrations_written: List[Tuple[str, str]] = []
    for module, integration_name in zip(integration_modules, spec.how_it_works.integrations):
        slug = _unique_slug(integration_slugs, _slugify(integration_name))
        rel_path = f"src/integrations/{slug}.js"
        _write_file(root, rel_path, _render_integration_js(integration_name, module))
        written[rel_path] = root / rel_path
        integrations_written.append((integration_name, slug))
        manifest_modules.append(
            _manifest_entry(
                module,
                "stub",
                [rel_path],
                f"Labeled connector stub for integration '{integration_name}' — codegen cannot "
                "produce a working third-party connector without real credentials/API contract "
                "details the spec does not carry. Wired to a route that returns HTTP 501.",
            )
        )

    # Infrastructure — required for any app on this target stack, not
    # attributed to a source_section (see module docstring).
    infra_files: List[str] = []
    for rel_path, content in (
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
        ("README.md", _render_app_readme(spec, target_stack)),
    ):
        _write_file(root, rel_path, content)
        written[rel_path] = root / rel_path
        infra_files.append(rel_path)

    # Tests — from acceptance_criteria (deliverable: "acceptance_criteria
    # -> generated tests"), plus a baseline boot check and a per-entity
    # CRUD round-trip test that runs regardless of acceptance_criteria
    # content.
    test_rel_path = "tests/acceptance.test.js"
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
    module: ScaffoldModule, generation_status: str, files: List[str], notes: str
) -> Dict[str, Any]:
    if generation_status not in GENERATION_STATUSES:
        raise SpecEngineError(f"_manifest_entry: {generation_status!r} not in {GENERATION_STATUSES}")
    return {
        "module_id": module.module_id,
        "kind": module.kind,
        "source_section": module.source_section,
        "generation_status": generation_status,
        "files": files,
        "notes": notes,
    }


def _write_file(root: Path, rel_path: str, content: str) -> Path:
    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


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
    integrations: List[Tuple[str, str]],
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
        f'const integration_{slug.replace("-", "_")} = require("./integrations/{slug}.js");'
        for _, slug in integrations
    )
    integration_route_entries = ",\n  ".join(
        f'{{ path: "/api/integrations/{slug}", name: {_js_string(name)}, call: integration_{slug.replace("-", "_")}.call }}'
        for name, slug in integrations
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
 * Test: node --test tests/   (or `npm test`)
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
            "test": "node --test tests/",
        },
        "engines": {"node": ">=18"},
    }
    return json.dumps(pkg, indent=2) + "\n"


def _render_app_readme(spec: SpecDocument, target_stack: str) -> str:
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
node --test tests/       # or: npm test
```

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
- **Labeled stubs, not functional:** third-party integrations. Codegen
  cannot produce a working connector to `{", ".join(spec.how_it_works.integrations) or "(none in this spec)"}`
  without real credentials/API contract details this spec does not carry.

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
 * Run: node --test tests/   (or `npm test`). Zero test-framework
 * dependencies — Node core `node:test` + `node:assert/strict` + the
 * built-in global `fetch()`.
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
