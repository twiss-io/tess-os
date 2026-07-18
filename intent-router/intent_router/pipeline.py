"""Top-level convenience entry point gluing the pieces together: load a
routing table, route one freeform input, log the decision. This is the
one function a wrapper (a slash command, an MCP tool, a future CLAUDE.md
hook) would call end to end.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from .decision_log import append_decision
from .routing_table import RoutingTable
from .router import resolve_clarification as _resolve_clarification
from .router import route as _route
from .types import ExternalSignal, RoutingDecision

PathLike = Union[str, Path]

DEFAULT_LOG_PATH = Path(__file__).resolve().parent.parent / "decisions" / "log.jsonl"


def run_intent_router(
    input_text: str,
    routing_table_path: PathLike,
    *,
    external_signal: Optional[ExternalSignal] = None,
    log_path: Optional[Union[PathLike, bool]] = None,
    mission_id: Optional[str] = None,
    force: bool = False,
) -> RoutingDecision:
    """Route `input_text` using the table at `routing_table_path`, then log
    the decision. Pass `log_path=False` to skip logging entirely (e.g. for
    a dry-run CLI call); omit it (or pass `None`) to use the component's
    default sink."""
    table = RoutingTable.load(routing_table_path)
    decision = _route(
        input_text,
        table,
        external_signal=external_signal,
        mission_id=mission_id,
        force=force,
    )
    if log_path is not False:
        append_decision(decision, log_path or DEFAULT_LOG_PATH)
    return decision


def continue_with_clarification(
    prior_decision: RoutingDecision,
    clarification_answer: str,
    routing_table_path: PathLike,
    *,
    log_path: Optional[Union[PathLike, bool]] = None,
) -> RoutingDecision:
    """Resolve a prior ambiguous decision with the user's one-line answer.
    Never asks a second clarifying question (see router.resolve_clarification)."""
    table = RoutingTable.load(routing_table_path)
    decision = _resolve_clarification(prior_decision, clarification_answer, table)
    if log_path is not False:
        append_decision(decision, log_path or DEFAULT_LOG_PATH)
    return decision
