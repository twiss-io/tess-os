# Playbook — L99 Merge Discipline

**Orchestrator:** Product and Delivery / Operational Reliability
**Mode:** standing authority (no per-merge sign-off required)
**Authority:** Standing authority — the operator has delegated /L99 merge decisions, conditioned on no conflicts with existing PRs or other agents' work (nothing that would undo previous work by merging out of order).
**When to use:** Audit-driven multi-PR fix waves (L99 / godmode / security retros) where 5–15 PRs must be merged across one or more repos without blocking the whole wave on the operator's per-PR bandwidth.

---

## What This Authority Is

Tess has **standing authority to merge L99 audit follow-up PRs (and similar audit fix waves) autonomously — without a per-PR green-light from the operator** — provided every guardrail and verification gate below is satisfied on every merge.

This is a deliberate exception to the default "ask before merge" posture, granted because audit fix waves spawn many PRs at once and per-PR gating stalls the entire wave on the operator's availability. The authority is **bounded**: it covers audit-follow-up PRs that are well-scoped, CI-green, and specialist-reviewed. It does **not** extend to feature launches, schema-destructive migrations without rollback, credential changes, or anything in [guardrails.md](../guardrails.md) Rule 18 (those always gate on the operator).

### Two flavours of autonomous merge

| Flavour | Scope | Source |
|---|---|---|
| **Trivial-auto** | ≤5 lines, defensive only, no logic-flow change (e.g. null guard, bound check) | production-alert auto-diagnose policy |
| **/L99-auto** | Larger but bounded — audit follow-up, well-tested, CI green, specialist-reviewed | this playbook |

Both share the **auto-revert + audit-trail** discipline below.

---

## When Tess May Merge Without Sign-Off

All of these must be true:
- The PR is part of a recognised audit fix wave (L99, godmode, security retro) or a trivial defensive fix.
- CI is **green** (mandatory — never merge against red).
- The PR is scoped to the audit finding it closes (no scope creep).
- Base branch is correct ([backend deploys only from `main`](../../CLAUDE.md); dashboard prod rules apply — never merge `main` on dashboard).
- No unresolved conflict with an earlier PR in the same wave (see sequencing).
- The change is **not** in the Rule 18 hard-floor set (credentials, money movement, destructive prod data ops, client-external factual claims).

If any condition fails → **halt and escalate to the operator** with the specific blocker.

---

## Sequencing Discipline (apply every wave)

1. **Same-file PRs merge in series, not parallel.** List all PRs touching the same path. After each merge, the next PR's branch needs `gh pr update-branch` (or rebase) before its CI is meaningful.
2. **Backend deploy stagger.** Wait ≥5 minutes between back-to-back backend deploys (config:cache / scheduler boot race). Same-repo backend PRs queue with explicit `sleep 300` between merges.
3. **Cross-repo PRs run parallel.** dashboard, backend, iOS, Android, workjoy have independent deploy pipelines and no shared state — merge concurrently.
4. **Pre-merge conflict check.** Before merging a PR, check whether it touches files an already-merged PR in the same wave changed. If yes, `gh pr update-branch` (rebase) the later PR **before** merging it, so an earlier merge cannot be silently undone.
5. **Branch-divergence audit.** Run `git diff HEAD...origin/main --stat` (and `git ls-remote` before any rebase + `--force-with-lease`) so a stale branch doesn't drop main's files.

### PR order priority within a wave
1. **P0 / critical first** — security fixes, exploit closure.
2. **Infrastructure-affecting second** — `deploy.yml`, migrations, supervisor/scheduler changes.
3. **Feature endpoints third.**
4. **Cosmetic / UI last.**

---

## Verification Gates That Still Apply

The standing authority removes the per-PR *sign-off*, **not** the verification gates. Every merge still runs:

- **CI gate** — green required, no exceptions ([verification-routing.md](../verification-routing.md)).
- **Mandatory domain verifier** for any prod-touching / client-facing / externally-visible change — the verifier (Reid / Quinn / Cyra / Verity / Maialen / Lysandra) reads primary artifacts, never Tess's summary.
- **Post-merge smoke after every merge** — backend `/health` (per-endpoint smoke, not just 200), dashboard page-load, mobile build status. Per-endpoint smokes matter: a green `/health` does not prove no 500s elsewhere.
- **Specialist-direct-to-main is a flag** — if a specialist pushed to `main` without a PR, audit the diff retroactively (this pattern has produced serious access-control regressions before).

---

## Auto-Revert Trigger

If a merged PR introduces **any** regression within 30 minutes — new error alerts, deploy failure, `/health` red, smoke 5xx — Tess **reverts immediately** (revert PR / `git revert`) and escalates to the operator with the diagnosis. **Auto-revert beats leaving prod broken.** Never debug-forward on a live regression; restore first, then root-cause.

---

## Audit Trail (mandatory)

Every autonomous merge posts a confirmation to the appropriate ops channel (ClientA group `<channel-id>` or the relevant client channel per [channel-guardrails.md](../channel-guardrails.md)) with:
- **PR number**
- **Merge SHA**
- **One-line description** of what it closed

the operator gets a wave-level Telegram summary at the end (new reply, not an edit, so his device pings).

---

## Execution Sequence

1. **Enumerate the wave** — list every PR, repo, file path, and priority tier.
2. **Order** by priority (P0 → infra → feature → cosmetic) and group by repo.
3. **Per PR:** confirm CI green → confirm no conflict with prior merges (rebase if needed) → run mandatory verifier if prod/client/external → merge → post-merge smoke → audit-trail post.
4. **Stagger** backend merges ≥5 min; run cross-repo merges in parallel.
5. **Watch** 30-min regression window after each deploy; auto-revert on any regression.
6. **Wave summary** to the operator when the wave completes (PRs merged, SHAs, any reverts, residual risk).

---

## Common Failure Modes to Avoid

- Merging same-file PRs in parallel → later merge silently undoes the earlier fix.
- Skipping `gh pr update-branch` before a second same-file merge → stale-branch overwrite.
- Back-to-back backend deploys inside 5 min → config:cache / scheduler boot race.
- Treating a green `/health` as a full smoke → misses endpoint-specific 500s.
- Debugging a live regression forward instead of reverting first.
- Merging anything in the Rule 18 hard-floor set under this authority — it never applies there.
- Forgetting the audit-trail post → loses the merge-decision paper trail the operator relies on.

---

## Related Doctrine

- [verification-routing.md](../verification-routing.md) — mandatory verifier per output domain
- [subagent-failure-protocol.md](../subagent-failure-protocol.md) — typed retry loop on failed merge/verify
- [guardrails.md](../guardrails.md) — Rule 1a incident-ops, Rule 18 clarification hard floor
- [dispatch-brief.md](../dispatch-brief.md) — destructive-ops 3-step pattern
- Memory: `feedback_autonomous_l99_merge_authority.md` (redirect pointer to this playbook), `feedback_scheduler_deploy_race_config_cache.md`, `feedback_tess_deploy_automation_bypasses_pr_review.md`, `feedback_branch_divergence_audit.md`, `feedback_ls_remote_before_rebase.md`
