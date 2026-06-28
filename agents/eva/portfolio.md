---
name: Eva
file: portfolio
---

# Managed Subagent Portfolio

**Maintained by Eva. Last reviewed: 2026-04-14.**

This file is the authoritative record of all agents promoted to managed subagent status. It tracks lifecycle status, tool access, promotion rationale, and review schedule per agent-lifecycle.md §10.

---

## Portfolio Summary

| Count | Status |
|---|---|
| 2 | core |
| 39 | active |
| 0 | standby |
| 0 | dormant |
| 0 | deprecated |
| **41** | **total managed subagents** |

---

## Core Agents

These agents are always active. They are the foundational infrastructure of the system.

| Agent | Role | Tools | Promoted |
|---|---|---|---|
| leah | Senior Researcher & Intelligence Lead | Read, Write, Glob, Grep, WebSearch, WebFetch | 2026-04-08 (founding batch) |
| eva | HR Specialist & AI Talent Strategist | Read, Write, Glob, Grep, WebSearch, WebFetch | 2026-04-08 (founding batch) |

---

## Active Agents

### Coding Team (13)

| Agent | Role | Tools |
|---|---|---|
| freya | Chief Systems Architect | Read, Glob, Grep, WebSearch, WebFetch |
| ada | Lead Backend Engineer | Read, Write, Edit, Bash, Glob, Grep, WebSearch, WebFetch |
| iris | Lead Frontend Engineer | Read, Write, Edit, Bash, Glob, Grep, WebSearch, WebFetch |
| nova | Lead Mobile Engineer | Read, Write, Edit, Bash, Glob, Grep, WebSearch, WebFetch |
| selene | AI and Automation Engineer | Read, Write, Edit, Bash, Glob, Grep, WebSearch, WebFetch |
| vega | DevOps and Infrastructure Engineer | Read, Write, Edit, Bash, Glob, Grep, WebSearch, WebFetch |
| cyra | Security and Risk Engineer | Read, Glob, Grep, Bash, WebSearch, WebFetch |
| quinn | QA and Reliability Architect | Read, Write, Edit, Bash, Glob, Grep, WebSearch, WebFetch |
| elena | Product Engineer | Read, Write, Edit, Glob, Grep, WebSearch, WebFetch |
| josephine | Technical Programme Director | Read, Write, Glob, Grep, WebSearch, WebFetch |
| camille | CTO Strategic Advisor | Read, Glob, Grep, WebSearch, WebFetch |
| reid | Code Quality and Standards Architect | Read, Glob, Grep, Bash |
| petra | Data Engineer | Read, Write, Edit, Bash, Glob, Grep |

### Creative, Design & Visual Systems Guild (8)

| Agent | Role | Tools |
|---|---|---|
| lavinia | Chief Creative Strategist | Read, Write, Glob, Grep, WebSearch, WebFetch |
| alouette | Art Direction and Campaign Visual Lead | Read, Write, Glob, Grep, WebSearch, WebFetch |
| cerise | Brand Design Systems Architect | Read, Write, Glob, Grep, WebSearch, WebFetch |
| eulalie | Experience Styling and Premium Touchpoint Designer | Read, Write, Glob, Grep, WebSearch, WebFetch |
| iseult | Interface Visual Language Strategist | Read, Write, Glob, Grep, WebSearch, WebFetch |
| zelie | Presentation and Deck Design Specialist | Read, Write, Glob, Grep, WebSearch, WebFetch |
| corisande | Motion and Visual Reveal Strategist | Read, Write, Glob, Grep, WebSearch, WebFetch |
| lysandra | Creative Quality and Taste Review Specialist | Read, Write, Glob, Grep, WebSearch, WebFetch |

### Research & Knowledge Systems Guild (8)

