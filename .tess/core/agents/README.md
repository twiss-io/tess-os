# Tess — Agent Roster

This is the canonical index for the Tess intelligence system. As of 2026-06-27, **all 150 agents are dispatchable** via `.claude/agents/<name>.md`. The two-class distinction (DISPATCHABLE vs PERSONA) no longer applies — every agent in this index has a definition file.

---

## Roster at a Glance

| Tier | Count | Purpose |
|---|---|---|
| **Core** | 16 | Always-on. Activated on every mission. Never leave this out. |
| **Guild Packs** | 134 | Domain specialists. Activated by Eva based on mission requirements. |
| **Total Dispatchable** | **150** | All have `.claude/agents/<name>.md` definitions. |

---

## Resolved Overlaps (2026-06-27 review)

Six routing confusions were identified and resolved. The agents are retained — the routing rules are now explicit:

| Pair | Confusion | Resolution |
|---|---|---|
| **Tamsin vs Mira** | Both "map competitive landscape" | Tamsin (Research Guild) = primary intelligence gatherer, produces landscape research artifacts. Mira (Strategy Guild) = market signal interpreter, translates external intelligence into strategic implications. Tamsin feeds Mira. Route intelligence research → Tamsin; market strategy judgment → Mira. |
| **Mira vs Sienna** | Both touch "competitive landscape" | Mira = market landscape and timing (what is the market doing, is it ready, where is the white space). Sienna = competitive differentiation and positioning (why THIS offering wins relative to named alternatives). Sienna works downstream of Mira's landscape read. |
| **Danica vs Zinnia** | Both synthesise data into decisions | Danica = upstream analytics framing (what to measure, measurement strategy, signal identification — called BEFORE analysis). Zinnia = downstream cross-functional synthesis (multiple findings → one prioritised recommendation — called AFTER analysis). Sequential, not duplicates. |
| **Leah vs Theodora** | Both offer research leadership | Leah = first responder at the research gate; executes all research directly on every mission. Theodora = research program architect; activates only when running a multi-agent research program requiring strategic direction across guild specialists. Theodora does not replace Leah — she multiplies her. |
| **Bianca vs Apolline** | Scope overlap at "conversion strategy" | Bianca (Growth Guild) = full commercial system diagnosis and growth strategy (acquisition + conversion + retention as a system). Apolline (Sales Guild) = sales execution strategy and pipeline architecture. Revenue Orchestrator defaults to Apolline for sales-specific missions, Bianca for commercial system-level diagnosis. |
| **Colette vs Elodie** | Both reduce friction and design flows | Colette = commercial funnel conversion friction (marketing/sales funnel context). Elodie = in-product UX friction (product experience and interaction logic). Context determines routing: marketing/sales funnel → Colette; in-product experience → Elodie. |

---

## Core Crew (16 agents — always on)

These agents are active on every mission. Eva does not need to recruit them — they are already in the room.

### Permanent Crew (3)

| Agent | Role | When |
|---|---|---|
| [Leah](leah/) | Senior Researcher & Intelligence Lead | Research gate — always first, before any specialist moves |
| [Eva](eva/) | HR Specialist & AI Talent Strategist | Crew gate — after research, before deployment |
| [Clio](clio/) | Session Scribe and Minute-Taker | Continuous — session logs, context retrieval across restarts |

### Outcome Orchestrators (6)

Sit above guilds and below Tess. Each produces crew plans for Tess to dispatch. They do not execute specialist work themselves.

| Orchestrator | Outcome Owned |
|---|---|
| founders-office-orchestrator | Founder decision quality and strategic momentum |
| revenue-orchestrator | Revenue creation, quality, momentum, and expansion |
| product-delivery-orchestrator | Product quality, delivery reliability, product-market fit |
| client-experience-orchestrator | Client retention, trust, satisfaction, and lifetime value |
| strategic-growth-orchestrator | Strategic expansion and long-term competitive positioning |
| operational-reliability-orchestrator | Operational stability and scalable execution |

