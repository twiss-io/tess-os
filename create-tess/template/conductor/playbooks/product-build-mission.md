# Playbook — Product and Build Mission

**Orchestrator:** Product and Delivery  
**Mode:** `/product-mode`  
**Output:** Validated product direction, scoped specification, sequenced build plan, release readiness assessment  
**When to use:** Any mission that involves deciding what to build, how to build it, or whether a build is ready to ship

---

## Trigger Conditions

Use this playbook when:
- A new product, feature, or capability needs to be designed and built
- The product roadmap needs to be reviewed and reprioritised
- A build vs buy vs partner decision needs to be made
- A release is approaching and readiness needs to be confirmed
- Post-launch performance needs to be reviewed and iterated on

---

## Intake Questions

Before activating any guild, Tess must answer:
1. What user problem is this solving? (Not the feature — the problem)
2. What business outcome is this build meant to produce?
3. What is the current state of validation? (Assumption / hypothesis / partially validated / fully validated)
4. What phase is the mission in? (Discovery / Design / Build / Rollout / Diagnosis / Review)
5. What is the minimum viable outcome — the smallest build that would prove or disprove the thesis?

---

## Standard Guild Pattern by Phase

**Discovery Phase:**
| Role | Guild | Mandate |
|---|---|---|
| Owner | Product (Livia / Arielle) | Problem definition, opportunity framing, prioritisation logic |
| Core Contributor | Research (Leah) | User research synthesis, market validation, competitive product landscape |
| Core Contributor | Analytics (Danica) | Existing usage data, signal interpretation |

**Design and Specification Phase:**
| Role | Guild | Mandate |
|---|---|---|
| Owner | Product (Elodie / Valina) | Requirements, acceptance criteria, definition of done |
| Core Contributor | Coding (Freya / Ada) | Feasibility, architecture, technical constraint assessment |
| Core Contributor | Design/UX | Interface and experience design |

**Build Phase:**
| Role | Guild | Mandate |
|---|---|---|
| Owner | Coding (Ada / Iris / Nova — by layer) | Engineering execution |
| Core Contributor | Product | Specification oversight, decision on ambiguities |
| Control | QA (Quinn) | Testing strategy, quality gates |

**Rollout Phase:**
| Role | Guild | Mandate |
|---|---|---|
| Owner | Product + QA (Quinn) | Release criteria confirmation |
| Core Contributor | Ops (Vega) | Deployment, infrastructure |
| Core Contributor | CX | Support readiness, client communication |

---

## Execution Sequence

1. **Intake** — Classify the product mission phase. Do not proceed to design before discovery is complete.
2. **Problem validation** — Is the user problem validated? If not, activate Research + Analytics before any specification work.
3. **Specification** — Product defines requirements and acceptance criteria. Coding confirms feasibility. Design completes interface specification.
4. **Design freeze** — Design is agreed before engineering begins. Changes after this point require explicit scope impact assessment.
5. **Build** — Coding executes to specification. QA is involved from the start, not at the end.
6. **Release readiness gate** — QA confirms all acceptance criteria are met. Ops confirms deployment readiness. CX confirms support readiness.
7. **Release** — Rollout strategy confirmed (full / phased / feature-flagged). Incident response and rollback plan in place.
8. **Post-launch review** — Analytics tracks against defined success criteria. CX monitors adoption. Product leads the review.

---

## Output Structure

**Discovery Output:**
- Validated problem statement
- Prioritisation rationale (why this, why now)
- Minimum viable build definition
- Success criteria

**Specification Output:**
- Requirements with acceptance criteria
- Technical design brief
- Dependencies and risks
- Sequenced build plan

**Release Readiness Output:**
- QA sign-off against defined criteria
- Rollout strategy
- Incident response and rollback plan
- Post-launch measurement plan

---

## Common Failure Modes to Avoid

- Starting specification before the problem is validated
- Design changes arriving during the engineering phase without scope assessment
- QA activated only at the end, not throughout the build
- Releasing without defined success metrics
- Treating engineering completion as delivery success
- Post-launch review skipped because the next build has already started
