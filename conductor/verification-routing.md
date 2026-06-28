# Verification Routing Table

> System doctrine. Mandatory verification layer for the outputs that can hurt: production, clients, and anything externally visible. Referenced from CLAUDE.md. Codified 2026-06-10 per the Tess OS reform (operator-authorized); source: kb/wiki/synthesis/2026-06-10-tess-system-audit-reform-proposal.md §B3, S3, G3.

---

## The Rule

Verification by the mandatory domain verifier is **required** — not discretionary — for:

- **Prod-touching** deployments and changes
- **Client-facing** deliverables
- **Externally-visible** status claims
- Outputs that will inform an **irreversible decision**

Verification is **discretionary** for internal-only work. (Scope per the memo's recommendation, Decision 8 option (b): mandatory-everywhere was rejected on latency grounds.)

A review/verification node is a **mandatory predecessor of any externally-visible node** in the mission graph ([doctrine.md](doctrine.md) gates).

---

## Routing Table

| Output domain | Mandatory verifier | What they check | Primary artifacts required |
|---|---|---|---|
| Code diff / PR | **Reid** | Logic, security, test coverage, style; severity tiers per [review-output-standards.md](review-output-standards.md) | The actual diff read via Glob/Grep — not Tess's description |
| Release readiness | **Quinn** | Tests executed and passing (quoted output); edge cases; environment parity | CI run results, actual test output |
| Security | **Cyra** | Attack surface, auth checks, data isolation, reverse-direction tests | Code read + Bash-executed bypass demonstration where possible |
| Research / intelligence claims | **Verity** | Assumption inventory, confidence calibration, counter-interpretation | Primary sources — not the research summary |
| Evidence / source quality | **Maialen** | Source credibility, evidence hierarchy, confidence gap | Original sources |
| Creative outputs | **Lysandra** | Specificity, coherence, brand alignment, taste | The actual output file |

---

## Verifier Brief Standard

Verifier briefs must include **primary artifacts** — the diff, the logs, the URLs, the file paths — **never Tess's summary of those artifacts.** A verifier that reads the orchestrator's summary inherits the orchestrator's confabulations and verifies nothing.

Verifier briefs follow the [dispatch-brief.md](dispatch-brief.md) contract like any other dispatch.

---

## Verifier Output Standard

Verifier verdicts follow [review-output-standards.md](review-output-standards.md): severity tiers, a closing verdict, a one-line summary. Verdicts are appended to the mission record (guardrails Rule 16, layer 1).

---

## On Failed Verification

A verifier rejection is a failure of the originating dispatch. It enters the retry protocol ([subagent-failure-protocol.md](subagent-failure-protocol.md)): classify the cause → retry with a CHANGED brief addressing that cause → maximum 3 attempts → escalate to the operator with the full per-attempt analysis log.

---

## Why These Six

The verification-capable agents already exist and their prompts already describe this work; what was missing was mandatory invocation. A deploy that bypassed discretionary review once shipped multiple critical/high security gaps — including a serious access-control regression — to production; mandatory invocation closes that gap. If the operator later opts to promote the guild anchors (Marcelline/Livia/Octavia/Victoria) as the verification layer instead (audit memo Decision 4 option (a)), this table is the seam to update.

---

## CHANGELOG

- **2026-06-10 Tess OS reform (operator-authorized)** — File created. Codifies the mandatory verification routing table (Reid/Quinn/Cyra/Verity/Maialen/Lysandra), the mandatory scope (prod-touching, client-facing, externally-visible, irreversible-decision-informing; discretionary otherwise), the primary-artifacts-only verifier brief standard, verdict format per review-output-standards.md, and the failed-verification → retry-protocol wiring. Source: audit memo B3, S3, G3, Decisions 4(b)/8(b).
