# Intent Router — the orchestrator front door

> Spec: `TESS-VISION-AND-BUILD-SPEC.html`, Phase 1, Epic E1 — "Intent
> Router: 'Tess Picks the Command.'" Product pillar: **Orchestrator-first**
> — "The user never picks a command. ... The user speaks in ideas; Tess
> selects the entry point, routes the mission, assembles the crew, and
> narrates what it chose and why."
>
> **Status: Buildable-Now, first slice.** This component ships the
> deterministic routing core end to end (classify → decide → sketch →
> narrate → log) against a real reference routing table (this repo's own
> 26 commands + 6 outcome orchestrators). It does **not** yet wire into
> `CLAUDE.md`, `conductor/commands.md`, or any live slash-command dispatch
> — see "Integration status" below for exactly why and what that follow-up
> PR needs to do.

## What this is

A **generalized tess-os framework component**, not a Twiss-specific
integration. Given freeform input — an idea, a ramble, a pasted doc — it:

1. **classifies** the input into a routing table's best-matching entry
   (an internal command + optional orchestrator + outcome type);
2. **decides**: confident enough to just route, or ambiguous enough to
   ask exactly one clarifying question;
3. **sketches** a first-cut crew-plan (candidate agents, one stage, gated
   on `intake-before-anything`) for the chosen entry — explicitly marked
   as a sketch, never a dispatchable plan;
4. **narrates** its choice in plain language — "here's what I'm doing and
   why" — so the user is never asked to pick a slash command; and
5. **logs** the decision (with its rationale) to a JSONL record.

Every deployment of tess-os can ship its own routing table — a
completely different set of commands/orchestrators — and every module
under `intent_router/` works unchanged. Nothing in this package is
hardcoded to Tess's specific 26 commands; `routing_table.example.yaml` is
a reference instance, not a baked-in default.

## Architecture

```
freeform text
     │
     ▼
intent_router.classifier.classify()      deterministic, pure functions —
     │  (keyword + example-token         no model call, no I/O, no shared
     │   scoring; optional              state. Unit-tested directly.
     │   ExternalSignal blend-in)
     ▼
intent_router.router.route()             confident → build a decision +
     │                                   crew-plan sketch
     │  ambiguous → ONE clarifying
     │  question, no sketch yet
     ▼
intent_router.crew_plan_sketch           intent_router.narrate
  .build_sketch()                          .narrate()
     │                                        │
     └──────────────┬─────────────────────────┘
                     ▼
          intent_router.types.RoutingDecision
                     │
                     ▼
          intent_router.decision_log.append_decision()
             (schema-validated JSONL record)
```

`intent_router.pipeline.run_intent_router()` is the one function that
glues load-table → route → log together; `intent_router.cli` is a thin
manual-testing wrapper around it (`python -m intent_router.cli route
"..." --table routing_table.example.yaml`).

## The deterministic core vs. model-assisted classification

The parent build brief for this component was explicit: *"Tests
(unit-level on the routing/classification logic; if it uses a model
call, keep the deterministic mapping testable separately)."* This
package never calls a model. `intent_router.classifier` scores every
route against the input using:

- **keyword/phrase matching** — an exact phrase match scores full
  weight; a partial, unordered token match on a multi-word keyword
  scores proportionally (so a paraphrase of a keyword still registers
  some signal); and
- **stopword-filtered example-token overlap** — shared vocabulary
  between the input and a route's example utterances, so a
  well-documented route generalizes to phrasing that never literally
  contains one of its keywords.

An **`ExternalSignal`** (`outcome_type`, `suggested_route_id`,
`confidence`, `reasoning`) is the hook point for a model-assisted
classification pass — e.g. a live Claude Code session reading the
freeform input and forming its own judgment — but it is optional and
purely additive: `intent_router.classifier.score_route()` blends it in
via two fixed, documented boosts (`EXTERNAL_ROUTE_BOOST`,
`EXTERNAL_OUTCOME_BOOST`). Every code path is a pure function of its
arguments — construct an `ExternalSignal` directly in a test and the
result is fully deterministic and reproducible, with **no real model
call required to test it**.

## Ambiguity handling — exactly what the epic specifies

> "Ambiguity → one clarifying question max, then route with stated
> assumption."

- `route()` on genuinely weak or closely-tied signal returns
  `ambiguous=True` with exactly one `clarifying_question` and **no**
  crew-plan sketch yet.
- `resolve_clarification(prior_decision, answer, table)` combines the
  original input with the user's one-line answer and **always forces** a
  final route (`force=True` internally) — it can never itself return a
  second `clarifying_question`. If the combined input is still
  ambiguous, it picks the top candidate and returns `assumption_stated`
  instead of asking again, exactly matching the epic's rule.
- **Zero cases leave the user stuck without a route.** Every ambiguous
  decision is resolvable in exactly one more turn.

## Configuring a routing table

