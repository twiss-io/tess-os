# The Agent Receipt

> **Status: v1 spec + reference implementation, shipped in this repository.**
> This is a new, narrowly-scoped accountability envelope built entirely out of
> signing primitives this repository already implements and tests (verdict
> signing, hard-floor sign-off signing). It is not a claim of external
> adoption, a new trust anchor, a certification, or a production admission
> control — see "What this is not" below and `docs/STATUS.md` for the
> repository's overall claim boundary.

## The pitch, in one paragraph

An AI agent proposes an action. Policy decides whether that action needs
approval, and why. Someone — an AI verifier or a human operator, depending on
what kind of approval the policy requires — reviews it and cryptographically
signs their decision. The **Agent Receipt** is the portable object that
records all four of those facts together — what was proposed, why approval
was required, who approved it and how, and where it sits in an unbroken
signed history — so that a third party holding only the receipt file and a
public key can independently confirm the whole chain, without needing this
repository's policy file, mission tree, or gate engine at all. "Show me the
receipt" becomes something you can actually run, not just something you can
say.

## This formalizes what already exists — it does not invent new trust

Tess OS already ships and tests three independent signed-decision
primitives — two GPG-backed (System B), and, as of the wedge-loop epic, one
locally HMAC-backed (System A). The Agent Receipt does not replace any of
them; it wraps whichever one applies to a given approval, verbatim, and adds
the two things no primitive carries on its own: **why** approval was
required, and an **append-only link** to the receipt that came before it.

| Existing primitive | What it already proves | Where | Trust system |
|---|---|---|---|
| **Verdict signing** | A named AI verifier (Reid, Quinn, Cyra, Verity, Maialen, or Lysandra) reviewed specific content and cryptographically signed a disposition. | `core/contracts/verdict.schema.json` (`$defs.VerdictSignature`), `.tess/bin/tessctl`'s `_gate_verify_verdict_signature` / `verdict_canonical_bytes` / `tessctl verdict sign` / `tessctl verdict verify`. | **B** — GPG, asymmetric, publicly verifiable |
| **Hard-floor sign-off signing** | A human operator explicitly authorized a Rule-18 hard-floor action (credentials, money movement, destructive production data, client-external claims) that a verifier's verdict can never satisfy alone. | `.tess/gate/signoffs/<rule-id>.signoff.json`, checked by `_gate_validate_signoff` / `_gate_verify_signoff_signature` / `signoff_canonical_bytes` in `.tess/bin/tessctl`. | **B** — GPG, asymmetric, publicly verifiable |
| **Local approval signing** (wedge-loop epic addition) | `orchestrator.pipeline.run_pipeline()`'s Hop-3 `ApprovalGate` recorded a decision, content-hash-bound to the `Plan` it approved, HMAC-signed with one OS account's local approval-identity key, and independently re-verified TWICE (`ApprovalGate.verify()`, then again at the `spec_engine.spec_builder.build_spec()` codegen boundary) before any code was generated. | `spec_engine.types.Approval`, `spec_engine.gate_identity.py` / `gate_approval.py`, `orchestrator/adapters/local_identity.py`. | **A** — local, symmetric HMAC-SHA256, verifiable only by a holder of the same secret key |

The two GPG-backed primitives use the identical trust model: an isolated,
throwaway GNUPGHOME per check, an exact 40-hex-character fingerprint match
(no short-ID or proximity matching), rejection of a cryptographically valid
signature made by a key gpg currently reports as expired or revoked, and
canonicalization as compact, key-sorted JSON with the signature field itself
excluded from what it signs over. The Agent Receipt reuses this exact model
for a GPG-backed envelope-level signature (see "Canonicalization" below).
The local approval primitive uses a DIFFERENT, deliberately weaker model —
HMAC-SHA256 with a single OS account's local key, no public half, verifiable
only by an independent holder of the same secret — and the Agent Receipt's
own envelope signature switches to the matching HMAC scheme when it wraps
one (`receipt_signature.algorithm: "local-hmac-sha256-v1"`). No THIRD
cryptographic scheme is introduced anywhere in this spec; the two crypto
primitives (GPG, HMAC-SHA256) are both ones this repository already shipped
and tested before this envelope existed.

