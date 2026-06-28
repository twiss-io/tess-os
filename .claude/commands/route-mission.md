---
description: Re-evaluate the orchestrator assignment for the active mission — confirm, transfer, or split ownership using the routing doctrine and integration precedence rules.
---

# /route-mission

Re-evaluate routing for the active mission. Apply the orchestrator selection doctrine in [conductor/outcome-orchestrators/README.md](../../conductor/outcome-orchestrators/README.md) and the overlap-resolution / precedence rules in [conductor/outcome-orchestrators/integration.md](../../conductor/outcome-orchestrators/integration.md).

1. Re-run the three-question intake test against the mission **as it stands now** (scope may have shifted since intake).
2. Compare the current orchestrator against the routing matrix.
3. Resolve overlaps with the precedence rules; identify whether the outcome now spans more than one orchestrator.

**Output — one of:**
- **Retain** current orchestrator (with rationale), or
- **Transfer** to another orchestrator (name it + why), or
- **Split** ownership (primary + supporting, with the coordination boundary).

Use when the mission has evolved or routing feels wrong. Routing change only — does not execute mission work.
