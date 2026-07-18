"""Build a first crew-plan SKETCH from a chosen route.

This is deliberately NOT a `core/contracts/crew-plan.schema.json` instance.
That schema requires, per task, a full six-field dispatch brief
(conductor/dispatch-brief.md) and an explicit verifier decision
(conductor/verification-routing.md) — neither of which the router can
respons­ibly fabricate from a freeform idea alone. Orchestra-model.md is
explicit that a crew-plan is "a dispatch program," not a paraphrase; this
module produces the thing that comes BEFORE that program exists — the
routing entry point plus a first-cut candidate roster the named
orchestrator (or the conductor) still has to turn into real briefs.

Every sketch carries `is_sketch: true` and an `expansion_required` string
precisely so nothing downstream can mistake it for something dispatchable.
`tests/intent_router/test_crew_plan_sketch.py` asserts the sketch's
`outcome_type` and `stages[].gate_in` values are drawn from the SAME live
enums `core/contracts/crew-plan.schema.json` defines — so the sketch's
vocabulary cannot silently drift from the real contract it will eventually
be expanded into.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .types import GATES, Route

EXPANSION_REQUIRED_NOTICE = (
    "This is a SKETCH, not a core/contracts/crew-plan.schema.json instance. "
    "Every task below needs a full six-field dispatch brief "
    "(conductor/dispatch-brief.md) and an explicit verifier decision "
    "(conductor/verification-routing.md) before anything is dispatched. "
    "The named orchestrator (in PLAN mode) or the conductor turns this "
    "sketch into a real crew-plan — see orchestra-model.md §3."
)


def build_sketch(route: Route, mission_id: str, notes: str = "") -> Dict[str, Any]:
    """Return a dict under the `crew_plan_sketch` key. `mission_id` is the
    caller's responsibility to generate as a safe slug (see
    `pipeline.default_mission_id`) — this module does not invent one so a
    caller integrating with a real mission ledger can pass its own id."""
    guilds = list(route.default_guilds) if route.default_guilds else []
    if not guilds:
        # No default_guilds configured for this route — fall back to naming
        # the route's own orchestrator (or entry command) as a single,
        # unexpanded Owner placeholder rather than emitting an empty task
        # list a caller could mistake for "nothing to do."
        guilds = [route.orchestrator or route.entry_command]

    tasks = [
        {
            "candidate_agent": guild,
            "role": "Owner" if i == 0 else "Core Contributor",
            "needs_brief": True,
        }
        for i, guild in enumerate(guilds)
    ]

    return {
        "is_sketch": True,
        "mission_id": mission_id,
        "outcome_owner": route.orchestrator or route.entry_command,
        "outcome_type": route.outcome_type,
        "entry_command": route.entry_command,
        "notes": notes,
        "stages": [
            {
                "stage": 1,
                "gate_in": GATES[0],  # "intake-before-anything"
                "parallel": False,
                "tasks": tasks,
            }
        ],
        "expansion_required": EXPANSION_REQUIRED_NOTICE,
    }


def default_notes(route: Route, matched_signals: Optional[list] = None) -> str:
    bits = [f"Auto-routed by the intent router to `{route.entry_command}`."]
    if route.orchestrator:
        bits.append(f"Outcome owner: {route.orchestrator}.")
    if matched_signals:
        bits.append(f"Matched signals: {', '.join(matched_signals)}.")
    bits.append(
        "This is a first-cut sketch; expand into a full crew-plan before dispatch."
    )
    return " ".join(bits)
