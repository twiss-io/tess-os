# Agent Receipt demo

A runnable, end-to-end walkthrough of the [Agent Receipt](../../docs/AGENT_RECEIPT_SPEC.md):
propose -> approve -> sign -> journal -> verify, producing two real, signed,
chained receipts and then running the [standalone verifier](../../tools/receipt-verify/)
against them exactly the way an independent third party would.

## Run it

```bash
./examples/receipt-demo/run_demo.sh
```

or, from the repository root:

```bash
make receipt-demo
```

Requires Python 3.9+ and the system `gpg` binary. No other setup.

## What it does

1. **Generates two ephemeral, demo-only GPG identities** — `Reid` (an
   AI-verifier stand-in) and `demo-operator` (a human-operator stand-in) —
   fresh, in throwaway homedirs, for this run only.
2. **Receipt 0 (genesis):** builds and signs a `verdict` (an AI verifier's
   reviewed `APPROVE` of an illustrative documentation change), embeds it in
   an Agent Receipt whose `policy_decision` explains why review was required,
   then signs the receipt's own envelope with the same identity.
3. **Receipt 1 (chained):** builds and signs a hard-floor `signoff` (a human
   operator's authorization of an illustrative sandbox money-movement
   action), embeds it in a second Agent Receipt that chains from Receipt 0
   via `chain.prev_receipt_hash`, and signs its own envelope.
4. **Journals** both receipts to `examples/receipt-demo/.output/` (gitignored
   — nothing here is committed) as a JSONL chain file, alongside both demo
   public keys.
5. **Verifies** the whole chain by invoking `tools/receipt-verify/receipt_verify.py
   verify-chain` as a **subprocess** — the same way an outside party would,
   given only the receipt files and the public keys — and expects
   `CHAIN INTACT`.
6. **Proves the negative case too:** tampers with a copy of Receipt 1 after
   it was signed (without re-signing) and re-runs the verifier, expecting
   rejection. A demo that only shows the happy path proves nothing about
   whether tampering is actually caught.

Exit code `0` means every step above succeeded, including the tamper
rejection in step 6. Any other exit code means something is wrong; see the
printed output for exactly what.

## What this does and does not prove

**Does prove:** the Agent Receipt object shape, canonicalization, chain-link
model, and standalone verifier all interoperate correctly, end to end, with
real (not mocked) GPG signatures — and that tampering after signing is
mechanically caught.

**Does not prove:** that these identities are trustworthy, that this
sequence happened inside a real Tess OS gate run, or that any real
`core/policy/policy.yaml` rule matches the illustrative `policy_decision`
values used here. The demo's `policy_decision.rule_id` values
(`demo-docs-review`, `demo-money-movement`) are **illustrative only** — they
do not correspond to real rules in this repository's shipped
`core/policy/policy.yaml`.

## Never real keys

Every GPG identity this demo creates is destroyed (private material deleted,
throwaway `gpg-agent` killed) before the script exits. Nothing here is ever
registered in `core/policy/policy.yaml`'s `verifier_keys` or `signoff_keys`,
and no output of this demo is committed to the repository — see
`examples/receipt-demo/.output/` in `.gitignore`. This mirrors
`conductor/verdict-signing.md`'s standing rule: never generate, register, or
sign a verifier/sign-off key to clear a real gate.

## Files

| File | Purpose |
|---|---|
| `run_demo.sh` | Entry point (checks for `gpg`, then runs `build_demo.py`). |
| `build_demo.py` | Orchestrates the full walkthrough and prints each step. |
| `demo_keys.py` | Ephemeral GPG identity generation/signing/teardown. |
| `demo_receipts.py` | Builds the two illustrative signed receipts. |
| `.output/` | Generated receipts, chain file, and demo public keys (gitignored). |