Full doctrine: [conductor/outcome-orchestrators/](../conductor/outcome-orchestrators/)

### Key Cross-Cutting Specialists (7)

These specialists anchor the most frequently recurring mission types. Eva selects additional guild members around them.

| Agent | Role | Guild |
|---|---|---|
| [Ada](ada/) | Lead Backend Engineer | Coding |
| [Iris](iris/) | Lead Frontend Engineer | Coding |
| [Cyra](cyra/) | Security and Risk Engineer | Coding |
| [Reid](reid/) | Code Quality and Standards Architect | Coding |
| [Quinn](quinn/) | QA and Reliability Architect | Coding |
| [Vega](vega/) | DevOps and Infrastructure Engineer | Coding |
| [Elena](elena/) | Product Engineer | Coding |

---

## Guild Packs (134 agents — activated by Eva)

Guild pack activation: Eva selects the minimum agents required for the mission. Default to the guild anchor first. Add specialists only when the mission clearly requires their specific domain.

---

### 1. Research Guild (8 agents)

**Anchor:** Theodora  
**Trigger:** Research strategy and knowledge programs requiring structured guild deployment  
**Note:** Leah (Core) handles all direct research. Theodora activates when running a multi-agent research program.

| Agent | Role |
|---|---|
| [Theodora](theodora/) | Chief Research Strategist — frames what must be known and at what confidence |
| [Thaïs](thais/) | Knowledge Architect — designs how intelligence is organised for long-term reuse |
| [Tamsin](tamsin/) | Competitive and Landscape Research Strategist — primary intelligence gatherer for market and competitor terrain |
| [Ilaria](ilaria/) | Case Study and Precedent Analyst — identifies comparable situations and transferable lessons |
| [Mélisande](melisande/) | Deep Synthesis and Insight Distillation Specialist — turns research volume into decision-ready clarity |
| [Morwenna](morwenna/) | Knowledge Retrieval and Library Systems Strategist — surfaces prior intelligence from knowledge bases |
| [Verity](verity/) | Research QA and Bias Challenge Specialist — pressure-tests conclusions before they drive decisions |
| [Maialen](maialen/) | Source Reliability and Evidence Specialist — audits source quality and evidence strength |

---

### 2. Creative-Design Guild (16 agents)

**Two sub-guilds, one activation sweep. Lavinia leads visual; Celeste leads verbal.**  
**Trigger:** Any mission with a visual design, brand aesthetic, creative direction, narrative, or messaging layer.

#### Visual and Design Sub-Guild

| Agent | Role |
|---|---|
| [Lavinia](lavinia/) | Chief Creative Strategist — aesthetic north star; escalation point for consequential creative decisions |
| [Alouette](alouette/) | Art Direction and Campaign Visual Lead — art direction, campaign visual execution |
| [Cerise](cerise/) | Brand Design Systems Architect — typography, colour tokens, layout logic, cross-component consistency |
| [Eulalie](eulalie/) | Experience Styling and Premium Touchpoint Designer — premium physical and digital touchpoints |
| [Iseult](iseult/) | Interface Visual Language Strategist — screen-level aesthetic direction; consulted before any UI code |
| [Zélie](zelie/) | Presentation and Deck Design Specialist — decks, presentations, visual storytelling |
| [Corisande](corisande/) | Motion and Visual Reveal Strategist — animation, transitions, scroll reveals, micro-interaction |
| [Lysandra](lysandra/) | Creative Quality and Taste Review Specialist — final taste check; flags generic choices and incoherence |

#### Brand and Communications Sub-Guild

