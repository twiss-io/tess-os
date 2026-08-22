# A13b — Protected regular-file to symlink swap

## Threat

A governed regular file can be replaced by a symlink to ungoverned content.
Git reports that as status `T` (type change), not `A`, `C`, `M`, or `R`.
If a ship-gate diff filter excludes `T`, the governed pathname is absent from
classification and can ship without any covering verdict. The same ingress
must include `D`: otherwise deleting a protected policy, gate, or lock control
can yield an empty change set and return PASS before policy evaluation. It must
also disable Git rename collapsing. An exact rename can be reported as `R100`,
where `--name-only` exposes only the ungoverned destination and hides the
protected source.

## Expected outcome

The gate must fail closed without a verdict:

- `conductor/guardrails.md` regular-file to symlink: blocked by both `gate ci`
  and explicit-ref `gate pre-push`, with the protected path in
  `changed_paths`.
- Combined `core/policy/policy.yaml` plus `conductor/guardrails.md` swaps:
  both protected paths are reported and blocked.
- Ordinary protected content edits remain blocked without a verdict.
- Protected deletions remain classified; policy, gate, and trusted-lock
  deletion is denied on the normal PR path.
- Protected renames are evaluated as deletion plus addition. Moving ordinary
  governed content remains verdict-gated, while moving a policy, gate, or lock
  control is denied as `SECURITY_CONTROL_DELETION`.
- An ungoverned type swap is still reported as changed but does not require a
  verdict.

The executable, no-key regression is
`tests/test_gate_type_swaps.py`. It uses disposable copies of the shipped
policy, including the current Cyra public registration, but supplies no
verdict artifact or private key. Every protected denial therefore proves the
reverse direction: no generated key, candidate registration, or signed verdict
makes the test pass.

## Scorecard disclosure

The full corpus was rerun on this branch and records A13 together with every
other case: 15/15 scripted attempts blocked. That aggregate is qualified by
the committed A14 disclosure: the live App-bound ruleset is active, strict,
and has no configured bypass, but external policy-epoch custody is not
implemented and a hostile owner could later change or remove the ruleset.
