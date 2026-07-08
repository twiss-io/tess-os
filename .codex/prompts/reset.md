---
description: Reset the working context for the current mission — clear active mission state for a fresh start while preserving all doctrine, crew, and system architecture.
---

# /reset

Clear the active mission state and start fresh.

- **Clears:** the current mission's working state, task graph, and in-flight framing.
- **Preserves:** Tess's full doctrine ([conductor/](../../conductor/README.md)), the agent roster ([agents/README.md](../../agents/README.md)), System Laws, and the orchestrator structure. `/reset` never alters system laws or orchestrator architecture.

Before clearing, confirm with the operator if there is unsaved mission work worth logging to `kb/wiki/` first. Use when mission direction has fundamentally changed or a clean start is needed.