| Agent | Role |
|---|---|
| [Celeste](celeste/) | Brand Strategist — strategic anchor; brand positioning, message architecture, verbal brand coherence |
| [Vivienne](vivienne/) | Narrative Architect — long-form narrative, founder story, brand narrative structure |
| [Simone](simone/) | Copy Chief — finished copy, wording, and editorial execution |
| [Isadora](isadora/) | Founder Voice and Executive Communications Specialist — the operator's voice, executive content |
| [Margot](margot/) | PR and Reputation Strategist — media relations, reputation management, press narrative |
| [Thea](thea/) | Campaign and Creative Strategy Lead — campaign concepting and execution |
| [Eloise](eloise/) | Audience Messaging Strategist — audience-specific message adaptation |
| [Noelle](noelle/) | Verbal Identity and Editorial Standards Lead — language standards, tone of voice, editorial consistency |

---

### 3. Coding Guild (6 agents)

**Note:** The 7 cross-cutting coding specialists (Ada, Iris, Cyra, Reid, Quinn, Vega, Elena) are in Core. These 6 handle architecture, infrastructure platforms, AI systems, and programme delivery.

| Agent | Role | Layer |
|---|---|---|
| [Freya](freya/) | Chief Systems Architect | Architecture, platform design, structural decisions |
| [Nova](nova/) | Lead Mobile Engineer | Mobile architecture, device-aware behaviour |
| [Selene](selene/) | AI and Automation Engineer | AI workflows, LLM orchestration, agent systems |
| [Josephine](josephine/) | Technical Program Director | Cross-functional engineering coordination, sequencing |
| [Camille](camille/) | CTO Strategic Advisor | Technical strategy, platform bets, buy-vs-build |
| [Petra](petra/) | Data Engineer | Schema design, migrations, query optimisation |

Full coding team doctrine: [coding-team.md](coding-team.md)

---

### 4. Commercial-Revenue Guild (24 agents)

**Three sub-guilds. Revenue Orchestrator routes across all three.**

#### Growth and Revenue Sub-Guild

**Anchor:** Bianca — diagnoses the full commercial system before any specialist is activated.

| Agent | Role |
|---|---|
| [Bianca](bianca/) | Chief Growth Strategist — commercial system diagnosis, full-funnel growth direction |
| [Daphne](daphne/) | Demand Generation Strategist — top-of-funnel demand engine design |
| [Colette](colette/) | Conversion Architect — commercial funnel leak diagnosis and conversion optimisation |
| [Renée](renee/) | Customer Lifecycle and Retention Strategist — lifecycle value, churn economics |
| [Paloma](paloma/) | Revenue Operations Strategist — revenue operations, forecasting, pipeline visibility |
| [Gia](gia/) | Performance Marketing Strategist — paid channels, performance media |
| [Marina](marina/) | Partnerships and Channel Growth Strategist — partner-led and channel demand |
| [Talia](talia/) | Offer and Monetisation Performance Strategist — offer design, pricing performance |

#### Sales and Business Development Sub-Guild

**Anchor:** Apolline — called for sales posture, pipeline diagnosis, and conversion logic.

| Agent | Role |
|---|---|
| [Apolline](apolline/) | Chief Sales Strategist — sales posture, pipeline architecture, conversion logic |
| [Bettina](bettina/) | Sales Systems Architect — CRM, pipeline systems, sales process infrastructure |
| [Domitille](domitille/) | Key Accounts and Enterprise Strategy Lead — enterprise and key account strategy |
| [Roxane](roxane/) | Business Development and Outbound Strategist — outbound and BD strategy |
| [Gaïane](gaiane/) | Consultative Conversion Specialist — consultative selling and trust-led conversion |
| [Ondine](ondine/) | Objection Handling and Closing Strategist — deal closing and objection handling |
| [Bérénice](berenice/) | Account Expansion and Renewal Strategist — account growth and renewal |
| [Xanthe](xanthe/) | Sales Enablement and Pipeline Discipline Specialist — sales enablement and hygiene |

#### Finance and Investor Sub-Guild

**Anchor:** Octavia — financial strategy and capital structure before financial specialists.

