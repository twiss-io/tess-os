---
description: Submit a new mission for intake and routing — applies the three-question intake protocol, frames the brief, and designates an outcome orchestrator before any guild is activated.
argument-hint: [mission brief]
---

# /add-mission

Start a new mission with the brief: **$ARGUMENTS**

Run the intake-before-anything gate from [conductor/doctrine.md](../../conductor/doctrine.md) and the routing doctrine in [conductor/mission-control.md](../../conductor/mission-control.md):

1. **Three-question intake protocol** — classify (a) outcome type, (b) founder-level test, (c) domain test. See [conductor/outcome-orchestrators/README.md](../../conductor/outcome-orchestrators/README.md).
2. **Frame the real mission** — state the decision/outcome required, not just the request as phrased.
3. **Produce the task graph** — decompose into nodes with dependency gates (research before build, crew before deploy, review before synthesis, verification before anything externally visible).
4. **Designate the outcome orchestrator** — apply the routing matrix and integration precedence in [conductor/outcome-orchestrators/integration.md](../../conductor/outcome-orchestrators/integration.md).
5. **Confirm routing before activating any guild.** Propose the guild set; do not dispatch specialists until the framing is confirmed.

**Output:** mission brief, outcome type, assigned orchestrator, proposed guild set, state set to FRAMING ([conductor/mission-states.md](../../conductor/mission-states.md)).

Notify the operator via Telegram on dispatch per [conductor/daily-operating-behavior.md](../../conductor/daily-operating-behavior.md). Remember Rule Zero: orchestrate and dispatch — never execute specialist work solo.
