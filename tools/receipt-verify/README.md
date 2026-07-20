# receipt-verify — standalone Agent Receipt verifier

Verifies an [Agent Receipt](../../docs/AGENT_RECEIPT_SPEC.md) — the signed
propose -> approve -> sign accountability envelope this repository already
produces via verdict signing and hard-floor sign-off signing (see the spec
for the full grounding) — **without** the rest of the Tess OS install:

- no `tessctl` import;
- no `core/policy/policy.yaml`, mission tree, or gate engine;
- no third-party Python package.

You need only this directory (`canonical.py`, `gpg_verify.py`, `checks.py`,
`receipt_verify.py`), a Python 3.9+ interpreter, and the system `gpg` binary.

## Why standalone

The whole point of a receipt is that a party who was never part of producing
it — an auditor, a client, a future maintainer — can independently confirm
"this specific approval genuinely happened, was signed by the identity it
claims, and has not been altered or removed from its place in the history,"
using only the receipt file(s) and the public key(s) of the parties they
already trust. A verifier that itself depends on the full framework, its
policy file, or its mission state is not actually independent of the system
whose claims it is supposed to check. This tool is deliberately small enough
to read in one sitting.

## Usage

Verify one receipt, given the identity(ies) you trust and their exact
fingerprints:

```bash
python3 receipt_verify.py verify path/to/receipt.json \
  --trust Reid F9321F92B4E2DF36304CB6BAA53B9C5A1F5876E9 path/to/reid.asc \
  --json
```

Verify a receipt that chains from a previous one (checks the hash link, not
just this receipt's own signatures):

```bash
python3 receipt_verify.py verify path/to/receipt-2.json \
  --prev path/to/receipt-1.json \
  --trust Xavier <FINGERPRINT> path/to/xavier.asc
```

Verify an entire chain file in one pass (one JSON receipt per line, in
sequence order) and get a single **CHAIN INTACT** / **CHAIN BROKEN** verdict:

```bash
python3 receipt_verify.py verify-chain path/to/chain.jsonl \
  --trust Reid <FINGERPRINT> path/to/reid.asc \
  --trust Xavier <FINGERPRINT> path/to/xavier.asc
```

`--trust NAME FINGERPRINT KEYFILE` is repeatable — one per identity you are
willing to trust. This mirrors `core/contracts/policy.schema.json`'s
`VerifierKeyEntry` (fingerprint + public key file) intentionally: the
fingerprint you supply is **pinned** — a signature made by any other key,
even one that happens to carry the same name/UID in its certificate, is
rejected (exact 40-hex-character match, no short-ID or proximity matching).
There is no ambient/system-keyring fallback: an identity with no `--trust`
entry can never verify, by design.

Exit code `0` means every check passed. Any other exit code means at least
one check failed; the printed `reasons` say exactly which one (tampered
content, wrong key, unregistered identity, broken chain link, a hard-floor
category paired with a verdict instead of a sign-off, and so on — see
[`checks.py`](checks.py) and the spec's "Verification algorithm").

## What this tool does NOT do

- It does not decide policy, run a gate, or grant approval authority. A
  receipt records that an approval already happened; this tool only confirms
  the record is genuine and unaltered (see
  `docs/MEMORY_AND_ORCHESTRATION_CONTRACT.md`'s invariant 5: "Receipts are
  evidence, not verdicts").
- It never generates or registers a key. Bringing your own already-trusted
  public key and fingerprint is the caller's responsibility, exactly as
  `conductor/verdict-signing.md` already documents for verdict verification.
- It does not fetch anything over the network.

## Files

| File | Purpose |
|---|---|
| `canonical.py` | Canonicalization + hashing — the same compact/key-sorted-JSON-minus-signature scheme `.tess/bin/tessctl` already uses for verdict/sign-off signing. |
| `gpg_verify.py` | Isolated-GNUPGHOME detached-signature verification, exact-fingerprint pinning, and expired/revoked-key rejection — a small independent re-implementation of `.tess/bin/tessctl`'s own `_gate_verify_verdict_signature` discipline. |
| `checks.py` | The structural + semantic checks a receipt must pass (shape, embedded-decision signature, envelope signature, identity consistency, hard-floor/path-rule pairing, chain-link integrity). |
| `receipt_verify.py` | The CLI entry point. |

## Tests

[`tests/test_receipt_verify_tool.py`](../../tests/test_receipt_verify_tool.py)
(repository root) exercises this tool with real, ephemeral GPG keys —
genuine signatures, genuine verification, never mocked — covering: a valid
receipt and a valid two-receipt chain both pass; an unsigned or tampered
receipt is rejected; a signature from the wrong key is rejected; a broken or
reordered chain link is rejected; a hard-floor category paired with a
`verdict` (instead of the required `signoff`) is rejected.