## ★ Trust levels are not interchangeable — read this before treating any decision_kind as equivalent to another

A `local_approval` receipt (System A) is **not** a lower-ceremony version of
a `verdict`/`signoff` receipt (System B) — it is different in kind, and
structurally weaker evidence:

- **Publicly verifiable vs. secret-bound.** A `verdict`/`signoff` receipt
  verifies from a public key any third party can safely hold. A
  `local_approval` receipt verifies ONLY with the exact secret key that
  signed it — a party able to verify one can also FORGE a new one under the
  same identity, which is never true of GPG verification.
- **A named human reviewer vs. a local process.** A `verdict` proves a named
  AI verifier reviewed specific content; a `signoff` proves a named human
  operator authorized a hard floor. A `local_approval` proves only that
  *some process holding one OS account's key* recorded the decision — see
  `spec_engine.gate_identity`'s own "Honest limitation" section for exactly
  what this does and does not prove about who was at the keyboard.
- **Never a hard-floor substitute.** guardrails.md Rule 18 already forbids a
  bare verdict from clearing a hard floor; a `local_approval` is weaker
  still and is EQUALLY forbidden — see `policy_decision.rule_kind:
  hard_floor_rule`'s pairing rule below, unchanged by this addition.
- **Structurally distinct, never blended.** The schema, `checks.py`, and
  `hmac_verify.py` all enforce this as more than a naming convention: a
  dedicated `decision_kind` value, a dedicated `receipt_signature.algorithm`
  value, and a dedicated `policy_decision.rule_kind` value
  (`pipeline_approval_gate`) that can ONLY pair with `local_approval` — see
  `core/contracts/agent-receipt.schema.json`'s `$defs.LocalApprovalArtifact`
  and its top-level `allOf` trust-pairing rules. A chain may freely mix
  receipts of different `decision_kind` values (e.g. a `local_approval`
  codegen-run receipt followed later by a `verdict`-backed review receipt),
  but a reader must always check each link's own `decision_kind` — never
  assume "it's in a chain of receipts" implies uniform trust strength.

## Distinct from the "proposed execution receipt"

`docs/MEMORY_AND_ORCHESTRATION_CONTRACT.md` already names a "receipt" concept
— a **proposed, `receipt_version: "proposed-v1"`, explicitly unimplemented**
future runtime-evidence format for a multi-agent task-graph/adapter runtime,
with "receipt signing, timestamping, provenance attestation, storage
authority, and retention" listed as **deferred decisions**. That document's
receipt and this spec's Agent Receipt are two different things:

- The proposed-v1 receipt is about *adapter/work-unit execution evidence* for
  a task-graph runtime that does not exist yet.
- The Agent Receipt in this spec is about *the propose -> approve -> sign
  accountability event* for the verdict-signing and hard-floor sign-off
  machinery that **already ships and is tested today**.

`receipt_schema` in this spec's own object is therefore its own namespaced
version string (`tess-os.agent-receipt/1`), never `proposed-v1`, specifically
so the two are never confused in a mixed corpus. If a future task-graph
runtime is built, it may reasonably choose to emit an Agent Receipt as (or
alongside) its own execution evidence — but that is a future integration
decision, not something this spec claims today.

## Object shape

