# Spec Engine — the idea -> spec -> app core

> Spec: `TESS-VISION-AND-BUILD-SPEC.html`, Phase 1 Epic E2 — "Spec Engine
> v1: Idea -> Complete Spec" — continued into the codegen slice of Phase 2
> Epic E4 ("Spec-to-App Pipeline v1... scaffolds the repo from SPEC.md").
> Product pillar: **Idea -> Spec -> App** — "Rough edges and open
> questions are treated as inputs, not blockers... after approval, the
> spec is written and becomes the source of truth — code is generated
> from the spec, never the reverse."
>
> **Status: Buildable-Now.** This component ships the deterministic idea
> -> plan -> (approval gate) -> spec pipeline end to end, PLUS real
> codegen: `codegen.generate_app()` turns an approved spec into an
> actually-runnable app (default target stack: plain Node core, zero npm
> dependencies) — see "The spec -> scaffold plan, and REAL codegen"
> below for exactly what's genuinely generated vs. still a labeled stub,
> and "Integration status" for what a follow-up PR still needs to wire.

## What this is

A **generalized tess-os framework component**, not a Twiss-specific
integration — same discipline `intent-router/` documents for itself.
Given freeform input — a voice-note transcript, a pasted doc, a rambling
fragment, a single terse paragraph — it:

1. **harvests** the input into draft content across four dimensions (what
   it does / how it looks / how it works / data model), explicitly
   capturing every gap and ambiguity into an **open-questions ledger**
   instead of demanding a finished brief;
2. **builds a Plan** — the harvested content plus a human-readable
   summary — for a real human to review;
3. **gates on approval** — a `SpecDocument` can only be built from a
   `Plan` that carries a real, attributed `Approval` record; there is no
   code path around this;
4. **renders `SPEC.md`** — the canonical markdown projection of the
   approved spec, meant to be committed as a generated app's root
   artifact;
5. **plans the scaffold** — a `ScaffoldPlan` derived deterministically
   from the spec's own content, plus the "code is generated from spec"
   rule written into the target repo's own `CLAUDE.md`/`AGENTS.md`; and
6. **generates a real, runnable app** — `codegen.generate_app()` turns
   that plan into actual files (entity CRUD stores, rendered pages, flow
   handlers, integration stubs, a real test suite, and the app's own
   server) for a default zero-dependency Node target stack — proven by
   actually booting a generated app as a subprocess, not just asserting
   files exist.

## Architecture

```
freeform text (+ optional RoutingContext, ModelAssistedHarvest)
     │
     ▼
spec_engine.intake.harvest_intake()        deterministic heuristics (keyword
     │                                     buckets, hedge-phrase detection,
     │                                     literal entity-declaration parse) +
     │                                     an optional, purely-additive
     │                                     model-assisted supplement
     ▼
spec_engine.plan_builder.build_plan()      -> Plan (draft content + ledger +
     │                                        summary_for_approval)
     │
     │        <<< a real human reviews plan.summary_for_approval >>>
     │
     ▼
spec_engine.approval.record_approval()     -> Approval (attributed, gated)
     │
     ▼
spec_engine.spec_builder.build_spec()      -> SpecDocument (REFUSES to run
     │                                        without a matching, approved
     │                                        Approval — see its docstring)
     │
     ├──► spec_engine.render.render_markdown()   -> SPEC.md text
     ├──► spec_engine.spec_lint.lint()            -> advisory findings
     ├──► spec_engine.scaffold.plan_scaffold_from_spec()
     │        -> ScaffoldPlan (codegen_status="not_started", pure, no I/O)
     │
     └──► spec_engine.codegen.generate_app(spec, target_dir)
              -> REAL, runnable files (target_stack: node-http-minimal):
                 src/models, src/pages, src/flows, src/integrations,
                 tests/acceptance.test.js, src/server.js + package.json,
                 PLUS (via scaffold.write_scaffold_stub(), called at the
                 end with codegen_status="generated") SPEC.md, spec.json,
                 .spec-engine/scaffold-plan.json, CLAUDE.md/AGENTS.md
```

`spec_engine.pipeline` glues the stages: `run_intake_and_plan()` gets you
to the human gate; a SEPARATE `finalize_spec()` call crosses it (mirroring
`intent_router.pipeline`'s `run_intent_router()` / `continue_with_clarification()`
two-call shape) — this split is deliberate, not incidental, see
`approval.py`'s module docstring.

