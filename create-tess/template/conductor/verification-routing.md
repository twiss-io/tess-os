# Verification Routing Table

> System doctrine. Mandatory verification layer for the outputs that can hurt: production, clients, and anything externally visible. Referenced from CLAUDE.md. Codified 2026-06-10 per the Tess OS reform (operator-authorized); source: the 2026-06-10 system audit §B3, S3, G3 (an internal record, not shipped with Tess OS).

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

| Output domain | Mandatory verifier (role + lens) | What they check | Primary artifacts required |
|---|---|---|---|
| Code diff / PR | **Reid** | Logic, security smells, test coverage, style; severity tiers per [review-output-standards.md](review-output-standards.md) | The actual diff read via Glob/Grep — not the conductor's description |
| Release readiness | **Quinn** | Tests executed and passing (quoted output); edge cases; environment parity | CI run results, actual test output |
| Externally visible launch (first public deploy, client-facing web release) | **Quinn** owns the verdict; each launch item goes to its checker (see [Launch Readiness](#launch-readiness)) | Every item of the launch-readiness checklist answered with evidence or N/A with a reason; the production rule in `core/policy/policy.yaml` names real paths | `launch-readiness.json` and the evidence it names; `tessctl launch check` output |
| Security, and changes to protected paths | **Cyra** (drafts the verdict; the operator signs it at their own terminal with `tessctl verdict sign`) | Attack surface, auth checks, data isolation, reverse-direction tests; anything that weakens the gate, lock or hooks. For security-tier changes and every release, the `security-audit` skill is a required step (see [Security Audit Is a Standard Step](#security-audit-is-a-standard-step)) | Code read + Bash-executed bypass demonstration where possible; the audit run's validator result and counts |
| Research / intelligence claims | **Reid** + `verity` lens | Assumption inventory, confidence calibration, counter-interpretation | Primary sources — not the research summary |
| Evidence / source quality | **Reid** + `maialen` lens | Source credibility, evidence hierarchy, confidence gap | Original sources |
| Creative outputs | **Reid** + `lysandra` lens (Iris supplies rendered evidence) | Specificity, coherence, brand alignment, taste | The actual output file |

Verifiers are three roles (Reid, Quinn, Cyra, see [roster.md](roster.md)); the domain expertise for research, evidence and creative review comes from the lens loaded into Reid's brief ([lenses/](lenses/README.md)). The verdict schema still accepts the names Verity, Maialen and Lysandra so verdicts signed before v0.2 keep validating; new verdicts are issued by Reid, Quinn or Cyra.

---

## Launch Readiness

An app can pass every test and still cost its owner money or a lawsuit in its
first week. Before any **first public deploy** or **client-facing web
release**, the launch-readiness checklist
([playbooks/launch-readiness.md](playbooks/launch-readiness.md)) is a
**mandatory predecessor** of the launch node, and its verifier is routed to
each item:

| Item | Checker | Primary evidence |
|---|---|---|
| `spend-limits`: hard caps or automatic shutdown (or at least billing alerts, stated as such) on hosting, functions and AI APIs | Vega | Plan or budget setting, cap values, host config |
| `self-trigger-guards`: no event-triggered function can re-trigger itself; instances capped | Reid | Function code and trigger configuration |
| `public-key-data-access`: row-level security proven with the public/anon key **against staging**: anonymous and cross-user reads return zero rows | Cyra | Probe script and output |
| `messaging-consent`: consent records exist and are checked before bulk SMS, email or calls | Reid + `aveline` lens | Consent store, the check in the sending code |
| `accessibility`: automated scan plus a keyboard-only pass on the main pages | Quinn (Iris supplies rendered pages) | Scan report, keyboard-pass notes |
| `security-audit`: the `security-audit` skill ran on this release and validated, no confirmed critical/high open | Cyra | Run status, counts, `findings.json` sha256 (run folder stays outside the repo) |

- Each item is answered `done` with evidence or `n/a` with a reason in
  `launch-readiness.json` (`tessctl launch init` writes it). "N/A" without a
  reason, evidence that only restates the item, and a skipped item are
  rejections.
- Quinn's release-readiness verdict cites each item's primary evidence, never
  a summary of it.
- **Mechanical floor:** once the record says `launched`, `tessctl launch
  check` and `tessctl doctor` fail and the ship gate refuses pushes while any
  item is unanswered or the production rule is still the shipped placeholder.
  While the record says `preparing` it is advisory. Tess cannot see dashboards,
  staging data or consent stores; the truth of the evidence is the checkers'
  and the verifier's responsibility.

---

## Security Audit Is a Standard Step

The bundled `security-audit` skill (Cloudflare's open-source method; read its
`TESS.md` for the role mapping) is **required**, not discretionary, for:

- **any change to a security-tier or protected path** (the gate, hooks,
  settings, lock, policy, workflows, security-tier doctrine): a scoped audit of
  the change, with every surface outside it recorded as `out_of_scope`;
- **every release and every externally visible launch**: a full audit for a
  first launch, a major or a minor release; at least a scoped audit of the
  change since the last release for a patch.

Required result before Cyra's APPROVE: `tessctl audit validate <run-dir>`
passes, `run_status` is `complete` (or the incomplete reason is stated and
accepted by the operator in writing), and no `confirmed` finding of severity
critical or high remains. Each `needs_validation` item is listed by
fingerprint and missing fact. The run folder stays outside the repository; the
verdict and release notes carry only the summary (reviewed commit, scope,
counts, validator result, `findings.json` sha256). Run it by asking for a
security audit of the project or the change; the skill's six phases run with
Cyra as hunter and a fresh Reid or Quinn as verifier
([review-and-verification.md](review-and-verification.md)).

---

## Verifier Brief Standard

Verifier briefs must include **primary artifacts** — the diff, the logs, the URLs, the file paths — **never Tess's summary of those artifacts.** A verifier that reads the orchestrator's summary inherits the orchestrator's confabulations and verifies nothing.

Verifier briefs follow the [dispatch-brief.md](dispatch-brief.md) contract like any other dispatch.

---

## Disprove Before Fix

Verification is not a formality after the build. Per
[review-and-verification.md](review-and-verification.md):

- Every review or audit candidate goes to a fresh verifier from the table above
  (one who did not raise it) whose job is to disprove it, **before** any fix is
  dispatched. Only a confirmed finding gets a severity and a fix;
  needs_validation names the exact missing fact and carries no severity.
- Each fix goes to a separate fresh verifier (not its builder, not the verifier
  that confirmed the finding), who checks it enforces the rule at the last
  trusted decision point and ships with a regression test.
- A verifier that runs the code under review does so under the execution-safety
  rules there: sandbox, no external network, scratch `HOME` and temp folder,
  read-only target, resource limits, never the operator's real home folder.

These add to the mandatory scope above; they never replace a mandatory
verifier or its signed verdict.

---

## Verifier Output Standard

Verifier verdicts follow [review-output-standards.md](review-output-standards.md): severity tiers, a closing verdict, a one-line summary. Verdicts are appended to the mission record (guardrails Rule 16, layer 1).

---

## On Failed Verification

A verifier rejection is a failure of the originating dispatch. It enters the retry protocol ([subagent-failure-protocol.md](subagent-failure-protocol.md)): classify the cause → retry with a CHANGED brief addressing that cause → maximum 3 attempts → escalate to the operator with the full per-attempt analysis log.

---

## Why Three Roles

Verification needs isolation (read-only, or tests without source edits) and an accountable signer, not a separate agent per domain. Reid, Quinn and Cyra hold those permissions; lenses carry the domain checklists. A deploy that bypassed discretionary review once shipped multiple critical/high security gaps — including a serious access-control regression — to production; mandatory invocation closes that gap.

---

## CHANGELOG

- **v1.0.0 (2026-10-25)** — Added the externally-visible-launch row and "Launch Readiness": the launch-readiness checklist (spend limits, self-trigger guards, public-key data access proven on staging, messaging consent, accessibility, security audit) is a mandatory predecessor of a first public deploy or client-facing web release, each item routed to its checker, Quinn owning the verdict; `tessctl launch` and the ship gate enforce it once a project is marked launched. Added "Security Audit Is a Standard Step": the `security-audit` skill is required for security-tier changes and every release, with the validator and severity bar Cyra's APPROVE depends on. Existing routing rows otherwise unchanged.
- **v1.0.0 (2026-09-30)** — Added "Disprove Before Fix": candidates are disproved by a fresh verifier before any fix, each fix gets a separate fresh verifier, and code runs under the execution-safety rules of review-and-verification.md. Routing table, mandatory scope and signed-verdict rules unchanged.
- **v0.2.0 (2026-09-24)** — Header no longer points at an internal audit file that Tess OS does not ship. Routing table and rules unchanged.
- **2026-06-10 Tess OS reform (operator-authorized)** — File created. Codifies the mandatory verification routing table (Reid/Quinn/Cyra/Verity/Maialen/Lysandra), the mandatory scope (prod-touching, client-facing, externally-visible, irreversible-decision-informing; discretionary otherwise), the primary-artifacts-only verifier brief standard, verdict format per review-output-standards.md, and the failed-verification → retry-protocol wiring. Source: audit memo B3, S3, G3, Decisions 4(b)/8(b).
- **v0.2 ten-role roster** — Verifiers are the three roles Reid, Quinn and Cyra. Research, evidence and creative verification are Reid with the `verity`, `maialen` or `lysandra` lens. Cyra covers protected-path changes and drafts the verdicts the operator signs. Schema enums keep the older names for backward compatibility. See roster.md.