Authoritative machine-checkable form:
[`core/contracts/agent-receipt.schema.json`](../core/contracts/agent-receipt.schema.json).
This schema is deliberately NOT wired into `tessctl validate`'s
CONTRACT-TYPE choices (`{brief, crew-plan, ledger-event, mission, policy,
retry, return-manifest, task, verdict}` — no `agent-receipt`; see "What
this is not" below, "Not new GPG signing infrastructure... no change to
`.tess/bin/tessctl`"), so there is no `tessctl validate agent-receipt`
command. Validate an instance against it with the real, standalone
verifier instead:
`tools/receipt-verify/receipt_verify.py verify path/to/receipt.json
--trust NAME FINGERPRINT KEY_FILE [--trust ...]` (structural + signature
verification together — see "Verification algorithm" below), or, for
structural-only checking against this schema directly (the same minimal
draft-07 subset `tessctl validate` itself uses), `tests/
test_agent_receipt_schema.py` exercises `schema_validate()` against it
programmatically. What follows is the same shape in prose, with the
doctrine each field is grounded in.

```jsonc
{
  "receipt_schema": "tess-os.agent-receipt/1",
  "receipt_id": "<uuid4 hex — same convention as tessctl's own trace event_id>",
  "issued_at": "<UTC ISO-8601 timestamp>",

  "proposed_action": {
    "actor": "<the agent/persona who proposed the action>",
    "summary": "<what was proposed, in plain language>",
    "repo": "<owner/repo, optional>",
    "ref": "<git ref / commit / PR, optional>",
    "paths": ["<repo-relative paths touched, optional>"]
  },

  "policy_decision": {
    "source": "core/policy/policy.yaml",
    "rule_id": "<the policy.schema.json rule that fired>",
    "rule_kind": "path_rule | hard_floor_rule | pipeline_approval_gate",
    "classification": ["prod_touching", "..."],   // path_rule only
    "category": "money_movement",                  // hard_floor_rule only
    "description": "<the rule's own prose, copied verbatim>"
  },

  "decision_kind": "verdict | signoff | local_approval",
  "decision": { /* the embedded, ALREADY-SIGNED verdict, sign-off, or local approval, verbatim */ },

  "chain": {
    "sequence": 0,
    "prev_receipt_hash": "GENESIS | <sha256 of the previous receipt's full canonical bytes>",
    "journal_ref": "<optional pointer into an existing trace/journal JSONL file>"
  },

  "receipt_signature": {
    "algorithm": "gpg-detached-armor | local-hmac-sha256-v1",
    "signed_by": "<the SAME identity that signed `decision`>",
    "signed_content_sha256": "<sha256 of the receipt's signing-canonical bytes>",
    "signature_armored": "<ASCII-armored GPG detached signature — gpg-detached-armor only>",
    "signature_hex": "<raw HMAC-SHA256 hex digest — local-hmac-sha256-v1 only>"
  }
}
```

`decision_kind: local_approval` (wedge-loop epic addition) embeds a
`$defs.LocalApprovalArtifact` — the exact shape of a real
`spec_engine.types.Approval`:

```jsonc
{
  "approval_id": "appr-<12 hex chars>",
  "plan_id": "<the approved Plan's plan_id>",
  "approved": true,          // a receipt can only represent a GRANTED approval
  "approved_by": "local:<os-username>#<16-hex local key fingerprint>",
  "approved_at": "<UTC ISO-8601 timestamp>",
  "notes": "<JSON-encoded string embedding the HMAC evidence — see spec_engine.gate_approval.sign_local_approval(); kept opaque at the schema level, parsed at the lint level (tools/receipt-verify/hmac_verify.py)>"
}
```

`policy_decision.rule_kind: pipeline_approval_gate` (wedge-loop epic
addition) is **not** a `core/policy/policy.yaml` rule at all — it represents
`orchestrator.pipeline.run_pipeline()`'s own Hop-3 `ApprovalGate` contract
(`orchestrator/approval_gate.py`), a product-layer control this
repository's ship-gate never consults. It can ONLY pair with
`decision_kind: local_approval` — see below.

Doctrine-grounded rules the schema encodes structurally (see the schema
file's own `allOf`/`if`/`then`/`else` conditionals):

1. `policy_decision.rule_kind: path_rule` requires `classification`;
   `hard_floor_rule` requires `category`; `pipeline_approval_gate` requires
   neither — mirroring `policy.schema.json`'s own `PathRule`/`HardFloorRule`
   split for the first two, and reflecting that the third isn't a
   `policy.yaml` instance at all.
2. `decision_kind: verdict` requires `decision` to independently validate
   against the real `verdict.schema.json` (referenced, never duplicated, so
   the two can never drift apart); `decision_kind: signoff` requires it to
   match this schema's own `$defs.SignoffArtifact` (the sign-off shape
   `_gate_validate_signoff` already checks at runtime); `decision_kind:
   local_approval` requires it to match `$defs.LocalApprovalArtifact` (the
   real `spec_engine.types.Approval` shape) — the sign-off and local-approval
   $defs are each that shape's first machine-checkable JSON Schema form.
3. `chain.sequence: 0` requires `prev_receipt_hash: "GENESIS"`; any other
   sequence requires a 64-hex-char sha256 digest.
4. **TRUST-LEVEL PAIRING** (wedge-loop epic addition): `decision_kind:
   verdict`/`signoff` requires `receipt_signature.algorithm:
   "gpg-detached-armor"`; `decision_kind: local_approval` requires
   `receipt_signature.algorithm: "local-hmac-sha256-v1"`. A System A
   decision can never be wrapped in a System B-looking envelope, or vice
   versa — this is checked structurally, not only by lint, precisely so the
   two trust levels can never be silently blurred.

One rule the schema **cannot** express (no `$data`-style cross-field
reference in this validator's supported subset — see
`core/contracts/README.md`'s own "Schema vs. lint" section for why that split
already exists in this repository) is enforced by the verifier tool instead,
as an explicit lint-level check: **`receipt_signature.signed_by` must equal
`decision`'s own identity** (`decision.verifier` for a verdict,
`decision.authorized_by` for a sign-off, `decision.approved_by` for a local
approval). A receipt whose envelope is signed by someone other than the
identity that signed the decision it wraps is rejected.

