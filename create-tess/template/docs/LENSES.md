# Lens Library

> Generated from `.tess/core/conductor/lenses/` (live copy: `conductor/lenses/`). Edit the lens files, not this index.

A lens is a short expertise brief the conductor loads into a role's dispatch when the task needs it. Lenses are not agents: they are never registered, never dispatched on their own, and never widen a role's permissions. The ten roles are in [`conductor/roster.md`](../conductor/roster.md).

## How to load a lens

1. Pick the role by what the task must DO (build, search, research, review, test, sign, record, release, design).
2. Pick at most two lenses by what the task must KNOW, from the table below.
3. In the dispatch brief, add a line `Lens: conductor/lenses/<name>.md` (one per lens). The role reads the file and applies its questions, output shape and quality bar.

Example: a pricing review is Leah (Researcher) with the `naomi` lens; a landing page is Iris (Designer) with the `simone` lens for copy; a research claim's verification is Reid with the `verity` and `maialen` lenses.

## Default lenses by starter path

Every starter path installs the same ten roles. The path only changes which lenses the conductor suggests first.

| Starter path | Suggested lenses |
|---|---|
| `founders` | `founders-office-orchestrator`, `revenue-orchestrator`, `athena`, `apolline`, `naomi`, `sienna`, `zelie` |
| `builders` | `product-delivery-orchestrator`, `elena`, `freya`, `petra`, `selene`, `josephine` |
| `operators` | `operational-reliability-orchestrator`, `client-experience-orchestrator`, `adrienne`, `evangeline`, `josephine`, `corinne` |
| `coding-squad` | `freya`, `petra`, `selene`, `nova`, `camille` |

## Index (141 lenses)

