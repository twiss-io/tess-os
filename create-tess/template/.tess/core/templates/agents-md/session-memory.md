This project keeps ONE memory shared across every harness, at
`.tess/state/memory/` (`tessctl memory adopt`, docs/STATE_LAYER.md). At the
start of a session, read `.tess/state/memory/MEMORY.md` — the index — and
follow a linked file only when it is relevant to the current task; do not
read the whole store up front.

Write durable, reusable learnings back to `.tess/state/memory/` only (a new
file plus an index line in `MEMORY.md`) — never to a private, harness-only
copy, and never anywhere outside this project's fenced state root.