A second rule enforced the same way: **guardrails.md Rule 18 pairing** — a
`hard_floor_rule` policy decision must be backed by a `signoff`, never a
`verdict` and never a `local_approval` (a verifier's approval — or a local,
single-OS-account HMAC approval, weaker still — can never satisfy a hard
floor alone); a `path_rule` policy decision must be backed by a `verdict`;
a `pipeline_approval_gate` policy decision must be backed by a
`local_approval`.

## Canonicalization

Two distinct canonical forms, both compact (no whitespace), key-sorted JSON —
identical style to `verdict_canonical_bytes` / `signoff_canonical_bytes` in
`.tess/bin/tessctl`, and used for the ENVELOPE regardless of which
`decision_kind`/algorithm the receipt carries:

- **Signing-canonical bytes** — the full receipt dict **minus**
  `receipt_signature` itself (a receipt cannot sign over its own signature).
  `receipt_signature.signed_content_sha256` is the sha256 hex digest of this
  form; `receipt_signature.signature_armored` (GPG) or `signature_hex`
  (local HMAC, wedge-loop epic addition) is a signature over these exact
  bytes. This is nothing new for the GPG cases; it is exactly
  `verdict_canonical_bytes`/`signoff_canonical_bytes` as already shipped —
  the local-HMAC case reuses the identical byte form, only the crypto
  operation over it differs (`hmac.new(key, bytes, sha256).hexdigest()`
  instead of `gpg --detach-sign`).
- **Full content hash** — sha256 hex digest of the **entire, already-signed**
  receipt (every key, including `receipt_signature`). This is the value a
  *later* receipt in the same chain records as its own
  `chain.prev_receipt_hash`. Using the full, post-signature bytes (rather
  than the signing-canonical bytes) means a later receipt's chain link binds
  the exact record that was published, signature included — not just its
  pre-signature content.

Reference implementation of both:
[`tools/receipt-verify/canonical.py`](../tools/receipt-verify/canonical.py).

