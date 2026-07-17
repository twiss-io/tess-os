"""Append plans and specs to durable, schema-validated JSONL logs — the
audit trail half of "every action signed, every claim carrying its
receipt" (the vision's north star, scoped honestly to what this component
actually does: no cryptographic signing here — that is Tess Cloud's job —
just a fail-loud, schema-checked, append-only record of every plan and
every finalized spec).

Mirrors intent_router.decision_log's shape and rationale exactly: this
component ships independent of any one deployment's `state/` conventions,
so the default sinks are this component's own `spec-engine/specs/*.jsonl`
files — a caller integrating this into a specific deployment passes its
own `log_path` (which could point at that deployment's `state/` directory)
with no code change required here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterator, Union

from .spec_check import validate
from .types import Approval, Plan, SpecDocument

PathLike = Union[str, Path]

_SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schema"
_PLAN_SCHEMA_PATH = _SCHEMA_DIR / "plan.schema.json"
_SPEC_SCHEMA_PATH = _SCHEMA_DIR / "spec.schema.json"

DEFAULT_PLANS_LOG_PATH = Path(__file__).resolve().parent.parent / "specs" / "plans.jsonl"
DEFAULT_SPECS_LOG_PATH = Path(__file__).resolve().parent.parent / "specs" / "specs.jsonl"
DEFAULT_APPROVALS_LOG_PATH = Path(__file__).resolve().parent.parent / "specs" / "approvals.jsonl"

_schema_cache: Dict[str, Any] = {}


def _load_schema(path: Path) -> Dict[str, Any]:
    key = str(path)
    if key not in _schema_cache:
        with path.open("r", encoding="utf-8") as f:
            _schema_cache[key] = json.load(f)
    return _schema_cache[key]


def _append_jsonl(record: Dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True))
        f.write("\n")
    return path


def append_plan(plan: Plan, log_path: PathLike = None) -> Path:
    """Append `plan` (its `to_log_record()` shape) to the plans log.
    FAILS LOUD on a schema violation rather than writing a malformed
    record — never a silent partial log entry."""
    record = plan.to_log_record()
    validate(record, _load_schema(_PLAN_SCHEMA_PATH))
    return _append_jsonl(record, Path(log_path or DEFAULT_PLANS_LOG_PATH))


def append_spec(spec: SpecDocument, log_path: PathLike = None) -> Path:
    """Append `spec` (its `to_log_record()` shape) to the specs log."""
    record = spec.to_log_record()
    validate(record, _load_schema(_SPEC_SCHEMA_PATH))
    return _append_jsonl(record, Path(log_path or DEFAULT_SPECS_LOG_PATH))


def append_approval_note(approval: Approval, log_path: PathLike) -> Path:
    """Approval records have no dedicated JSON schema of their own (they
    are small enough, and always logged alongside the spec/plan they
    decided on) — this appends a plain dict, not schema-validated, for a
    caller that wants a standalone rejection/approval trail separate from
    the plans/specs logs. Every field is present so the record is
    self-contained without needing to be joined back to a Plan/Approval
    object to be read."""
    record = {
        "approval_id": approval.approval_id,
        "plan_id": approval.plan_id,
        "approved": approval.approved,
        "approved_by": approval.approved_by,
        "approved_at": approval.approved_at,
        "notes": approval.notes,
    }
    return _append_jsonl(record, Path(log_path))


def read_jsonl(log_path: PathLike) -> Iterator[Dict[str, Any]]:
    """Yield each record (dict) from `log_path`, in append order. Returns
    an empty iterator if the file does not exist — a fresh log with
    nothing logged yet is not an error."""
    path = Path(log_path)
    if not path.is_file():
        return
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)