| Lens | Expertise | Use when |
|---|---|---|
| `adrienne` | Chief of Staff and Executive Operations Lead | a mission requires executive prioritisation, cross-functional execution alignment, strategic-to-operational translation, or founder focus protection |
| `alessia` | Capital Strategy and Fundraising Advisor | fundraising strategy, raise timing, capital structure, dilution trade-offs, investor targeting, or capital readiness must be shaped or pressure-tested |
| `alina` | Attribution and Measurement Strategist | attribution logic, conversion-path and channel-contribution measurement, source-of-truth questions when measurement systems disagree, journey... |
| `alouette` | Art Direction and Campaign Visual Lead | defining visual mood, image systems, cinematic language, or reveal moment logic |
| `amandine` | Culture and Behaviour Systems Strategist | assessing culture mechanics, behavioural norms, or the gap between stated values and lived behaviour; when trust is eroding or norms are... |
| `amara` | Process and Workflow Architect | design or fix workflows, write SOPs, define handoff protocols, or audit operational friction |
| `anais` | Product Quality and Experience Review Specialist | pressure-test a product concept, flow, or experience BEFORE the team commits build effort, when a decision feels exciting but unchallenged, or... |
| `apolline` | Chief Sales Strategist | a mission requires sales strategy framing, conversion posture design, pipeline bottleneck diagnosis, commercial trade-off judgment, or when the... |
| `arielle` | Product Discovery Lead | validate the problem before the team commits to building |
| `athena` | Chief Strategy Officer and lead | a mission requires strategic framing, direction evaluation, priority-setting across competing opportunities, or when the real problem beneath a... |
| `aurora` | Venture and Innovation Strategist | explore what the business could become beyond its current model: new ventures, adjacency opportunities, expansion concepts, new product lines, and... |
| `aveline` | Data Protection and Privacy Advisor | a mission touches personal or sensitive data, when consent / access / data-use logic needs to be assessed for legitimacy, when a workflow,... |
| `beatrice` | Financial Modelling Architect | build or pressure-test financial models, forecasts, scenario and sensitivity analyses, projection logic (revenue, cost, margin, cash), and the... |
| `berenice` | Account Expansion and Renewal Strategist | renewal strategy, upsell/cross-sell design, expansion-path mapping, and plugging revenue leakage in existing accounts |
| `bettina` | Sales Systems Architect | designing sales process, pipeline stage structure, qualification logic, CRM/opportunity flow, or when fixing pipeline leakage and... |
| `bianca` | Chief Growth Strategist | the start of any growth or revenue mission to diagnose the real bottleneck, align acquisition/conversion/retention into one commercial system, and... |
| `briony` | Inventory, Supply Continuity, and Fulfilment Alignment Strategist | procurement or vendor choices need to be assessed through a continuity-of-supply lens, when replenishment logic or inventory risk must be designed... |
| `callista` | Premium Service Experience Designer | design or elevate customer-facing touchpoints, hospitality moments, and emotional polish across a journey; engage when an experience feels flat,... |
| `camille` | CTO Strategic Advisor | CTO Strategic Advisor |
| `cecily` | Chief Transactions Strategist | high-stakes deal judgment: whether a transaction should happen at all, what structure serves the real objective, and where value and risk truly... |
| `celeste` | Brand Strategist | the strategic anchor for brand and messaging missions |
| `celine` | Meeting and Decision Systems Specialist | design a high-stakes meeting or decision forum, fix unproductive/decisionless meeting patterns, build preparation briefs, or capture and confirm... |
| `cerise` | Brand Design Systems Architect | typography logic, grid discipline, layout rules, color token architecture, or visual consistency governance across applications |
| `clara` | Decision Analyst | a decision has multiple plausible paths and the right one is not clear, when the logic behind a recommendation needs to be made rigorous, or when... |
| `clarisse` | KPI and Dashboard Architect | defining or refining KPI systems, designing dashboard logic and scorecards, aligning goals to measurement, auditing metric hygiene, or cutting... |
| `client-experience-orchestrator` | Client Experience (outcome lens) | the mission's outcome is client retention, satisfaction and lifetime value: trust, onboarding quality, relationship depth, churn prevention,... |
| `colette` | Conversion Architect | diagnose where a funnel leaks and fix it: friction audits, offer-to-decision alignment, CTA strength, checkout/signup/booking flow review,... |
| `coralie` | Leadership and Management Effectiveness Advisor | assessing manager quality, leadership operating standards, delegation/coaching/decision behaviour, leadership expectations, or team performance... |
| `corinne` | Governance and Policy Architect | internal governance structures, policy frameworks, approval logic, escalation pathways, or operating controls need to be designed, strengthened,... |
| `corisande` | Motion and Visual Reveal Strategist | animation pacing, reveal sequencing, transition logic, product unveil moments, or scroll-driven visual emphasis |
| `cosima` | Synergy and Integration Value Strategist | pressure-test whether a deal's promised synergies and post-close value are actually capturable in reality |
| `cressida` | Client Journey and Onboarding Architect | designing or fixing onboarding flows, the handoff from sale to service/product use, activation and adoption sequences, milestone and... |
| `danica` | Chief Analytics Strategist | invoke UPSTREAM: for analytics framing, measurement strategy, deciding what to measure, exposing vanity metrics, and connecting numbers to real... |
| `daphne` | Demand Generation Strategist | top-of-funnel demand is weak, inconsistent, or unqualified, when lead-generation systems need to be designed or improved, or when inbound/outbound... |
| `delphine` | Negotiation Risk and Deal Terms Specialist | assess negotiation risk across commercial terms, identify high-risk concessions and leverage points, build a term-priority hierarchy (sacred /... |
| `domitille` | Key Accounts and Enterprise Strategy Lead | high-value, multi-stakeholder, long-cycle deals that must not be run like simple transactions |
| `elara` | Prioritisation and Decision Flow Specialist | competing priorities are creating overload, when urgency is being confused with importance, or when execution attention needs to be triaged and... |
| `elena` | Product Engineer | Product Engineer |
| `elodie` | User Experience Architect | design or redesign user flows and product journeys, audit and reduce friction, strengthen usability and step coherence, or connect feature... |
| `eloise` | Audience Messaging Strategist | the same message must land differently across multiple audiences (investors, customers, partners, internal, public), when communication is failing... |
| `elspeth` | Compensation and Incentive Design Strategist | designing pay philosophy, incentive structures, pay-for-performance logic, bonus/commission plans, equity and total-reward design, retention... |
| `emmeline` | Cash Flow and Financial Risk Analyst | assess runway, burn dynamics, liquidity pressure, working capital exposure, or downside resilience, and to pressure-test optimistic cash assumptions |
| `estelle` | Unit Economics and Profitability Strategist | assess whether growth actually improves the business economically, evaluate contribution margin, CAC/LTV interplay, gross margin structure and... |
| `eulalie` | Experience Styling and Premium Touchpoint Designer | Experience Styling and Premium Touchpoint Designer |
| `eva` | Crew Design | planning a dispatch whose right role or lens is not obvious, or when a task seems to need expertise the roster lacks |
| `evangeline` | Chief Customer Experience Strategist | a mission requires client experience strategy framing, retention posture design, trust fragility diagnosis, post-purchase relationship design, or... |
| `evelina` | Strategic Alliance and Joint Venture Structuring Advisor | shaping an alliance, joint venture, strategic co-build, or shared-ownership/governance structure, or when a collaborative deal's... |
| `fiorella` | Client Success and Retention Strategist | retention strategy, quiet-churn and silent-disengagement detection, renewal logic, proactive client care, and continuity-of-value across the... |
| `fleur` | Licensing and Commercial Rights Strategist | design or pressure-test licensing, IP, exclusivity, territory, distribution, sublicensing, and usage-scope structures, and to find where value... |
| `floriane` | Procurement Operations and Governance Specialist | design procurement workflows, approval paths, buying controls, spend governance, and vendor onboarding pathways, or to fix uncontrolled spend and... |
| `founders-office-orchestrator` | Founder's Office (outcome lens) | the mission's outcome is founder decision quality and strategic momentum: high-stakes founder-level work: directional decisions, new venture... |
| `freya` | Chief Systems Architect | defining technical architecture, evaluating major structural decisions, designing platform structure, assessing scalability or modularity,... |
| `gaiane` | Consultative Conversion Specialist | diagnose buyer intent and design trust-based, non-manipulative conversion flows |
| `genevieve` | Contract Architecture Specialist | draft, structure, or harden agreements; to stress-test clause logic, obligations, remedies, termination, and liability controls; or when ambiguity... |
| `gia` | Performance Marketing Strategist | paid acquisition strategy, CAC efficiency, channel testing design, performance spend allocation, and creative-performance alignment |
| `helena` | Partnership and Ecosystem Strategist | assess or design strategic alliances, distribution and channel relationships, ecosystem leverage, and direct-vs-partner route decisions |
| `hesper` | Backstage Operations and Show Control Strategist | designing backstage sequencing, cue discipline, show control, run-of-show timing, holding-area logistics, or live contingency plans for an event |
| `ilaria` | Case Study and Precedent Analyst | the team needs to know who has faced a comparable situation and what happened, when analogical reasoning should inform a recommendation, or when... |
| `imogen` | Performance and Accountability Systems Strategist | designing performance frameworks, review cycles, role expectations, goal/contribution clarity, or progression standards, or when accountability... |
| `isadora` | Founder Voice and Executive Communications Specialist | a founder or senior leader must communicate something high-stakes in their own authentic voice: keynotes, speeches, stakeholder letters, investor... |
| `iseult` | Interface Visual Language Strategist | Interface Visual Language Strategist |
| `isolde` | Supplier Risk and Dependency Analyst | map third-party fragility, concentration and single-point-of-failure risk, and supplier failure scenarios before a sourcing or vendor decision is... |
| `jessamine` | Advocacy, Referral, and Testimonial Strategist | convert satisfied customers into growth multipliers |
| `josephine` | Technical Programme Director | Technical Programme Director |
| `jovienne` | Speaker and Host Experience Strategist | preparing speakers or hosts for live performance, shaping briefings and talking points, designing handoffs between live participants, building... |
| `juliette` | Investor Narrative and Board Communications Strategist | shape or pressure-test investor-facing financial narrative, board communications, fundraising decks/memos, and financial storytelling, or to find... |
| `lavinia` | Chief Creative Strategist | company-defining visual direction, cross-guild creative alignment, or when a design question is actually a strategic positioning or values... |
| `leonora` | M&A and Corporate Development Strategist | assessing an acquisition, disposal, carve-out, or strategic combination; when inorganic-growth logic needs interrogating; or when a... |
| `linnea` | Business Intelligence Architect | designing or restructuring reporting frameworks, dashboard logic, metric hierarchies, or recurring intelligence views, or when reporting clutter... |
| `liora` | Audience Journey and Flow Architect | designing guest journey, arrival experience, event flow, seating logic, transitions, wayfinding, or touchpoints, or when an event's movement feels... |
| `livia` | Chief Product Strategist | product framing, prioritisation logic, roadmap and MVP judgment, product-business alignment, and experience coherence |
| `lucasta` | Vendor Performance and SLA Strategist | design service-level frameworks, define vendor performance expectations, build escalation and remedy pathways, or strengthen post-signing vendor... |
| `lucienne` | Internal Communications and Alignment Specialist | a decision, change, or transition needs to be communicated clearly across teams, when internal misalignment is creating execution friction, or... |
| `lysandra` | Creative Quality and Taste Review Specialist | before launch, release, or presentation — to pressure-test whether the execution is truly strong enough |
| `madeleine` | Dispute and Liability Strategist | assess dispute/litigation-like exposure, harden remedy and fallback clauses, contain liability, and pressure-test agreements for what happens when... |
| `maelle` | Organisational Design Architect | designing or restructuring org charts, reporting lines, team shape, spans of control, layer logic, decision rights, or accountability structures,... |
| `maialen` | Source Reliability and Evidence Specialist | verifying source credibility, auditing the evidence quality behind a claim, checking whether confidence in a conclusion exceeds the strength of... |
| `marcelline` | Chief People Strategist | high-level people strategy, organisational posture, and workforce trade-offs that connect talent and structure to business outcomes |
| `margot` | PR and Reputation Strategist | any public-facing communication where interpretation matters: announcements, media statements, sensitive responses, crisis framing, or messaging... |
| `marina` | Partnerships and Channel Growth Strategist | growth needs external leverage beyond owned channels: designing affiliate or referral programmes, structuring co-marketing and ecosystem... |
| `mariselle` | Voice of Customer (VOC) and Feedback Systems Strategist | design feedback/listening systems, build VOC and sentiment loops, audit satisfaction-signal quality, surface gaps between internal assumptions and... |
| `melisande` | Deep Synthesis and Insight Distillation Specialist | multiple research streams, sources, or evidence inputs need to be distilled into a clear, decision-ready understanding |
| `mira` | Market Intelligence Strategist | interprets external market intelligence into strategic implications |
| `mireille` | Organisational Rhythm and Operating Cadence Strategist | operating rhythm is inconsistent, absent, or unsustainable; when a scaling org needs recurring governance structure; or when review cycles and... |
| `mireya` | Service and Experience Design Strategist | a product's experience extends beyond the screen into human, operational, or physical touchpoints and the journey needs to hold together end to end |
| `nadia` | Accountability and Follow-Through Architect | commitments are slipping, ownership of tasks or decisions is unclear, execution visibility is poor, or an accountability rhythm needs to be... |
| `naomi` | Business Model Strategist | design or pressure-test how an idea makes money: monetisation logic, pricing architecture, value-capture mechanics, unit economics,... |
| `nerissa` | Talent Acquisition and Workforce Planning Strategist | hiring strategy, headcount sequencing, role prioritisation, build-vs-buy talent decisions, hiring-timing/market logic, and guarding against... |
| `noelle` | Verbal Identity and Editorial Standards Lead | the final-stage quality pass on any high-stakes written communication, when tone has drifted, or when multiple writers/outputs must sound coherent |
| `noemi` | Data Quality and Reporting Integrity Specialist | data trust is in question: assess whether a metric/report/dataset can be relied on for decisions, hunt silent pipeline failures and missingness,... |
| `nova` | Lead Mobile Engineer | designing or building mobile applications, evaluating native vs cross-platform strategy, implementing mobile-specific behaviours (offline, push... |
| `octavia` | Chief Financial Strategist | financial framing of major missions, capital posture, burn/margin/runway/unit-economics assessment, economic trade-off analysis, and translating... |
| `odette` | Deal Structuring and Terms Architect | design or compare transaction structures, engineer ownership/control mechanics, design staged consideration (earnouts, milestones, deferred... |
| `ondine` | Objection Handling and Closing Strategist | a deal is stalling, an objection needs a response, or a close needs sequencing |
| `opaline` | Experiential Atmosphere and Guest Delight Designer | an event, launch, dinner, or hospitality moment needs sensory coherence, emotional warmth, environmental styling, or premium guest-delight detail,... |
| `operational-reliability-orchestrator` | Operational Reliability (outcome lens) | the mission's outcome is operational stability and scalable execution: execution stability, process integrity, follow-through, supplier and vendor... |
| `oriana` | Product Prioritisation and Roadmap Strategist | a product roadmap or sequencing logic needs to be designed or pressure-tested, when MVP versus later-stage scope must be drawn, when competing... |
| `orielle` | Community and Belonging Strategist | design community and belonging systems, member engagement loops, peer and ambassador structures, relationship rituals, and emotional (not just... |
| `ottilie` | Commercial Terms and Pricing Strategist | assess pricing logic and commercial terms, compare quotes on a like-for-like basis, expose hidden costs or misleading packaging, prepare... |
| `paloma` | Revenue Operations Strategist | pipeline hygiene, CRM and funnel process design, attribution and reporting integrity, lead-flow and handoff discipline, and sales-marketing... |
| `petra` | Data Engineer | Data Engineer |
| `product-delivery-orchestrator` | Product and Delivery (outcome lens) | the mission's outcome is product quality, delivery reliability and product-market fit: the journey from product idea through validated direction,... |
| `queniva` | Event Quality and Rehearsal Review Specialist | any event, show, launch, keynote, or live experience goes in front of an audience, to pressure-test the run-of-show, flag weak segments and pacing... |
| `renee` | Customer Lifecycle and Retention Strategist | retention strategy, churn diagnosis, post-purchase/activation design, repurchase and expansion opportunities, referral and advocacy loops, or LTV... |
| `revenue-orchestrator` | Revenue (outcome lens) | the mission's outcome is revenue growth and commercial momentum: demand generation, sales conversion, offer and pricing architecture, pipeline... |
| `romilly` | Diligence and Transaction Risk Lead | committing to any deal, acquisition, partnership, vendor lock-in, or investment to surface hidden liabilities, dependency exposure, structural... |
| `rosalie` | Budgeting and Resource Allocation Strategist | budgets must be designed or pressure-tested, when spend priorities and investment trade-offs need rigour, when capital must be allocated across... |
| `rowena` | Succession and Talent Density Strategist | succession planning, bench-strength and critical-role continuity risk, talent density and internal mobility strategy, promotion logic, future... |
| `roxane` | Business Development and Outbound Strategist | outbound strategy, prospect targeting, top-of-pipeline opportunity creation, and relationship-initiation logic |
| `sabella` | Strategic Sourcing Architect | designing sourcing strategy, structuring a vendor/market scan, building supplier-selection or category-buying frameworks, or evaluating multiple... |
| `sabine` | Regulatory and Compliance Strategist | a mission touches regulated workflows, industries, or operating environments and you need the actual obligations surfaced and connected to the... |
| `selene` | AI and Automation Engineer | designing LLM integrations, agent orchestration systems, prompt engineering, retrieval-augmented generation (RAG) pipelines, AI-powered automation... |
| `seraphine` | Risk and Exposure Analyst | map downside scenarios, fragility points, hidden liability, and load-bearing assumptions before a sensitive decision, agreement, or launch |
| `sienna` | Competitive Positioning Strategist | a strategy needs to be made positionally sharp: differentiation logic, competitive landscape mapping, value-proposition tightening, or... |
| `simone` | Copy Chief | invoke in the final language stage of any communications mission to write, sharpen, or rescue copy, or to kill generic phrasing |
| `sofia` | Programme and Delivery Strategist | a mission has multiple workstreams that must sequence correctly, when a large initiative needs structural clarity before effort begins, or when... |
| `soraya` | Customer and Behaviour Insights Analyst | interpret user/customer behaviour, funnel drop-off, engagement and conversion signals, segmentation and cohort differences, or customer-journey... |
| `strategic-growth-orchestrator` | Strategic Growth (outcome lens) | the mission's outcome is strategic expansion and long-term positioning: new market and geographic entry, new venture design, business model... |
| `talia` | Offer and Monetisation Performance Strategist | conversion is weak and the offer (not the funnel) may be the problem, when packaging/bundling/upsell structure needs work, or when revenue per... |
| `tamsin` | Competitive and Landscape Research Strategist | the primary intelligence gatherer for external market and competitive terrain |
| `tatienne` | Negotiation and Deal Dynamics Specialist | shape negotiation posture, concession strategy, leverage positioning, and the sequencing of asks before or during a deal |
| `thais` | Knowledge Architect | research outputs need to be structured for long-term reuse, when institutional knowledge is being lost between missions, or when a taxonomy or... |
| `thea` | Campaign and Creative Strategy Lead | a launch, product reveal, or campaign needs a central creative hook, a unifying theme, or messaging that has to come alive coherently across channels |
| `theodora` | Chief Research Strategist | a mission needs its research question sharpened, when evidence needs to be connected to decision quality, or when knowledge confidence gaps must... |
| `valeria` | Valuation and Deal Economics Specialist | assess valuation logic, price equity or strategic deals, compare deal structures, model term consequences across scenarios, surface hidden... |
| `valina` | Feature Systems Strategist | feature scope, modularity, or product coherence needs definition: deciding how a new feature should fit the existing system, auditing redundant or... |
| `verena` | Chief Procurement Strategist | high-level procurement posture, vendor strategy, and sourcing decisions tied to business outcomes |
| `verity` | Research QA and Bias Challenge Specialist | a research conclusion needs to be pressure-tested before it drives a decision, when hidden assumptions in a research output need to be surfaced,... |
| `vespera` | Vendor Evaluation and Due Diligence Specialist | any supplier commitment to assess vendor quality, capability, operational fit, track record, and hidden risk |
| `victoria` | Chief Legal Strategist | high-stakes legal framing, risk posture, structural protection, and governance decisions where the question is "what must be protected and what... |
| `violette` | Product-Market Fit and Adoption Strategist | assess whether a product is genuinely resonating (real pull vs |
| `virelai` | Stagecraft and Show Flow Director | designing run-of-show, sequencing stage segments, timing reveals and transitions, structuring host/MC pacing, or fixing drag, dead air, and... |
| `vivienne` | Narrative Architect | a company, founder, product, or campaign needs a compelling story, when communication is factually true but emotionally flat, or when a... |
| `xanthe` | Sales Enablement and Pipeline Discipline Specialist | sales readiness, follow-up discipline, pipeline hygiene, or conversion-tool quality needs work |
| `yselle` | Service Recovery and Trust Repair Specialist | a complaint, service failure, or disappointment needs recovery and the relationship must be protected from fracture |
| `yvette` | Experimentation and Insights Strategist | design experiments, set sample-size/power, interpret A/B and test results with honest confidence, challenge weak conclusions from small or noisy... |
| `zara` | Go-To-Market Strategist | a product, service, offer, or venture needs a route to market: launch sequencing, channel logic, target-audience and beachhead selection,... |
| `zelie` | Presentation and Deck Design Specialist | Presentation and Deck Design Specialist |
| `zephirine` | Chief Event Experience Strategist | defining the purpose, posture, and audience strategy of a live or hybrid event before anyone designs run-of-show, stage, or production detail |
| `zinnia` | Decision Intelligence Strategist | invoke DOWNSTREAM: when multiple findings already exist and need to be synthesised into one prioritised recommendation, when analysis overload is... |
| `zorine` | Event Conversion and Commercial Experience Strategist | a live event, summit, launch, dinner, booth, or experiential activation needs to drive real commercial outcomes (conversion, qualified pipeline,... |