| Agent | Role |
|---|---|
| [Octavia](octavia/) | Chief Financial Strategist — financial strategy, capital structure, investor positioning |
| [Beatrice](beatrice/) | Financial Modelling Architect — financial models, scenario analysis |
| [Alessia](alessia/) | Capital Strategy and Fundraising Advisor — fundraising strategy and investor approach |
| [Juliette](juliette/) | Investor Narrative and Board Communications Strategist — investor decks, board communications |
| [Estelle](estelle/) | Unit Economics and Profitability Strategist — unit economics, margin analysis |
| [Rosalie](rosalie/) | Budgeting and Resource Allocation Strategist — budgeting and resource planning |
| [Emmeline](emmeline/) | Cash Flow and Financial Risk Analyst — cash flow management and financial risk |
| [Valeria](valeria/) | Valuation and Deal Economics Specialist — valuation, deal terms, financial diligence |

---

### 5. Strategy Guild (8 agents)

**Anchor:** Athena — called first for strategic framing, direction, and prioritisation.  
**Trigger:** Strategic Growth Orchestrator or Founder's Office Orchestrator missions requiring strategic advisory depth.

| Agent | Role |
|---|---|
| [Athena](athena/) | Chief Strategy Officer — strategic framing, direction, and prioritisation |
| [Naomi](naomi/) | Business Model Strategist — monetisation logic, value capture, commercial model design |
| [Mira](mira/) | Market Intelligence Strategist — external market signals, timing, opportunity mapping (interprets what Tamsin researches) |
| [Zara](zara/) | Go-To-Market Strategist — launch sequencing, channels, traction, market entry |
| [Helena](helena/) | Partnership and Ecosystem Strategist — strategic alliances, distribution, ecosystem leverage |
| [Clara](clara/) | Decision Analyst — structured options, evaluation criteria, rigorous choice |
| [Sienna](sienna/) | Competitive Positioning Strategist — differentiation logic, value proposition, why this wins |
| [Aurora](aurora/) | Venture and Innovation Strategist — new ventures, adjacency opportunities, expansion bets |

Full strategy guild doctrine: [strategy-guild.md](strategy-guild.md)

---

### 6. Client-Experience Guild (16 agents)

**Two sub-guilds. Client Experience Orchestrator routes across both.**

#### Client Success and CX Sub-Guild

**Anchor:** Evangeline — called first for CX strategy, retention posture, and trust architecture.

| Agent | Role |
|---|---|
| [Evangeline](evangeline/) | Chief Customer Experience Strategist — CX strategy, retention posture, trust architecture |
| [Cressida](cressida/) | Client Journey and Onboarding Architect — onboarding flow, sale-to-service handoff |
| [Fiorella](fiorella/) | Client Success and Retention Strategist — post-onboarding lifecycle, quiet churn detection |
| [Yselle](yselle/) | Service Recovery and Trust Repair Specialist — trust repair after service failures |
| [Mariselle](mariselle/) | Voice of Customer and Feedback Systems Strategist — client insight and feedback loops |
| [Orielle](orielle/) | Community and Belonging Strategist — community design and belonging systems |
| [Jessamine](jessamine/) | Advocacy, Referral, and Testimonial Strategist — referral systems, testimonial strategy |
| [Callista](callista/) | Premium Service Experience Designer — premium touchpoint and service experience design |

#### Events and Experiences Sub-Guild

**Anchor:** Zéphirine — called for event strategy and live experience design.

| Agent | Role |
|---|---|
| [Zéphirine](zephirine/) | Chief Event Experience Strategist — event strategy, audience journey, commercial design |
| [Liora](liora/) | Audience Journey and Flow Architect — how audiences move through events |
| [Virelai](virelai/) | Stagecraft and Show Flow Director — show direction, production flow, technical staging |
| [Jovienne](jovienne/) | Speaker and Host Experience Strategist — speaker experience, host coaching |
| [Zorine](zorine/) | Event Conversion and Commercial Experience Strategist — event-led commercial activation |
| [Hesper](hesper/) | Backstage Operations and Show Control Strategist — backstage ops and technical control |
| [Opaline](opaline/) | Experiential Atmosphere and Guest Delight Designer — atmosphere, guest experience, delight |
| [Queniva](queniva/) | Event Quality and Rehearsal Review Specialist — rehearsal review, event QA |

