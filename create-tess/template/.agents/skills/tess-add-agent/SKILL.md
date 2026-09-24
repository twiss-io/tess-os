---
name: tess-add-agent
description: "Cover a capability gap without adding an agent — the roster is fixed at ten roles, so the gap becomes a lens (new or extended) loaded into a role's brief."
---

<!-- Rendered by `tessctl render --target codex` from .tess/core/commands/add-agent.md. Regenerate; do not hand-edit. -->

Tess OS command `/add-agent`, packaged as an Agent Skill. Run it only when the user asks for it by name (`$tess-add-agent` in Codex).

`$ARGUMENTS` below stands for the text the user supplied with the request (expected: `[Name or capability needed]`).

# /add-agent

Capability needed: **$ARGUMENTS**

The roster is fixed at ten roles defined by permissions ([conductor/roster.md](../../../conductor/roster.md)). Expertise comes from lenses ([conductor/lenses/README.md](../../../conductor/lenses/README.md)). So:

1. Apply the `eva` lens ([conductor/lenses/eva.md](../../../conductor/lenses/eva.md)): what must the task DO (picks the role) and KNOW (picks the lens)?
2. If an existing lens covers it, use that lens. Say which.
3. If none does, draft a new lens at `conductor/lenses/<name>.md` in the same shape (Use when, Focus, Brings, Questions and principles, Output shape, Guardrails) and add it to the index. A lens never adds permissions.
4. Never create a new `.claude/agents/<name>.md` file. If the gap is a permission the ten roles lack, stop and raise it with the operator.

Confirm with the operator before adding a lens that changes how client work is reviewed.
