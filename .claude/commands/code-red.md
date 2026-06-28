---
description: Emergency escalation — classify a situation as CODE RED, pause lower-priority work, activate the relevant orchestrator's recovery mode, and recommend containment first then structural fix.
argument-hint: [situation brief]
---

# /code-red

Emergency escalation for: **$ARGUMENTS**

Activate the emergency protocol:

1. **Classify as CODE RED** — acute revenue loss, client at critical risk, product/prod incident, reputational threat, legal exposure, or operational breakdown at scale.
2. **Pause lower-priority work** to free capacity.
3. **Notify the operator immediately** via Telegram — do not wait for milestones ([conductor/channel-guardrails.md](../../conductor/channel-guardrails.md)).
4. **Activate the relevant orchestrator's recovery mode** ([conductor/outcome-orchestrators/README.md](../../conductor/outcome-orchestrators/README.md)); if cross-orchestrator, Tess synthesises across them via [conductor/outcome-orchestrators/integration.md](../../conductor/outcome-orchestrators/integration.md).
5. **Recommend containment first, then structural fix** — stabilise before root-causing.

For ClientA / live-prod P0 incidents, follow the `clienta-incident` workflow and the narrow incident-ops exception conditions in [conductor/guardrails.md](../../conductor/guardrails.md) Rule 1a. Destructive/prod-mutating remediation stays gated on the operator's explicit authorization (Rule 18). Verification gates still apply before anything externally visible.

**Output:** immediate containment recommendation, escalation path, and Tess-level synthesis if cross-orchestrator.
