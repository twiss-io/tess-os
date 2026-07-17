"""The codegen boundary's OWN authentication of an `Approval` — closes
two disclosed findings from the PR #81 security review (Cyra):

**[MEDIUM-1] The boundary was forgeable.** Before this module existed,
`record_approval(approved_by="Xavier") -> build_spec() -> generate_app()`
produced a real, running app WITHOUT ever going through an
`orchestrator.approval_gate.ApprovalGate`. `spec_builder.build_spec()`
only checked that *an* `Approval` existed matching the plan's `plan_id`
with `approved=True` — never *who* signed it, never whether it was
cryptographically genuine at all. This module gives `build_spec()`
(the actual codegen boundary — the sole gateway to a `SpecDocument`,
which is the sole input `spec_engine.codegen.generate_app()` accepts) a
way to independently re-verify an approval against the SAME
`gate_identity` HMAC mechanism `orchestrator.adapters.local_identity.
LocalIdentityApprovalGate` signs with — not merely trust a caller-set
boolean or a bare `approved_by` string.

**[MEDIUM-2] The approval wasn't bound to the artifact's content.**
`plan_id` is a mutable, caller-settable field on a plain (non-frozen)
`Plan` dataclass — a slug, not a cryptographic commitment to WHAT was
approved. `verify_gate_approval()` below independently recomputes
`content.plan_content_hash(plan)` from the plan's CURRENT content and
compares it against the hash embedded in the approval's signed payload
(see `gate_identity.canonical_payload()`) — so an approval genuinely
signed for one plan's content can never authorize building a
`SpecDocument` from a DIFFERENT plan's content, even one sharing the
same `plan_id` (a substituted or in-place-mutated `Plan` object).

## The two functions

    sign_local_approval(plan, approved_by=..., approved=True, notes="")
        -> Approval        # produces a genuinely gate-verifiable Approval,
                            # content-hash-bound to `plan`, HMAC-signed
                            # with THIS OS account's local key.

    verify_gate_approval(approval, plan) -> GateVerifiedApproval
        # independently RE-verifies `approval` against `plan`'s CURRENT
        # content; raises ApprovalVerificationError on ANY failure
        # (missing/malformed evidence, wrong mechanism, content-hash
        # mismatch, bad signature). Never returns a "maybe".

`sign_local_approval()` is what `spec_engine.pipeline.finalize_spec()`
now calls internally (in place of the old bare `approval.record_approval()`)
— see that module's docstring. It is ALSO what
`orchestrator.adapters.local_identity.LocalIdentityApprovalGate` calls,
once ITS OWN interactive terminal confirmation has decided `approved`/
`human_notes` — both paths mint an approval using the exact same
underlying signing math, so there is only ever one implementation to
keep correct, not two that could silently drift apart. The DIFFERENCE
between the two callers is entirely about WHERE consent was actually
captured (a live human answer at a real terminal prompt vs. a caller's
own `approved_by` string in a scripted/CI/test context) — not the
cryptographic strength of the result. See `gate_identity.py`'s module
docstring for this mechanism's full honest limitation (a local-OS-account
trust boundary, not a per-human production IdP) — `sign_local_approval()`
inherits that limitation exactly; it is NOT a substitute for a real
interactive/production `ApprovalGate` adapter in a genuine human-approval
flow, and any caller documenting itself as "already knows the approval
decision" (scripts, tests, the eval harness) is responsible for that
decision having been made through some OTHER legitimate means.

## Replay: nonce tracking, and its disclosed scope

Every signed payload carries a fresh, random `nonce`. `build_spec()`
calls `consume_approval_nonce()` (below) exactly once, at the moment an
`Approval` is actually spent to produce a `SpecDocument` — a second
`build_spec()` call reusing the SAME already-spent `Approval` object
(e.g. a caller accidentally or maliciously replaying it) is rejected.
**Disclosed limitation:** this tracker is IN-PROCESS / IN-MEMORY only —
it resets on every fresh Python process (a fresh `pytest` run, a fresh
`python -m orchestrator.cli run ...` invocation). It stops a replay
WITHIN one process's lifetime (e.g. a long-running server holding many
approvals) but does not, by itself, stop a genuinely persisted-then-later-
replayed approval across two SEPARATE process runs. Approvals ARE
persisted today (`spec_log.append_approval_note()` -> `specs/
approvals.jsonl`), so a durable, cross-process nonce ledger (backed by
that same log, or a dedicated one) is the natural next hardening step —
flagged as an open question for Xavier in the PR body, not silently
treated as fully closed here.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Optional, Set

from .content import SpecEngineError, new_id, plan_content_hash, utc_now_iso
from .gate_identity import (
    AUTH_MECHANISM,
    IdentityError,
    canonical_payload,
    load_or_create_local_identity,
    read_current_key,
    sign_payload,
    verify_signature,
)
from .types import Approval, Plan

_NOTES_AUTH_KEY = "auth"
_NOTES_HUMAN_KEY = "human_notes"

_LOG = logging.getLogger(__name__)


class ApprovalVerificationError(SpecEngineError):
    """Fail loud: an `Approval` could not be independently re-verified at
    the codegen boundary — missing/malformed signed evidence, an unknown
    mechanism, a content-hash mismatch (spec-substitution), or a bad/
    tampered signature. Distinct from `SpecEngineError`'s other subtypes
    (still a `SpecEngineError`, so an existing `except SpecEngineError`
    catches this too) so a caller that cares can catch it specifically."""


class ApprovalReplayError(ApprovalVerificationError):
    """A verified approval's nonce has already been spent once — this
    EXACT `Approval` (or a replay of it) already authorized a
    `build_spec()` call before. See module docstring's "Replay" section
    for this tracker's disclosed in-process-only scope."""


