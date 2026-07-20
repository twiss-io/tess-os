# receipt-emit — Agent Receipt EMIT CLI

The write-side counterpart to [`tools/receipt-verify/`](../receipt-verify/)
(verify-only, standalone, zero third-party dependency). This tool PRODUCES
an [Agent Receipt](../../docs/AGENT_RECEIPT_SPEC.md) from an
ALREADY-SIGNED verdict or hard-floor sign-off, and closes the gap that tool
left open: `tools/receipt-verify` can confirm a receipt is genuine, but
until this tool existed nothing in this repository actually EMITTED one.

## Architecture — attaches to System B, never System A

This tool wraps a REAL, GPG-signed verdict
([`core/contracts/verdict.schema.json`](../../core/contracts/verdict.schema.json))
or hard-floor sign-off (the
`.tess/gate/signoffs/<rule-id>.signoff.json` shape) — "System B" in this
project's own accountability model, the exact GPG verdict/sign-off loop
`tools/receipt-verify/` already verifies standalone.

It is explicitly **not** a wrapper for the `run_pipeline` HMAC approval
("System A"). That approval is a single-OS-account mechanism, not a
receipt `decision_kind` this schema recognizes — wrapping it in a receipt
would overstate the trust an Agent Receipt is supposed to represent.
`--decision` must structurally match a `verdict.schema.json` instance
(`disposition: APPROVE`) or a `SignoffArtifact`; anything else — including,
deliberately, anything shaped like a System A HMAC approval — is refused
before any file is touched (`assemble.infer_decision_kind`).

## Usage

```bash
python3 receipt_emit.py emit \
  --decision path/to/signed-verdict-or-signoff.json \
  --rule-id demo-docs-review \
  --policy core/policy/policy.yaml \
  --actor Ada \
  --summary "Proposed a documentation change to docs/AGENT_RECEIPT_SPEC.md" \
  --key-id <GPG-KEY-ID-OR-FINGERPRINT> \
  --chain path/to/chain.jsonl \
  --json
```

Exit code `0` means the receipt was assembled, signed, self-verified (a
real `tools/receipt-verify/receipt_verify.py verify-chain` subprocess call
against the candidate chain reported `CHAIN INTACT`), and atomically
committed to `--chain`. Any other exit code means the emit was **REFUSED**
— see the printed reasons — and `--chain` is guaranteed byte-for-byte
unchanged.

## Behavior

1. **Assemble** the receipt envelope per
   [`core/contracts/agent-receipt.schema.json`](../../core/contracts/agent-receipt.schema.json),
   embedding the signed verdict/signoff from `--decision` VERBATIM.
2. **Copy the fired policy rule VERBATIM** from `--policy` (default
   `core/policy/policy.yaml`) by `--rule-id` — READ-ONLY, this tool never
   writes to the policy file (`policy_lookup.py`).
3. **GPG-sign** the envelope with `--key-id` (detached-armor over the same
   canonical bytes `tools/receipt-verify/canonical.py` already defines and
   checks against).
4. **Chain-link** to the prior receipt in `--chain` (its full content hash
   becomes this receipt's `chain.prev_receipt_hash`; sequence increments by
   one) and **atomically append** exactly one line (`chain_atomic.py`).
5. **Self-verify** by invoking the real, independent
   `tools/receipt-verify/receipt_verify.py verify-chain` against the
   CANDIDATE chain file — BEFORE that candidate ever becomes the real
   `--chain` file. Only a `CHAIN INTACT` result is ever committed.

## Fail-closed (all buildable today, no key ceremony)

- **Non-`APPROVE` verdict / incomplete-or-unsigned signoff → REFUSE, write
  NO receipt.** `assemble.validate_decision_or_refuse` runs
  `tools/receipt-verify/checks.py`'s OWN `check_decision_shape` — the same
  check the verifier will run later — before any file is touched.
- **Signer identity ≠ decision identity → REFUSE.** `receipt_signature
  .signed_by` is always DERIVED from the decision's own identity field
  (`verifier` / `authorized_by`), never independently supplied; a
  defense-in-depth re-check (`checks.py`'s `check_identity_consistency`,
  reused, not reimplemented) runs again on the fully-assembled receipt.
- **Mid-emit kill → no partial line, no orphan.** `chain_atomic.py` writes
  the full candidate content to a temp file in the same directory, fsyncs
  it, self-verifies it, and only THEN performs an atomic `os.replace` onto
  the real chain file. Any failure at any step — including a simulated
  crash between the temp write and the rename — leaves `--chain` exactly
  as it was found and deletes the temp file; see that module's own header
  for the full argument.

## Known limitation — no concurrent-writer lock

Two `emit` invocations racing against the SAME `--chain` file can each
compute the same `(sequence, prev_hash)` and independently win their own
atomic rename — the second overwrites the first receipt's line, silently
dropping it (last-writer-wins; never a corrupted/partial file, but a real
dropped receipt). `chain_atomic.py` guarantees no partial line and no
orphaned temp file even under a crash; it does **not** guarantee mutual
exclusion between concurrent emitters onto the same chain file. A
single-writer-at-a-time model (one emit at a time) is safe today without
it; a per-chain-file advisory lock, mirroring `.tess/state/tasks/**`'s own
precedent (`docs/STATE_LAYER.md`), is a natural, scoped follow-on
deliberately left out of this PR rather than silently assumed away.

