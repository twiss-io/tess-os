"""Append a routing decision to a JSONL decision log.

Epic E1 deliverable: "Routing decision logged to state/ with rationale."
This component ships independently of any one deployment's `state/`
conventions (the private Tess repo's `state/` registry is Twiss-specific;
see intent-router/README.md "Integration status"), so the default sink is
this component's own `intent-router/decisions/log.jsonl` — a caller
integrating this into a specific deployment passes its own `log_path`
(which could point at that deployment's `state/` directory) with no code
change required here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Union

from .schema_check import validate
from .types import RoutingDecision

PathLike = Union[str, Path]

_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema" / "routing-decision.schema.json"
_schema_cache: Dict[str, Any] = {}


def _load_schema() -> Dict[str, Any]:
    if "schema" not in _schema_cache:
        with _SCHEMA_PATH.open("r", encoding="utf-8") as f:
            _schema_cache["schema"] = json.load(f)
    return _schema_cache["schema"]


def append_decision(decision: RoutingDecision, log_path: PathLike) -> Path:
    """Append `decision` as one JSON line to `log_path`. FAILS LOUD
    (raises `intent_router.schema_check.SchemaValidationError`) rather
    than writing a malformed record — never a silent partial log entry."""
    path = Path(log_path)
    record = decision.to_log_record()
    validate(record, _load_schema())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True))
        f.write("\n")
    return path


def read_decisions(log_path: PathLike):
    """Yield each logged decision record (dict) from `log_path`, in
    append order. Returns an empty iterator if the file does not exist —
    a fresh log with nothing logged yet is not an error."""
    path = Path(log_path)
    if not path.is_file():
        return
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)
