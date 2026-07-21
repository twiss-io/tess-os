---
name: Tess
file: review-output-standards
---

# Review Output Standards

System-wide output format for all review-mode agents. These standards apply whenever an agent produces a review, audit, or assessment output.

---

## Severity-Tiered Output Format

Every finding must follow this format:

```
[SEVERITY] area/file:line — finding — risk — fix/action
```

### Severity Levels

| Level | Meaning | Action Required |
|---|---|---|
| **CRITICAL** | Exploitable vulnerability, data loss risk, broken core functionality, secret exposure | Must be fixed before merge/deploy. Blocks approval. |
| **HIGH** | Significant bug, security weakness, architectural flaw, missing validation | Should be fixed before merge. Blocks approval unless explicitly accepted. |
| **MEDIUM** | Code quality issue, minor bug, suboptimal pattern, missing test coverage | Should be addressed. Does not block approval. |
| **LOW** | Style inconsistency, naming suggestion, minor improvement, documentation gap | Nice to have. Does not block approval. |

### Example Findings

```
[CRITICAL] auth/session.ts:47 — JWT secret hardcoded in source — credential exposure — move to environment variable
[HIGH] api/users.ts:112 — no rate limiting on login endpoint — brute force risk — add rate limiter middleware
[MEDIUM] utils/parser.ts:23 — catches generic Error instead of specific type — masks root cause — catch specific exceptions
[LOW] components/Header.tsx:8 — unused import of useState — dead code — remove import
```

---

## Mandatory Closing Verdict

Every review must end with a closing verdict. The verdict format varies by agent role:

### Quinn (QA & Reliability)

```
Merge recommendation: BLOCK | APPROVE WITH SUGGESTIONS | APPROVE
```

- **BLOCK** — critical or high-severity issues that must be resolved before merge
- **APPROVE WITH SUGGESTIONS** — no blocking issues, but improvements recommended
- **APPROVE** — clean, ready to merge

### Cyra (Security)

```
Security verdict: BLOCK | CONDITIONAL PASS | CLEAR
```

- **BLOCK** — critical or high-severity security issues present
- **CONDITIONAL PASS** — no critical issues, but medium-severity items should be addressed within a defined timeframe
- **CLEAR** — no security issues found

### Reid (Code Review)

```
Code review verdict: BLOCK | APPROVE WITH SUGGESTIONS | APPROVE
```

Same semantics as Quinn's verdict, applied from an engineering quality perspective.

### Leah (Research & Intelligence)

```
Confidence: HIGH | MEDIUM | LOW
```

- **HIGH** — multiple corroborating primary sources, recent data, consistent findings
- **MEDIUM** — some sources, partial corroboration, or data is not fully current
- **LOW** — limited sources, conflicting data, or significant uncertainty

---

## Review Summary Line

Every review must include a summary line immediately before the closing verdict:

```
Reviewed [scope]. Found [N] CRITICAL, [N] HIGH, [N] MEDIUM, [N] LOW. Top priority: [description].
```

### Examples

```
Reviewed 14 files in auth/ module. Found 1 CRITICAL, 2 HIGH, 4 MEDIUM, 1 LOW. Top priority: hardcoded JWT secret in session.ts.

Reviewed API security posture for payments service. Found 0 CRITICAL, 1 HIGH, 3 MEDIUM, 0 LOW. Top priority: missing rate limiting on transaction endpoint.

Reviewed competitive landscape for Kong Inc. Found 0 CRITICAL, 0 HIGH, 0 MEDIUM, 0 LOW. Confidence: HIGH.
```

---

## Applicability

These standards apply to all agents operating in review mode, including but not limited to:

- **Quinn** — QA reviews, release readiness assessments, test coverage audits
- **Cyra** — security reviews, vulnerability assessments, architecture audits
- **Reid** — code reviews, PR reviews, technical assessments
- **Leah** — research findings, intelligence reports, competitive analyses

Any agent producing review-type output must conform to these standards. Agents not listed here that produce review outputs must adopt the format closest to their function.
