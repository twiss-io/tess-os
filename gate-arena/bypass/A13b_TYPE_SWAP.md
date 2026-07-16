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
- malformed, ambiguous, non-UTF-8, or non-NFC raw path records.

Only governed regular additions (`100644`/`100755`) and same-mode regular
content modifications proceed to normal review. An ungoverned transition is
still reported but does not gain a new policy requirement.

The executable, no-key regressions are `tests/test_gate_path_ingress.py` and
`tests/test_gate_type_swaps.py`. They use disposable copies of the shipped
policy with its intentionally empty verifier registry, so no generated key,
registered key, or signed verdict is used to make a test pass.

## Scorecard disclosure

`gate-arena/results/bypass-scorecard.*` remains the historical A1-A12 12/12
run. A13's separate no-key record is
`gate-arena/results/path-ingress-scorecard.*`: **48/48 passed, with 0
failures/errors/skips**. The scores are deliberately not combined and must not
be represented as 60/60 or as proof of unbypassability.
