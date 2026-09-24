---
name: tess-finalize
description: "Close the mission with the full 10-section executive decision memo — the canonical Master Mission Output Framework synthesis."
---

<!-- Rendered by `tessctl render --target codex` from .tess/core/commands/finalize.md. Regenerate; do not hand-edit. -->

Tess OS command `/finalize`, packaged as an Agent Skill. Run it only when the user asks for it by name (`$tess-finalize` in Codex).

# /finalize

Deliver the final executive synthesis for the active mission.

**Precondition (review-before-synthesis gate):** all specialist outputs must have been pressure-tested, and any prod-touching/client-facing/externally-visible output must have cleared its mandatory verifier ([conductor/verification-routing.md](../../../conductor/verification-routing.md)) — the verifier reads primary artifacts, never Tess's summary. Do not finalize on unverified work.

Synthesize using the 10-section executive decision memo from [conductor/output-framework.md](../../../conductor/output-framework.md):

1. Mission Framing
2. Outcome Sought
3. Active Owner and Guilds
4. Key Facts and Signal (flag fact vs inference)
5. Critical Tensions
6. Recommendation
7. Why This Path
8. Immediate Next Moves (specific, sequenced, assigned)
9. Risks to Monitor
10. Optional Upside

Move the mission to AWAITING DECISION / COMPLETED as appropriate ([conductor/mission-states.md](../../../conductor/mission-states.md)). Deliver the final memo through the active runtime's native channel: in Claude Code with the Telegram integration, as a new Telegram reply (not an edit) so the operator's device pings; in any runtime without it (Codex, Gemini CLI, other AGENTS.md tools), as the final answer.
