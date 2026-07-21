"""Hop 7 — OPTIONAL Agent Receipt emission for a completed
`run_pipeline()` mission (see `orchestrator.pipeline`'s own module
docstring for the full hop list). Builds and locally HMAC-signs a
`decision_kind: "local_approval"` Agent Receipt
(`core/contracts/agent-receipt.schema.json`, `docs/AGENT_RECEIPT_SPEC.md`)
embedding VERBATIM the SAME `spec_engine.types.Approval` Hop 3/4 already
produced, authenticated, and independently re-verified TWICE
(`ApprovalGate.verify()`, then again at `spec_engine.spec_builder.
build_spec()`'s own codegen boundary) — this module never re-derives or
re-decides anything; it only RECORDS, the exact same "observes that fact;
it never gates it" discipline `telemetry.events.record_mission_completion()`
already applies for Hop 6.

★ TRUST LEVEL — this is System A: local, symmetric HMAC-SHA256
(`spec_engine.gate_identity`), NOT System B: GPG, asymmetric
(`tools/receipt-emit/`'s verdict/sign-off loop, deliberately untouched by
this module). See `core/contracts/agent-receipt.schema.json`'s
`$defs.LocalApprovalArtifact` and `docs/AGENT_RECEIPT_SPEC.md` for the
full trust-level disclosure this receipt kind carries — it is NEVER
equivalent to, and must never be confused with, a `verdict`/`signoff`
receipt in the same chain.

Reuses the SAME envelope-assembly SHAPE
`examples/receipt-demo/demo_receipts.py`'s `build_genesis_receipt`/
`build_second_receipt` already establish for the two GPG-backed decision
kinds (assemble the required top-level fields, THEN attach
`receipt_signature` last, over the assembled bytes) — NOT that module's
ephemeral demo keys. Signs with THIS install's REAL local
approval-identity key (`spec_engine.gate_identity`), the exact same key
`orchestrator.adapters.local_identity.LocalIdentityApprovalGate` already
signs the embedded `Approval` with.

★ DISCLOSED, SCOPED LIMITATION — always emits a GENESIS receipt
(`chain.sequence: 0`, `prev_receipt_hash: "GENESIS"`) and writes it to a
single JSON file, never a `tools/receipt-emit`-style atomic JSONL chain
append. This hop does not persist or extend a durable, multi-run
mission-receipt chain across separate `run_pipeline()` calls — that,
along with the full idea->route->approve->boots->receipt-verify (+
rejection / mid-kill unhappy-path) end-to-end proof, is the disclosed
follow-up noted in `docs/AGENT_RECEIPT_SPEC.md`, not built here.
"""

from __future__ import annotations

import hashlib
import hmac
import importlib.util
import json
import sys
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional, Union

from spec_engine.content import utc_now_iso
from spec_engine.gate_identity import IdentityError, load_or_create_local_identity, read_current_key
from spec_engine.types import Approval, Plan, SpecDocument

# tools/receipt-verify/canonical.py — reused, not reimplemented (the SAME
# canonicalization scheme every other Agent Receipt envelope, GPG or HMAC,
# already uses for signed_content_sha256/receipt_signature).
#
# Loaded via an explicit `importlib.util` module spec, under a PRIVATE,
# namespaced module name (`orchestrator._receipt_canonical`), rather than
# a `sys.path` insertion of `tools/receipt-verify/` (tess-os #162, Reid
# MEDIUM — post-#161 hardening). `tools/receipt-verify/` is a flat,
# unpackaged directory of genuinely-generic top-level module names
# (`checks.py`, `canonical.py`, ...); `orchestrator/__init__.py` used to
# put that whole directory onto `sys.path[0]` for exactly this one import,
# which would make `checks`/`canonical` importable, PROCESS-WIDE, for the
# rest of any process that did `import orchestrator` — silently shadowing
# any other module or installed package with those names, no error
# raised. This loads exactly the one file this module needs, registered
# under a name nothing else could plausibly collide with, with ZERO
# process-wide `sys.path` mutation — the same narrow, opt-in footprint
# this hop's own emission (genesis-only, never a durable chain append)
# already keeps everywhere else. See `orchestrator/__init__.py`'s own
# module docstring for the removed loop entry.
_RECEIPT_CANONICAL_MODULE_NAME = "orchestrator._receipt_canonical"
_RECEIPT_CANONICAL_PATH = Path(__file__).resolve().parent.parent / "tools" / "receipt-verify" / "canonical.py"


