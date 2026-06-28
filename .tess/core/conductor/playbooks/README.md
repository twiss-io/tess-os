# Operating Playbooks

Reusable mission playbooks for the most common high-value mission types.

Each playbook defines: trigger conditions, intake questions, guild pattern, execution sequence, output structure, and common failure modes to avoid.

---

| Playbook | Orchestrator | Mode | Use When |
|---|---|---|---|
| [Founder Decision Memo](founder-decision-memo.md) | Founder's Office | `/founder-mode` | High-stakes decision requiring structured analysis and a clear recommendation |
| [Investor / Fundraising Prep](investor-fundraising-prep.md) | Founder's Office | `/founder-mode` | Preparing for a fundraising round, investor meeting, or board presentation |
| [Product and Build Mission](product-build-mission.md) | Product and Delivery | `/product-mode` | Deciding what to build, how to build it, or confirming release readiness |
| [Revenue Diagnosis](revenue-diagnosis.md) | Revenue | `/revenue-mode` | Revenue underperforming, stalled, or declining — diagnosing the bottleneck |
| [Event and Launch Orchestration](event-launch-orchestration.md) | Revenue + CX + Events | `/revenue-mode` | Any live event or launch with commercial intent |
| [L99 Merge Discipline](l99-merge-discipline.md) | Product and Delivery / Ops | standing authority (the operator, 2026-05-11) | Audit-driven multi-PR fix waves (L99 / godmode / security retros) — autonomous merge sequencing with conflict + smoke discipline |

**Documented playbook files: 6.**

---

## CHANGELOG

- **2026-06-27 Phase 2** — Wrote `l99-merge-discipline.md` (the standing-authority playbook) and re-linked it. Documented playbook files back to 6. The playbook codifies the autonomous L99 merge authority (the operator, 2026-05-11): when Tess may merge audit-wave PRs without per-PR sign-off, the sequencing/conflict discipline, the verification gates that still apply, the auto-revert trigger, and the mandatory audit trail. Source: memory `feedback_autonomous_l99_merge_authority.md` (now a redirect pointer to this file).
- **2026-06-27 Phase 0 cleanup** — Removed the dangling `l99-merge-discipline.md` link: the file was indexed (and a prior changelog claimed it had been "added") but never existed. The row is retained as a de-linked standing-authority note; documented playbook files corrected to 5. No file fabricated. Source: `kb/wiki/synthesis/2026-06-26-tess-starter-review.md` §3 (broken doctrine-index links).
- **2026-06-10 Tess OS reform (operator-authorized)** — *(superseded by the 2026-06-27 note above)* claimed to add l99-merge-discipline.md to the index; the file was never actually created. Source: audit memo Appendix C.