---

### 7. Operations Guild (24 agents)

**Three sub-guilds. Operational Reliability Orchestrator routes across all three.**

#### Operations and Chief of Staff Sub-Guild

**Anchor:** Adrienne — called for executive prioritisation, cross-functional alignment, strategic-to-operational translation.

| Agent | Role |
|---|---|
| [Adrienne](adrienne/) | Chief of Staff and Executive Operations Lead — executive prioritisation, founder focus protection |
| [Sofia](sofia/) | Programme and Delivery Strategist — programme structure, delivery tracking |
| [Amara](amara/) | Process and Workflow Architect — process design, workflow architecture |
| [Elara](elara/) | Prioritisation and Decision Flow Specialist — decision queues, prioritisation systems |
| [Nadia](nadia/) | Accountability and Follow-Through Architect — accountability systems, commitment tracking |
| [Lucienne](lucienne/) | Internal Communications and Alignment Specialist — internal comms, alignment systems |
| [Céline](celine/) | Meeting and Decision Systems Specialist — meeting design, decision hygiene |
| [Mireille](mireille/) | Organisational Rhythm and Operating Cadence Strategist — operating cadence design |

#### Procurement, Vendor, and Strategic Sourcing Sub-Guild

**Anchor:** Verena — called for vendor strategy, sourcing decisions, and procurement governance.

| Agent | Role |
|---|---|
| [Verena](verena/) | Chief Procurement Strategist — procurement strategy, sourcing decisions |
| [Sabella](sabella/) | Strategic Sourcing Architect — sourcing architecture and supplier strategy |
| [Vespera](vespera/) | Vendor Evaluation and Due Diligence Specialist — vendor assessment and diligence |
| [Ottilie](ottilie/) | Commercial Terms and Pricing Strategist — contract terms, pricing negotiation |
| [Lucasta](lucasta/) | Vendor Performance and SLA Strategist — vendor SLA design and performance governance |
| [Isolde](isolde/) | Supplier Risk and Dependency Analyst — supply chain risk, dependency analysis |
| [Floriane](floriane/) | Procurement Operations and Governance Specialist — procurement ops and governance |
| [Briony](briony/) | Inventory, Supply Continuity, and Fulfilment Alignment Strategist — supply continuity |

#### People, Talent, and Organisational Design Sub-Guild

**Anchor:** Marcelline — called for people strategy, org design, and talent architecture.

| Agent | Role |
|---|---|
| [Marcelline](marcelline/) | Chief People Strategist — people strategy, talent architecture, org effectiveness |
| [Maëlle](maelle/) | Organisational Design Architect — org structure design |
| [Nerissa](nerissa/) | Talent Acquisition and Workforce Planning Strategist — hiring strategy, workforce planning |
| [Coralie](coralie/) | Leadership and Management Effectiveness Advisor — leadership development, management quality |
| [Imogen](imogen/) | Performance and Accountability Systems Strategist — performance systems |
| [Amandine](amandine/) | Culture and Behaviour Systems Strategist — culture design, values-in-practice |
| [Elspeth](elspeth/) | Compensation and Incentive Design Strategist — comp architecture, incentive design |
| [Rowena](rowena/) | Succession and Talent Density Strategist — succession planning, key-role depth |

---

### 8. Knowledge Guild (8 agents)

**Analytics, data intelligence, and measurement. Danica leads; Zinnia synthesises.**  
**Trigger:** Any mission requiring measurement strategy, analytics framing, KPI design, or cross-functional signal synthesis.

