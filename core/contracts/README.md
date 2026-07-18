# Contracts — Phase 0 (Contracts-as-Code) + Phase 2 (`policy.schema.json`) + Goal #5 (`mission`/`retry`)

> Spec: `docs/ULTIMATE_FRAMEWORK_PLAN.md` Phase 0 and Design Decision #3 ("Contracts become schemas"); Phase 2 and Design Decisions #2/#6 for `policy.schema.json`; §C3/§C4 for `mission.schema.json`/`retry.schema.json`.
> Validator: `tessctl validate <contract-type> <file>` (`.tess/bin/tessctl`).
> Gate: `tessctl gate` (`.tess/bin/tessctl`) — see the top-level `README.md` "`tessctl gate` — the enforcement spine" section.
> Missions: `tessctl mission` / `gate-status` / `gate clear` / `retry` (`.tess/bin/tessctl`'s MISSION LEDGER region) — see `missions/README.md`.

This directory is the first piece of `core/` — the framework's single source of
truth for machine-checkable contracts. It exists ahead of the full `core/`
extraction the plan schedules for Phase 1 ("Portable core + render targets");
Phase 0 deliberately scopes to contracts only, per the plan's own Phase 0
acceptance criteria. `policy.schema.json` was the plan's own deferred fifth
contract (§B.2: "`policy.schema.json` (hard floors, whitelists, gate map)"),
built in Phase 2 alongside the `tessctl gate` spine that is its only consumer.
`mission.schema.json`/`retry.schema.json` are the sixth and seventh, built in
Goal #5 alongside `tessctl mission`/`gate-status`/`gate clear`/`retry` — the
machine-checkable form of `conductor/doctrine.md`'s "The Gates" table and
`conductor/subagent-failure-protocol.md`'s typed retry protocol.

## The seven contracts

| Schema | Doctrine source | What it's grounded in |
|---|---|---|
| `brief.schema.json` | `conductor/dispatch-brief.md` | The six required fields, the Decomposition Rule, the mandatory 3-step destructive-ops pattern |
| `crew-plan.schema.json` | `conductor/orchestra-model.md` §3.1–§3.2 | The crew-plan required shape and the seven plan-validation rules the conductor rejects a plan for violating |
| `verdict.schema.json` | `conductor/review-output-standards.md` + `conductor/verification-routing.md` | The severity grammar, the mandatory closing verdict (normalized across Quinn/Reid/Cyra/Leah's differing per-role vocabularies), the six named verifiers, primary-artifacts-only. Phase 2 adds an optional `covers_paths` field (path globs the verdict's review actually scoped to) so `tessctl gate` can match a verdict against a diff. Fable-review fix adds an optional `artifact_hashes` field (repo-relative path → the reviewed git blob SHA) so `tessctl gate` binds that coverage to the exact CONTENT reviewed, not just the path shape — a verdict clears the exact change it reviewed, not every future edit under the same glob. **Phase 2b adds an optional `signature` field** (`$defs.VerdictSignature` — a GPG detached signature over the verdict's canonical content) — optional at the schema level, but functionally required for a verdict to cover anything: see `conductor/verdict-signing.md`. |
| `return-manifest.schema.json` | **New in Phase 0** — no single pre-existing doctrine file | Operationalizes `orchestra-model.md` §4c ("read the primary artifact, never the summary"), `dispatch-brief.md`'s evidence requirement, and `subagent-failure-protocol.md`'s five failure states |
| `policy.schema.json` | **New in Phase 2, extended Phase 2b** — `conductor/verification-routing.md` + `conductor/guardrails.md` Rule 18 | The path→classification map (prod-touching/client-facing/externally-visible/irreversible-decision) that requires a covering verdict, plus the four Rule-18 hard-floor categories (credentials, money movement, destructive prod data, client-external claims) that are never verdict-satisfiable. **Phase 2b adds `policy.verifier_keys`** — the allowed-key set a verdict's `signature` is checked against (verifier name → fingerprint + bundled public-key file path). The actual policy DATA a project ships lives at `core/policy/policy.yaml`, not in this schema. |
| `mission.schema.json` | **New in Goal #5** — `conductor/doctrine.md` "The Gates" table + `conductor/mission-states.md` | A mission record's id/name/state/gates — the five canonical gates (reusing `crew-plan.schema.json`'s own `Stage.gate_in` enum verbatim), each seeded pending and only flippable to `cleared:true` via `tessctl gate clear`, which requires a real, on-disk evidence artifact. Authored as `missions/<id>/mission.md` (front-matter) and/or `missions/<id>/mission.json` (pure JSON) — two serializations of the same record. |
| `retry.schema.json` | **New in Goal #5** — `conductor/subagent-failure-protocol.md` | One logged retry attempt: `failure_state` (the five-state table) and `cause_class` (the four-class table) verbatim, `attempt` capped at 3 (`maximum: 3`), and the VERBATIM `brief_text` used for that attempt — the literal string `tessctl retry check`/`retry log` diff against the next attempt to enforce "same-brief retries are forbidden for every non-transient cause." Written to `missions/<id>/retries/<task>.attempt-N.md`. |

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

## Wired into keystone tracking (Phase 1, extended Phase 2)

As of Phase 1 ("Portable core + render targets"), `core/contracts/**` is a
tracked, framework-owned subtree; Phase 2 adds `policy.schema.json` to it and
wires the sibling `core/policy/**` data directory the same way:

- `tess.manifest.json`'s `owned_globs` includes `"core/contracts/**"` and
  `"core/policy/**"`, so `tessctl restore` / `render` / `update` are permitted
  to write here (the manifest write gate denies everything not on the
  allowlist).
- `.tess/core/contracts/**` and `.tess/core/policy/**` are the pristine
  mirrors — the actual source of truth — with a `.tess/tess.lock` entry per
  file (`status: core-managed`, `base_sha` pinned to the pristine bytes). The
  live copies at `core/contracts/` and `core/policy/` are the resolved output
  of those mirrors, exactly like every other doctrine file under
  `conductor/**`.
- `brief.schema.json`, `verdict.schema.json`, and `policy.schema.json` carry
  `tier: security` — they are the machine-checkable form of
  `conductor/dispatch-brief.md`, `conductor/verification-routing.md`, and
  `conductor/guardrails.md` Rule 18 (all already `tier: security` prose), so
  weakening any of them (e.g. dropping the milestones-required-when-
  prod-touching conditional, the BLOCK-on-CRITICAL conditional, or a
  hard-floor category) is exactly as security-relevant as editing the prose
  doctrine, and is quarantined the same way. `core/policy/policy.yaml` (the
  actual policy DATA, not the schema) is also `tier: security` for the same
  reason — see its own header. `crew-plan.schema.json`,
  `return-manifest.schema.json`, `mission.schema.json`, `retry.schema.json`,
  and this README stay `tier: normal` — their doctrine sources
  (`orchestra-model.md`; none; `doctrine.md`; `subagent-failure-protocol.md`)
  are not themselves `tier: security` prose, same as the original two.
- `tessctl doctor` / `tessctl verify` / `tessctl lock --check` cover all nine
  files (the five above + `mission.schema.json` + `retry.schema.json`) like
  any other core-managed entry: unpinned `.tess/core` tamper is flagged as
  CORE TAMPER (SECURITY-TIER for the three schemas + policy.yaml above), and
  live drift from the pristine core is flagged and remediated the same way
  as any other doctrine file.

This closes the deferred Phase 0 item ("Not yet wired into keystone
tracking") — the contracts are no longer invisible to the keystone
update/integrity machinery; they are part of the rendered/tracked framework.
`policy.schema.json` + `core/policy/policy.yaml` are new in Phase 2, wired in
from the moment they were introduced (never had an "unwired" period the way
Phase 0's four original contracts briefly did).

**Phase 2b note:** verdict signing (`verdict.schema.json`'s new `signature`
field, `policy.schema.json`'s new `verifier_keys` field) extends these SAME
already-wired files rather than adding new ones to this list.
`.tess/keys/verifiers/<name>.asc` (each verifier's bundled PUBLIC key) is
deliberately NOT core-managed/keystone-tracked, the same posture
`.tess/keys/twiss-release-key.asc` already has — it's a plain committed
repo asset, not part of the `.tess/core` mirror system. During a ship-gate
run, however, the gate reads both verifier registration and exact public-key
bytes from the immutable BASE Git tree; candidate checkout bytes cannot add,
replace, delete, symlink, or roll back the trust material used for that run.
The directory is also covered by `core/policy/policy.yaml`'s own
`tess-os-security-tier-doctrine` rule (`.tess/keys/verifiers/**` was added to
that rule's `globs` in Phase 2b). See
`docs/TRUST_BOOTSTRAP_SECURITY_DESIGN.md` for the trust boundary.

**Goal #5 note:** `mission.schema.json` + `retry.schema.json` are wired into
`tess.lock`/`tier: normal` the same way `crew-plan.schema.json` was from the
start — no "unwired" interim period. Their INSTANCE data
(`missions/<id>/mission.md`/`mission.json`/`retries/*.md`), unlike
`core/policy/policy.yaml`, is deliberately NOT keystone-tracked at all —
`missions/**` is per-project mission data (added to `tess.manifest.json`'s
`never_touch`, same fenced-off treatment `kb/**`/`clients/*/**` already
get), not framework doctrine. See `missions/README.md`.
