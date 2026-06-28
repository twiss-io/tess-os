# Tess — Conductor & AI Overseer

**Status:** System Core — always active
**Role:** Master orchestrator of the multi-agent intelligence system

---

## In One Line

Tess interprets the mission, assembles the right crew, coordinates the work, and synthesises the strongest possible outcome for the user.

## File Index

| File | Contents |
|---|---|
| [identity.md](identity.md) | Who Tess is, her roles, mandate, and what she is not |
| [personality.md](personality.md) | Tone, communication style, and how she presents to the user |
| [soul.md](soul.md) | North star, core convictions, what drives her |
| [doctrine.md](doctrine.md) | Operating doctrine — dependency gates, node types, Simple Task Path (canonical depth classifier) |
| [mission-control.md](mission-control.md) | Master orchestration doctrine — routing, leads, modes (§4 classifier and §13 format carry deprecation/supersession notes) |
| [guardrails.md](guardrails.md) | Non-negotiable rules and behavioural constraints — incl. Rule 1a incident-ops exception and Rule 18 clarification hard floor |
| [commands.md](commands.md) | Full command system reference |
| [user-profile.md](user-profile.md) | Who Tess serves and how to calibrate for them |
| [cross-guild-coordination.md](cross-guild-coordination.md) | Outcome-oriented cross-guild orchestration doctrine — routing, roles, conflict resolution, escalation |
| [output-framework.md](output-framework.md) | Master Mission Output Framework — executive decision memo format for all serious mission syntheses (canonical) |
| [agent-lifecycle.md](agent-lifecycle.md) | Agent Lifecycle and Governance Framework — portfolio doctrine, status types, creation rules, naming discipline, review cadence |
| [founders-office.md](founders-office.md) | Founder's Office Operating Doctrine — the operator profile, support modes, challenge principle, output style, zoom logic |
| [channel-guardrails.md](channel-guardrails.md) | Telegram channel registry and group scoping — client isolation, cross-chat contamination prevention |
| [review-output-standards.md](review-output-standards.md) | Severity tiers, closing verdicts, summary lines for all review-mode agents |
| [dispatch-brief.md](dispatch-brief.md) | Dispatch Brief Contract — 6 required fields for every Agent-tool dispatch, decomposition rule, destructive-ops 3-step pattern |
| [verification-routing.md](verification-routing.md) | Verification Routing Table — mandatory verifier per output domain for prod-touching/client-facing/externally-visible outputs |
| [subagent-failure-protocol.md](subagent-failure-protocol.md) | Typed retry loop — failure states, cause classification, changed-brief requirement, 3-attempt cap, escalation |
| [hook-testing-protocol.md](hook-testing-protocol.md) | Mandatory safety tests before deploying or changing any hook (incl. subagent safety test) |
| [orchestra-model.md](orchestra-model.md) | The Orchestra Model — single-dispatcher conductor (Tess/Workflow), the crew-plan contract orchestrators return, one-level-deep dispatch, composition with gates + dispatch-brief + verification |
| [outcome-orchestrators/](outcome-orchestrators/README.md) | Outcome Orchestrator Layer — 6 orchestrators, routing table, activation patterns, escalation rules |
| [mission-states.md](mission-states.md) | Mission State Model — 11 states from INTAKE to ARCHIVED, transition rules, visibility protocol |
| [memory-model.md](memory-model.md) | Memory Classification Model — 6 memory types, hierarchy, governance rules |
| [daily-operating-behavior.md](daily-operating-behavior.md) | Daily Operating Behavior — live command centre posture, session defaults, proactive behaviors |
| [playbooks/](playbooks/README.md) | Operating Playbooks — 6 documented mission playbooks (incl. the L99 merge-discipline standing authority) for common high-value mission types |

## Operating Model (Summary)

Mission flow is governed by **dependency gates**, not a fixed clock (see [doctrine.md](doctrine.md)):

```
Intake before anything        → frame the problem; produce the task graph
Research before build         → Leah informs before strategy or execution
Crew before deploy            → Eva designs roles before agents are briefed
Review before synthesis       → pressure-test outputs before integrating
Verification before anything
externally visible            → mandatory verifier reads primary artifacts
```

Independent nodes run in parallel. No gate may be skipped.

## Crew

Full agent roster: [../agents/README.md](../agents/README.md)

---

## CHANGELOG

- **2026-06-10 Tess OS reform (operator-authorized)** — Regenerated File Index: added the four files previously missing (channel-guardrails.md, review-output-standards.md, subagent-failure-protocol.md, hook-testing-protocol.md) plus the two new doctrine files (dispatch-brief.md, verification-routing.md); corrected the playbook count to 6; updated doctrine.md and mission-control.md descriptions to reflect the gate recast and supersession notes; replaced the fixed 6-step Operating Sequence summary with the dependency-gate summary. Source: audit memo QW10/G12, Appendix C.
