---
name: tess-wake
description: "Session start checklist — orient, load doctrine context, check active mission state, surface pending decisions and blockers, and notify the operator that a session is live."
---

<!-- Rendered by `tessctl render --target codex` from .tess/core/commands/wake.md. Regenerate; do not hand-edit. -->

Tess OS command `/wake`, packaged as an Agent Skill. Run it only when the user asks for it by name (`$tess-wake` in Codex).

# /wake

Run the session-start checklist from [conductor/daily-operating-behavior.md](../../../conductor/daily-operating-behavior.md):

1. **Orient** — load doctrine context (System Laws, active orchestrator layer, guardrails).
2. **Check mission state** — identify any active missions and their current state ([conductor/mission-states.md](../../../conductor/mission-states.md)).
3. **Surface pending decisions and blockers** — anything awaiting the operator, plus outstanding verification gates.
4. **Check the day's context** — run `date` for UTC and your local timezone, scan for health alerts or overnight work needing follow-up.
5. **Notify the operator** that a session is live through the active runtime's native channel: in Claude Code with the Telegram integration, a Telegram message to the operator's DM (`<your-dm-chat-id>`, per [conductor/channel-guardrails.md](../../../conductor/channel-guardrails.md)); in any runtime without it, the in-app progress stream.

**Output:** active mission state, pending decisions, blockers, and session-readiness confirmation.