| Agent | Role |
|---|---|
| [Danica](danica/) | Chief Analytics Strategist — what to measure, measurement strategy, signal identification (upstream) |
| [Linnea](linnea/) | Business Intelligence Architect — BI reporting frameworks, dashboard architecture, metric hierarchies |
| [Yvette](yvette/) | Experimentation and Insights Strategist — A/B testing, experiment design, insight extraction |
| [Alina](alina/) | Attribution and Measurement Strategist — attribution modelling, measurement frameworks |
| [Soraya](soraya/) | Customer and Behaviour Insights Analyst — behavioural intelligence, customer patterns |
| [Clarisse](clarisse/) | KPI and Dashboard Architect — KPI definitions, metric specifications, scorecard design |
| [Noemi](noemi/) | Data Quality and Reporting Integrity Specialist — data quality governance, reporting accuracy |
| [Zinnia](zinnia/) | Decision Intelligence Strategist — cross-functional signal synthesis → prioritised recommendation (downstream) |

---

### 9. Product Guild (8 agents)

**Trigger:** Product strategy, discovery, user experience design, roadmap, and MVP decisions.  
**Anchor:** Livia — called for product framing and prioritisation before any specialist activates.

| Agent | Role |
|---|---|
| [Livia](livia/) | Chief Product Strategist — product framing, prioritisation, MVP definition, product-business alignment |
| [Arielle](arielle/) | Product Discovery Lead — user problem validation, assumption mapping, discovery-grounded go/no-go |
| [Elodie](elodie/) | User Experience Architect — in-product UX flows, friction reduction, interaction coherence |
| [Valina](valina/) | Feature Systems Strategist — feature architecture, scope logic, feature system coherence |
| [Mireya](mireya/) | Service and Experience Design Strategist — service design, touchpoint architecture |
| [Oriana](oriana/) | Product Prioritisation and Roadmap Strategist — roadmap design, sequencing logic |
| [Violette](violette/) | Product-Market Fit and Adoption Strategist — PMF signal, adoption and activation strategy |
| [Anaïs](anais/) | Product Quality and Experience Review Specialist — product experience QA, usability review |

---

### 10. Legal-Risk Guild (8 agents)

**Trigger:** Any mission with legal, compliance, regulatory, governance, or contract exposure.  
**Anchor:** Victoria — called first for legal strategy framing.

| Agent | Role |
|---|---|
| [Victoria](victoria/) | Chief Legal Strategist — legal strategy, governance structure, legal risk posture |
| [Geneviève](genevieve/) | Contract Architecture Specialist — contract structure, terms, and legal framework design |
| [Sabine](sabine/) | Regulatory and Compliance Strategist — regulatory landscape, compliance programme design |
| [Séraphine](seraphine/) | Risk and Exposure Analyst — legal risk identification, exposure quantification |
| [Corinne](corinne/) | Governance and Policy Architect — governance frameworks, internal policy design |
| [Madeleine](madeleine/) | Dispute and Liability Strategist — dispute strategy, liability management |
| [Delphine](delphine/) | Negotiation Risk and Deal Terms Specialist — deal terms risk, negotiation strategy |
| [Aveline](aveline/) | Data Protection and Privacy Advisor — data privacy, PDPA/GDPR compliance |

---

### 11. Transactions and M&A Guild (8 agents)

**Trigger:** M&A evaluation, deal structuring, licensing, joint ventures, and strategic transaction diligence.  
**Anchor:** Cecily — called first for deal strategy and transaction framing.

| Agent | Role |
|---|---|
| [Cecily](cecily/) | Chief Transactions Strategist — deal strategy, transaction framing, M&A direction |
| [Leonora](leonora/) | M&A and Corporate Development Strategist — M&A target identification and evaluation |
| [Odette](odette/) | Deal Structuring and Terms Architect — deal structure, term sheet architecture |
| [Fleur](fleur/) | Licensing and Commercial Rights Strategist — licensing strategy, IP commercialisation |
| [Romilly](romilly/) | Diligence and Transaction Risk Lead — due diligence, transaction risk assessment |
| [Cosima](cosima/) | Synergy and Integration Value Strategist — synergy quantification, integration design |
| [Tatienne](tatienne/) | Negotiation and Deal Dynamics Specialist — negotiation strategy and deal dynamics |
| [Evelina](evelina/) | Strategic Alliance and Joint Venture Structuring Advisor — JV and alliance design |

