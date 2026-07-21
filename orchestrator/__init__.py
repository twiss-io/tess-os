"""orchestrator — wires `intent-router/` and `spec-engine/` into one
callable, end-to-end pipeline: freeform idea -> classify/route -> intake
-> Plan -> REAL authenticated approval gate -> SpecDocument -> generated
app -> OPTIONAL, opt-in Agent Receipt (see `mission_receipt.py`, Hop 7).

Both sibling components (`intent-router/`, `spec-engine/`) deliberately
keep ZERO hard import dependency on each other (see
`spec_engine/integrations/from_intent_router.py`'s module docstring) so
each stays independently deployable. This package is different on
purpose: wiring the two of them together end to end IS its entire
purpose, so it is the first component in this repo that imports both
`intent_router` and `spec_engine` directly, unconditionally.

Public API:

    from orchestrator import run_pipeline, PipelineResult, PipelineError
    from orchestrator import ApprovalGate, ApprovalAuthenticationError
    from orchestrator import LocalIdentityApprovalGate

See orchestrator/README.md for the full wiring contract, the
`ApprovalGate` adapter interface, and how the shipped local adapter
authenticates `approved_by` (plus its honest, disclosed limitation).
"""

from __future__ import annotations

import sys
from pathlib import Path

# `intent-router/` and `spec-engine/` are sibling top-level directories,
# not installed packages — mirror the exact sys.path bootstrap pattern
# their own test suites use (tests/intent_router/_paths.py,
# tests/spec_engine/_spec_engine_paths.py) so `import intent_router` /
# `import spec_engine` resolve for every module in THIS package. This
# runs once, here, before any submodule below is imported — Python always
# fully executes a package's __init__.py before any of its submodules.
#
# `tools/receipt-verify/` (also not an installed package) is included for
# the same reason, added by the wedge-loop epic: `mission_receipt.py`
# (Hop 7 — optional Agent Receipt emission) imports its `canonical.py`
# directly, the SAME reused-not-reimplemented canonicalization
# `examples/receipt-demo/demo_receipts.py` and `tools/receipt-emit/
# receipt_emit.py` already import it via an identical sys.path bootstrap.
_REPO_ROOT = Path(__file__).resolve().parent.parent
for _component_dir in ("intent-router", "spec-engine", "tools/receipt-verify"):
    _p = _REPO_ROOT / _component_dir
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from .adapters.local_identity import LocalIdentityApprovalGate  # noqa: E402
from .approval_gate import ApprovalAuthenticationError, ApprovalGate  # noqa: E402
from .identity import IdentityError, LocalIdentity, load_or_create_local_identity  # noqa: E402
from .mission_receipt import MissionReceiptError  # noqa: E402
from .pipeline import PipelineError, PipelineResult, run_pipeline  # noqa: E402

__all__ = [
    "run_pipeline",
    "PipelineResult",
    "PipelineError",
    "ApprovalGate",
    "ApprovalAuthenticationError",
    "LocalIdentityApprovalGate",
    "LocalIdentity",
    "IdentityError",
    "load_or_create_local_identity",
    "MissionReceiptError",
]

__version__ = "0.1.0"
