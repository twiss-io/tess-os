# A13b — Protected regular-file to symlink swap

## Threat

A governed regular file can be replaced by a symlink to ungoverned content.
Git reports that as status `T` (type change), not `A`, `C`, `M`, or `R`.
If a ship-gate diff filter excludes `T`, the governed pathname is absent from
classification and can ship without any covering verdict.

## Expected outcome

The gate must fail closed without a verdict:

- `conductor/guardrails.md` regular-file to symlink: blocked by both `gate ci`
  and explicit-ref `gate pre-push`, with the protected path in
  `changed_paths`.
- Combined `core/policy/policy.yaml` plus `conductor/guardrails.md` swaps:
  both protected paths are reported and blocked.
- Ordinary protected content edits remain blocked without a verdict.
- An ungoverned type swap is still reported as changed but does not require a
  verdict.

The executable, no-key regression is
`tests/test_gate_type_swaps.py`. It uses disposable copies of the shipped
policy with its intentionally empty verifier registry, so every protected
denial proves the reverse direction: no generated key, registered key, or
signed verdict makes the test pass.

## Scorecard disclosure

`gate-arena/results/bypass-scorecard.*` remains the historical 12/12 run on
this branch. This A13b record is deliberately **not** added to that aggregate
until the full corpus is rerun and records every outcome together. It must not
be represented as a new 13/13 score from this focused regression alone.
