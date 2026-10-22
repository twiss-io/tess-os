---
name: Tess
file: review-and-verification
---

# Review and Verification Discipline

> System doctrine. How every review, audit, QA pass and verification in Tess
> decides what counts as a finding, how sure it is, and what happens next.
> It applies to code review, security review, QA, research checks and
> multi-round audits alike, not only to security work. Adopted in v1.0.0
> from Cloudflare's open-source security-audit method
> (`.tess/core/skills/security-audit/`, MIT, see its `UPSTREAM.md`).
> [review-output-standards.md](review-output-standards.md) sets the output
> format; [verification-routing.md](verification-routing.md) sets who
> verifies what. This file sets the evidence bar both of them use.

---

## 1. What counts as a finding

A finding names all six of these:

1. **Who** — the lower-trust person, process or input that acts (an
   anonymous user, another tenant, a web page, a file someone else wrote, a
   hostile tool result).
2. **What they do** — the exact input or action.
3. **The control that should stop it** — the check, rule or boundary the
   system intends to enforce.
4. **The boundary it crosses** — where that control fails.
5. **Who or what is hurt** — the affected person, record, resource or
   service.
6. **The result** — what concretely happens, observed or checkable by the
   owner.

If one of the six is missing, it is not a finding yet. A checklist gap
("no rate limiting", "should use X"), general hardening advice, a guess about
how production is configured, or an effect only on the actor's own data is
not a finding on its own. It may go in the review as a note, never as a
severity-rated finding. Outside security the same test holds: "who is
affected, by what input, and what goes wrong" (a wrong total, a lost record,
a broken release), not "this could be better".

## 2. Three verdicts, and severity only for confirmed

Every candidate ends in exactly one state:

- **confirmed** — the full path and the result were shown from source and a
  bounded local check. Only confirmed findings get a severity.
- **needs_validation** — the path is real in the source, but one decisive
  fact cannot be seen from here (a deployment setting, a proxy, an identity
  policy). Name that exact missing fact and a safe way for the owner to check
  it. **No severity.** It is not a low-confidence confirmed finding, and it is
  not a parking place for a hunch.
- **rejected** — source, a local check, a visible control or missing impact
  disproves it. Keep it, with the reason, so the next round does not raise it
  again without new evidence.

Severity anchors (the skill's scale; map to the tiers in
[review-output-standards.md](review-output-standards.md), informational
reported as LOW):

- **critical** — an unauthenticated actor gets code execution, full data
  store access, or takeover of any account.
- **high** — an actor fully defeats an explicit control with real
  consequences: auth bypass, cross-tenant read or write, stored script that
  runs for other users, authenticated code execution, an unauthenticated
  remote stop of a shared service.
- **medium** — a real boundary crossed, but with a limited blast radius,
  unusual preconditions, or a narrow set of resources.
- **low** — non-secret internals exposed, or much effort for little gain.
- **informational** — confirmed but minimal; mainly useful as one step inside
  a larger finding.

The test between high and medium: does the shown result fully defeat an
explicit control for something that matters, or only weaken it? Severity never
exceeds the impact actually shown. If you cannot state the damage, the
severity is lower than it feels.

## 3. Disprove before fix

1. Every candidate goes to a **fresh verifier** (Reid, Quinn or Cyra per
   [verification-routing.md](verification-routing.md)) who did not find it
   and whose job is to **disprove** it: re-read every cited file and line,
   find the strongest control on the path, reproduce the result only as far
   as needed.
2. The verifier gets the candidate and the primary artifacts, never another
   verifier's conclusion and never Tess's summary.
3. **No fix is dispatched until the candidate is confirmed.** A fix for a
   finding that turns out to be wrong adds risk and hides the real cause.
4. Each fix then goes to a **separate fresh verifier** (not the builder, not
   the verifier that confirmed the finding), who checks that the fix enforces
   the rule, does not just move the trust somewhere else, and comes with a
   regression test that fails without it.

Exception: a live production incident follows the incident-ops rules
(guardrails Rule 1a). Stopping the damage comes first; the fix still gets a
fresh verifier afterwards, and the incident record says so.

## 4. Coverage ledger for multi-round work

Any review or audit that runs more than one round, or more than one reviewer,
keeps a coverage ledger:

- **Units** are surface × boundary × attack class (for non-security reviews:
  area × risk × kind of check). One unit is roughly one reviewer assignment.
- **States:** `planned`, `in_progress`, `candidate`, `covered`, `blocked`,
  `deferred`, `out_of_scope`, `not_applicable`. A unit is `covered` only from the paths
  and checks a reviewer actually reports, never from "auth was reviewed".
- **Every reviewer says what they did NOT cover**, and returns unexpected new
  areas as uncovered so they become units, not footnotes.
- **Later rounds read the prior ledger** instead of starting over: unchanged
  covered units lower priority but stay visible; changed source, blocked,
  deferred and needs_validation units become current work; a rejected claim
  is suppressed only while its evidence is unchanged.
- A scoped or quick pass says it is partial. No single pass claims the target
  is exhausted.

In a security audit the ledger is the skill's `coverage-ledger.json`, checked
with `tessctl audit validate <run-dir>`. Elsewhere a table in the mission
record is enough.

## 5. Execution safety when a review runs code

When a review, audit or test run executes the code under review (builds,
tests, fixtures, harnesses):

- inside a sandbox, with **no external network** (loopback only if needed);
- with an **empty environment** plus an explicit allowlist, and a **scratch
  `HOME`, temp folder and caches**;
- with the **target read-only** and writes only into the assigned scratch
  folder;
- with **low CPU, memory, process, disk and time limits**;
- **never against the operator's real home folder**, keys, `~/.config/tess`,
  sockets or shared services, and never against deployed systems or real
  accounts. Use dummy users, fixtures and secrets.

If a control cannot be enforced, do not run the code: record the gap as
needs_validation with a safe plan. Lesson (v1.0.0, commit 5196eb4): full test
runs wrote 75 anchor copies (14 MB) plus empty project folders into the real
`~/.config/tess`. Test suites must use a scratch home, and a reviewer lists
`~/.config/tess` before and after a run to prove it was left alone.

## 6. Anti-patterns

1. Checklist deviations presented as vulnerabilities or bugs.
2. Defence-in-depth advice with no reachable boundary crossing.
3. Testing against live or shared environments when a bounded local check
   would do.
4. Guessing provider, proxy, browser, identity or deployment behaviour that
   is not in the source.
5. Treating a user's own authority or self-harm as a cross-boundary result.
6. Reporting a stronger effect than the one observed.
7. Prose-only results that cannot be deduplicated or verified.
8. Re-reporting last round's unchanged confirmed findings, or letting them
   anchor the new search.
9. Giving a severity to a needs_validation item.
10. Writing the report before independent verification, or letting the prose
    and the structured record disagree.

## 7. The fix

For each confirmed finding, name the rule the code must enforce and make the
**smallest change that enforces it at the last trusted decision point** (the
last place the system still knows who is asking and what they may do), plus a
**regression test** that fails before the fix and passes after. Prefer that
over general hardening. The review describes the fix; the builder (Ada)
makes it; a fresh verifier checks it (section 3).

---

## CHANGELOG

- **v1.0.0 (2026-09-30)** — File created. Adopts the finding contract, the
  three verdicts with severity for confirmed only, disprove-before-fix,
  the coverage ledger, execution safety, the anti-patterns and the
  smallest-fix rule from Cloudflare's security-audit method (commit
  c1c8a8c), for all review work. Referenced from review-output-standards.md,
  verification-routing.md and the Cyra, Reid and Quinn role files.
