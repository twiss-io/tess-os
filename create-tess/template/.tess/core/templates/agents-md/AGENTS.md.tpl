# AGENTS.md

> **Worker doctrine profile — deliberately lean.** Rendered from the same
> `.tess/core/**` source that produces `CLAUDE.md` for Claude Code, and read
> natively by Codex, Cursor, GitHub Copilot, Gemini CLI, Zed, Devin, and
> other AGENTS.md-standard harnesses. A 2026-07-07 proving-ground benchmark
> measured that mounting the FULL multi-agent coordination doctrine (the
> mandatory crew-handoff rule, the six-way routing layer, the mission-
> ceremony command table) into a harness like this one does not help — and
> once caused a weak model to attempt a nested subagent spawn on a task
> that only asked for `python3 --version`. Nothing below is a performance
> claim: every section is a repo/gate fact, a safety floor, or a statement
> of which `CLAUDE.md` rules do not apply to you. See
> `RenderTarget.doctrine_profile` in `.tess/bin/tessctl`.

## This Project

This project runs on **Tess OS** ([twiss-io/tess-os](https://github.com/twiss-io/tess-os))
for doctrine rendering and the ship-gate below. `tessctl doctor` checks core
integrity; regenerate this file with `tessctl render --target codex` /
`--target generic` after a doctrine change — never hand-edit it (hand-edits
are flagged as uncaptured drift).
{{OPERATOR_BUILD_FACTS}}

{{WORKER_HARD_FLOOR}}

{{WORKER_DISPATCH_SCOPE}}

{{WORKER_CHANNEL}}

{{WORKER_FILE_PLACEMENT}}

{{WORKER_GATE_COMPLIANCE}}

## Command Shortcuts

{{HARNESS_NOTE}}

## Session Memory (Shared)

{{WORKER_SESSION_MEMORY}}

## Shared Tasks

{{WORKER_SHARED_TASKS}}

## Public Preview Handoffs

Use the shipped `python3 scripts/preview/tesspreview.py` launcher for previews
(macOS/Linux/Windows WSL; Python 3.9+). It starts only when explicitly requested.
Explain LAN exposure, select only approved files in an isolated public build
directory with repeated `--file`, and use a clean `/dev/<project-slug>` route.
Never serve the workspace, private KB/brain, credentials or internal control
state. Default binding is `0.0.0.0`; use `--localhost-only` when LAN sharing is
not wanted. The launcher detects a current LAN IPv4 address and selects a free
port without stopping any listener. Configure the build's asset base for
`/dev/<project-slug>/`; use `--spa` only for approved SPA previews.

Run `verify <slug>` before handoff: both available addresses, all selected
assets, deep links and denied private paths must pass. Return the launcher's
clickable **This computer** and **Other computers on the same LAN** links, plus
PID, private log and restart/stop commands. If no LAN address exists, give the
localhost link and explicit limitation. Host-side checks are not a second-device
test. Keep the host awake and LAN-connected; HTTP only, no public tunnel,
router forwarding or firewall weakening. Snapshot bytes stay fixed until
explicit restart; re-verify after rebuild/restart. Full contract:
[docs/LAN_PREVIEWS.md](docs/LAN_PREVIEWS.md).

---

Full orchestration doctrine (Claude Code as {{ASSISTANT_NAME}}) lives in
`CLAUDE.md` — not reproduced here by design (see the banner above).
