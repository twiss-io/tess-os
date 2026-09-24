---
name: tess-show-owner
description: "Display the current outcome owner and orchestrator assignment, with ownership rationale and any co-ownership arrangements."
---

<!-- Rendered by `tessctl render --target codex` from .tess/core/commands/show-owner.md. Regenerate; do not hand-edit. -->

Tess OS command `/show-owner`, packaged as an Agent Skill. Run it only when the user asks for it by name (`$tess-show-owner` in Codex).

# /show-owner

Return the ownership picture for the active mission, per [conductor/outcome-orchestrators/README.md](../../../conductor/outcome-orchestrators/README.md) and [conductor/outcome-orchestrators/integration.md](../../../conductor/outcome-orchestrators/integration.md):

- **Mission name**
- **Outcome orchestrator** (the coordination layer that owns the outcome)
- **Outcome owner** (the accountable lead)
- **Ownership rationale** — why this orchestrator holds it
- **Co-ownership / split arrangements**, if any, and the boundary between them

Read-only. Use when ownership is unclear or needs confirming.
