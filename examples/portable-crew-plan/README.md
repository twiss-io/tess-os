# Portable crew-plan reference

`plan.json` is a small, host-neutral **planning contract**. It has no
provider configuration, credentials, execution command, concurrency claim, or
certification claim. It does not dispatch an agent, execute a task, approve a
change, or establish any authority. A host may use a valid plan only after it
applies its own dispatch, isolation, and approval controls.

The one task deliberately describes internal planning. It carries no
production, client-facing, externally-visible, or irreversible flag, so its
`verifier` is explicitly the internal-only form: no named verifier and no
approval requirement. Changing one of those flags requires a separate,
named verifier and a real primary artifact under the crew-plan contract.

## Validate in a disposable root

Run **validation only**; do not use `tessctl run` for this reference.
`tessctl validate` checks schema and relational rules, but does not execute a
crew-plan. It does write a local trace event, so use a disposable project root
rather than treating validation as read-only.

Create a scratch root containing copies of `tess.manifest.json`,
`.tess/bin/tessctl`, and `core/contracts/`, then copy `plan.json` to the
scratch root (not beneath `missions/`). From the repository root, one example
is:

```bash
scratch="$(mktemp -d)"
mkdir -p "$scratch/.tess/bin" "$scratch/core"
cp tess.manifest.json "$scratch/"
cp .tess/bin/tessctl "$scratch/.tess/bin/tessctl"
cp -R core/contracts "$scratch/core/contracts"
cp examples/portable-crew-plan/plan.json "$scratch/plan.json"
TESS_ROOT="$scratch" python3 "$scratch/.tess/bin/tessctl" \
  validate crew-plan "$scratch/plan.json" --json
rm -rf "$scratch"
```

For a root-level `plan.json`, the validator appends one JSONL record under
`$scratch/.tess/trace/runs/`. That fallback trace directory is ignored in a
normal Tess OS project, but it is still a write; deleting the scratch root
removes it. Do not put this validation input under `missions/<id>/`, because
that would instead create a mission trace there.

## Contract checks illustrated by the tests

[`tests/test_portable_crew_plan_example.py`](../../tests/test_portable_crew_plan_example.py)
runs the actual CLI against disposable roots. It proves that the example
passes, while each of these invalid forms is rejected:

- a task ID that can escape the safe-slug contract;
- a parallel stage with a dependency edge;
- a synthesis input that does not name a task; and
- an externally-visible task without a real named verifier and primary
  artifact.

Those are validation properties only. They do not demonstrate execution,
provider support, concurrency, deployment, release readiness, or approval.