@dataclass(frozen=True)
class GateVerifiedApproval:
    """Proof that `approval` was independently re-verified, AT THE
    CODEGEN BOUNDARY ITSELF, against `plan`'s CURRENT content — not
    merely structurally valid (`plan_id` match + `approved=True`), and
    not merely trusted because some upstream caller claimed it was
    already checked. The only producer of this type is
    `verify_gate_approval()`; nothing else in this package constructs
    one. `build_spec()` requires one internally before it will build a
    `SpecDocument`."""

    approval: Approval
    content_hash: str
    identity_fingerprint: str
    mechanism: str
    nonce: str


def sign_local_approval(
    plan: Plan,
    *,
    approved_by: str,
    approved: bool = True,
    notes: str = "",
    identity_dir: Optional[str] = None,
) -> Approval:
    """Produce a genuinely gate-verifiable `Approval` for `plan`:
    HMAC-SHA256-signed with THIS OS account's local approval-identity key
    (`gate_identity.py`) and content-hash-bound to `plan`'s CURRENT
    content (`content.plan_content_hash()`). See module docstring for
    exactly what this proves and does not prove, and how this differs
    from `orchestrator.adapters.local_identity.LocalIdentityApprovalGate`
    (which calls this function too, after its OWN interactive
    confirmation step)."""
    identity = load_or_create_local_identity(identity_dir)
    key = read_current_key(identity.key_path)
    content_hash = plan_content_hash(plan)
    payload = canonical_payload(
        approval_id=new_id("appr"),
        plan_id=plan.plan_id,
        content_hash=content_hash,
        approved=approved,
        approved_by=approved_by,
        approved_at=utc_now_iso(),
        nonce=new_id("nonce"),
    )
    signature = sign_payload(key, payload)
    notes_json = json.dumps({
        _NOTES_HUMAN_KEY: notes,
        _NOTES_AUTH_KEY: {
            "mechanism": AUTH_MECHANISM,
            "identity_fingerprint": identity.fingerprint,
            "content_hash": content_hash,
            "nonce": payload["nonce"],
            "signature": signature,
        },
    })
    # Built directly (not via approval.record_approval()) so THIS
    # approval_id/approved_at are the ones signed above — record_approval()
    # generates its own internally, which would desync payload from
    # object. Approval.__post_init__ still enforces the same invariants
    # record_approval() relies on (non-empty approved_by, a safe-slug
    # plan_id).
    return Approval(
        approval_id=payload["approval_id"],
        plan_id=plan.plan_id,
        approved=approved,
        approved_by=approved_by,
        approved_at=payload["approved_at"],
        notes=notes_json,
    )


