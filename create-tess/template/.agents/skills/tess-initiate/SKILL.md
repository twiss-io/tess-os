---
name: tess-initiate
description: "Start a new mission using the legacy flow — equivalent to /add-mission, kept for backward compatibility."
---

<!-- Rendered by `tessctl render --target codex` from .tess/core/commands/initiate.md. Regenerate; do not hand-edit. -->

Tess OS command `/initiate`, packaged as an Agent Skill. Run it only when the user asks for it by name (`$tess-initiate` in Codex).

`$ARGUMENTS` below stands for the text the user supplied with the request (expected: `[mission brief]`).

# /initiate

Legacy alias for [`/add-mission`](../tess-add-mission/SKILL.md). Start a new mission with the brief: **$ARGUMENTS**

Follow the full `/add-mission` flow — three-question intake protocol, framing, task graph, orchestrator designation, routing confirmation before any guild is activated. See [conductor/commands.md](../../../conductor/commands.md) and [conductor/mission-control.md](../../../conductor/mission-control.md). Retained only for backward compatibility; prefer `/add-mission`.