| Agent | Role | Tools |
|---|---|---|
| theodora | Chief Research Strategist | Read, Write, Glob, Grep, WebSearch, WebFetch |
| thais | Knowledge Architect | Read, Write, Glob, Grep, WebSearch, WebFetch |
| maialen | Source Reliability and Evidence Specialist | Read, Write, Glob, Grep, WebSearch, WebFetch |
| tamsin | Competitive and Landscape Research Strategist | Read, Write, Glob, Grep, WebSearch, WebFetch |
| ilaria | Case Study and Precedent Analyst | Read, Write, Glob, Grep, WebSearch, WebFetch |
| melisande | Deep Synthesis and Insight Distillation Specialist | Read, Write, Glob, Grep, WebSearch, WebFetch |
| morwenna | Knowledge Retrieval and Library Systems Strategist | Read, Write, Glob, Grep, WebSearch, WebFetch |
| verity | Research QA and Bias Challenge Specialist | Read, Write, Glob, Grep, WebSearch, WebFetch |

### Outcome Orchestrators (6)

| Agent | Role | Tools |
|---|---|---|
| founders-office-orchestrator | Founder's Office Orchestrator | Read, Write, Glob, Grep, WebSearch, WebFetch |
| revenue-orchestrator | Revenue Orchestrator | Read, Write, Glob, Grep, WebSearch, WebFetch |
| product-delivery-orchestrator | Product and Delivery Orchestrator | Read, Write, Glob, Grep, WebSearch, WebFetch |
| client-experience-orchestrator | Client Experience Orchestrator | Read, Write, Glob, Grep, WebSearch, WebFetch |
| strategic-growth-orchestrator | Strategic Growth Orchestrator | Read, Write, Glob, Grep, WebSearch, WebFetch |
| operational-reliability-orchestrator | Operational Reliability Orchestrator | Read, Write, Glob, Grep, WebSearch, WebFetch |

### Guild Leads — Key Dispatch Points (4)

Promoted 2026-04-09. Enables orchestrators to dispatch work to guild leads directly.

| Agent | Role | Tools |
|---|---|---|
| athena | Chief Strategy Officer | Read, Write, Glob, Grep, WebSearch, WebFetch |
| apolline | Chief Sales Strategist | Read, Write, Glob, Grep, WebSearch, WebFetch |
| evangeline | Chief Customer Experience Strategist | Read, Write, Glob, Grep, WebSearch, WebFetch |
| adrienne | Chief of Staff and Executive Operations Lead | Read, Write, Glob, Grep, WebSearch, WebFetch |

---

## Promotion Log

| Date | Agent(s) | Reason |
|---|---|---|
| 2026-04-08 | leah, eva, freya, ada, iris, nova, selene, vega, cyra, quinn, elena, josephine, camille, lavinia, alouette, cerise, eulalie, iseult, zelie, corisande, lysandra, theodora, thais, maialen, tamsin, ilaria, melisande, morwenna, verity | Founding batch — system build. Retroactively documented. |
| 2026-04-09 | All 6 outcome orchestrators | Doctrine compliance — orchestrators defined in conductor/ but had no dispatchable managed subagent files. |
| 2026-04-09 | athena, apolline, evangeline, adrienne | Gap fix — orchestrators (FO, Revenue, CX, ORO) needed their primary guild leads to be dispatchable. |
| 2026-04-14 | reid, petra | Coding team expansion — code quality review and data engineering capabilities added. |

---

## Next Review

**Scheduled:** 2026-07-09 (90 days from founding)

**Review questions per agent-lifecycle.md §6:**
- Does this agent improve outcomes materially?
- Is the mandate still sharp?
- Is the agent activated for the right reasons?
- Is there role confusion?
- Should this role be narrower, broader, split, merged, or retired?

---

## Agents Intentionally Not Promoted

The following guilds remain doctrine-only. Their guild leads are not managed subagents because their primary contribution is advisory (perspective, not execution) and mission evidence for tool dependency has not been demonstrated:

- Strategy Guild specialists (Naomi, Mira, Zara, Helena, Clara, Sienna, Aurora) — Athena covers the dispatch point
- Growth & Revenue Guild (Bianca, Daphne, Colette, etc.)
- Operations & CoS specialists (Sofia, Amara, Elara, etc.) — Adrienne covers the dispatch point
- Data & Analytics Guild
- Product Guild
- Finance & Investor Guild
- Legal & Risk Guild
- Procurement & Vendor Guild
- People & Talent Guild
- Transactions & M&A Guild
- Events & Stagecraft Guild
- Sales & BD specialists — Apolline covers the dispatch point
- CX & Client Success specialists — Evangeline covers the dispatch point