## The spec format — the contract everything hangs on

A `SpecDocument` (schema: [`schema/spec.schema.json`](schema/spec.schema.json))
carries:

| Section | Field | Notes |
|---|---|---|
| What It Does | `what_it_does` | summary, goals, user stories |
| How It Looks | `how_it_looks` | description, key screens, design references |
| How It Works | `how_it_works` | description, key flows, integrations |
| Data Model | `data_model` | entities, fields, relationships — **never fabricated from vague prose**, only from an explicit `<Name> entity (field, field)` declaration or a model-assisted supplement (see intake.py's module docstring) |
| Non-Goals | `non_goals` | explicit scope exclusions |
| Acceptance Criteria | `acceptance_criteria` | the testable "how do we know it's done" |
| **Open Questions Ledger** | `open_questions` | every harvested ambiguity/gap: id, question, category, raised-from excerpt, blocking flag, status, resolution |
| **Provenance** | `provenance` | source_type, input excerpt, plan id, approver + timestamp, and (if routed through intent-router) the routing decision id/entry command/orchestrator/mission id |

`spec_id`, `title`, `spec_version` (starts at 1), and `status`
(`active`/`superseded` — the latter reserved for a future spec-diff
regeneration flow, Epic E5, out of scope here) round out the top level.

A `Plan` ([`schema/plan.schema.json`](schema/plan.schema.json)) carries the
same four content dimensions plus the ledger, PRE-approval — this is what
gets shown to a human before a `SpecDocument` ever exists.

Both schemas are validated by this component's own dependency-free
[`spec_engine/spec_check.py`](spec_engine/spec_check.py) (a verbatim-in-spirit
duplicate of `intent_router/schema_check.py` — see that module's docstring
for why this component doesn't import it instead: zero cross-component
import edges between top-level tess-os components).

## Human-in-the-loop is a real gate, not a formality

`spec_builder.build_spec()` raises `SpecEngineError` — fails loud — unless
handed an `Approval` whose `plan_id` matches the plan being built,
whose `approved` is `True`, **AND which independently re-verifies as a
genuinely gate-signed approval, content-hash-bound to the plan's current
content** (`gate_approval.verify_gate_approval()` — see below).
`Approval.approved_by` is required even on a rejection (no anonymous
decisions). This is a deliberate design choice: "Human-in-the-loop is a
design decision — not every step should be automated; know when to
defer." Nothing downstream of the gate — the rendered `SPEC.md`, the
scaffold plan, the directive written into a generated repo, or a
generated app (`codegen.generate_app()`, which only ever accepts a
`SpecDocument` — the sole output of `build_spec()`) — is reachable
without a real, attributed, cryptographically-verified approval having
happened first.

### The codegen boundary is hardened, not just gated on a matching id

A bare `approval.record_approval(plan, approved_by="Xavier")` call — no
signature, no `ApprovalGate` involvement at all — is REJECTED by
`build_spec()`. Before this hardening, it was not: `plan_id` match +
`approved=True` was the entire check, so any in-process caller could
forge an `Approval` claiming to be anyone. Two new modules close this:

- **`gate_identity.py`** — the local, HMAC-SHA256 signing/verification
  primitives (a random 256-bit key per OS account at
  `~/.tess-os/approval-identity/<username>.key`, `chmod 600` enforced).
  Moved here (from `orchestrator/identity.py`, which is now a
  backward-compatible re-export shim) because the codegen boundary that
  must independently re-verify a signature lives HERE, in `spec_engine`
  — and `orchestrator` already depends on `spec_engine`, never the
  reverse.
- **`gate_approval.py`** — `sign_local_approval()` (mints a genuinely
  gate-verifiable `Approval`, content-hash-bound to the plan via
  `content.plan_content_hash()`) and `verify_gate_approval()` (the
  independent re-check `build_spec()` calls internally). `content.
  plan_content_hash()` closes a second, related gap: `Plan.plan_id` is a
  mutable, caller-settable field on a plain (non-frozen) dataclass — a
  slug, not a cryptographic commitment — so an approval genuinely signed
  for one plan's content can no longer authorize building a
  `SpecDocument` from a DIFFERENT plan, even one sharing the same
  `plan_id` (a substituted or in-place-mutated `Plan` object).
  `build_spec()` also consumes the approval's nonce on success
  (`consume_approval_nonce()`), rejecting a replayed approval on a
  second use — disclosed as in-process/in-memory only (does not survive
  a fresh process) in that function's own docstring.

`pipeline.finalize_spec()` keeps its EXACT existing call signature
(`approved_by`/`approved`/`notes` strings — one new optional
`identity_dir` kwarg) but now mints a genuine signed approval under the
hood via `gate_approval.sign_local_approval()` instead of a bare one —
every existing caller (this component's own tests, the eval harness,
`spec_engine.cli`'s `finalize` subcommand) keeps working unchanged.
A caller that already has a real, independently-produced `Approval`
object (the shipped `orchestrator.pipeline.run_pipeline()` does, after
its `ApprovalGate` round-trip) should call the new
`pipeline.finalize_spec_with_approval()` instead, so it is not silently
re-signed under a possibly-different identity scope — see that
function's own docstring.

See `tests/spec_engine/test_spec_builder.py` and `test_gate_approval.py`
for the required adversarial proof (a bare approval rejected, a
spec-substitution attempt rejected, a tampered signature rejected — all
at this exact boundary, with no target directory ever created).

## Harvesting ambiguity — exactly what the epic asks for

> "Intake explicitly harvests ambiguities into an open-questions ledger
> rather than demanding a finished brief."

`intake.harvest_intake()` never raises because content is thin, rough, or
contradictory — only on structurally invalid arguments (empty input, an
unknown `source_type`). For each of the four core dimensions, either a
real signal was found in the text, or an explicit open question is
raised capturing exactly what's missing. Hedge phrases ("not sure",
"maybe", "TBD", a bare "?", ...) are harvested directly into the ledger,
verbatim, as `category="ambiguity"` questions. See
[`eval/fixtures/brief_voice_ramble.txt`](eval/fixtures/brief_voice_ramble.txt)
for a representative rambling input and the ledger it produces.

An optional `ModelAssistedHarvest` (same purely-additive, optional-hook
contract `intent_router.types.ExternalSignal` uses for routing) lets a
caller with a real model-assisted read of the input — e.g. a live Claude
Code session — fill gaps and add richness the deterministic heuristics
miss, without making the deterministic path any less independently
testable.

## The spec -> scaffold plan, and REAL codegen

`scaffold.plan_scaffold_from_spec()` deterministically derives a
`ScaffoldPlan` from a spec's own content (one module per data-model
entity, one per key screen, one per key flow, one per integration, plus a
test-suite module derived from acceptance criteria) — every module traces
back to a named `source_section`, so "the spec is authoritative" is
provable, not just asserted. This function stays pure (no filesystem
access) and always returns `codegen_status == "not_started"`.