A routing table is a YAML file shaped:

```yaml
routes:
  - id: product-mode                       # safe slug, unique
    entry_command: "/product-mode"          # free text — your deployment's vocabulary
    orchestrator: product-delivery-orchestrator   # optional
    outcome_type: build                     # one of the 9 values below
    description: "..."
    default_guilds: [product-guild, coding-team]  # optional, feeds the sketch
    keywords: ["roadmap", "ship a release", ...]
    examples: ["We need to decide what to build next quarter...", ...]
```

`outcome_type` is constrained to the same 9-value enum
`core/contracts/crew-plan.schema.json` already defines: `decide`,
`design`, `build`, `convert`, `recover`, `govern`, `review`,
`communicate`, `scale` — one vocabulary, not two.
`routing_table.example.yaml` is the reference instance, built from this
repo's own `conductor/commands.md` (26 commands) and
`conductor/outcome-orchestrators/README.md` (6 orchestrators) — every
one of the 26 is present, so the routing target is genuinely "the
complete command + orchestrator system," not a curated subset.

## The 40-case eval

Epic E1's acceptance criterion: *"A 40-case routing eval (real
historical mission briefs from `kb/wiki/log.md` as ground truth) routes
≥90% to the same entry point a human operator chose."*

**Honest data-source note:** `kb/wiki/log.md` is the *private* Tess
repo's mission log and does not exist in this public tess-os repo. The
40 cases in
[`tests/intent_router/fixtures/routing_eval_cases.yaml`](../tests/intent_router/fixtures/routing_eval_cases.yaml)
are synthetic-but-representative utterances across the same six
outcome-orchestrator domains plus ten mission-lifecycle/system commands
— deliberately paraphrased away from the routing table's own
keyword/example wording, so the eval measures generalization rather than
string-matching against itself. This is **not** a claim that these are
the private repo's actual historical missions.

Run it directly:

```bash
python3 intent-router/eval/routing_eval.py
```

or as part of the test suite (`tests/intent_router/test_routing_eval.py`
— enforced in CI via `python -m pytest`). Current result: **40/40
(100%)**, comfortably above the required 90% — see the eval script's
output for the full per-case breakdown, and the "honest labeling"
discipline this repo applies everywhere: a small number of cases (M&A)
carry two acceptable answers where the framework's own doctrine
(`conductor/outcome-orchestrators/integration.md`: "SGO leads
assessment... FO takes over at commitment") documents genuine overlap,
not classifier sloppiness.

## Integration status — what this PR does and does not wire up

**Built, tested, working standalone:** the classify → route → sketch →
narrate → log pipeline, against a real reference routing table, callable
from Python (`intent_router.pipeline.run_intent_router`) or from the CLI
(`python -m intent_router.cli`).

**Deliberately NOT touched by this PR:**

- `CLAUDE.md` — keystone-rendered from `.tess/core/templates/claude-md/`
  (`.tess/**`), not hand-edited in the live repo.
- `conductor/commands.md`, `conductor/*.md` more broadly — doctrine
  files, out of this PR's scope per its own build constraints.
- `.claude/commands/**`, `.github/workflows/**`, `core/policy/**`,
  `core/contracts/**`, `.tess/bin/tessctl` — all keystone/policy-owned or
  gate-critical paths, explicitly out of scope for a first-slice PR that
  should not need a signed ship-gate verdict to merge.

A follow-up integration PR — scoped separately, since it *does* touch
`.tess/**` template sources and possibly `conductor/*.md` — should wire
`run_intent_router()` into the actual front-door entry point (e.g. a
`CLAUDE.md` instruction block telling the live conductor to call this
component before offering the user any slash command, or an MCP/tool
binding). That PR is also the natural place to point `log_path` at a
real deployment's own `state/`-equivalent registry instead of this
component's local `intent-router/decisions/` default sink.

## Running the tests

```bash
python -m pytest tests/intent_router        # this component's suite only
python -m pytest                            # full repo suite (includes the above)
python3 intent-router/eval/routing_eval.py  # the 40-case eval as a standalone report
```

The test suite lives under the repo's existing `tests/` directory (not a
separate `intent-router/tests/`) specifically so it runs inside the
existing `python -m pytest` CI step with zero workflow changes — see
`tests/intent_router/_paths.py`'s docstring for why it is not named
`conftest.py` (a real collision was caught and fixed against the
existing root test suite during development).

## Fields reference

See [`intent_router/types.py`](intent_router/types.py) for the full
`Route`, `ExternalSignal`, `ScoredCandidate`, and `RoutingDecision`
dataclasses, and
[`schema/routing-decision.schema.json`](schema/routing-decision.schema.json)
for the machine-checkable shape of a logged decision (validated by this
component's own dependency-free
[`intent_router/schema_check.py`](intent_router/schema_check.py) — it
does not import or depend on `.tess/bin/tessctl`'s internal validator).
