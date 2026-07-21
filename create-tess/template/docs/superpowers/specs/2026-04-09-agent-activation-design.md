# Agent Activation Design
**Date:** 2026-04-09  
**Status:** Superseded (see addendum)

> **Addendum 2026-04-09:** This spec approved activation of 29 agents. After the founding batch, a system optimisation pass identified two additional gaps: (1) the 6 outcome orchestrators existed in doctrine but were not dispatchable as managed subagents — promoted 2026-04-09; (2) 4 key guild leads (Athena, Apolline, Evangeline, Adrienne) were needed for orchestrator-to-guild delegation — promoted 2026-04-09. Total managed subagent count is now **42**. See `agents/eva/portfolio.md` for the authoritative record.

---

## Context

The Tess agent roster contains ~141 agents across 16 guilds. All currently exist as doctrine-only files (`agents/<name>/identity.md`, `personality.md`, `soul.md`, `capabilities.md`). None are wired as Claude Code managed subagents.

The question was: activate all, some, or none?

**Decision: selective activation of 29 agents** where managed subagent status provides material execution capability. The remaining ~112 agents stay as doctrine — Tess voices their perspective inline.

**Activation test:** Does this agent use tools, run in parallel, or need context isolation? If not, doctrine is sufficient.

---

## Agents to Activate (29 total)

### Permanent Crew (2)
| Agent | Role |
|---|---|
| Leah | Senior Researcher & Intelligence Lead |
| Eva | HR Specialist & AI Talent Strategist |

### Coding Team (11)
| Agent | Role |
|---|---|
| Freya | Chief Systems Architect |
| Ada | Lead Backend Engineer |
| Iris | Lead Frontend Engineer |
| Nova | Lead Mobile Engineer |
| Selene | AI and Automation Engineer |
| Vega | DevOps and Infrastructure Engineer |
| Cyra | Security and Risk Engineer |
| Quinn | QA and Reliability Architect |
| Elena | Product Engineer |
| Josephine | Technical Program Director |
| Camille | CTO Strategic Advisor |

### Research & Knowledge Guild (8)
| Agent | Role |
|---|---|
| Theodora | Chief Research Strategist |
| Thaïs | Knowledge Architect |
| Maialen | Source Reliability and Evidence Specialist |
| Tamsin | Competitive and Landscape Research Strategist |
| Ilaria | Case Study and Precedent Analyst |
| Mélisande | Deep Synthesis and Insight Distillation Specialist |
| Morwenna | Knowledge Retrieval and Library Systems Strategist |
| Verity | Research QA and Bias Challenge Specialist |

### Creative & Design Guild (8)
| Agent | Role |
|---|---|
| Lavinia | Chief Creative Strategist |
| Alouette | Art Direction and Campaign Visual Lead |
| Cerise | Brand Design Systems Architect |
| Eulalie | Experience Styling and Premium Touchpoint Designer |
| Iseult | Interface Visual Language Strategist |
| Zélie | Presentation and Deck Design Specialist |
| Corisande | Motion and Visual Reveal Strategist |
| Lysandra | Creative Quality and Taste Review Specialist |

---

## Agents NOT Activated (remain as doctrine)

~112 agents across: Strategy, Growth & Revenue, Operations & Chief of Staff, Data & Analytics, Product, Finance & Investor, Legal & Risk, Procurement & Vendor, Sales & BD, Customer Experience, People & Talent, Transactions & M&A, Events & Stagecraft guilds.

Tess voices their perspective inline. No managed subagent overhead.

---

## File Location

Each activated agent gets a file at:
```
.claude/agents/<name>.md
```

Where `<name>` is the lowercase agent name (ASCII only — accented names use ASCII equivalents, e.g., `thais`, `melisande`, `zelie`).

---

## Agent File Structure

```markdown
---
name: <name>
description: <role>. Invoke for <primary use cases>.
model: claude-sonnet-4-6
tools: <comma-separated tool list>
---

[Self-contained system prompt: identity + role + key capabilities + operating rules]
```

**System prompt is self-contained** — not a pointer to `agents/<name>/` doctrine files. The doctrine files remain the detailed human-readable reference. The subagent file has everything it needs inline so it can run without reading other files at activation time.

**Model is Sonnet 4.6 for all** — right balance for execution agents.

---

## Tool Allocation

### Coding Team

| Agent | Tools |
|---|---|
| Freya | Read, Glob, Grep, WebSearch, WebFetch |
| Ada | Read, Write, Edit, Bash, Glob, Grep |
| Iris | Read, Write, Edit, Bash, Glob, Grep |
| Nova | Read, Write, Edit, Bash, Glob, Grep |
| Selene | Read, Write, Edit, Bash, Glob, Grep |
| Vega | Read, Write, Edit, Bash, Glob, Grep |
| Cyra | Read, Glob, Grep, Bash, WebSearch |
| Quinn | Read, Write, Edit, Bash, Glob, Grep |
| Elena | Read, Write, Edit, Glob, Grep |
| Josephine | Read, Write, Glob, Grep |
| Camille | Read, Glob, Grep, WebSearch, WebFetch |

**Rationale for Freya and Camille:** Architects and strategic advisors review and direct — they don't write code or run commands.

**Rationale for Cyra:** Security auditing role — reads and analyses, doesn't build features.

**Rationale for Josephine:** Programme coordination — documents and tracks, no need for Bash.

### Research & Knowledge Guild (all 9 including Leah)

All agents: `Read, Write, Glob, Grep, WebSearch, WebFetch`

### Creative & Design Guild

Base (all 8): `Read, Write, WebSearch, WebFetch`

Iseult and Cerise additionally: `Glob, Grep`
- Rationale: Both work with design system files and need to navigate codebases for visual language and component consistency.

---

## What Stays Unchanged

- All doctrine files in `agents/<name>/` remain untouched — they are the detailed reference
- Tess's orchestration sequence (6 phases) is unchanged
- Eva still recruits mission-specific agents; those continue as doctrine unless promoted
- The remaining 112 doctrine agents are not downgraded — they are properly classified

---

## Promotion Path

**Eva owns all promotion decisions.** Tess does not promote agents unilaterally.

Eva assesses any doctrine agent against three criteria before recommending promotion:
1. Tool dependency — does tool access materially improve their output?
2. Execution mandate — do they produce outputs, not just perspectives?
3. Mission evidence — have real missions demonstrated the gap?

Only when all three are true does Eva draft the `.claude/agents/<name>.md` file and bring it to Tess for approval.

Eva may also recommend demotion — reverting a managed subagent to doctrine-only — if tool access goes unused.
