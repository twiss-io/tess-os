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
> claim: every section is a repo/gate fact or a safety floor. See
> `RenderTarget.doctrine_profile` in `.tess/bin/tessctl`.

## This Project

This project runs on **Tess OS** ([twiss-io/tess-os](https://github.com/twiss-io/tess-os))
for doctrine rendering and the ship-gate below. `tessctl doctor` checks core
integrity; regenerate this file with `tessctl render --target codex` /
`--target generic` after a doctrine change — never hand-edit it (hand-edits
are flagged as uncaptured drift).
{{OPERATOR_BUILD_FACTS}}

{{WORKER_HARD_FLOOR}}

{{WORKER_GATE_COMPLIANCE}}

## Command Shortcuts

{{HARNESS_NOTE}}

---

Full orchestration doctrine (Claude Code as {{ASSISTANT_NAME}}) lives in
`CLAUDE.md` — not reproduced here by design (see the banner above).