def _load_receipt_canonical():
    """Load `tools/receipt-verify/canonical.py` by explicit file path and
    return it as a module — cached in `sys.modules` under
    `_RECEIPT_CANONICAL_MODULE_NAME` (never the bare name `canonical`) so
    a second import of this module (or a second call to this function) is
    a cheap `sys.modules` lookup, not a re-exec. Raises `ImportError` if
    the file cannot be found or loaded — the same failure a bare `import
    canonical` would raise if `tools/receipt-verify/` were ever moved or
    deleted, just against an explicit path instead of a name resolved off
    `sys.path`."""
    cached = sys.modules.get(_RECEIPT_CANONICAL_MODULE_NAME)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(_RECEIPT_CANONICAL_MODULE_NAME, _RECEIPT_CANONICAL_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load receipt canonicalization module from {_RECEIPT_CANONICAL_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_RECEIPT_CANONICAL_MODULE_NAME] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[_RECEIPT_CANONICAL_MODULE_NAME]
        raise
    return module


canonical = _load_receipt_canonical()

PathLike = Union[str, Path]

RECEIPT_SCHEMA_VERSION = "tess-os.agent-receipt/1"
RECEIPT_SIGNATURE_ALGORITHM = "local-hmac-sha256-v1"

PIPELINE_APPROVAL_GATE_RULE_ID = "orchestrator-pipeline-hop3-approval-gate"
PIPELINE_APPROVAL_GATE_SOURCE = "orchestrator/approval_gate.py"
PIPELINE_APPROVAL_GATE_DESCRIPTION = (
    "orchestrator.pipeline.run_pipeline() Hop 3 requires a real, authenticated "
    "ApprovalGate decision (independently re-verified by ApprovalGate.verify(), "
    "then AGAIN, independently, at the spec_engine.spec_builder.build_spec() "
    "codegen boundary via spec_engine.gate_approval.verify_gate_approval()) "
    "before Hop 4/5 may build a SpecDocument or write a generated app to disk. "
    "This is a product-layer ApprovalGate requirement (orchestrator/"
    "approval_gate.py), NOT a core/policy/policy.yaml PathRule or "
    "HardFloorRule — see orchestrator/README.md 'The approval gate' for the "
    "full contract this rule_kind (pipeline_approval_gate) represents."
)


class MissionReceiptError(Exception):
    """The narrow, EXPECTED failure surface for Agent Receipt emission —
    an unusable local approval-identity key, or a filesystem error writing
    the receipt file. `orchestrator.pipeline._emit_governed_mission_receipt()`
    catches ONLY this type and downgrades it to a non-fatal warning
    (mirrors `telemetry.consent.TelemetryError`'s own, identical role for
    Hop 6) — any OTHER exception (a genuine bug in this module) is left to
    propagate and fail loudly, never silently swallowed."""


def _proposed_action(plan: Plan, spec: SpecDocument, target_dir: PathLike) -> Dict[str, Any]:
    return {
        "actor": "orchestrator.pipeline.run_pipeline",
        "summary": (
            f"Generated a running app for spec {spec.spec_id!r} "
            f"({spec.title!r}) from plan {plan.plan_id!r}."
        ),
        "paths": [str(target_dir)],
    }


def _policy_decision() -> Dict[str, Any]:
    return {
        "source": PIPELINE_APPROVAL_GATE_SOURCE,
        "rule_id": PIPELINE_APPROVAL_GATE_RULE_ID,
        "rule_kind": "pipeline_approval_gate",
        "description": PIPELINE_APPROVAL_GATE_DESCRIPTION,
    }


def _local_approval_decision(approval: Approval) -> Dict[str, Any]:
    """The embedded `LocalApprovalArtifact`, VERBATIM — `spec_engine.
    types.Approval` already has EXACTLY this schema's five required
    fields (approval_id, plan_id, approved, approved_by, approved_at,
    notes) and nothing else, so this is a plain field copy, never a
    re-derivation."""
    return asdict(approval)


def build_local_approval_receipt(
    *,
    plan: Plan,
    approval: Approval,
    spec: SpecDocument,
    target_dir: PathLike,
    identity_dir: Optional[PathLike] = None,
) -> Dict[str, Any]:
    """Assemble + locally HMAC-sign one genesis Agent Receipt for THIS
    `run_pipeline()` call. See module docstring for the disclosed
    genesis-only scope. Raises `MissionReceiptError` if the local
    approval-identity key cannot be resolved/read — never returns a
    partially-built or unsigned receipt."""
    try:
        identity = load_or_create_local_identity(identity_dir)
        key_bytes = read_current_key(identity.key_path)
    except IdentityError as exc:
        raise MissionReceiptError(
            f"could not resolve a local approval identity to sign this receipt with: {exc}"
        ) from exc

    receipt: Dict[str, Any] = {
        "receipt_schema": RECEIPT_SCHEMA_VERSION,
        "receipt_id": uuid.uuid4().hex,
        "issued_at": utc_now_iso(),
        "proposed_action": _proposed_action(plan, spec, target_dir),
        "policy_decision": _policy_decision(),
        "decision_kind": "local_approval",
        "decision": _local_approval_decision(approval),
        "chain": {"sequence": 0, "prev_receipt_hash": "GENESIS"},
    }
    canon = canonical.receipt_signing_bytes(receipt)
    signature_hex = hmac.new(key_bytes, canon, hashlib.sha256).hexdigest()
    receipt["receipt_signature"] = {
        "algorithm": RECEIPT_SIGNATURE_ALGORITHM,
        "signed_by": approval.approved_by,
        "signed_content_sha256": canonical.sha256_hex(canon),
        "signature_hex": signature_hex,
        "signed_at": utc_now_iso(),
    }
    return receipt


def write_receipt(receipt: Dict[str, Any], receipt_path: PathLike) -> Path:
    """Write `receipt` to `receipt_path` as a single JSON file (not a
    JSONL chain — see `build_local_approval_receipt`'s own docstring for
    why this hop stays genesis-only). Raises `MissionReceiptError` on any
    `OSError`."""
    path = Path(receipt_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError as exc:
        raise MissionReceiptError(f"could not write receipt to {path}: {exc}") from exc
    return path


__all__ = [
    "MissionReceiptError",
    "build_local_approval_receipt",
    "write_receipt",
    "RECEIPT_SCHEMA_VERSION",
    "RECEIPT_SIGNATURE_ALGORITHM",
    "PIPELINE_APPROVAL_GATE_RULE_ID",
]