`scaffold.write_scaffold_stub()` writes the concrete artifacts a
generated app's repo needs: `SPEC.md`, `spec.json`, `.spec-engine/
scaffold-plan.json`, and the spec-is-authoritative rule appended (or, for
a fresh repo, written fresh) into that repo's own `CLAUDE.md` **and**
`AGENTS.md` — both harness idioms, per the epic's own deliverable (4)
wording.

**`codegen.generate_app(spec, target_dir)`** is where "code is generated
FROM the spec" stops being a stub and becomes real: it takes a `spec` (+
optionally an existing `ScaffoldPlan`) and writes an actual, runnable
app — default target stack `node-http-minimal` (plain Node core, **zero
npm dependencies**, no build step; see `codegen.py`'s module docstring
for why). Deterministic, traceable mapping from `ScaffoldModule.kind` to
real files:

| `kind` | Generated file(s) | `generation_status` (in `.spec-engine/codegen-manifest.json`) |
|---|---|---|
| `backend-model` | `src/models/<entity-slug>.js` — real in-memory CRUD store | `generated` |
| `frontend-page` | `src/pages/<screen-slug>.js` — real server-rendered HTML, live entity data if the screen name matches an entity | `generated` |
| `service` (flow) | `src/flows/<flow-slug>.js` — real, executable step sequence wired to a live route; each step's business-logic body is a `// TODO` (flow steps are free text — codegen can't compile prose into working logic) | `generated-stub-logic` |
| `integration` | `src/integrations/<slug>.js` — a labeled connector STUB (codegen can't produce a working third-party connector without real credentials/API contract); wired to a route that returns HTTP 501 | `stub` |
| `test-suite` | `tests/acceptance.test.js` — real `node:test` tests: a baseline boot/health check, one CRUD round-trip per entity, and one test per `acceptance_criteria` entry | `generated` |

`ScaffoldPlan.codegen_status` becomes `"generated"` once `generate_app()`
has run (`scaffold.py`'s `CODEGEN_STATUSES` now has two values, not one).
That single top-level status **cannot** express the per-module mix above
on its own — `.spec-engine/codegen-manifest.json` (schema:
`schema/codegen-manifest.schema.json`) is the honest, machine-checkable
ledger of exactly which files are fully real vs. labeled stubs, matching
the parent build spec's "these labels are load-bearing... do not
silently upgrade a label" discipline down to the file level. `README.md`
and `CLAUDE.md`/`AGENTS.md` in every generated app point back to it.

The proof this actually runs — not just "files exist" — lives in
[`tests/spec_engine/test_codegen_app_boots.py`](../tests/spec_engine/test_codegen_app_boots.py):
it generates a real app from a real (pipeline-produced) spec into
pytest's throwaway `tmp_path`, spawns `node src/server.js` as a genuine
subprocess, and asserts it boots and serves real HTTP traffic across
every route kind (entity CRUD, a rendered page, a flow execution, an
honest integration 501) — plus runs the GENERATED `tests/acceptance.test.js`
with the real `node --test` runner and asserts it passes. Skips cleanly
(does not fail) if no `node` binary is on PATH.

## How this composes with the front door (intent-router)

Epic E2's own dependency line: *"Dependencies: E1 (intake routes to it)."*
`spec_engine.integrations.from_intent_router.routing_context_from_decision()`
adapts a real `intent_router.types.RoutingDecision` into a spec_engine
`RoutingContext`, which then rides through `Plan.routing_context` into the
finished spec's `provenance` (routing decision id, entry command,
orchestrator, mission id) — full traceability from "Tess picked
`/product-mode`" to "here is the spec that came out of it."

This adapter is duck-typed, not `isinstance`-checked, and `spec_engine`
does **not** `import intent_router` anywhere in its own package — the two
components stay independently deployable (a checkout with only one of the
two still works; only
[`tests/spec_engine/test_intent_router_bridge.py`](../tests/spec_engine/test_intent_router_bridge.py)
imports both together, and it skips itself cleanly if `intent-router/` is
absent). That test is the concrete, executable proof of the composition —
run it directly to see a real routed decision feed a real generated spec.

## The 3-brief acceptance test

Epic E2's acceptance criterion: *"Three real briefs (one detailed, one
voice-ramble, one single-paragraph idea) each produce a spec that a
DIFFERENT agent pool can build from without asking the original author
anything not already in the open-questions ledger."*

