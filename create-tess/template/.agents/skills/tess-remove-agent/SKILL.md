---
name: tess-remove-agent
description: "Retire a lens, or bench one of the nine roles for a stated reason — the ten-role roster itself is fixed."
---

<!-- Rendered by `tessctl render --target codex` from .tess/core/commands/remove-agent.md. Regenerate; do not hand-edit. -->

Tess OS command `/remove-agent`, packaged as an Agent Skill. Run it only when the user asks for it by name (`$tess-remove-agent` in Codex).

`$ARGUMENTS` below stands for the text the user supplied with the request (expected: `[Name]`).

# /remove-agent

Assess removal of: **$ARGUMENTS**

1. If it is a lens ([conductor/lenses/](../../../conductor/lenses/README.md)): check no active mission brief loads it, then remove it from the index or mark it retired, and say what covers that expertise now.
2. If it is one of the nine roles ([conductor/roster.md](../../../conductor/roster.md)): `tessctl bench <name>` stages it. Benching Reid, Quinn or Cyra removes a mandatory verifier (conductor/verification-routing.md); do it only with the operator's explicit reason, and say what verifies in its place.
3. Confirm no active mission depends on it before removal.

Confirm with the operator before removing anything tied to live client work.