## Honest label

Every successful emit prints (and, with `--json`, returns as
`trust_status: "signed_not_trust_anchored"` plus a full `honest_label`
string):

> This receipt is genuinely GPG-signed and tamper/chain-evident, but is NOT
> trust-anchored until the signer's key is registered in
> `core/policy/policy.yaml` (`verifier_keys` / `signoff_keys` — currently
> empty). Key-ceremony registration is Xavier-gated and is not performed by
> this tool. A self-verify PASS proves the receipt is genuine and
> unaltered; it does not mean a trusted party's approval is enforced by
> policy.

Do not read a `CHAIN INTACT` result — from this tool or from
`tools/receipt-verify` — as "a trusted party approved this." It means "this
specific signature is genuine and this specific record has not been
altered." Trust-anchoring a signer's key is a separate, later,
human-custody decision (`docs/TRUST_BOOTSTRAP_SECURITY_DESIGN.md`).

## Why this tool is not zero-dependency like `tools/receipt-verify`

`tools/receipt-verify/` is a THIRD-PARTY-AUDITOR-FACING tool — an outside
party runs it with nothing but a receipt file and a public key, so it is
deliberately zero-third-party-dependency (stdlib + the system `gpg` binary
only).

`tools/receipt-emit/` is not that: it only makes sense to run from inside a
Tess OS checkout, because it reads this repository's own
`core/policy/policy.yaml`. `.tess/bin/tessctl` already requires PyYAML to
parse that exact file (`requirements-dev.txt: PyYAML>=6.0`, already
installed in this repo's own CI). `policy_lookup.py` reuses that SAME
already-required dependency rather than hand-rolling a second, independent
YAML parser whose whole job would be to copy policy rule text VERBATIM — a
parser that silently disagreed with `tessctl`'s own `_gate_load_policy` on
any edge case (folded scalars, quoting, block styles) would be a
correctness/security regression on a field a reader is meant to trust as
authoritative, not an improvement. See `policy_lookup.py`'s own header for
the full reasoning.

## Two deliberate, documented deviations from the original CLI sketch

- **`--chain` is REQUIRED, not defaulted.** Where a receipt chain belongs
  by default is a real repository-convention decision — extending
  `docs/STATE_LAYER.md`'s four-layer `.tess/state/**` fence
  (`never_touch`, `.gitignore`, the publish-clean gate, `create-tess`
  scaffold-strip) to a new subsystem touches `.tess/bin/tessctl`, which is
  explicitly out of this PR's scope. Requiring `--chain` avoids silently
  picking a convention inside a narrowly-scoped emit-tool PR.
- **`--trust NAME FINGERPRINT PUBLIC_KEY_FILE` (repeatable, optional) is an
  added flag.** It exists so this tool's own self-verify step can actually
  return `CHAIN INTACT` for a chain whose EARLIER receipts were signed by a
  DIFFERENT identity than this emit's own `--key-id` (e.g. an AI verdict
  followed by a human sign-off, mirroring `examples/receipt-demo/`). The
  current signer is always included in self-verify automatically;
  `--trust` supplies any additional identities already present earlier in
  the chain. It is used ONLY for this emit's own self-verify subprocess
  call — never embedded in the receipt, never a substitute for a real
  key-ceremony registration.

## Files

| File | Purpose |
|---|---|
| `receipt_emit.py` | The CLI entry point; orchestrates the full pipeline. |
| `assemble.py` | Decision-kind inference, envelope assembly + signing, and the identity/pairing checks reused from `tools/receipt-verify/checks.py`. |
| `policy_lookup.py` | READ-ONLY lookup of a fired policy rule from `core/policy/policy.yaml`, copied verbatim. |
| `gpg_sign.py` | The signing-side GPG operations (fingerprint resolution, key export, detached-sign) — the counterpart to `tools/receipt-verify/gpg_verify.py`'s verification-side operations. |
| `chain_atomic.py` | Atomic, verify-before-commit temp+rename append to the chain file. |
| `errors.py` | The shared `EmitRefused` exception every refusal in this tool raises. |

## Tests

[`tests/test_receipt_emit_cli.py`](../../tests/test_receipt_emit_cli.py)
(subprocess, real GPG keys, end-to-end including self-verify) and
[`tests/test_receipt_emit_semantics.py`](../../tests/test_receipt_emit_semantics.py)
(unit-level: policy lookup, decision-kind inference, atomic-append
crash-safety, identity-consistency guard) cover: a happy emit reports
`CHAIN INTACT`; a non-`APPROVE` verdict is refused with nothing written; a
forced signer/decision identity mismatch is refused; a simulated crash
between the candidate write and the atomic rename leaves the chain file
unchanged with no orphaned temp file; and a two-emit (verdict then
signoff) chain continuity round trip.
