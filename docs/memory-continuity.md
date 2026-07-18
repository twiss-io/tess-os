# Memory-Continuity Capability

> **Not the same thing as `docs/MEMORY_AND_ORCHESTRATION_CONTRACT.md`.** That
> document is a proposed, non-executable architecture contract for a future
> portable memory/orchestration layer across multiple agent hosts. This page
> describes a narrower, already-working capability: a git-tracked open-projects
> registry plus an optional scheduled heartbeat that re-derives its evidence
> and can flag a stall without a human needing to check first. It grants no
> policy authority, satisfies no gate, and is not a trust anchor — consistent
> with that contract's "memory is not authority" invariant, even though it
> predates and does not depend on that contract being implemented.

## What problem this solves

Long-lived or autonomous work (a background job, a multi-session build, an
agent loop) can silently stall or die between sessions with nothing forcing
anyone to notice — the only way to catch it is luck: a later session happening
to touch the same area. This capability answers "what's currently open, and
is it actually still moving?" from re-checked evidence (a commit, a PR, a file
mtime) instead of from memory or a self-report.

## Two layers

| Layer | Location | What it is | Status |
|---|---|---|---|
| **L1 — registry** | `memory/` | A durable, git-tracked instance store: one YAML-fronted card per open project (`memory/projects/*.md`), compiled into a dashboard (`memory/registry.md`). Hand-maintained; makes stall detection *possible* but does not poll on its own. | Ships enabled — it's just files. |
| **L2 — heartbeat** | `scripts/heartbeat/` | An external scheduler (macOS `launchd` example under `scripts/launchd/`, or your own cron/systemd equivalent) that re-derives every card's evidence on a fixed cadence, classifies a genuine new stall via a narrowly-scoped model call, and can send a notification. | **Off by default** — see Activation below. |

Full detail: `memory/README.md` (card schema) and `scripts/heartbeat/README.md`
(cost model, write discipline, configuration reference).

## Safety design (the part that must not be weakened)

The heartbeat's one model-invoking step (`tier2_classify.py`) is invoked
**fail-closed with a verified-zero tool surface**:

```
claude -p "<prompt>" --model sonnet --output-format json \
  --tools "" --allowed-tools "" \
  --strict-mcp-config --mcp-config scripts/heartbeat/empty_mcp_config.json
```

This exact flag combination was live-tested during this port (against
`claude` 2.1.208) rather than assumed:

- **`--tools ""`** is the flag verified to actually zero the CLI's built-in
  tool list. A stale `--disallowed-tools` denylist and a bare
  `--allowed-tools ""` were both tried first and **rejected** — a denylist
  leaves every tool it forgot to name reachable (Task, Workflow, SendMessage,
  ScheduleWakeup, CronCreate/Delete, RemoteTrigger, ToolSearch, ...), and an
  empty `--allowed-tools` value alone was observed, live, to be silently
  ignored (the init event still showed the full default toolset).
- **`--strict-mcp-config --mcp-config <committed empty config>`** is
  independently required: with no MCP flags at all, `--tools ""` alone still
  connects every MCP server from the operator's own global config and exposes
  every one of their tools. The tool allowlist and the MCP server list are
  two separate gates; closing one does not close the other.
- **Smoke-test proof** (re-run live during this port, `claude` 2.1.208, a
  fresh isolated `$HOME` with no other settings): the `stream-json` init
  event came back as

  ```json
  {"type":"system","subtype":"init", ..., "tools":[], "mcp_servers":[], ...}
  ```

  — zero entries in both `tools` and `mcp_servers`, confirming the call can
  only reason over its prompt text and answer in JSON. It cannot read a file,
  run a command, dispatch an agent, reach any MCP server, or notify anyone
  directly. The parent Python process is the only thing that ever writes a
  card or sends a notification, based on the JSON Tier-2 returns.

Do not replace `--tools ""` with `--disallowed-tools` or a bare
`--allowed-tools ""` — both were tested and shown not to achieve a zero tool
surface on this CLI version. If you upgrade the `claude` CLI, re-run the smoke
test above before trusting this unattended.

## What was generalized for this framework

Ported from a single-operator reference implementation and made
instance-agnostic:

- **Notification channel** — was hardcoded to one Telegram chat id; now
  `notify.channel` (`"none"` default / `"telegram"` / `"webhook"`) with
  secrets read from operator-named environment variables, never committed
  (`scripts/heartbeat/notify.py`).
- **Org/repo scope** — the daily recompile's "unregistered work" scan was
  hardcoded to one GitHub org; now `daily_recompile.org_repo_scan` (default
  `[]`, opt-in per org).
- **Cross-session memory conventions** — the scan across memory/wiki files
  was hardcoded to one operator's exact file layout; now
  `daily_recompile.memory_project_glob` and `daily_recompile.wiki_log_path`
  (both optional/nullable, default the latter to this repo's own `kb/wiki/`
  convention since it's already present here).
- **Runtime paths** — the lockfile/state dir was hardcoded to one machine's
  home directory convention; now `state_dir` (default
  `~/.tess-os/memory-heartbeat/`, override via `TESS_MEMORY_STATE_DIR`).
- **Timezone** — the "is today's recompile due" check was hardcoded to one
  operator's local timezone; now `timezone` (IANA name, default `"UTC"`).
- **Stall-reason enum naming** — `awaiting-xavier` renamed to the
  operator-neutral `awaiting-decision`.
- **A second, independent off-switch** — `heartbeat.config.json`'s
  `activated` field (default `false`). The reference implementation relied
  solely on "the scheduler isn't installed" for its off-by-default posture;
  this port adds a second gate inside `run.py` itself (forces `--dry-run`
  regardless of CLI flags until `activated` is true), specifically because
  this code now ships to every instance of this framework rather than
  running on one trusted operator's own machine.

## Activation (off by default — two gates, both required)

1. `scripts/heartbeat/heartbeat.config.json`: set `"activated": true` (or
   export `TESS_MEMORY_HEARTBEAT_ACTIVATED=1` in your scheduler's
   environment), and pick a `notify.channel` + export its secret env var.
2. Install and load a scheduler — see `scripts/launchd/README.md` for the
   staged, NOT-yet-loaded macOS example and its one-command activation
   sequence, or point your own cron/systemd equivalent at
   `scripts/heartbeat.sh`.

Until *both* are true, every invocation of `scripts/heartbeat/run.py` forces
`--dry-run`: probes still run for real, but nothing is written, no model is
spawned, no notification is sent, and no git commit/push happens.

## Known limitations (honest, not hidden)

- A scheduler-based heartbeat pauses when the machine sleeps — late
  detection, not lost detection (evidence timestamps are re-derived each run,
  not counted in ticks).
- `git push` from a scheduler-spawned background process depends on your own
  machine's SSH/credential setup being reachable outside an interactive
  shell — verify this once, live, before activating.
- The `claude -p --output-format json` response shape has been observed to
  vary across CLI versions; `tier2_classify.py` handles the shapes seen so
  far defensively but this is worth one real smoke-test call at first
  activation.
- The daily recompile's "unregistered work" scan is best-effort and entirely
  opt-in — it starts doing nothing until real org/glob/log values are
  configured, and will likely need tuning after the first few real runs.
