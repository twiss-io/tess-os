# Dispatch Brief Contract

> System doctrine. Every dispatch via the Agent tool uses this contract. Referenced from CLAUDE.md (Rule Zero). Codified 2026-06-10 per the Tess OS reform (operator-authorized); source: kb/wiki/synthesis/2026-06-10-tess-system-audit-reform-proposal.md §B1–B2, S4, G5.

---

## Why This Contract Exists

Weak brief in, weak output out. The audited failure record shows two specific brief-level failure modes:

- **Fabrication inheritance:** agents given Tess's transcription of data, instead of pointers to the primary artifacts, inherit and amplify transcription errors — a fabricated identifier passed downstream can target the wrong record.
- **One-shot destructive dispatch:** long single-shot briefs combining verify + execute can complete an irreversible production operation before a correction can intervene. Milestone decomposition with per-milestone evidence is the countermeasure.

---

## The Six Required Fields

Every dispatch brief contains all six. (A PreToolUse-on-Task validator may surface a warning when fields are absent — see Validator below.)

1. **Objective** — one sentence describing what success looks like for *this specific agent*, not the mission overall.

2. **Output schema (the output contract)** — file path, format, required sections. Not "a good analysis" but "a markdown file at [path] with sections [X, Y, Z]."

3. **Tools, sources, and constraints** — what the agent may use; which **primary artifacts** to read (file paths, URLs, log endpoints) — never transcribed data; and the constraints that bind the work (scope limits, conventions, branch targets, deploy windows, things the agent must not touch). This field carries the **evidence requirement**: every factual claim in the agent's return must be grounded in a primary artifact the agent itself read or a tool call it itself ran — inference must be labeled as inference.

4. **NOT-responsible-for boundary** — the one line that prevents scope bleed into the adjacent agent's territory.

5. **Milestones with acceptance evidence (the acceptance criteria)** — required for tasks >15 minutes or production-touching; optional otherwise. Each milestone names: a concrete deliverable, a named acceptance-evidence artifact (tool output, file diff, curl response, test result), and an owner.

6. **Escalation trigger** — the condition that requires the agent to stop and surface to Tess rather than proceeding.

---

## Decomposition Rule

Any task estimated at **more than 15 minutes or touching production** is decomposed into milestones *before* dispatch, not after. Tess returns to the operator between milestones on destructive or client-facing work — not on internal build steps.

Tasks under 15 minutes with no production touch: decomposition optional; the Simple Task Path ([doctrine.md](doctrine.md)) applies.

---

## Destructive Operations — Mandatory 3-Step Dispatch

Never one-shot a destructive operation. The mandatory pattern:

1. **Verify/snapshot dispatch** — confirm targets, capture cannot-lose state (local gitignored seeders per the standing memory rule)
2. **Report + go/no-go** — results to the operator (this is also a hard-floor gate per guardrails Rule 18 for prod data, money movement, credentials)
3. **Execute dispatch** — only after the go

---

## Recommended Optional Field — Prior Incidents

The strongest dispatch on record (2026-06-09 `ordered_at` deployment, 11/11 verified) cited its own incident-log memories inline. Where relevant `memory/feedback_*` lessons exist for the task's domain, pull them into the brief.

---

## Validator (warn-mode only — never blocks)

A PreToolUse-on-Task validator may check briefs for the six fields and emit a visible warning when fields are absent. It is **WARN-MODE ONLY**: it must never block a dispatch — a blocked dispatch during a live incident would leave the operator without action, which is worse than an incomplete brief. The hook implementation is tracked separately from this doctrine; this file defines the contract the validator checks against.

---

## CHANGELOG

- **2026-06-10 Tess OS reform (operator-authorized)** — File created. Codifies the dispatch-brief contract: six required fields (objective; output contract/schema; tools/sources/constraints with the evidence requirement; NOT-responsible-for boundary; milestones with acceptance evidence; escalation trigger), the >15-min/prod-touching decomposition rule, the mandatory 3-step destructive-ops dispatch, the optional prior-incidents field, and the warn-mode-only validator contract. Source: audit memo B1–B2, S4, G5.
