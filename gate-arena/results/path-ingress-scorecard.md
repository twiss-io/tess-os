# Gate Arena — A13 path-ingress scorecard

Measured: `2026-07-16T21:08:52.975603Z`

**Result: 48/48 tests passed.** Failures: 0; errors: 0; skips: 0.

## Scope

The no-key corpus covers strict NUL-delimited raw-diff parsing; full SHA-1/SHA-256 IDs at raw Git ingress; SHA-1-only verdict-schema denial for governed SHA-256 blobs; malformed and U/X/B status/mode/OID states; deletion and rename-away; executable-bit and type transitions; symlink and gitlink states; newline, tab, NFC, NFD, and non-UTF-8 paths; the local staged diagnostic, explicit-ref ship-check, pre-push stdin, installed local hook, locally invoked CI phase, and MCP ingress; and the 100644 addition/same-mode M controls that must still proceed to normal review.

## Trust-boundary disclosure

This run performed no GPG/key generation, verifier registration, verdict signing, sign-off signing, or trust bootstrap. The shipped empty verifier registry remains untouched. Reviewable governed controls therefore pass this corpus only when they reach the expected fail-closed `no covering APPROVE verdict` result; they do not clear the ship-gate.

This score is separate from the historical A1-A12 `12/12` GPG-backed bypass scorecard. The numbers are not added together and do not prove that the gate is unbypassable.

## Reproduce

```sh
python3 gate-arena/bypass/run_path_ingress_corpus.py
```

Engine SHA-256: `27a7edf0146b69a277803b047e82ec319b0521c5542e58d960c213c9e496d034`

## Non-passing cases

None.
