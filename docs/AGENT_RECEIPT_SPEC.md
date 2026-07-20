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

Tess OS already ships and tests two independent signed-decision primitives.
The Agent Receipt does not replace either one; it wraps whichever one applies
to a given approval, verbatim, and adds the two things neither primitive
carries on its own: **why** approval was required, and an **append-only
link** to the receipt that came before it.

| Existing primitive | What it already proves | Where |
|---|---|---|
| **Verdict signing** | A named AI verifier (Reid, Quinn, Cyra, Verity, Maialen, or Lysandra) reviewed specific content and cryptographically signed a disposition. | `core/contracts/verdict.schema.json` (`$defs.VerdictSignature`), `.tess/bin/tessctl`'s `_gate_verify_verdict_signature` / `verdict_canonical_bytes` / `tessctl verdict sign` / `tessctl verdict verify`. |
| **Hard-floor sign-off signing** | A human operator explicitly authorized a Rule-18 hard-floor action (credentials, money movement, destructive production data, client-external claims) that a verifier's verdict can never satisfy alone. | `.tess/gate/signoffs/<rule-id>.signoff.json`, checked by `_gate_validate_signoff` / `_gate_verify_signoff_signature` / `signoff_canonical_bytes` in `.tess/bin/tessctl`. |

Both already use the identical trust model: an isolated, throwaway GNUPGHOME
per check, an exact 40-hex-character fingerprint match (no short-ID or
proximity matching), rejection of a cryptographically valid signature made by
a key gpg currently reports as expired or revoked, and canonicalization as
compact, key-sorted JSON with the signature field itself excluded from what
it signs over. The Agent Receipt reuses this exact model for its own,
additional envelope-level signature (see "Canonicalization" below) — no new
cryptographic scheme is introduced anywhere in this spec.

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
Validate an instance against it (inside a full Tess OS checkout) with
`tessctl validate agent-receipt path/to/receipt.json`. What follows is the
same shape in prose, with the doctrine each field is grounded in.

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
    "rule_kind": "path_rule | hard_floor_rule",
    "classification": ["prod_touching", "..."],   // path_rule only
    "category": "money_movement",                  // hard_floor_rule only
    "description": "<the rule's own prose, copied verbatim>"
  },

  "decision_kind": "verdict | signoff",
  "decision": { /* the embedded, ALREADY-SIGNED verdict or sign-off, verbatim */ },

  "chain": {
    "sequence": 0,
    "prev_receipt_hash": "GENESIS | <sha256 of the previous receipt's full canonical bytes>",
    "journal_ref": "<optional pointer into an existing trace/journal JSONL file>"
  },

  "receipt_signature": {
    "algorithm": "gpg-detached-armor",
    "signed_by": "<the SAME identity that signed `decision`>",
    "signed_content_sha256": "<sha256 of the receipt's signing-canonical bytes>",
    "signature_armored": "<ASCII-armored GPG detached signature>"
  }
}
```

Three doctrine-grounded rules the schema encodes structurally (see the
schema file's own `if`/`then`/`else` conditionals):

1. `policy_decision.rule_kind: path_rule` requires `classification`;
   `hard_floor_rule` requires `category` — mirroring
   `policy.schema.json`'s own `PathRule`/`HardFloorRule` split.
2. `decision_kind: verdict` requires `decision` to independently validate
   against the real `verdict.schema.json` (referenced, never duplicated, so
   the two can never drift apart); `decision_kind: signoff` requires it to
   match this schema's own `$defs.SignoffArtifact` (the sign-off shape
   `_gate_validate_signoff` already checks at runtime — this is its first
   machine-checkable JSON Schema form).
3. `chain.sequence: 0` requires `prev_receipt_hash: "GENESIS"`; any other
   sequence requires a 64-hex-char sha256 digest.

One rule the schema **cannot** express (no `$data`-style cross-field
reference in this validator's supported subset — see
`core/contracts/README.md`'s own "Schema vs. lint" section for why that split
already exists in this repository) is enforced by the verifier tool instead,
as an explicit lint-level check: **`receipt_signature.signed_by` must equal
`decision`'s own identity** (`decision.verifier` for a verdict,
`decision.authorized_by` for a sign-off). A receipt whose envelope is signed
by someone other than the person who signed the decision it wraps is
rejected.

A second rule enforced the same way: **guardrails.md Rule 18 pairing** — a
`hard_floor_rule` policy decision must be backed by a `signoff`, never a
`verdict` (a verifier's approval can never satisfy a hard floor alone); a
`path_rule` policy decision must be backed by a `verdict`.

## Canonicalization

Two distinct canonical forms, both compact (no whitespace), key-sorted JSON —
identical style to `verdict_canonical_bytes` / `signoff_canonical_bytes` in
`.tess/bin/tessctl`:

- **Signing-canonical bytes** — the full receipt dict **minus**
  `receipt_signature` itself (a receipt cannot sign over its own signature).
  `receipt_signature.signed_content_sha256` is the sha256 hex digest of this
  form; `receipt_signature.signature_armored` is a GPG detached signature
  over these exact bytes. The embedded `decision`'s own signature uses the
  identical pattern one level down (the decision object minus its own
  `signature` key) — this is nothing new; it is exactly
  `verdict_canonical_bytes`/`signoff_canonical_bytes` as already shipped.
- **Full content hash** — sha256 hex digest of the **entire, already-signed**
  receipt (every key, including `receipt_signature`). This is the value a
  *later* receipt in the same chain records as its own
  `chain.prev_receipt_hash`. Using the full, post-signature bytes (rather
  than the signing-canonical bytes) means a later receipt's chain link binds
  the exact record that was published, signature included — not just its
  pre-signature content.

Reference implementation of both:
[`tools/receipt-verify/canonical.py`](../tools/receipt-verify/canonical.py).

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
GPG subprocess, mirroring `.tess/bin/tessctl`'s own "fail fast, expensive
check last" discipline):

1. **Shape** — every required field is present; `receipt_schema` matches;
   `decision_kind` is a recognized value.
2. **Decision shape** — the embedded `decision` carries every field its kind
   requires, including its own `signature` block; a `verdict` decision's
   `disposition` must be `APPROVE` (a receipt represents a *granted*
   approval — a `BLOCK` verdict is not something a receipt claims cleared
   anything).
3. **Policy/decision pairing** — `hard_floor_rule` implies `signoff`;
   `path_rule` implies `verdict` (guardrails.md Rule 18).
4. **Identity consistency** — `receipt_signature.signed_by` equals
   `decision`'s own identity field.
5. **Decision signature** — `decision.signature.signed_content_sha256`
   matches the decision's current signing-canonical bytes (tamper check,
   before the GPG call); then the GPG signature verifies against the
   caller-supplied, fingerprint-pinned public key for that identity.
6. **Envelope signature** — the same two-step check
   (content-hash-then-GPG) for `receipt_signature` itself, over the
   receipt's own signing-canonical bytes.
7. **Chain link** — `sequence: 0` requires `prev_receipt_hash: "GENESIS"`
   and no supplied previous receipt; any other sequence requires a supplied
   previous receipt whose full content hash matches `prev_receipt_hash`
   exactly, and whose own `sequence` is one less than this receipt's.

Every step fails closed: a missing field, an unregistered identity, a
mismatched fingerprint, a stale content hash, an expired/revoked signing key,
or a broken chain link is reported as an explicit reason, never silently
skipped.

## Producing a receipt

There is no `tessctl receipt sign` command in this repository (see "What
this is not" — signing infrastructure for this new envelope is deliberately
scoped out of this change). Producing a receipt today means: build the
`proposed_action`/`policy_decision`/`chain` fields, embed the
already-produced `tessctl verdict sign` or hard-floor sign-off artifact
verbatim as `decision`, then sign the receipt's own signing-canonical bytes
with the SAME identity's key using a plain `gpg --detach-sign --armor`
invocation (see the reference recipe in
[`examples/receipt-demo/`](../examples/receipt-demo/README.md), which runs
this exact sequence end to end with **test-only, ephemeral GPG keys never
committed to this repository**).

## Third-party verification

```bash
python3 tools/receipt-verify/receipt_verify.py verify path/to/receipt.json \
  --trust Reid <PINNED_FINGERPRINT> path/to/reid-public-key.asc
