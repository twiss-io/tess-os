---
name: tess-show-risks
description: "Surface current risks, blockers, unresolved tensions, and early-warning signals for the active mission."
---

<!-- Rendered by `tessctl render --target codex` from .tess/core/commands/show-risks.md. Regenerate; do not hand-edit. -->

Tess OS command `/show-risks`, packaged as an Agent Skill. Run it only when the user asks for it by name (`$tess-show-risks` in Codex).

# /show-risks

Surface the risk picture for the active mission.

Report:
1. **Active risks** — each with severity and owner. Use the severity tiers in [conductor/review-output-standards.md](../../../conductor/review-output-standards.md).
2. **Unresolved tensions** — competing priorities or trade-offs not yet decided.
3. **Open decisions blocking progress** — including anything gating on the operator per [conductor/guardrails.md](../../../conductor/guardrails.md) Rule 18 (credentials, money movement, destructive prod ops, client-external claims).
4. **Early-warning signals** that could stall or fail the mission.
5. **Verification gates outstanding** per [conductor/verification-routing.md](../../../conductor/verification-routing.md).

Read-only. Use before proceeding, or when something feels off.
