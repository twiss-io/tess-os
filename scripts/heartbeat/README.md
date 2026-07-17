# Memory-Continuity Heartbeat (L2)

Generalized framework port of a memory-continuity heartbeat originally built
for one operator's own Tess instance. Built on top of the L1 open-projects
registry (`memory/README.md`, `memory/registry.md`, `memory/projects/*.md`).

**Status: ready-to-activate, NOT activated.** Every file here is committed.
Nothing has been copied into `~/Library/LaunchAgents/`, no scheduler has
been installed, and `heartbeat.config.json`'s `activated` field defaults to
`false` — a persistent daemon spawning `claude -p` and sending notifications
on an operator's behalf is a materially different trust boundary than an
interactive session, and this ships inert until the operator deliberately
flips it on. See "Activation" below.

## What this is

An external, unattended process (any scheduler — the shipped example is a
macOS `launchd` LaunchAgent, see `scripts/launchd/`) that iterates every card
under `memory/projects/*.md` on a fixed schedule and detects a stall without
requiring a human to run a wake/review command first.

## Two-tier cost model

| Tier | When | Cost | What it does |
|---|---|---|---|
| **1 — evidence probes** | Every tick, every card | $0, no LLM | `gh api repos/<repo>/commits` + `gh pr list --repo <repo>` per card's own `repo:` field. Mechanically refreshes `heartbeat.last_activity`/`activity_proof` when fresher evidence exists. Classifies `healthy` / `cleared` / `repeat-stall` purely by comparing timestamps to the card's own `stall_after` — no model call. |
| **2 — classification** | Only on a **new** stall event, or the **daily recompile** | 1 model call, tool-less | Reads the card + fresh evidence, picks the `stall.reason` enum value, composes the notification text, and decides whether to queue the card's `resume:` recipe. The daily recompile additionally cross-references any *configured* memory-project titles, wiki-log tail, and org-wide repo scan — all opt-in, none assumed. |

Repeat reminders for an **already-classified** stall are pure arithmetic
(`escalation.py`) — no LLM call, ever. The only place this system spends a
token is deciding something genuinely new, not re-confirming something a
human or a prior Tier-2 call already decided.

## Rule Zero, applied to an unattended daemon

The runner **checks and queues**. It never does the actual resume work:

- Tier-2's `claude -p` calls are invoked fail-closed with a verified-empty
  tool surface: `--tools ""` (zeroes the built-in tool list) plus
  `--strict-mcp-config --mcp-config empty_mcp_config.json` (committed next
  to `tier2_classify.py`, `{"mcpServers": {}}`). Both flags were live-tested
  during this port against `claude` 2.1.208 — see `tier2_classify.py`'s
  module docstring for the full write-up, including why a stale
  `--disallowed-tools` denylist and a bare `--allowed-tools ""` were both
  tried and rejected (neither actually zeroes the tool surface), and why
  `--bare` was tested and not used (breaks OAuth-subscription auth). With
  this flag set the call can only reason over the text embedded in its
  prompt (including untrusted commit/PR/wiki content — a prompt-injection
  surface) and answer in JSON. It cannot touch the filesystem, dispatch an
  agent, notify anyone directly, reach any MCP server, or "fix" anything.
- The parent Python process is the only thing that ever writes a card (and
  only the six whitelisted leaf fields — see `cards.py`'s `WRITABLE_FIELDS`)
  or sends a notification, based on what Tier-2 returns.
- A queued `resume:` recipe is a pointer for the next real session/agent to
  act on — never executed by the runner itself.

## What writes, when

- **The per-tick mechanical refresh** (heartbeat.last_activity/activity_proof
  bump, no stall-state change) is written to the card **on disk but not
  committed** — anyone reading the card locally sees it immediately; git
  doesn't gate a local file read.
- **A new stall event** is written locally immediately, but **not committed
  or pushed at that moment**. The card only becomes durably visible to
  another machine (or a fresh clone) once the next daily recompile commits
  + pushes — so worst case a stall notification can arrive up to ~24h before
  the corresponding repo state is visible elsewhere. This is a documented
  gap, not a bug: push-once-daily (rather than push-per-event) bounds an
  unattended process's write authority over a shared repo to one commit/day.
- **The daily recompile** always commits + pushes once (`memory/registry.md`
  regenerated, plus any card writes accumulated since the last recompile)
  and sends exactly one notification digest.

## Configuration (`heartbeat.config.json`)

Every value in this file is safe to commit — no secrets live here, only the
*names* of environment variables that hold secrets. See `config.py` for the
full schema; summary:

| Field | Default | Meaning |
|---|---|---|
| `activated` | `false` | Master off-switch. See "Activation" below. |
| `model` | `"sonnet"` | Model passed to Tier-2's `claude -p --model`. |
| `state_dir` | `null` (→ `~/.tess-os/memory-heartbeat/`) | Where the lockfile/state.json/logs live — outside the git repo. Override with `TESS_MEMORY_STATE_DIR`. |
| `timezone` | `"UTC"` | IANA timezone the "is today's daily recompile due" check runs in. |
| `notify.channel` | `"none"` | `"none"` \| `"telegram"` \| `"webhook"`. See `notify.py`. |
| `notify.telegram_bot_token_env` / `telegram_chat_id_env` | env var *names* | Read fresh on every send — never cached, never committed. |
| `notify.webhook_url_env` | env var *name* | Generic HTTPS POST of `{"text": ...}` — compatible with Slack incoming webhooks and most chat-ops webhooks. |
| `daily_recompile.org_repo_scan` | `[]` | List of GitHub orgs to scan for unregistered work via `gh repo list`. Empty = skipped. |
| `daily_recompile.memory_project_glob` | `null` | Optional glob for cross-session project-note files (any convention an operator uses). `null` = skipped. |
| `daily_recompile.wiki_log_path` | `"kb/wiki/log.md"` | Optional repo-relative path to tail for the recompile's fuzzy scan. `null` = skipped. |

## Activation

Two independent gates, both must be satisfied — see
`scripts/launchd/README.md` for the full sequence:

1. `heartbeat.config.json`: `"activated": true` (or
   `TESS_MEMORY_HEARTBEAT_ACTIVATED=1` in the scheduler's environment).
2. Install and load a scheduler (the staged, NOT-loaded launchd example
   under `scripts/launchd/`, or your own cron/systemd equivalent pointed at
   `scripts/heartbeat.sh`).

Until *both* are true, `run.py` forces `--dry-run` no matter what invokes
it — see its module docstring.

## Known limitations (honest, not hidden)

- **Scheduler pauses when the machine sleeps** (macOS launchd example) — a
  laptop-scoped heartbeat, not a durable server-side one. Late, not lost:
  `since` is recomputed from evidence each run.
- **`git push` from a scheduler-spawned process is unverified in every
  environment** — depends on your own machine's SSH agent/credential setup
  being reachable from a background process. Verify once, live, before
  activating.
- **The `claude -p --output-format json` response shape has been observed to
  vary** across versions (single dict vs. array of turn objects) —
  `tier2_classify.py` handles both defensively, but smoke-test this path for
  real at first activation before trusting it fully unattended.
- **The daily recompile's "unregistered work" scan is best-effort** and
  entirely opt-in (empty by default) — it will need tuning to whatever
  conventions an operator actually uses once real org/glob/log values are
  configured.
