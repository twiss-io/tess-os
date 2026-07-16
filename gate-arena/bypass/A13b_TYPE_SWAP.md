# A13b — Protected regular-file to symlink swap (expanded path-ingress closure)

## Threat

A governed regular file can be replaced by a symlink to ungoverned content.
Git reports that as status `T` (type change), not `A`, `C`, `M`, or `R`.
If a ship-gate diff filter excludes `T`, the governed pathname is absent from
classification and can ship without any covering verdict. Merely adding `T`
to a path-only diff filter is incomplete: deletion, rename-away, chmod,
gitlink/submodule state, hostile path encoding, and mode/OID ambiguity still
cannot be represented or authorized safely.

## Expected outcome

The gate now parses `git diff --raw -z --no-renames --no-abbrev` and retains a
strict `PathDelta` (status, old/new mode, full old/new object IDs, path). It
must fail closed before verdict/sign-off evaluation for:

- governed deletion or rename-away (`D` on the old pathname);
- governed type or executable-bit transitions;
- governed symlink or gitlink/submodule additions/modifications; and
- unmerged/unknown/broken-pairing (`U`/`X`/`B`), malformed, ambiguous,
  non-UTF-8, or non-NFC raw path records.

Only governed non-executable regular additions (`100644`) and same-mode regular
content modifications proceed to normal review. A new governed executable
(`100755`) is unavailable until signed evidence binds Git status/mode. An
ungoverned existing transition is still reported but does not gain a new policy
requirement; the local pre-commit diagnostic nevertheless denies every new
symlink/gitlink and reads old governance only from immutable `HEAD` policy.

Full SHA-1/SHA-256 object IDs are retained at raw Git ingress. This is not a
claim of SHA-256 verdict support: `verdict.artifact_hashes` remains SHA-1-only,
and a governed SHA-256 approval-shaped fixture is required to fail closed.
Pre-push ref deletion is also denied, without adopting A14's still-open
multi-ref/multi-push policy.

The executable, no-key regressions are `tests/test_gate_path_ingress.py` and
`tests/test_gate_type_swaps.py`. They use disposable copies of the shipped
policy with its intentionally empty verifier registry, so no generated key,
registered key, or signed verdict is used to make a test pass.

## Scorecard disclosure

`gate-arena/results/bypass-scorecard.*` remains the historical A1-A12 12/12
run. A13's separate no-key record is
`gate-arena/results/path-ingress-scorecard.*`: **49/49 passed, with 0
failures/errors/skips**. The scores are deliberately not combined and must not
be represented as 60/60 or as proof of unbypassability.
