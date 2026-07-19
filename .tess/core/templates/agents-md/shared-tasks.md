This project keeps ONE task board shared across every harness, at
`.tess/state/tasks/` (`tessctl tasks`, docs/STATE_LAYER.md). Run
`tessctl tasks pull --unclaimed` (or `--status ready`) to see what is
available before starting new work.

Claim a task with your OWN `--host`/`--pid`/`--uuid` identity before
working it — `tessctl tasks claim <id> --host <hostname> --pid <pid>
--harness codex` (a stable `--uuid` is derived from `--host`+`--pid` if you
omit it) — rather than starting on something nobody has claimed, or a task
someone else already holds.

Record progress back to the SAME shared board as you go — never a
private, harness-only list: `tessctl tasks set <id> --status <status>
--harness codex [--add-note TEXT]`, and `tessctl log append --origin
codex --event <event> --summary TEXT` for the accountability trail.