**Honest data-source note** (same discipline `intent-router/`'s own 40-case
eval applies): [`eval/fixtures/`](eval/fixtures/) are hand-authored,
representative inputs across the three named styles — a standup-log tool
(detailed), a shared grocery list (voice-ramble, hedge-heavy), and an
invoice-nudge app (single paragraph) — not real historical user briefs
(this public repo carries none). What's measured is real and
machine-checkable: for each brief, every one of the four core dimensions
is either populated or has a matching category in the open-questions
ledger — operationalizing "nothing to ask that isn't already in the
ledger" as an assertable invariant, not a vibe.

Run it directly:

```bash
python3 spec-engine/eval/spec_engine_eval.py
```

or as part of the test suite
([`tests/spec_engine/test_spec_engine_eval.py`](../tests/spec_engine/test_spec_engine_eval.py)
— enforced in CI via `python -m pytest`). Current result: **3/3 PASS** —
the detailed brief resolves to a fully-specified spec with zero open
questions (its explicit `<Name> entity (field, field)` declarations parse
cleanly and every dimension has real content); the voice-ramble and
single-paragraph briefs correctly harvest real ambiguity into the ledger
rather than silently guessing.

## Integration status — what this PR does and does not wire up

**Built, tested, working standalone:** the harvest -> plan -> (approval
gate) -> spec -> render/lint/scaffold/codegen pipeline, callable from
Python (`spec_engine.pipeline.run_intake_and_plan` / `finalize_spec` /
`run_spec_engine`, then `spec_engine.codegen.generate_app()`) or from the
CLI (`python -m spec_engine.cli`) for the pre-codegen stages. Real code
generation to a real target stack, proven by actually booting a generated
app as a subprocess (see "The spec -> scaffold plan, and REAL codegen"
above).

