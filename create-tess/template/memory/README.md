# memory/

Durable, git-tracked open-projects registry (L1 of the memory-continuity
capability — see `docs/memory-continuity.md` for the full design). Source of
truth for "what is currently open and what state is it in" — re-derived from
evidence (commits, PRs, file mtimes), never from recall or a self-report.

- `projects/*.md` — one YAML-fronted card per currently-open project.
  Hand-maintained: create one when you start tracking a project, update
  `next_move`/`resume`/`gates` as the project's plan changes. See
  `projects/EXAMPLE.md` for the schema and field notes — copy it as a
  starting point.
- `registry.md` — the compiled dashboard, generated FROM the cards above,
  sorted by priority then staleness-risk. **Auto-generated — do not
  hand-edit the tables.** The "Why this registry exists" section and
  everything below it IS hand-authored and preserved verbatim across every
  regeneration — that's where a team's own worked examples/incident record
  belongs.

## Card schema (frontmatter)

| Field | Written by | Meaning |
|---|---|---|
| `id` | human | Slug, must match the filename stem. |
| `title` | human | Display name. |
| `state` | human | Free-text status label (ACTIVE / PAUSED / AWAITING DECISION / UNDER REVIEW / ... — use your own team's taxonomy if you have one). |
| `owner` | human | Who/what is driving this project. |
| `priority` | human | `P0`–`P3`. Drives registry sort order. |
| `repo` | human | `org/name` — the GitHub repo the heartbeat's Tier-1 probes check for evidence. |
| `working_clone` | human | Where the local checkout lives, with any staleness warning if it's known to be behind origin. |
| `heartbeat.cadence` | human | Prose describing the project's own rhythm (a fixed loop, session-driven, etc.) — informational, not machine-read. |
| `heartbeat.last_activity` | **heartbeat** (mechanical) | ISO-8601 timestamp of the freshest known evidence. |
| `heartbeat.activity_proof` | **heartbeat** (mechanical) | The exact command + result that proves `last_activity`. |
| `heartbeat.stall_after` | human | Prose containing a duration (e.g. "7 days with no commit to main") — parsed by `scripts/heartbeat/duration.py`. |
| `stall.stalled` | **heartbeat** (mechanical) | `true`/`false`. |
| `stall.reason` | **heartbeat** (Tier-2, on a new stall event) | One of the fixed enum in `scripts/heartbeat/tier2_classify.py`. |
| `stall.since` | **heartbeat** (mechanical) | When the stall threshold was objectively crossed. |
| `next_move` | human | The single next action — specific enough that a fresh session/agent can act on it without a clarifying question. |
| `resume` | human | A recipe that always starts "fresh clone from origin HEAD" — never "continue from the local copy." |
| `gates` | human | Any pending external dependency/approval blocking the project. |
| `facts_last_verified` | **heartbeat** (mechanical) | Timestamp of the last time any field above was re-checked against a primary source. |

Only the six fields marked **heartbeat (mechanical)** are ever written by the
automated runner (`scripts/heartbeat/cards.py`'s `WRITABLE_FIELDS`) — every
other field is a human/agent judgment call, never overwritten automatically.

**Invariant-vs-mutable-state claim rule:** classify every claim in a card as
either an *invariant* (true regardless of when it's read) or a
*mutable-state claim* (true only as of a point in time — e.g. "PR #26 is
open"). Every mutable-state claim needs both a `last_verified` timestamp and
a `verify_via` pointer (the exact command/file that would re-confirm it) or
it isn't usable as fact — it's a hypothesis to re-check before acting on or
relaying it.

## Phase 0 (this directory) vs Phase 1 (the heartbeat)

This directory's cards + `registry.md` are the durable registry that makes
stall detection *possible* by giving a session something real to read and
re-verify. On their own they do **not** poll — detection still requires a
human (or agent) to open the registry and check it.

`scripts/heartbeat/` closes that gap: an external scheduler that re-derives
every card's evidence on a fixed cadence ($0, no LLM on the common path),
classifies a genuine new stall via a narrowly-scoped, tool-less model call
only when needed, and can push a stall alert without waiting for a session
to start. **Ships off by default** — see `scripts/heartbeat/README.md` and
`docs/memory-continuity.md` for the full activation sequence and safety
design.