def verify_gate_approval(
    approval: Approval, plan: Plan, *, identity_dir: Optional[str] = None,
) -> GateVerifiedApproval:
    """Independently re-verify `approval` against `plan`, using the local
    HMAC-signed identity mechanism `sign_local_approval()` (and
    `LocalIdentityApprovalGate`) signs with. Non-consuming — safe to call
    more than once on the same still-unspent `approval` (e.g. a gate's
    own self-check right after signing, then again by an independent
    caller's pre-flight check); does NOT by itself protect against
    replay — see `consume_approval_nonce()`, which `build_spec()` calls
    exactly once, at the point an approval is actually spent.

    Raises `ApprovalVerificationError` (never returns a "maybe") on:
      - a `plan_id` mismatch between `approval` and `plan`;
      - missing/malformed signed evidence in `approval.notes` (a bare
        approval never routed through a real gate — [Cyra MEDIUM-1]);
      - an unrecognized/unsupported `auth.mechanism`;
      - a `content_hash` that does not match `plan`'s CURRENT content
        (spec-substitution or an in-place content mutation after
        approval — [Cyra MEDIUM-2]);
      - a signature that does not verify (forged or tampered in transit).
    """
    if approval.plan_id != plan.plan_id:
        raise ApprovalVerificationError(
            f"approval {approval.approval_id!r} is for plan {approval.plan_id!r}, "
            f"not the plan being verified ({plan.plan_id!r})"
        )

    try:
        parsed = json.loads(approval.notes)
        auth = parsed[_NOTES_AUTH_KEY]
        if not isinstance(auth, dict):
            raise ValueError("auth block is not a JSON object")
        mechanism = auth["mechanism"]
        nonce = auth["nonce"]
        signature = auth["signature"]
        identity_fingerprint = auth["identity_fingerprint"]
        content_hash = auth["content_hash"]
    except Exception as exc:
        raise ApprovalVerificationError(
            f"approval {getattr(approval, 'approval_id', '?')!r} carries no valid "
            f"gate-verification evidence in .notes ({type(exc).__name__}: {exc}) — "
            "refusing to build a spec or generate code from an approval that was "
            "not independently, cryptographically verified"
        ) from exc

    if mechanism != AUTH_MECHANISM:
        raise ApprovalVerificationError(
            f"approval {approval.approval_id!r} carries unsupported/unknown "
            f"mechanism {mechanism!r} (expected {AUTH_MECHANISM!r})"
        )

    expected_hash = plan_content_hash(plan)
    if content_hash != expected_hash:
        raise ApprovalVerificationError(
            f"approval {approval.approval_id!r} content-hash does not match plan "
            f"{plan.plan_id!r}'s CURRENT content — refusing to authorize a "
            "substituted or mutated artifact different from what was actually "
            "approved"
        )

    try:
        identity = load_or_create_local_identity(identity_dir)
    except IdentityError as exc:
        raise ApprovalVerificationError(
            f"could not resolve a local approval identity to re-verify against: {exc}"
        ) from exc

    if identity_fingerprint != identity.fingerprint:
        raise ApprovalVerificationError(
            f"approval {approval.approval_id!r} was signed by identity fingerprint "
            f"{identity_fingerprint!r}, which does not match this account's own "
            f"key ({identity.fingerprint!r})"
        )

    payload = canonical_payload(
        approval_id=approval.approval_id,
        plan_id=approval.plan_id,
        content_hash=content_hash,
        approved=approval.approved,
        approved_by=approval.approved_by,
        approved_at=approval.approved_at,
        nonce=nonce,
    )
    key = read_current_key(identity.key_path)
    if not verify_signature(key, payload, signature):
        raise ApprovalVerificationError(
            f"approval {approval.approval_id!r} signature verification failed — "
            "forged or tampered after signing"
        )

    return GateVerifiedApproval(
        approval=approval,
        content_hash=content_hash,
        identity_fingerprint=identity_fingerprint,
        mechanism=mechanism,
        nonce=nonce,
    )


# Process-lifetime only — see module docstring's "Replay" section for the
# disclosed, honest limitation (does not survive a fresh process).
_consumed_nonces: Set[str] = set()


def consume_approval_nonce(verified: GateVerifiedApproval) -> None:
    """Mark `verified`'s nonce as SPENT. Called exactly once, by
    `build_spec()`, at the moment an approval is actually used to
    authorize building a `SpecDocument`. Raises `ApprovalReplayError` if
    this nonce was already spent."""
    if verified.nonce in _consumed_nonces:
        raise ApprovalReplayError(
            f"approval {verified.approval.approval_id!r} (nonce {verified.nonce!r}) "
            "has already been consumed once — refusing to authorize a replayed "
            "approval"
        )
    _consumed_nonces.add(verified.nonce)


__all__ = [
    "ApprovalVerificationError",
    "ApprovalReplayError",
    "GateVerifiedApproval",
    "sign_local_approval",
    "verify_gate_approval",
    "consume_approval_nonce",
]