**Deliberately NOT touched by this PR** (same reasoning
`intent-router/README.md` gives for its own scope, and the same scope
boundary the original spec-engine PR (#79) drew for itself):

- `CLAUDE.md` — keystone-rendered from `.tess/core/templates/claude-md/`,
  not hand-edited in the live repo.
- `conductor/*.md` — doctrine files, out of scope for a first-slice PR.
- `.claude/commands/**`, `.github/workflows/**`, `core/policy/**`,
  `core/contracts/**`, `.tess/bin/tessctl` — all keystone/policy-owned or
  gate-critical paths.
- Wiring `intent_router`'s output directly into a live slash command or
  orchestrator flow that then calls `spec_engine.codegen` — that's the
  natural next PR (it would touch `.tess/**` template sources and
  possibly `conductor/*.md`, so it needs its own scope and likely a
  signed ship-gate verdict).
- Provisioning a real, persistent database for generated apps, deploying
  them, or producing the roadmap/deck bundle — the rest of Phase 2 Epic
  E4's own deliverable list, explicitly out of scope for this codegen
  slice (see `codegen.py`'s module docstring on the in-memory-persistence
  boundary).
- A second target stack — `codegen.py`'s `SUPPORTED_TARGET_STACKS` has
  exactly one entry (`node-http-minimal`); adding a second is an additive
  change (a new name + a matching generator function), not a rewrite, but
  it isn't built here.

A follow-up integration PR is the natural place to: (a) wire a real
`/add-mission`-equivalent flow to call `run_intake_and_plan()` after
`intent_router` routes to a build-shaped outcome, then `codegen.generate_app()`
after approval; (b) point `log_path` at a real deployment's own
`state/`-equivalent registry instead of this component's local
`spec-engine/specs/` default sink; (c) decide how a real human approval
(Telegram button, CLI prompt, etc.) calls `finalize_spec()`; and (d)
provision a real database and a deploy target for generated apps
(Phase 2 Epic E4's remaining deliverables).

## Running the tests

```bash
python -m pytest tests/spec_engine        # this component's suite only
python -m pytest                          # full repo suite (includes the above)
python3 spec-engine/eval/spec_engine_eval.py   # the 3-brief eval as a standalone report
```

`tests/spec_engine/test_codegen_app_boots.py` — the real boot-proof suite
— additionally requires a `node` binary (>=18) on PATH; it skips cleanly
(does not fail the run) if `node` is unavailable. Everything it spawns
(the generated app, the `node` subprocess) lives under pytest's own
`tmp_path` and is torn down at the end of each test.

The test suite lives under the repo's existing `tests/` directory (not a
separate `spec-engine/tests/`) for the same reason `intent-router/`'s
does — zero CI workflow changes needed. Its path-bootstrap helper is named
`_spec_engine_paths.py`, NOT `_paths.py` (which `tests/intent_router/`
already uses) and NOT `conftest.py` — pytest's default "prepend" import
mode requires every helper/test module basename to be unique across the
WHOLE collected tree when no directory carries an `__init__.py`; a second
file named `_paths.py` collides with `tests/intent_router/_paths.py`
exactly the way two `conftest.py` files would (see
`_spec_engine_paths.py`'s own docstring, and
`tests/spec_engine/test_spec_engine_pipeline.py` / `test_spec_engine_render.py`,
renamed for the same reason against pre-existing `test_pipeline.py` /
`test_render.py` basenames elsewhere in `tests/`).

## Fields reference

See [`spec_engine/content.py`](spec_engine/content.py) and
[`spec_engine/types.py`](spec_engine/types.py) for the full dataclass set,
and [`schema/`](schema/) for the machine-checkable shapes
(`spec.schema.json`, `plan.schema.json`, `scaffold-plan.schema.json`,
`codegen-manifest.schema.json`).