**A THIRD, SEPARATE canonicalization exists one level down, for the
embedded `local_approval` decision only** — the pre-existing
`spec_engine.gate_identity.canonical_payload()` / `sign_payload()` shape
(`{approval_id, plan_id, content_hash, approved, approved_by, approved_at,
nonce}`, `ensure_ascii` left at Python's default `True`), unrelated to and
never mixed with the envelope's own `canonical.py` convention (which sets
`ensure_ascii=False`). This is deliberate: the embedded decision's HMAC
evidence is `spec_engine.gate_approval.sign_local_approval()`'s
ALREADY-EXISTING signature, produced before this envelope ever wraps it — it
is reused verbatim (inside `decision.notes`), never re-derived or
re-canonicalized under this spec's own scheme.
[`tools/receipt-verify/hmac_verify.py`](../tools/receipt-verify/hmac_verify.py)'s
`local_approval_signing_bytes()` is the standalone, independent
reimplementation of that pre-existing shape used to re-verify it.

## The chain

A single receipt is evidence of one approval. A **chain** of receipts —
genesis receipt at `sequence: 0` with `prev_receipt_hash: "GENESIS"`, each
subsequent receipt recording the full content hash of the one before it — is
evidence of an unbroken accountability history: altering, deleting, or
reordering any earlier receipt breaks the recorded hash in every receipt
issued after it, the same tamper-evidence property a Certificate Transparency
log or a git commit's parent hash already gives you, applied here to
approval records instead of certificates or commits.

This is deliberately **not** a new ledger. `chain.journal_ref` is an optional
pointer into the append-only trace/journal JSONL files this repository
already writes (`missions/<id>/trace.jsonl`, `.tess/trace/runs/<run_id>.jsonl`
— see `_trace_append_event` in `.tess/bin/tessctl` and
`docs/OBSERVABILITY.md`). A receipt chain may be stored as its own JSONL file
(one receipt per line, in sequence order — see
`tools/receipt-verify/receipt_verify.py verify-chain`) or referenced from an
existing trace log; either way, per
`docs/MEMORY_AND_ORCHESTRATION_CONTRACT.md`'s invariant 5, the journal
reference itself carries no authority — it is a pointer, not a substitute for
the cryptographic checks.

## Verification algorithm

This is exactly what
[`tools/receipt-verify/checks.py`](../tools/receipt-verify/checks.py)'s
`verify_receipt()` runs, in this order (cheap structural checks before any
GPG subprocess or HMAC comparison, mirroring `.tess/bin/tessctl`'s own "fail
fast, expensive check last" discipline):

1. **Shape** — every required field is present; `receipt_schema` matches;
   `decision_kind` is a recognized value (`verdict`, `signoff`, or
   `local_approval`).
2. **Decision shape** — the embedded `decision` carries every field its kind
   requires. A `verdict` decision's `disposition` must be `APPROVE`; a
   `local_approval` decision's `approved` must be `true` (both: a receipt
   represents a *granted* approval, never a `BLOCK`/rejected one). A
   `verdict`/`signoff` decision must carry its own `signature` block; a
   `local_approval` decision must carry a `notes` string with a
   structurally valid embedded HMAC `auth` block instead (see
   `hmac_verify.parse_local_approval_auth`).
3. **Policy/decision pairing** — `hard_floor_rule` implies `signoff`;
   `path_rule` implies `verdict`; `pipeline_approval_gate` implies
   `local_approval` (guardrails.md Rule 18, extended to System A).
4. **Identity consistency** — `receipt_signature.signed_by` equals
   `decision`'s own identity field (`verifier`, `authorized_by`, or
   `approved_by`, depending on `decision_kind`).
5. **Decision signature/evidence** — for `verdict`/`signoff`:
   `decision.signature.signed_content_sha256` matches the decision's
   current signing-canonical bytes (tamper check, before the GPG call),
   then the GPG signature verifies against the caller-supplied,
   fingerprint-pinned public key for that identity. For `local_approval`:
   the embedded `auth.mechanism` is the recognized value, `auth.
   identity_fingerprint` matches the caller-pinned 16-hex local
   fingerprint EXACTLY, and the HMAC-SHA256 signature verifies against the
   caller-supplied SECRET key for that identity (`hmac_verify.
   verify_local_approval_decision` — no separate signed_content_sha256
   pre-check needed here; the HMAC comparison itself is the tamper check).