---

## Operating Sequence

```
Mission Intake (Tess)
        ↓
Research Gate — Leah (always first)
        ↓
Crew Gate — Eva (after research, before deployment)
        ↓
Orchestrator Activation (Tess routes to the right outcome orchestrator)
        ↓
Guild Specialist Deployment (orchestrator returns crew plan; Tess dispatches)
        ↓
Review Gate — domain verifier (Reid / Quinn / Cyra / Verity / Maialen / Lysandra)
        ↓
Synthesis (Tess → the operator via Telegram)
```

---

## Routing Quick Reference

| If the mission is about... | Start with... |
|---|---|
| Any research or intelligence gap | Leah |
| Crew design and agent selection | Eva |
| Revenue and commercial momentum | revenue-orchestrator → Apolline (sales) or Bianca (full system) |
| Major strategic moves | strategic-growth-orchestrator → Athena |
| Founder decisions and priorities | founders-office-orchestrator |
| Product quality and delivery | product-delivery-orchestrator → Livia (strategy) or Elena (engineering) |
| Client retention and trust | client-experience-orchestrator → Evangeline |
| Operational reliability | operational-reliability-orchestrator → Adrienne |
| Competitive intelligence research | Tamsin (gather) → Mira (interpret) → Sienna (position) |
| Analytics and measurement | Danica (what to measure) → Linnea/Clarisse (how to measure) → Zinnia (synthesise) |
| Brand visual | Lavinia → Cerise / Iseult / Alouette |
| Brand verbal and messaging | Celeste → Vivienne → Simone |
| Code review and quality | Reid |
| Security and access control | Cyra |
| Deployment and infrastructure | Vega |
| Test confidence and release | Quinn |

---

## Further Reading

| Document | Purpose |
|---|---|
| [intelligence-staffing.md](intelligence-staffing.md) | Intelligence and talent command doctrine |
| [coding-team.md](coding-team.md) | Full coding team doctrine |
| [brand-guild.md](brand-guild.md) | Brand and communications guild doctrine |
| [strategy-guild.md](strategy-guild.md) | Strategy guild doctrine |
| [growth-guild.md](growth-guild.md) | Growth and revenue guild doctrine |
| [ops-guild.md](ops-guild.md) | Operations and chief of staff guild doctrine |
| [data-analytics-guild.md](data-analytics-guild.md) | Data, analytics and intelligence guild doctrine |
| [product-guild.md](product-guild.md) | Product guild doctrine |
| [finance-investor-guild.md](finance-investor-guild.md) | Finance and investor guild doctrine |
| [legal-risk-guild.md](legal-risk-guild.md) | Legal and risk guild doctrine |
| [procurement-vendor-guild.md](procurement-vendor-guild.md) | Procurement, vendor and sourcing guild doctrine |
| [people-talent-guild.md](people-talent-guild.md) | People, talent and organisational design guild doctrine |
| [transactions-ma-guild.md](transactions-ma-guild.md) | Transactions, M&A and strategic deals guild doctrine |
| [cx-client-success-guild.md](cx-client-success-guild.md) | Customer experience and client success guild doctrine |
| [events-stagecraft-guild.md](events-stagecraft-guild.md) | Events, experiences and stagecraft guild doctrine |
| [research-knowledge-guild.md](research-knowledge-guild.md) | Research and knowledge guild doctrine |
| [creative-design-guild.md](creative-design-guild.md) | Creative, design and visual systems guild doctrine |
| [eva/hiring-framework.md](eva/hiring-framework.md) | Eva's hiring criteria and framework |
