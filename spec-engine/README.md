# Spec Engine — the idea -> spec -> app core

> Spec: `TESS-VISION-AND-BUILD-SPEC.html`, Phase 1, Epic E2 — "Spec Engine
> v1: Idea -> Complete Spec." Product pillar: **Idea -> Spec -> App** —
> "Rough edges and open questions are treated as inputs, not blockers...
> after approval, the spec is written and becomes the source of truth —
> code is generated from the spec, never the reverse."
>
> **Status: Buildable-Now, first slice.** This component ships the
> deterministic idea -> plan -> (approval gate) -> spec pipeline end to
> end, plus a spec -> scaffold DIRECTION stub (no real codegen yet — see
> "Integration status" below for exactly what a follow-up PR needs to do).

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
   artifact; and
5. **stubs the scaffold direction** — a `ScaffoldPlan` derived
   deterministically from the spec's own content, plus the "code is
   generated from spec" rule written into the target repo's own
   `CLAUDE.md`/`AGENTS.md`.

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
     └──► spec_engine.scaffold.write_scaffold_stub()
              -> SPEC.md, spec.json, .spec-engine/scaffold-plan.json,
                 CLAUDE.md/AGENTS.md spec-is-authoritative directive
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
handed an `Approval` whose `plan_id` matches the plan being built AND
whose `approved` is `True`. `Approval.approved_by` is required even on a
rejection (no anonymous decisions). This is a deliberate design choice:
"Human-in-the-loop is a design decision — not every step should be
automated; know when to defer." Nothing downstream of the gate — the
rendered `SPEC.md`, the scaffold plan, the directive written into a
generated repo — is reachable without a real, attributed approval having
happened first.

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

## The spec -> scaffold DIRECTION (stub, not codegen)

`scaffold.plan_scaffold_from_spec()` deterministically derives a
`ScaffoldPlan` from a spec's own content (one module per data-model
entity, one per key screen, one per key flow, one per integration, plus a
test-suite module derived from acceptance criteria) — every module traces
back to a named `source_section`, so "the spec is authoritative" is
provable, not just asserted. `codegen_status` is pinned to the single
enum value `"not_started"`: this is a **plan for a future real codegen
step, never code itself** — honest labeling discipline, matching the
parent build spec's "these labels are load-bearing... do not silently
upgrade a label."

`scaffold.write_scaffold_stub()` writes the concrete artifacts a
generated app's repo needs: `SPEC.md`, `spec.json`, `.spec-engine/
scaffold-plan.json`, and the spec-is-authoritative rule appended (or, for
a fresh repo, written fresh) into that repo's own `CLAUDE.md` **and**
`AGENTS.md` — both harness idioms, per the epic's own deliverable (4)
wording.

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
gate) -> spec -> render/lint/scaffold pipeline, callable from Python
(`spec_engine.pipeline.run_intake_and_plan` / `finalize_spec` /
`run_spec_engine`) or from the CLI (`python -m spec_engine.cli`).

**Deliberately NOT touched by this PR** (same reasoning
`intent-router/README.md` gives for its own scope):

- `CLAUDE.md` — keystone-rendered from `.tess/core/templates/claude-md/`,
  not hand-edited in the live repo.
- `conductor/*.md` — doctrine files, out of scope for a first-slice PR.
- `.claude/commands/**`, `.github/workflows/**`, `core/policy/**`,
  `core/contracts/**`, `.tess/bin/tessctl` — all keystone/policy-owned or
  gate-critical paths.
- Wiring `intent_router`'s output directly into a live slash command or
  orchestrator flow that then calls `spec_engine` — that's the natural
  next PR (it would touch `.tess/**` template sources and possibly
  `conductor/*.md`, so it needs its own scope and likely a signed
  ship-gate verdict).

A follow-up integration PR is the natural place to: (a) wire a real
`/add-mission`-equivalent flow to call `run_intake_and_plan()` after
`intent_router` routes to a build-shaped outcome; (b) point `log_path`
at a real deployment's own `state/`-equivalent registry instead of this
component's local `spec-engine/specs/` default sink; and (c) decide how a
real human approval (Telegram button, CLI prompt, etc.) calls
`finalize_spec()`.

## Running the tests

```bash
python -m pytest tests/spec_engine        # this component's suite only
python -m pytest                          # full repo suite (includes the above)
python3 spec-engine/eval/spec_engine_eval.py   # the 3-brief eval as a standalone report
```

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
(`spec.schema.json`, `plan.schema.json`, `scaffold-plan.schema.json`).