6. **Envelope signature** — the same content-hash-then-crypto check for
   `receipt_signature` itself, over the receipt's own signing-canonical
   bytes — GPG for `algorithm: "gpg-detached-armor"`, HMAC-SHA256 (against
   the caller-supplied secret key) for `algorithm: "local-hmac-sha256-v1"`.
7. **Chain link** — `sequence: 0` requires `prev_receipt_hash: "GENESIS"`
   and no supplied previous receipt; any other sequence requires a supplied
   previous receipt whose full content hash matches `prev_receipt_hash`
   exactly, and whose own `sequence` is one less than this receipt's. A
   chain may freely mix `decision_kind` values receipt-by-receipt — the
   chain-link check itself does not care — but see "★ Trust levels are not
   interchangeable" above for why a reader must still check each link's own
   `decision_kind`.

Every step fails closed: a missing field, an unregistered identity, a
mismatched fingerprint (GPG's 40-hex or local HMAC's 16-hex — never
confusable with each other, see `hmac_verify.LOCAL_FINGERPRINT_RE`), a stale
content hash, an expired/revoked GPG signing key, or a broken chain link is
reported as an explicit reason, never silently skipped.

★ **`local_approval` verification has a disclosed non-replay scope.** A PASS
proves authenticity + integrity (this exact content was HMAC-signed by a
holder of this exact key) — the same scope GPG verification has. It does
NOT prove the embedded approval was never replayed across two separate
process runs; `spec_engine.gate_approval`'s own nonce-consumption tracker is
disclosed, in that module's own docstring, as in-process/in-memory only.
`tools/receipt-verify/hmac_verify.py` is not, and does not claim to be, a
replay/freshness check.

## Producing a receipt

There is no `tessctl receipt` command in this repository (see "What this
is not" — signing infrastructure for this new envelope is deliberately
scoped out of `.tess/bin/tessctl` itself). Two SEPARATE producers exist,
one per trust system, and neither wraps the other:

**System B (GPG — `verdict`/`signoff`):**
[`tools/receipt-emit/`](../tools/receipt-emit/README.md) — a standalone
CLI, separate from `tessctl`, that takes an already-produced `tessctl
verdict sign` or hard-floor sign-off artifact, builds the
`proposed_action`/`policy_decision`/`chain` fields (copying the fired
`core/policy/policy.yaml` rule verbatim), signs the receipt's own
signing-canonical bytes with the SAME identity's key (a plain `gpg
--detach-sign --armor` invocation), atomically appends it to a chain file,
and self-verifies the result against `tools/receipt-verify` before
committing — refusing, with nothing written, on a non-`APPROVE` verdict, an
incomplete sign-off, an identity mismatch, or a failed self-verify. It
attaches ONLY to the GPG verdict/sign-off loop — by design, it still
structurally refuses anything shaped like a `local_approval` decision (see
`assemble.infer_decision_kind`, unchanged by the wedge-loop epic) — and
prints the same "genuinely signed, not trust-anchored" honest label every
successful emit — see that tool's own README for its exact fail-closed
behavior. `examples/receipt-demo/` still exists alongside it as the
illustrative, ephemeral-key, end-to-end walkthrough (never real keys, never
committed output); `tools/receipt-emit/` is the tool an operator would
actually run against a real (if still unregistered) key.

**System A (local HMAC — `local_approval`, wedge-loop epic addition):**
[`orchestrator/mission_receipt.py`](../orchestrator/mission_receipt.py) —
NOT a standalone CLI, wired directly into
`orchestrator.pipeline.run_pipeline()` as an optional, opt-in Hop 7 (off
unless a caller supplies `receipt_path`). Assembles the receipt embedding
the SAME `spec_engine.types.Approval` Hop 3/4 already authenticated and
independently re-verified twice, and HMAC-signs the envelope with this
install's real local approval-identity key (`spec_engine.gate_identity`) —
never the demo's ephemeral keys. Deliberately simpler than `tools/
receipt-emit/`: it always writes a single genesis (`sequence: 0`) receipt
to one JSON file, not an atomically-appended JSONL chain — durable,
cross-run chain persistence for `local_approval` receipts is a disclosed,
scoped follow-up, not built here. The full idea→route→approve→boots→
receipt-verify (plus rejection/mid-kill unhappy-path) end-to-end proof
DoD B.9 asks for now EXISTS and passes:
[`tests/orchestrator/test_e2e_wedge_loop.py`](../tests/orchestrator/test_e2e_wedge_loop.py),
driven entirely through `run_pipeline()`, Node hard-required (not
silently skipped) in CI — see `orchestrator/README.md`'s "Wedge-loop
epic addition" section. A receipt-emission failure is caught and
downgraded to a non-fatal warning — it can never un-complete an
already-finished mission.

## Third-party verification

```bash
# System B (verdict/signoff) — KEYFILE is a GPG PUBLIC key, safe to share:
python3 tools/receipt-verify/receipt_verify.py verify path/to/receipt.json \
  --trust Reid <PINNED_FINGERPRINT> path/to/reid-public-key.asc

