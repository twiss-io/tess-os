# Orchestrator — wiring the spine end to end

> Follow-up to `intent-router/` (Epic E1) and `spec-engine/` (Epic E2 +
> the codegen slice of Epic E4). Both components' own READMEs flagged the
> same two debts under "Integration status": the three spine components
> existed but were never wired into one callable flow, and
> `spec_engine.approval.record_approval()`'s `approved_by` was
> unauthenticated free text. This package closes both.
>
> **Status: Buildable-Now.** `orchestrator.pipeline.run_pipeline()` runs
> `intent_router` -> `spec_engine` intake/plan -> a REAL, authenticated
> approval gate -> `spec_engine.codegen.generate_app()` -> OPTIONAL,
> opt-in Agent Receipt emission (wedge-loop epic addition, see "Agent
> Receipt" below) as one call. `orchestrator.cli` is a thin manual-testing
> wrapper around it.

## What this is

The first component in this repo that intentionally imports **both**
`intent_router` and `spec_engine` directly. Those two components
deliberately keep zero hard import dependency on each other (see
`spec-engine/spec_engine/integrations/from_intent_router.py`'s module
docstring) so each stays independently deployable — wiring them together
end to end is this package's entire purpose, so that discipline does not
apply here.

```
freeform text
     │
     ▼
intent_router.pipeline.run_intent_router()        REAL — classify, route,
     │  ambiguous, no clarification given?         crew-plan sketch, logged
     │  -> stop HONESTLY, return "needs_clarification"
     ▼
spec_engine.integrations.from_intent_router
     .routing_context_from_decision()               REAL — carries routing
     ▼                                               provenance through
spec_engine.pipeline.run_intake_and_plan()          REAL — harvest -> Plan
     ▼
   <<< orchestrator.approval_gate.ApprovalGate >>>   REAL, AUTHENTICATED —
     │  .request_approval(plan) -> Approval          see "The approval
     │  .verify(approval, plan) -> bool, checked      gate" below
     │  BEFORE anything downstream runs
     ▼
spec_engine.pipeline.finalize_spec_with_approval()  REAL — build_spec()'s
     │                                               OWN codegen-boundary
     │                                               re-verification (gate-
     │                                               verifiable, content-
     │                                               hash-bound approval
     │                                               required — see
     │                                               "CODEGEN-BOUNDARY
     │                                               HARDENING" below)
     ▼
spec_engine.codegen.generate_app()                  REAL codegen — see
     │                                               spec-engine/README.md
     │                                               for exactly what's
     │                                               generated vs. a
     │                                               labeled stub per
     │                                               module kind
     ▼
   <<< telemetry.events.record_mission_completion() >>> OPT-IN, off by
     │                                               default — see
     │                                               "Telemetry" below
     ▼
   <<< orchestrator.mission_receipt (Hop 7) >>>       OPTIONAL, opt-in —
                                                       see "Agent Receipt"
                                                       below (wedge-loop
                                                       epic addition)
```

`orchestrator.pipeline.run_pipeline()` is the one function above the
line. Nothing in this package reimplements classify/route/harvest/build/
codegen logic, and nothing here introduces a new stub label of its own —
where a downstream hop is itself partially a stub
(`spec_engine.codegen`'s `service`/`integration` module honesty), that
labeling rides through unchanged into the generated app's own
`.spec-engine/codegen-manifest.json`.

## The approval gate — what was forgeable, and what changed

`spec_engine.approval.record_approval(plan, *, approved_by: str, ...)`
accepts `approved_by` as a bare string, and still does today — that part
is unchanged by design (see `approval.py`'s own docstring). What this
package originally added (PR #81, described below) was authentication of
WHO `approved_by` is attributed to, at the point of decision.
`spec_builder.build_spec()`'s own gate — an `Approval` object matching
`plan_id` with `approved=True` — was, AT THAT TIME, real but untouched:
it only checked that *an* approval existed, never *who* it was
attributed to, and never whether it had actually been through any
`ApprovalGate` at all. A follow-up codegen-boundary hardening epic closed
that remaining gap directly inside `build_spec()` itself — see
"CODEGEN-BOUNDARY HARDENING" further down this doc for what changed and
why it had to happen at that layer, not only this one.

`orchestrator.approval_gate.ApprovalGate` is a new, ADDITIONAL,
product-layer control in front of `finalize_spec_with_approval()` in the
wired pipeline:

```python
class ApprovalGate(ABC):
    def request_approval(self, plan: Plan) -> Approval:
        """Block until a REAL, authenticated human decision is made.
        Must not forward an unauthenticated, caller-suppliable string
        into approved_by unexamined — authenticate through YOUR OWN
        mechanism first."""

    def verify(self, approval: Approval, plan: Plan) -> bool:
        """Independently re-check that `approval` genuinely came from
        THIS gate's mechanism, FOR `plan` specifically, and was not
        tampered with. Must return False (never raise) on a forged/
        malformed/spec-substituted input."""
```

`run_pipeline()` calls `request_approval()`, then calls `verify(approval,
plan)` on whatever it got back, and **raises `ApprovalAuthenticationError`
and never calls `finalize_spec_with_approval()`/`generate_app()`** if
verification fails — this is what makes "codegen only runs after a valid,
authenticated approval" true for the wired flow, not just an aspiration.

### CODEGEN-BOUNDARY HARDENING (closes the "Also open" gap below)

The paragraph immediately above described the state as of PR #81: a real,
authenticated `ApprovalGate` sat in front of `finalize_spec()`, but
`spec_engine.spec_builder.build_spec()` itself — the actual codegen
boundary, reachable by ANY caller of `spec_engine`, not only ones going
through this package — still accepted a bare, unsigned `spec_engine.
approval.record_approval(approved_by="Xavier")` call with zero
verification. A follow-up hardening epic closed this:

- `spec_engine.spec_builder.build_spec()` now REQUIRES an approval that
  independently re-verifies via `spec_engine.gate_approval.
  verify_gate_approval()` — the SAME HMAC mechanism this package's
  `LocalIdentityApprovalGate` signs with — not merely a structurally
  matching `plan_id` + `approved=True`. A bare `record_approval(...)`
  call is now rejected AT THE CODEGEN BOUNDARY ITSELF, for every caller,
  not only ones routed through `orchestrator`.
- The signed payload now ALSO binds a content-hash of the plan
  (`spec_engine.content.plan_content_hash()`), not just the mutable,
  caller-settable `plan_id` slug — an approval genuinely signed for one
  plan's content can no longer authorize building a `SpecDocument` from a
  DIFFERENT plan/spec, even one sharing the same `plan_id` (a substituted
  or in-place-mutated `Plan` object).
- `ApprovalGate.verify()`'s signature grew a required `plan` parameter
  for the same reason, at this seam.
- The low-level signing/verification primitives moved from
  `orchestrator/identity.py` into `spec_engine.gate_identity` (this
  package's own `identity.py` is now a backward-compatible re-export
  shim) — `spec_engine` is the lower layer both this package's
  `LocalIdentityApprovalGate` (signing) AND `build_spec()`
  (re-verification) need to share, without `spec_engine` reaching "up"
  into `orchestrator`.

See `spec_engine/spec_builder.py` and `spec_engine/gate_approval.py`'s
module docstrings for the full mechanism, and
`tests/spec_engine/test_spec_builder.py` /
`tests/spec_engine/test_gate_approval.py` for the adversarial proof this
holds at the codegen boundary directly (not merely at this package's own
seam, tested below).

### The shipped default: `LocalIdentityApprovalGate`

`orchestrator/identity.py` (now a thin re-export shim over
`spec_engine.gate_identity`) + `orchestrator/adapters/local_identity.py`.
On first use, generates a random 256-bit key at
`~/.tess-os/approval-identity/<os-username>.key` (`chmod 600`, enforced —
`verify()` and `request_approval()` both refuse a group/world-readable
key file). `request_approval()`:

1. Prints `plan.summary_for_approval` and prompts for a real terminal
   confirmation (`APPROVE` / `REJECT`) — `approved_by` is derived from
   `getpass.getuser()`, **never accepted as a parameter a caller could
   override**.
2. Delegates to `spec_engine.gate_approval.sign_local_approval()` — the
   SAME function `build_spec()` uses to independently re-verify — to
   HMAC-SHA256-sign every identity-relevant field of the resulting record
   (`approval_id`, `plan_id`, a plan CONTENT HASH, `approved`,
   `approved_by`, `approved_at`, a fresh nonce) with that local key.
3. Embeds the signature evidence into `Approval.notes` as JSON (rides
   through, unchanged, into spec-engine's own existing
   `specs/approvals.jsonl` audit log via `finalize_spec_with_approval()`
   -> `append_approval_note()` — no new log sink needed).

`verify(approval, plan)` delegates to `spec_engine.gate_approval.
verify_gate_approval()`, which independently recomputes the signature
over the approval's *actual* current field values AND `plan`'s current
content-hash, and compares with `hmac.compare_digest`. Tamper with
`approved_by`, `approved`, `approved_at`, `plan_id`, or the content-hash
after signing — or hand-construct an `Approval` without ever going
through the gate, or replay a genuine approval against a DIFFERENT plan —
and `verify()` returns `False`, logging a WARNING first (never silently).
See `tests/orchestrator/test_pipeline_adversarial.py` for the required
proof that a forged approval is rejected and codegen never runs at this
seam, and `tests/spec_engine/test_spec_builder.py` for the SAME proof one
layer down, at the codegen boundary itself.

This is **not the same system** as `.tess/bin/tessctl verdict`'s GPG
verifier-key registry (`core/policy/policy.yaml`). That is the ship-gate's
cryptographic identity system for signing mission verdicts; this is an
unrelated, product-layer mechanism for authenticating who approved a
spec. `orchestrator/` never generates, registers, or signs a verifier
key/verdict, and never touches `core/policy/**` or `.tess/**`.

### Honest limitation — read before treating this as production-grade

`LocalIdentityApprovalGate` proves "the process producing this signature
had read access to this OS account's local approval-identity key file,
and a live terminal confirmation happened." It does **not** prove which
human was physically at the keyboard, does not survive a compromised OS
account (same trust model as an SSH key), and supports exactly one
identity per OS account — not a genuinely multi-human production
deployment. **This is an open design question for Xavier**, not a gap
papered over: a production adapter (Telegram button bound to a known
chat/user id, a web session token, SSO/WebAuthn) needs a real,
per-human IdP, and is a drop-in `ApprovalGate` implementation once one
is decided on. See `spec_engine.gate_identity`'s module docstring for the
full statement.

**Previously open, now closed by the codegen-boundary hardening epic**
(see the section above): `spec_engine.approval.record_approval()` itself
is STILL unchanged on purpose (it remains a deliberately dumb, no-opinion
constructor — see `approval.py`'s own docstring), but
`spec_builder.build_spec()` no longer accepts its bare output.
`Approval.approved_by` is now checked for gate-verifiable, content-hash-
bound evidence for *every* caller of spec-engine — not only ones going
through this orchestrator — closing the exact gap this section used to
describe as open. `spec_engine.pipeline.finalize_spec()` (the common,
still-unchanged-signature entry point for tests/scripts/CI/`spec_engine.
cli`) transparently mints a genuinely gate-verifiable approval under the
hood now (via `gate_approval.sign_local_approval()`) instead of a bare
one — see that function's own docstring for exactly what changed and
what stayed the same for existing callers.

**Still genuinely open, deliberately not built here:** a
production-grade `ApprovalGate` adapter (Telegram/web/SSO) — see the
"Honest limitation" section above — and DURABLE (cross-process) nonce
anti-replay tracking for spent approvals (today's tracker is
in-process/in-memory only — see `spec_engine.gate_approval`'s module
docstring's "Replay" section). Both are flagged as open questions for
Xavier in the hardening PR that introduced this section.

## Telemetry (opt-in, off by default)

`run_pipeline()`'s final hop, right after `generate_app()` succeeds, calls
`telemetry.events.record_mission_completion()` — a local, OPT-IN
activation/retention event for this install's governed-mission pipeline.
It is OFF by default and a complete, instant no-op (nothing counted,
timestamped, or written) unless a human has explicitly run
`python -m telemetry.cli enable`. `PipelineResult.telemetry` carries the
result (`MissionCompletionEvent(recorded=False)` in the default, disabled
case — not an error).

This is a genuinely separate concern from the approval gate above:
`ApprovalGate` authenticates WHO approved a plan; `telemetry` counts
THAT a governed mission (approval -> spec -> generated app) completed,
locally, with no content, no PII, and no network call. See
`telemetry/README.md` for the module's own architecture and
`docs/TELEMETRY.md` for the full privacy contract — what is/isn't
captured, where it lives, and how to inspect/disable/delete it.

## Agent Receipt (Hop 7, opt-in, off by default — wedge-loop epic addition)

`run_pipeline()`'s final hop, right after Hop 6's telemetry, calls
`_emit_governed_mission_receipt()` (`orchestrator/mission_receipt.py`) —
OPTIONAL, off unless a caller supplies `receipt_path`. When given one, it
assembles and locally HMAC-signs one `decision_kind: "local_approval"`
[Agent Receipt](../docs/AGENT_RECEIPT_SPEC.md)
(`core/contracts/agent-receipt.schema.json`) embedding the SAME `Approval`
Hop 3/4 already authenticated and independently re-verified TWICE, signs
the envelope with THIS install's real local approval-identity key
(`spec_engine.gate_identity` — never demo/ephemeral keys), and writes it
to `receipt_path` as a single JSON file. `PipelineResult.receipt` carries
the result (`None` by default, and on any receipt-emission failure — a
`mission_receipt.MissionReceiptError` is caught and downgraded to a
non-fatal warning, exactly mirroring telemetry's own "an optional sidecar
failing must never un-complete a governed mission" discipline).

★ **TRUST LEVEL — read `docs/AGENT_RECEIPT_SPEC.md`'s "★ Trust levels are
not interchangeable" before treating this like a GPG-backed receipt.**
This is System A: local, symmetric HMAC-SHA256, verifiable only by an
independent holder of the same secret key — deliberately WEAKER evidence
than `tools/receipt-emit/`'s System B (GPG, `verdict`/`signoff`, publicly
verifiable), which this hop never touches, never wraps, and never
upgrades. `tools/receipt-verify/hmac_verify.py` is the standalone,
dependency-free verifier a third party would run against a receipt this
hop produced — see its own module docstring for the "verifying is not a
lower-privilege operation than signing" disclosure before sharing a
`local_approval` receipt's key material with anyone.

Genesis-only, single-file, disclosed scope: this hop does not persist or
extend a durable, multi-run receipt CHAIN the way `tools/receipt-emit/`
atomically appends to one for GPG receipts — every emitted receipt is
`chain.sequence: 0`, `prev_receipt_hash: "GENESIS"`. Durable cross-run
chaining, and the full idea->route->approve->boots->receipt-verify (plus
rejection and mid-kill unhappy-path) end-to-end proof, are a disclosed,
scoped follow-up — see `docs/AGENT_RECEIPT_SPEC.md`.

## Handling ambiguous routing

If `intent_router` returns `ambiguous=True` and no `clarification_answer`
was supplied, `run_pipeline()` stops at `status="needs_clarification"`
and returns the one clarifying question — it does not silently guess, and
it does not ask a second question if you re-run with an answer
(`intent_router.pipeline.continue_with_clarification()`'s own contract).
Pass `force_route=True` to skip asking entirely (mirrors
`intent_router.cli --force`).

## Running it

```bash
python -m orchestrator.cli run "An app that tracks vendor invoices and flags overdue ones." \
    --table intent-router/routing_table.example.yaml \
    --target-dir /tmp/generated-invoice-app
```

Programmatically:

```python
from orchestrator.adapters.local_identity import LocalIdentityApprovalGate
from orchestrator.pipeline import run_pipeline

gate = LocalIdentityApprovalGate()
result = run_pipeline(
    "An app that tracks vendor invoices and flags overdue ones.",
    "intent-router/routing_table.example.yaml",
    gate,
    target_dir="/tmp/generated-invoice-app",
)
assert result.status == "generated"
```

## Running the tests

```bash
python -m pytest tests/orchestrator     # this component's suite only
python -m pytest                        # full repo suite (includes the above)
```

`tests/orchestrator/_orchestrator_paths.py` is this component's own
sys.path bootstrap helper, following the exact naming discipline
`tests/intent_router/_paths.py` and `tests/spec_engine/
_spec_engine_paths.py` document for themselves (a unique basename per
test directory — pytest's default "prepend" import mode requires it).
Every orchestrator test that touches `LocalIdentityApprovalGate` passes
an explicit `identity_dir=tmp_path/...` — none of this suite ever reads
or writes the real `~/.tess-os/approval-identity/` on the machine running
the tests.

## Integration status — what this PR does and does not wire up

**Built, tested, working standalone:** the route -> intake/plan ->
authenticated-approval-gate -> finalize -> codegen pipeline, callable
from Python (`orchestrator.pipeline.run_pipeline`) or the CLI
(`python -m orchestrator.cli`).

**Deliberately NOT touched by this PR** (same scope boundary
`intent-router/README.md` and `spec-engine/README.md` already drew for
themselves):

- `CLAUDE.md`, `conductor/*.md`, `.claude/commands/**`,
  `.github/workflows/**`, `core/policy/**`, `core/contracts/**`,
  `.tess/bin/tessctl` — all keystone/policy-owned or gate-critical paths.
- A Telegram-button, web, or CLI-with-real-auth `ApprovalGate` — the
  interface is documented and ready for one; none is built here (design
  constraint: "GENERALIZED/pluggable — do NOT hardcode Telegram").
- Hardening `spec_engine.approval.record_approval()` itself against a
  caller that bypasses this orchestrator — see "Honest limitation" above.
- Provisioning a real, persistent database or a deploy target for
  generated apps — `spec_engine.codegen`'s own already-disclosed scope
  boundary (Phase 2 Epic E4's remaining deliverables), unaffected by this
  PR.

## Wedge-loop epic addition — what THIS change does and does not wire up

The line above ("Deliberately NOT touched by this PR") described the
codegen-boundary hardening epic's own scope; the wedge-loop epic that adds
Hop 7 is a LATER, separate change with a narrower, different footprint —
listed here rather than silently editing the historical claim above:

**Touched:**

- `core/contracts/agent-receipt.schema.json` — added `decision_kind:
  "local_approval"` (`$defs.LocalApprovalArtifact`), extended
  `receipt_signature.algorithm` with `"local-hmac-sha256-v1"`, and added
  `policy_decision.rule_kind: "pipeline_approval_gate"` — the FIRST and
  ONLY change this schema has received since it shipped; see
  `docs/AGENT_RECEIPT_SPEC.md` for the full trust-level disclosure this
  addition carries.
- `tools/receipt-verify/hmac_verify.py` (new file) and
  `tools/receipt-verify/checks.py` (extended, not rewritten) — the
  standalone verifier now handles `local_approval` receipts; `tools/
  receipt-emit/` (the GPG emit CLI) is UNCHANGED and still refuses
  anything Approval-shaped, by design.
- `orchestrator/mission_receipt.py` (new file), `orchestrator/pipeline.py`
  (`_emit_governed_mission_receipt()`, Hop 7, and a new opt-in
  `receipt_path` parameter on `run_pipeline()`), `orchestrator/__init__.py`
  (sys.path bootstrap extended to include `tools/receipt-verify/`).

**Deliberately NOT built here (disclosed follow-up):**

- Durable, cross-run `local_approval` receipt CHAIN persistence (atomic
  JSONL append, mirroring `tools/receipt-emit/`'s own chain discipline) —
  Hop 7 always emits a single genesis receipt to one file.
- The full idea -> route -> approve -> app-boots -> receipt-verify
  end-to-end proof, INCLUDING the rejection and mid-kill unhappy paths —
  this change's own tests prove the schema, the standalone verifier, and
  `run_pipeline()` emitting one verifiable receipt on a successful run;
  the complete DoD-level e2e (with its unhappy-path coverage) is a
  separate, follow-up piece of work.
- Wiring `tessctl gate`, `core/policy/policy.yaml`, or any other
  keystone/policy-owned path to require or consume a `local_approval`
  receipt — unchanged, same scope boundary the original PR already drew.
