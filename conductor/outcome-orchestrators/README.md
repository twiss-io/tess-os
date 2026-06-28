# Outcome Orchestrator Layer

**Position in System:** Above guilds. Below Tess.  
**Purpose:** Coordinate guilds around business outcomes, not around domains.

Outcome orchestrators are not specialist guilds. They are outcome owners and cross-guild coordinators. They **determine** the leanest high-performance set of guilds required to achieve a defined business outcome and **return it as a structured crew-plan** for Tess (or a Workflow) to dispatch.

Every serious mission should be considered for routing through an outcome orchestrator before routing directly to a single guild.

> **Dispatcher rule (read first).** An outcome orchestrator is a **routing brain, not a dispatcher**. In Claude Code a subagent cannot spawn subagents — only the top-level loop (Tess) or a Workflow holds the Agent/Task tool. So an orchestrator never activates, dispatches, or spawns a guild. It **returns a crew-plan** (the crew-plan contract: which agents, order/parallelism, each with a six-field [dispatch brief](../dispatch-brief.md), gates, and the mandatory verifier); **Tess or a Workflow is the sole dispatcher.** Throughout these files, "activate / assemble / brief a guild" means "name it in the crew-plan you return." Full model: [conductor/orchestra-model.md](../orchestra-model.md).

---

## The Six Outcome Orchestrators

| Orchestrator | Primary Outcome | File |
|---|---|---|
| [Founder's Office](founders-office-orchestrator.md) | Founder decision quality and strategic momentum | founders-office-orchestrator.md |
| [Revenue](revenue-orchestrator.md) | Revenue growth and commercial momentum | revenue-orchestrator.md |
| [Product and Delivery](product-delivery-orchestrator.md) | Product quality, delivery reliability, product-market fit | product-delivery-orchestrator.md |
| [Client Experience](client-experience-orchestrator.md) | Client retention, satisfaction, and lifetime value | client-experience-orchestrator.md |
| [Strategic Growth](strategic-growth-orchestrator.md) | Strategic expansion and long-term competitive positioning | strategic-growth-orchestrator.md |
| [Operational Reliability](operational-reliability-orchestrator.md) | Operational stability, efficiency, and scalable execution | operational-reliability-orchestrator.md |

---

## Outcome Routing Table

Use this table to route missions to the right orchestrator at intake.

| Mission Type | Route To |
|---|---|
| High-stakes directional decision | Founder's Office |
| New venture or investment evaluation | Founder's Office |
| Fundraising, board communication | Founder's Office |
| Executive messaging, personal brand | Founder's Office |
| Sales conversion, pipeline improvement | Revenue |
| Pricing, packaging, offer architecture | Revenue |
| Commercial recovery | Revenue |
| Client acquisition strategy | Revenue |
| New product or feature design | Product and Delivery |
| Build prioritisation and roadmap | Product and Delivery |
| Technical architecture | Product and Delivery |
| Launch readiness | Product and Delivery |
| Client onboarding and retention | Client Experience |
| Churn risk, renewal strategy | Client Experience |
| Client satisfaction improvement | Client Experience |
| Strategic partnership or deal | Strategic Growth |
| Market expansion, new geography | Strategic Growth |
| Competitive positioning | Strategic Growth |
| M&A or joint venture assessment | Strategic Growth |
| Operational breakdown or failure | Operational Reliability |
| Org design and hiring | Operational Reliability |
| Workflow and process optimisation | Operational Reliability |
| Compliance and governance | Operational Reliability |
| Scaling infrastructure | Operational Reliability |

---

## Default Guild Activation Patterns

Minimum viable crew for each orchestrator. Expand only when it materially improves the outcome.

| Orchestrator | Minimum Crew | Common Additions |
|---|---|---|
| Founder's Office | Strategy + Research (Leah) | Finance, Legal, Messaging |
| Revenue | Sales + Analytics | Growth, Finance, Brand, CX |
| Product and Delivery | Product + Coding | Analytics, Design, QA |
| Client Experience | CX + Analytics | Sales, Product, Ops |
| Strategic Growth | Strategy + Research (Leah) | Finance, Legal, Brand, Analytics |
| Operational Reliability | Ops + Analytics | People, Finance, Legal, Coding |

---

## Escalation Rules — Orchestrators to Tess

An orchestrator must escalate to Tess when any of the following conditions are true:

1. **Cross-orchestrator impact** — the mission affects multiple business-critical outcomes across more than one orchestrator
2. **Unresolvable guild conflict** — guild disagreement within the orchestrator cannot be resolved through the cross-guild conflict resolution process
3. **Irreversible, large-scale trade-off** — the decision is non-reversible and has material commercial, strategic, or reputational consequences
4. **Founder-level priority** — the mission directly affects the operator's priorities, values, or long-range direction
5. **No single orchestrator can credibly own the full mission** — the outcome spans more than one primary outcome area

When escalating:
- State the outcome type and the specific reason for escalation
- Provide a summary of guild positions and the nature of the disagreement
- Propose the synthesis options available to Tess

---

## When Tess Routes Through an Orchestrator vs Directly to a Guild

### Use an Outcome Orchestrator when:
- The mission involves more than one guild or domain
- The outcome requires cross-functional coordination
- The mission has commercial, strategic, or operational stakes
- There is a risk of guild sprawl or diffused ownership
- The mission maps clearly to one of the six outcome areas

### Route Directly to a Single Guild when:
- The mission is tightly scoped to a single domain
- Only one type of specialist input is required
- The task is execution, not decision
- Speed matters more than coordination
- The user has explicitly specified the guild

### Never:
- Activate multiple guilds without routing through an orchestrator or assigning explicit cross-guild roles
- Allow a mission to proceed without a designated outcome owner
- Default to orchestrator routing out of habit — use it because it improves the outcome

---

## Integration Doctrine

Cross-orchestrator routing rules, precedence logic, master routing matrix, and structural audit:  
**[integration.md](integration.md)**

Key resolved boundaries:
- FO vs SGO on positioning: FO = whole-business identity · SGO = market-specific
- Revenue vs SGO on new models: SGO leads model decisions · Revenue leads execution
- CX vs Revenue on expansion: CX owns timing · Revenue owns commercial motion
- P&D vs ORO on infrastructure: P&D = product-facing · ORO = internal/operational
- CX vs ORO on delivery failures: CX acts first (trust) · ORO acts in parallel (root cause)
- SGO vs FO on M&A: SGO leads assessment · FO takes over at commitment

---

## System Laws Governing This Layer

All outcome orchestrators must operate under the following system-level laws:

| Law | Source |
|---|---|
| Cross-Guild Coordination Protocol | [../cross-guild-coordination.md](../cross-guild-coordination.md) |
| Master Mission Output Framework | [../output-framework.md](../output-framework.md) |
| Agent Lifecycle and Governance Framework | [../agent-lifecycle.md](../agent-lifecycle.md) |
| Founder's Office Operating Doctrine | [../founders-office.md](../founders-office.md) |
