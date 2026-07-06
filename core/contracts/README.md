# Contracts — Phase 0 (Contracts-as-Code)

> Spec: `docs/ULTIMATE_FRAMEWORK_PLAN.md` Phase 0 and Design Decision #3 ("Contracts become schemas").
> Validator: `tessctl validate <contract-type> <file>` (`.tess/bin/tessctl`).

This directory is the first piece of `core/` — the framework's single source of
truth for machine-checkable contracts. It exists ahead of the full `core/`
extraction the plan schedules for Phase 1 ("Portable core + render targets");
Phase 0 deliberately scopes to contracts only, per the plan's own Phase 0
acceptance criteria.

## The four contracts

| Schema | Doctrine source | What it's grounded in |
|---|---|---|
| `brief.schema.json` | `conductor/dispatch-brief.md` | The six required fields, the Decomposition Rule, the mandatory 3-step destructive-ops pattern |
| `crew-plan.schema.json` | `conductor/orchestra-model.md` §3.1–§3.2 | The crew-plan required shape and the seven plan-validation rules the conductor rejects a plan for violating |
| `verdict.schema.json` | `conductor/review-output-standards.md` + `conductor/verification-routing.md` | The severity grammar, the mandatory closing verdict (normalized across Quinn/Reid/Cyra/Leah's differing per-role vocabularies), the six named verifiers, primary-artifacts-only |
| `return-manifest.schema.json` | **New in this phase** — no single pre-existing doctrine file | Operationalizes `orchestra-model.md` §4c ("read the primary artifact, never the summary"), `dispatch-brief.md`'s evidence requirement, and `subagent-failure-protocol.md`'s five failure states |

Every field in every schema carries a `description` (or `$comment`) citing the
exact doctrine line it encodes. Where a schema field has **no** direct doctrine
precedent (e.g. `brief.prod_touching`, `crew-plan.Task.client_facing`), the
description says so explicitly — these are documented Phase-0 interpretive
choices that make a prose trigger ("more than 15 minutes or touching
production") schema-enforceable, not silent inventions.

## Schema vs. lint

The plan's own C1 module spec distinguishes "schema" checks (structural — does
this instance have the right shape and types?) from "lint" checks (business
rules that are true *of* the doctrine but are relational across sibling array
items, and awkward or impossible to express as a single JSON Schema node).
`tessctl validate` runs both and reports failures from either as violations:

- **Schema** — implemented as a deterministic subset of JSON Schema draft-07
  (see the keyword list in every file's trailing `$comment`), including
  `if`/`then`/`else` for the two doctrine-mandated conditional rules
  (`brief`: milestones required when prod-touching/>15min; `crew-plan.Task`:
  `verifier.required` must be true when prod-touching/client-facing/
  externally-visible/irreversible-informing; `verdict`: `disposition` must be
  `BLOCK` when any finding is `CRITICAL`; `return-manifest.Claim`: a
  non-inferred claim must carry non-empty `evidence`).
- **Lint** (`_lint_checks` in `.tess/bin/tessctl`) — `crew-plan`: no intra-stage
  `depends_on` edges when `parallel: true` (§3.2 rule 7); `synthesis.inputs`
  must reference real task ids in `stages[]`. `verdict`: `severity_counts`
  must match the actual tally of `findings[]` by severity.

Not implemented in Phase 0 (explicitly deferred, and noted inline in the
schemas): cross-checking `crew-plan.Task.agent` against the installed roster
(`.claude/agents/*`), and the ≤4-guild cap (§3.2 rule 5) — both require
roster/guild membership data this validator does not yet load.

## Schema-miss → degraded_output classification

A contract instance that fails validation — structural or lint — is classified
`degraded_output` (`subagent-failure-protocol.md`'s failure-state table: "Agent
returns output but quality is below threshold... wrong format"), defaulted to
cause class `context-gap` (L4 citation fix, Fable adversarial review: this
specific line — "The retry protocol's context-gap class exists precisely
because this is the most common cause" — is `docs/ULTIMATE_FRAMEWORK_PLAN.md`
§A.1's commentary on the doctrine, not `subagent-failure-protocol.md` itself;
that file states the cause-classification table and the "changed brief
required" retry rule but does not itself argue context-gap is the most common
cause), and flagged `same_brief_retry_forbidden: true` per the protocol's rule that
non-transient causes require a changed brief. `tessctl validate` exits non-zero
on any violation so a git hook / CI action can gate on it deterministically.
Full retry orchestration (writing the retry to a mission record, dispatching
the changed-brief retry itself) is out of scope for Phase 0 — this phase
implements the classification and the signal only, per the dispatch brief for
this build.

## Format an instance file can take

`tessctl validate` accepts `.json`, `.yaml`/`.yml`, or `.md` (a file with a
`---`-delimited YAML front-matter block — the instance is the front-matter,
not the markdown body). This matches the plan's own file-format description
for briefs and verdicts (`missions/<id>/briefs/<task>.md`,
`missions/<id>/verdicts/<task>.verdict.md`) while also allowing pure
JSON/YAML for crew-plans and return-manifests.

## Not yet wired into keystone tracking

`core/contracts/**` is **not** added to `tess.manifest.json`'s `owned_globs`
or to `.tess/tess.lock` in this phase. `tessctl doctor`/`verify` only iterate
`tess.lock`'s tracked entries, so this is safe — the new files are simply
invisible to the keystone update/integrity machinery for now, not
mismanaged by it. Extending `owned_globs` + `tess.lock` to `core/**` is
explicitly a Phase 1 task ("extend `tess.manifest.json` owned_globs + `tess.lock`
to the new outputs so keystone upgrades all adapters atomically").
