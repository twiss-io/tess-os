"""Content dataclasses shared by `Plan` (pre-approval draft) and
`SpecDocument` (post-approval source of truth) — the four core spec
dimensions the epic names verbatim (what it does / how it looks / how it
works / data model) plus the open-questions ledger entry shape.

Spec: TESS-VISION-AND-BUILD-SPEC.html, Phase 1, Epic E2 ("Spec Engine v1:
Idea -> Complete Spec"). A `Plan` and a `SpecDocument` carry the SAME
dataclasses defined here — approval (see approval.py / spec_builder.py)
promotes a Plan's draft content into a SpecDocument's authoritative
content verbatim. Nothing is silently rewritten by the approval step
itself; approval is a gate on WHETHER to proceed, not an editing pass.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from .types import Plan

# Pillar 02: "rough edges and open questions are treated as INPUTS, not
# blockers... intake explicitly harvests ambiguities into an
# open-questions ledger." These five categories are deliberately broad
# enough to cover every kind of gap the intake heuristics in intake.py can
# detect (a missing dimension, a hedge phrase, a genuinely unresolved
# design/technical/data decision) without needing a model call to classify.
OPEN_QUESTION_CATEGORIES = ("ambiguity", "scope", "design", "technical", "data")
OPEN_QUESTION_STATUSES = ("open", "resolved")

# Same safe-slug pattern intent_router.types uses (itself matching
# core/contracts/crew-plan.schema.json's Task.id/mission_id pattern):
# lowercase-alnum first character, then alnum/'.'/'_'/'-' only. No '/' or
# '\\' can ever validate, so an id can never be used as a path-traversal
# payload by any caller that joins it into a filesystem path (scaffold.py).
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def is_valid_slug(value: str) -> bool:
    return bool(value) and bool(_SLUG_RE.match(value))


def new_id(prefix: str) -> str:
    """A safe-slug id: `<prefix>-<12 hex chars>`. Prefix is the caller's
    responsibility to keep slug-safe (all call sites in this package pass
    a fixed literal)."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def utc_now_iso() -> str:
    """UTC ISO-8601 with a millisecond-precision 'Z' suffix — the same
    convention core/contracts/mission.schema.json documents for
    `created_at`, and intent_router.types.utc_now_iso() implements.
    Duplicated here (not imported) so spec-engine has zero import
    dependency on intent-router — see integrations/from_intent_router.py
    for the one place the two components actually meet."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def plan_content_hash(plan: "Plan") -> str:
    """SHA-256 hex digest of `plan`'s APPROVAL-RELEVANT content — the
    exact dimensions an approver actually reviewed via `plan.
    summary_for_approval` and that end up copied verbatim into a
    `SpecDocument` by `spec_builder.build_spec()`. Deliberately excludes
    `plan_id`, `created_at`, and `summary_for_approval` itself (the first
    two are identifiers/timestamps, not content; the third is a rendered
    PROJECTION of the fields already hashed here, not an independent
    fact) — including them would make the hash change on every
    id/timestamp/rendering tweak, defeating its purpose.

    This is the codegen-boundary hardening's fix for the "mutable
    plan_id slug" gap: `Plan` is a plain (non-frozen) dataclass, so
    `plan.plan_id` alone is not proof the CONTENT a human approved is the
    content that ends up in a generated app — nothing stops a caller from
    mutating `plan.what_it_does`/`plan.data_model`/etc. in place after
    approval while leaving `plan_id` untouched, or hand-constructing a
    SECOND `Plan` object that reuses a first plan's `plan_id` with
    different content. `gate_identity.canonical_payload()` binds a
    signed approval to THIS hash (see `gate_approval.py`), so either
    attack changes the hash and fails re-verification at the codegen
    boundary — see `gate_approval.verify_gate_approval()`.

    Deterministic and pure: same content in, same hex digest out, every
    time, on every platform (canonical JSON — sorted keys, no
    whitespace — same discipline `gate_identity.sign_payload()` already
    applies to the signed payload itself)."""
    payload = {
        "source_type": plan.source_type,
        "input_excerpt": plan.input_excerpt,
        "what_it_does": asdict(plan.what_it_does),
        "how_it_looks": asdict(plan.how_it_looks),
        "how_it_works": asdict(plan.how_it_works),
        "data_model": asdict(plan.data_model),
        "non_goals": list(plan.non_goals),
        "acceptance_criteria": list(plan.acceptance_criteria),
        "open_questions": [asdict(q) for q in plan.open_questions],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class SpecEngineError(ValueError):
    """Base class for all spec-engine validation/contract errors. Fail
    loud — never silently coerce a malformed plan/approval/spec into
    something plausible-looking (same discipline intent_router.types
    documents for IntentRouterError)."""


@dataclass(frozen=True)
class OpenQuestion:
    """One entry in the open-questions ledger — the mechanism that lets
    rough edges and ambiguity be INPUTS rather than blockers. `blocking`
    is informational (surfaced to whoever builds from the spec next), it
    never itself prevents `build_spec()`/`plan_scaffold_from_spec()` from
    proceeding — see spec_lint.py for the quality checks that DO flag an
    unresolved blocking question loudly, without ever hard-stopping the
    pipeline on one."""

    id: str
    question: str
    category: str
    raised_from: str
    blocking: bool = False
    status: str = "open"
    resolution: Optional[str] = None

    def __post_init__(self) -> None:
        if not is_valid_slug(self.id):
            raise SpecEngineError(f"OpenQuestion id {self.id!r} is not a safe slug")
        if not self.question.strip():
            raise SpecEngineError(f"OpenQuestion {self.id!r} must have a non-empty question")
        if self.category not in OPEN_QUESTION_CATEGORIES:
            raise SpecEngineError(
                f"OpenQuestion {self.id!r} has category {self.category!r}, "
                f"must be one of {OPEN_QUESTION_CATEGORIES}"
            )
        if self.status not in OPEN_QUESTION_STATUSES:
            raise SpecEngineError(
                f"OpenQuestion {self.id!r} has status {self.status!r}, "
                f"must be one of {OPEN_QUESTION_STATUSES}"
            )


@dataclass(frozen=True)
class WhatItDoes:
    summary: str = ""
    goals: List[str] = field(default_factory=list)
    user_stories: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class KeyScreen:
    name: str
    description: str = ""


@dataclass(frozen=True)
class HowItLooks:
    description: str = ""
    key_screens: List[KeyScreen] = field(default_factory=list)
    design_references: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class KeyFlow:
    name: str
    steps: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class HowItWorks:
    description: str = ""
    key_flows: List[KeyFlow] = field(default_factory=list)
    integrations: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class EntityField:
    name: str
    type: str = "string"
    description: str = ""


@dataclass(frozen=True)
class Entity:
    name: str
    fields: List[EntityField] = field(default_factory=list)
    relationships: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class DataModel:
    entities: List[Entity] = field(default_factory=list)
