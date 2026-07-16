# Gate Arena — A13 path-ingress scorecard

Measured: `2026-07-16T20:27:27.970677Z`

**Result: 48/48 tests passed.** Failures: 0; errors: 0; skips: 0.

## Scope

The no-key corpus covers strict NUL-delimited raw-diff parsing; SHA-1 and SHA-256 object IDs; malformed status/mode/OID tuples; deletion and rename-away; executable-bit and type transitions; symlink and gitlink states; newline, tab, NFC, NFD, and non-UTF-8 paths; staged, explicit-ref, pre-push stdin, installed-hook, CI, and MCP ingress; and the regular-file A/M controls that must still proceed to normal review.

## Trust-boundary disclosure

This run performed no GPG/key generation, verifier registration, verdict signing, sign-off signing, or trust bootstrap. The shipped empty verifier registry remains untouched. Reviewable governed controls therefore pass this corpus only when they reach the expected fail-closed `no covering APPROVE verdict` result; they do not clear the ship-gate.

This score is separate from the historical A1-A12 `12/12` GPG-backed bypass scorecard. The numbers are not added together and do not prove that the gate is unbypassable.

## Reproduce

```sh
python3 gate-arena/bypass/run_path_ingress_corpus.py
```

Engine SHA-256: `f682eb3d63268e92b77210bdf17155a5379e01d1c76f14df5b515023f7161b32`

## Non-passing cases

None.