# System A (local_approval, wedge-loop epic addition) — KEYFILE is the SAME
# SECRET local approval-identity key that produced the signature; treat it
# like any other credential, never publish it:
python3 tools/receipt-verify/receipt_verify.py verify path/to/receipt.json \
  --trust "local:xavier#0123456789abcdef" 0123456789abcdef \
  ~/.tess-os/approval-identity/xavier.key
```

The caller supplies their own trusted identity/fingerprint/key mapping
directly on the command line — never this repository's
`core/policy/policy.yaml` — because a third party verifying a receipt has no
reason to hold this project's policy file at all. ★ `--trust`'s KEYFILE
means two different things depending on the receipt's `decision_kind` — a
GPG public key for `verdict`/`signoff`, the local HMAC secret key for
`local_approval` — see
[`tools/receipt-verify/README.md`](../tools/receipt-verify/README.md) and
[`tools/receipt-verify/hmac_verify.py`](../tools/receipt-verify/hmac_verify.py)'s
own module docstring for the full disclosure before verifying a
`local_approval` receipt, including whole-chain verification.

## Why an open spec

The schema (`core/contracts/agent-receipt.schema.json`) and this document are
plain JSON Schema and Markdown, covered by this repository's Apache-2.0
license like everything else in it (see `../LICENSE`, `../NOTICE`). Nothing
about the object shape or the verification algorithm depends on Tess OS
internals a different project couldn't equally implement against its own
signed-decision primitives — the standalone verifier in
`tools/receipt-verify/` is deliberately dependency-free precisely so it can
be copied into, or reimplemented against, another project without adopting
the rest of this framework. This is a v1 proposal and a working reference
implementation, not a claim that any other project has adopted it yet.

## What this is not

- **Not a new trust anchor.** An Agent Receipt is only as trustworthy as the
  key that signed it. This repository ships with empty `verifier_keys` /
  `signoff_keys` registries by design (`conductor/verdict-signing.md`); an
  Agent Receipt signed by a key nobody has independently agreed to trust
  proves nothing on its own. See `docs/TRUST_BOOTSTRAP_SECURITY_DESIGN.md`.
- **Not a gate, and not the ship-gate's replacement.** `tessctl gate` decides
  whether a change may proceed, using `covers_paths`/`artifact_hashes`
  binding a verdict to exact reviewed content. An Agent Receipt does not
  currently plug into that gate check — it is a portable RECORD of an
  approval that already happened (or, for a hard floor, of a sign-off that
  already happened), consumed by a human or an external auditor, not (yet)
  by `tessctl gate` itself. Wiring the gate to also require/emit Agent
  Receipts is a natural follow-on, out of scope for this change.
- **Not new GPG signing infrastructure.** There is no new GPG key type, no
  new `tessctl` subcommand, and no change to `.tess/bin/tessctl`,
  `core/policy/policy.yaml`, or any file this repository's own
  `tess-os-security-tier-doctrine` policy rule already protects — including
  `tools/receipt-emit/` (the emit CLI, untouched by the wedge-loop epic): it
  reads `core/policy/policy.yaml` READ-ONLY, signs with a key the operator
  already holds, and is a standalone tool alongside `tessctl`, not a change
  to it. Verdict/sign-off signing and their trust boundary are unchanged.
  See `conductor/verdict-signing.md`. The wedge-loop epic's ONE new signing
  primitive (`decision_kind: local_approval`, `receipt_signature.algorithm:
  "local-hmac-sha256-v1"`) reuses `spec_engine.gate_identity`'s ALREADY-
  EXISTING local HMAC mechanism — no new key type there either, just this
  envelope's first use of an existing one.
- **Not a claim that `local_approval` is a substitute for `verdict`/
  `signoff`.** See "★ Trust levels are not interchangeable" above — a
  `local_approval` receipt is weaker evidence by design, never a drop-in
  replacement for a GPG-backed decision, and never satisfies a hard floor.
- **Not a durable, multi-run `local_approval` receipt chain (yet).**
  `orchestrator/mission_receipt.py` always emits a single genesis receipt
  per `run_pipeline()` call, to one JSON file — atomic, cross-run
  JSONL-chain persistence for `local_approval` receipts (mirroring `tools/
  receipt-emit/`'s own chain-append discipline for GPG receipts) is still
  a disclosed, scoped follow-up. The full idea→route→approve→boots→
  receipt-verify (+ rejection, + mid-kill unhappy paths) end-to-end proof
  is no longer a follow-up — see `tests/orchestrator/test_e2e_wedge_loop.py`
  and `orchestrator/README.md`'s "★ DoD B.9" callout.
- **Not a claim of external adoption.** "Open spec" means the license and the
  design allow adoption; it does not mean any other project uses this format
  today.
- **Not a production admission control.** Like every other capability in this
  repository, see `docs/STATUS.md`'s claim-label table before deciding
  whether this fits a particular workflow.

## Reference material

| Artifact | Path |
|---|---|
| JSON Schema | `core/contracts/agent-receipt.schema.json` |
| Standalone verifier | `tools/receipt-verify/` (`gpg_verify.py` — System B; `hmac_verify.py` — System A, wedge-loop epic addition) |
| Emit CLI (produces a real GPG-backed receipt from an already-signed verdict/signoff — System B only) | `tools/receipt-emit/` |
| Hop 7 — optional, opt-in `local_approval` receipt emission wired into `run_pipeline()` (System A, wedge-loop epic addition) | `orchestrator/mission_receipt.py`, `orchestrator/pipeline.py` |
| Runnable demo (test keys only, System B) | `examples/receipt-demo/` |
| Contract tests | `tests/test_agent_receipt_schema.py`, `tests/test_receipt_verify_cli.py`, `tests/test_receipt_verify_semantics.py`, `tests/test_receipt_emit_cli.py`, `tests/test_receipt_emit_semantics.py`, `tests/test_hmac_verify.py`, `tests/orchestrator/test_receipt_integration.py`, `tests/orchestrator/test_mission_receipt.py` |
| Existing verdict-signing doctrine this builds on | `conductor/verdict-signing.md` |
| Existing local approval-identity mechanism this builds on (System A) | `spec_engine.gate_identity`, `spec_engine.gate_approval`, `orchestrator/adapters/local_identity.py` |
| Existing policy/rule contract this builds on | `core/contracts/policy.schema.json`, `core/policy/policy.yaml` |
| Disambiguation from the unrelated, deferred future receipt proposal | `docs/MEMORY_AND_ORCHESTRATION_CONTRACT.md` |
| Exportable auditor pack that can embed this receipt for a scope | `docs/AUDIT_PACK_SPEC.md` (`tessctl audit export --receipt <path>`) |