```

The caller supplies their own trusted identity/fingerprint/public-key
mapping directly on the command line — never this repository's
`core/policy/policy.yaml` — because a third party verifying a receipt has no
reason to hold this project's policy file at all. See
[`tools/receipt-verify/README.md`](../tools/receipt-verify/README.md) for
full usage, including whole-chain verification.

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
- **Not new signing infrastructure.** There is no new key type, no new
  `tessctl` subcommand, and no change to `.tess/bin/tessctl`,
  `core/policy/policy.yaml`, or any file this repository's own
  `tess-os-security-tier-doctrine` policy rule already protects. This change
  adds a new, independent contract + tool + docs + example only.
  Verdict/sign-off signing and their trust boundary are unchanged.
  See `conductor/verdict-signing.md`.
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
| Standalone verifier | `tools/receipt-verify/` |
| Runnable demo (test keys only) | `examples/receipt-demo/` |
| Contract tests | `tests/test_agent_receipt_schema.py`, `tests/test_receipt_verify_tool.py` |
| Existing verdict-signing doctrine this builds on | `conductor/verdict-signing.md` |
| Existing policy/rule contract this builds on | `core/contracts/policy.schema.json`, `core/policy/policy.yaml` |
| Disambiguation from the unrelated, deferred future receipt proposal | `docs/MEMORY_AND_ORCHESTRATION_CONTRACT.md` |
| Exportable auditor pack that can embed this receipt for a scope | `docs/AUDIT_PACK_SPEC.md` (`tessctl audit export --receipt <path>`) |
