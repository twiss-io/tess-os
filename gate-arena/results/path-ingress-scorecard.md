# Gate Arena — A13 path-ingress scorecard

Measured: `2026-07-17T10:00:00.719987Z`

**Result: 49/49 tests passed.** Failures: 0; errors: 0; skips: 0.

## Scope

The no-key corpus covers strict NUL-delimited raw-diff parsing; full SHA-1/SHA-256 IDs at raw Git ingress; SHA-1-only verdict-schema denial for governed SHA-256 blobs; malformed and U/X/B status/mode/OID states; deletion and rename-away; executable-bit and type transitions; symlink and gitlink states; newline, tab, NFC, NFD, and non-UTF-8 paths; the local staged diagnostic, explicit-ref ship-check, pre-push stdin, installed local hook, locally invoked CI phase, and MCP ingress; and the 100644 addition/same-mode M controls that must still proceed to normal review.

## Trust-boundary disclosure

This run performed no GPG/key generation, verifier registration, verdict signing, sign-off signing, or trust bootstrap. The shipped empty verifier registry remains untouched. Reviewable governed controls therefore pass this corpus only when they reach the expected fail-closed `no covering APPROVE verdict` result; they do not clear the ship-gate.

This score is separate from the historical A1-A12 `12/12` GPG-backed bypass scorecard. The numbers are not added together and do not prove that the gate is unbypassable.

## Reproduce

```sh
python3 gate-arena/bypass/run_path_ingress_corpus.py
```

Engine SHA-256: `bc9579292439b815abe483922d6d307ee6ddd7a851d17ffa6e25da73928a7296`

## Non-passing cases

None.
