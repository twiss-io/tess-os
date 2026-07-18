"""The human-in-the-loop approval gate. This module intentionally contains
NO logic that decides whether a plan is good — that decision belongs to
the human (or the explicitly-named caller relaying a real human decision)
approving it. `record_approval()` only shapes and validates the decision
INTO an auditable `Approval` record; it never approves anything on its
own initiative, and it never runs on a timer or a default.

This is a deliberate design choice, not an oversight: "Human-in-the-loop
is a design decision — not every step should be automated; know when to
defer." The plan/approval split exists specifically so nothing downstream
of `spec_builder.build_spec()` can be reached without a real, attributed
approval event having happened first.
"""

from __future__ import annotations

from .content import new_id, utc_now_iso
from .types import Approval, Plan


def record_approval(plan: Plan, *, approved_by: str, approved: bool = True, notes: str = "") -> Approval:
    """Record a decision on `plan`. `approved_by` is mandatory and must be
    non-empty regardless of `approved` — see `Approval.__post_init__` for
    the "no anonymous approvals" invariant this enforces even on a
    rejection. This function does not persist anything; pass the result
    to `spec_log.append_approval()` if a durable audit trail is needed."""
    return Approval(
        approval_id=new_id("appr"),
        plan_id=plan.plan_id,
        approved=approved,
        approved_by=approved_by,
        approved_at=utc_now_iso(),
        notes=notes,
    )


def reject_plan(plan: Plan, *, approved_by: str, notes: str = "") -> Approval:
    """Convenience wrapper — same contract as `record_approval(approved=False)`,
    named for readability at call sites that reject rather than approve."""
    return record_approval(plan, approved_by=approved_by, approved=False, notes=notes)
