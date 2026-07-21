# Routing Rubric — the intake classification doctrine

> Epic E1 deliverable: "An intake classification layer (doctrine + a
> routing rubric file...) mapping any input — text, voice-note
> transcript, pasted doc — to the correct internal command/orchestrator."
>
> This file is the **doctrine half** of that deliverable — the rubric a
> human, or a model reading freeform input inside a live session, applies
> when forming judgment about intent. `intent_router/classifier.py` +
> `intent_router/router.py` are the **deterministic half** — the
> mechanical scoring/decision logic this rubric's judgments feed into (as
> an optional `ExternalSignal`) or that runs standalone without any
> judgment at all.
>
> This rubric is deliberately **generalized**: it names no specific
> command, orchestrator, or agent. Read it against whatever routing table
> a given tess-os deployment ships (see `README.md` "Configuring a
> routing table"). `routing_table.example.yaml` is Tess's own concrete
> instance, not part of this rubric.

## 1. The one rule that matters most

**The user never picks a command.** Any input — a full paragraph, a
one-line question, a rambling voice-note transcript, a pasted document —
gets routed to an internal entry point automatically. If routing surfaces
any choice to the user at all, it is exactly one clarifying question, not
a menu of commands.

## 2. Classify by outcome type first, not by keyword

Before matching against any specific route, form a judgment about what
kind of outcome is actually being sought. This repo's own doctrine
(`conductor/cross-guild-coordination.md` §1, "Outcome-First Routing
Rule") already defines nine outcome types, reused verbatim as this
rubric's classification vocabulary (and as
`intent_router.types.OUTCOME_TYPES`):

| Outcome type | Reading it in freeform input |
|---|---|
| `decide` | High-stakes judgment calls, direction-setting, "should I even do this" |
| `design` | Open-ended exploration, not yet ready to commit to a direction |
| `build` | Making or shipping something concrete — a feature, a system, a plan |
| `convert` | Turning interest/pipeline into closed outcomes — sales, revenue |
| `recover` | Something is going wrong and needs to be stabilized or repaired |
| `govern` | Process, structure, roster, or operating-model concerns |
| `review` | Status, state, or progress checks — "where do things stand" |
| `communicate` | Producing a synthesis, summary, or explanation for someone else |
| `scale` | Expansion, new markets, partnerships, structural growth moves |

A single input can carry signal for more than one outcome type — that is
expected, not a bug. See §4.

## 3. Signal to read for, in priority order

1. **Explicit stated urgency or damage** ("production is down,"
   "everyone is furious," "this is an emergency") outranks everything
   else — route to whatever the table's `recover`/emergency-flavored
   entry is before considering anything else.
2. **A named object of concern** — a client, a metric, a market, a
   piece of the product, a person/role — narrows the outcome type fast.
   "Our biggest client" points at client-experience-flavored routes;
   "the pipeline"/"pricing" points at revenue-flavored routes; "the
   roadmap"/"architecture" points at product-flavored routes.
3. **The verb of intent** — "should we," "I'm deciding," "help me
   figure out" reads `decide`; "let's build," "ship," "add a feature"
   reads `build`; "what's the status," "where do we stand" reads
   `review`.
4. **Session-lifecycle framing** — "I just sat down," "catch me up,"
   "that's it for today," "wrap this up" are almost never about outcome
   domain at all; they are about the mission-lifecycle commands
   (session start/end, status snapshots) a table should carry
   independently of the outcome-orchestrator set.
5. **Absence of any strong signal** — a short greeting, a single vague
   sentence with no named object and no clear verb of intent — is
   itself a signal: route to whatever the table names as its generic
   fallback entry (e.g. `add-mission`-equivalent), or ask the one
   clarifying question if even the fallback is not confident.

## 4. Genuine overlap is not a classifier failure

Some inputs honestly straddle two routes because the underlying
orchestration doctrine itself documents shared ownership at that stage.
The clearest example already on record
(`conductor/outcome-orchestrators/integration.md`): *"SGO vs FO on M&A:
SGO leads assessment... FO takes over at commitment."* An early-stage
acquisition idea can correctly land on either a founder-level or a
strategic-growth-flavored route — treat this as **disclosed overlap**,
not a bug to eliminate by forcing a single "correct" answer. When
building a routing table, note these overlaps explicitly (see
`routing_table.example.yaml`'s M&A-flavored route entries) rather than
hiding them.

## 5. Ambiguity → exactly one clarifying question, then commit

If, after applying §2–4, no single route stands out clearly:

1. Ask **exactly one** clarifying question, framed around the two (or
   more) most plausible outcome types/routes — never a menu of internal
   command names.
2. On the answer — whatever it is — **commit to a route.** Never ask a
   second clarifying question on the same input. If the answer still
   does not resolve the ambiguity, pick the strongest remaining
   candidate and **say so explicitly** ("I'm assuming this is primarily
   about X because Y — tell me if that's wrong and I'll re-route").

This is a hard ceiling, not a soft preference: one question, then a
routed decision with a stated assumption if needed. `intent_router.router`
enforces this mechanically (`resolve_clarification()` cannot itself
return a second `clarifying_question`); this rubric states the same rule
for a model-assisted judgment call operating without that code path.

## 6. Narrate every choice

Whatever the entry point, state — in plain language, before doing
anything else — which entry point was chosen and why. Cite the concrete
signal that drove the choice (a phrase from the input, a named
object of concern, an outcome type), not a vague "this seems like a
product thing." A user should be able to read the narration and
immediately understand (and, if needed, correct) the routing decision
without ever having seen a list of internal commands.

## 7. What this rubric does not decide

This rubric governs **entry-point selection only** — which command,
orchestrator, or crew-plan sketch to start with. It does not:

- expand a sketch into a real crew-plan (that is the named
  orchestrator's job, per `orchestra-model.md`);
- write dispatch briefs (six-field contract, `conductor/dispatch-brief.md`);
- decide verification/sign-off requirements (`conductor/verification-routing.md`);
  or
- grant any dispatch authority by itself. A routing decision is a
  recommendation for where to start, never an executed action.
