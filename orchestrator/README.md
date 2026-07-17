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
> approval gate -> `spec_engine.codegen.generate_app()` as one call.
> `orchestrator.cli` is a thin manual-testing wrapper around it.

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
     │  .verify(approval) -> bool, checked BEFORE     gate" below
     │  anything downstream runs
     ▼
spec_engine.pipeline.finalize_spec()                REAL — build_spec()'s
     │                                               own existing gate
     │                                               (matching, approved
     │                                               Approval required)
     │                                               is untouched
     ▼
spec_engine.codegen.generate_app()                  REAL codegen — see
                                                      spec-engine/README.md
                                                      for exactly what's
                                                      generated vs. a
                                                      labeled stub per
                                                      module kind
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
accepts `approved_by` as a bare string. Before this PR, ANY caller could
write `record_approval(plan, approved_by="Xavier", approved=True)` and
get back a structurally-valid `Approval` — nothing verified that the
caller actually was Xavier. `spec_builder.build_spec()`'s gate (an
`Approval` object matching `plan_id` with `approved=True` is required) is
real and untouched by this PR, but it only checks that *an* approval
exists, never *who* it is attributed to.

`orchestrator.approval_gate.ApprovalGate` is a new, ADDITIONAL,
product-layer control in front of `finalize_spec()` in the wired
pipeline:

```python
class ApprovalGate(ABC):
    def request_approval(self, plan: Plan) -> Approval:
        """Block until a REAL, authenticated human decision is made.
        Must not forward an unauthenticated, caller-suppliable string
        into approved_by unexamined — authenticate through YOUR OWN
        mechanism first."""

    def verify(self, approval: Approval) -> bool:
        """Independently re-check that `approval` genuinely came from
        THIS gate's mechanism and was not tampered with. Must return
        False (never raise) on a forged/malformed input."""
```

`run_pipeline()` calls `request_approval()`, then calls `verify()` on
whatever it got back, and **raises `ApprovalAuthenticationError` and
never calls `finalize_spec()`/`generate_app()`** if verification fails —
this is what makes "codegen only runs after a valid, authenticated
approval" true for the wired flow, not just an aspiration.

### The shipped default: `LocalIdentityApprovalGate`

`orchestrator/identity.py` + `orchestrator/adapters/local_identity.py`.
On first use, generates a random 256-bit key at
`~/.tess-os/approval-identity/<os-username>.key` (`chmod 600`, enforced —
`verify()` and `request_approval()` both refuse a group/world-readable
key file). `request_approval()`:

1. Prints `plan.summary_for_approval` and prompts for a real terminal
   confirmation (`APPROVE` / `REJECT`) — `approved_by` is derived from
   `getpass.getuser()`, **never accepted as a parameter a caller could
   override**.
2. HMAC-SHA256-signs every identity-relevant field of the resulting
   record (`approval_id`, `plan_id`, `approved`, `approved_by`,
   `approved_at`, a fresh nonce) with that local key.
3. Embeds the signature evidence into `Approval.notes` as JSON (rides
   through, unchanged, into spec-engine's own existing
   `specs/approvals.jsonl` audit log via `finalize_spec()` ->
   `append_approval_note()` — no new log sink needed).

`verify()` independently recomputes the signature over the approval's
*actual* current field values and compares with `hmac.compare_digest`.
Tamper with `approved_by`, `approved`, `approved_at`, or `plan_id` after
signing — or hand-construct an `Approval` without ever going through the
gate — and `verify()` returns `False`. See
`tests/orchestrator/test_pipeline_adversarial.py` for the required proof
that a forged approval is rejected and codegen never runs.

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
is decided on. See `orchestrator/identity.py`'s module docstring for the
full statement.

**Also open:** `spec_engine.approval.record_approval()` itself is
unchanged — a caller who bypasses the orchestrator entirely and calls
`spec_engine.pipeline.finalize_spec()` directly still has the same
freedom spec-engine always documented itself as having (any caller can
attribute an approval to any string). That is spec-engine's own existing,
deliberate design boundary (see `approval.py`'s module docstring: "this
module intentionally contains NO logic that decides whether a plan is
good"), not something this PR silently closes at that layer. Making
`Approval.approved_by` structurally unforgeable for *every* caller of
spec-engine, not just ones going through this orchestrator, is the
natural next hardening step and is likewise left for Xavier to decide —
it would touch spec-engine's own tested contract (`tests/spec_engine/
test_approval.py`), which this PR deliberately leaves alone.

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
