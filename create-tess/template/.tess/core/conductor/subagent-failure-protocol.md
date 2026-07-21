# Subagent Failure & Retry Protocol

What Tess does when a dispatched subagent fails, times out, returns degraded output — or when a verifier rejects an output.

**Failed verification enters this protocol.** When a mandatory verifier ([verification-routing.md](verification-routing.md)) rejects an output, that rejection is a failure of the originating dispatch and goes through cause classification and the retry loop below exactly like any other failure.

---

## Failure States (what came back)

| State | Definition | Example |
|---|---|---|
| **Empty return** | Agent returns no substantive output | Hook deadlock, context overflow, tool block |
| **Partial return** | Agent completes some but not all assigned tasks | File writes succeeded but git commit failed |
| **Degraded output** | Agent returns output but quality is below threshold | Shallow analysis, missing sections, wrong format |
| **Timeout** | Agent does not return within reasonable time | Stuck on blocked tool, infinite loop |
| **Error** | Agent returns an explicit error message | Permission denied, file not found, API failure |

---

## Cause Classification (why it failed) — mandatory before any retry

Classifying the failure state is not enough. Before any retry, Tess must classify the cause:

| Cause class | Definition | Retry rule |
|---|---|---|
| **Transient** | Network flap, flaky tool, rate limit, infrastructure hiccup | Same-brief retry permitted, with backoff between attempts |
| **Context-gap** | The agent lacked information the brief did not provide | Changed brief required — inject the missing context (file paths, primary sources, conventions) |
| **Wrong-approach** | Right task, wrong methodology | Changed brief required — name what failed and redirect the approach |
| **Wrong-task** | The agent misread scope or solved the wrong problem | Changed brief required — reframe the Objective and the NOT-responsible-for boundary |

**Same-brief retries are forbidden for every non-transient cause.** A retry whose brief does not specifically address the classified cause is a wasted attempt and counts against the cap.

---

## The Retry Loop

```
Attempt N dispatched
  -> Agent returns (or verifier rejects)
  -> Classify failure state, then cause class:
     Transient | Context-Gap | Wrong-Approach | Wrong-Task
       [Transient: same-brief retry with backoff permitted]
       [All others: changed brief required, addressing the classified cause]
  -> Notify the operator (one-line Telegram): "Attempt N failed, class [X], action [Y]"
  -> Append the per-attempt error analysis to the mission record
  -> Attempt N+1 dispatched (changed brief if non-transient)
  -> If N = 3 (the cap):
     -> STOP
     -> Escalate to the operator with the full per-attempt analysis log
     -> Do not dispatch again without the operator's direction
```

Per-attempt rules:

1. **Classify first.** No retry is dispatched before the failure state and cause class are identified.
2. **Transient** → same-brief retry with backoff permitted.
3. **All other classes** → the retry brief MUST change in a way that specifically addresses the classified cause.
4. **No silent retries.** One-line Telegram narration per attempt. the operator should know when agents fail.
5. **Every attempt's error analysis is appended to the mission record** (per Rule 16 three-layer trail) — failure state, cause class, what the brief changed, result.

---

## Attempt Cap — 3

**Maximum 3 total attempts on the same task.**

> **Supersession note (2026-06-10, Tess OS reform — operator-authorized):** this protocol previously read "If the same agent fails twice on the same task: stop retrying." The 2-attempt cap is superseded by the operator's ratified 3-attempt cap with mandatory per-retry error analysis and the changed-brief requirement. The escalation requirement is unchanged in force.

At the cap: **STOP.** Escalate to the operator with the full per-attempt analysis log — every attempt, its failure state, its cause class, what each brief changed, and Tess's read on why the task is failing. Do not dispatch again without the operator's direction.

---

## Per-State Responses

| Failure State | Action (after cause classification) |
|---|---|
| Empty return | Check if hooks or permissions blocked the agent. If so, fix the blocker (transient/system) and re-dispatch. If not, classify cause and re-dispatch with a changed, simpler brief. |
| Partial return | Accept completed work. Re-dispatch only the remaining tasks — the changed brief scopes down to what is left. |
| Degraded output | If usable with minor gaps, accept and note the gaps (counts as success with caveats, not a retry). If unusable, classify cause and re-dispatch with a brief that addresses it. |
| Timeout | Kill the agent if possible. Re-dispatch with a narrower scope (changed brief). |
| Error | Read the error. Transient errors permit same-brief retry; root-cause errors (permissions, missing file, wrong path) are context-gap — fix the cause in the brief and re-dispatch. |

---

## Systemic Failures

If multiple agents fail in the same session: this is likely a system-level issue (hooks, permissions, settings). Diagnose the system before re-dispatching any work. System-level failures do not consume the per-task attempt cap, but they do get narrated to the operator immediately.

---

## CHANGELOG

- **2026-06-10 Tess OS reform (operator-authorized)** — Rewritten as a typed retry loop: kept the existing 5-state failure table; added mandatory cause-level classification (Transient / Context-Gap / Wrong-Approach / Wrong-Task); same-brief retries now permitted only for transient causes (with backoff), all other causes require a changed brief addressing the classified cause; attempt cap raised 2 → 3 (the operator's number — explicit supersession note above); escalation at the cap now requires the full per-attempt analysis log; per-attempt one-line Telegram narration and mission-record error analyses made mandatory; failed verification (verification-routing.md) wired in as an entry point. Source: audit memo G4/S5/B4, Decision 3 resolved to 3.
