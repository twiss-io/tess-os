#!/usr/bin/env python3
"""Standalone runner for Epic E2's acceptance criterion: "Three real briefs
(one detailed, one voice-ramble, one single-paragraph idea) each produce a
spec that a DIFFERENT agent pool can build from without asking the original
author anything not already in the open-questions ledger."

Honest data-source note (same discipline intent-router's routing_eval.py
applies): these three fixtures are hand-authored, representative inputs
across the three input styles the epic names — a shared grocery-list app,
a standup-log tool, an invoice-nudge app — not real historical user briefs
(this public repo carries none). What's being measured is real: whether
the deterministic intake/plan/spec pipeline, run against genuinely
different input styles (fully-specified, rambling-with-hedges, and
terse-single-paragraph), always produces a schema-valid spec where every
core dimension is either populated or explicitly captured as an open
question — the operational, machine-checkable form of "nothing to ask
that isn't already in the ledger."

    python3 spec-engine/eval/spec_engine_eval.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

COMPONENT_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = COMPONENT_ROOT.parent
FIXTURES_DIR = COMPONENT_ROOT / "eval" / "fixtures"

if str(COMPONENT_ROOT) not in sys.path:
    sys.path.insert(0, str(COMPONENT_ROOT))

from spec_engine.pipeline import run_spec_engine  # noqa: E402
from spec_engine.render import render_markdown  # noqa: E402
from spec_engine.spec_check import validate  # noqa: E402
from spec_engine.spec_lint import lint  # noqa: E402
import json  # noqa: E402

SPEC_SCHEMA_PATH = COMPONENT_ROOT / "schema" / "spec.schema.json"

CASES = [
    ("detailed", "brief_detailed.txt", "structured_brief"),
    ("voice_ramble", "brief_voice_ramble.txt", "voice_transcript"),
    ("single_paragraph", "brief_single_paragraph.txt", "fragment"),
]

REQUIRED_MD_HEADERS = [
    "## What It Does",
    "## How It Looks",
    "## How It Works",
    "## Data Model",
    "## Non-Goals",
    "## Acceptance Criteria",
    "## Open Questions Ledger",
    "## Provenance",
]


def _unaccounted_gaps(spec) -> list:
    """The machine-checkable form of the acceptance criterion: for each
    core dimension, it must be populated OR the ledger must carry a
    matching open question. Returns the list of dimensions that are
    neither — this should always be empty."""
    gaps = []
    oq_categories = {q.category for q in spec.open_questions}
    if not spec.what_it_does.summary.strip():
        gaps.append("what_it_does (empty, and no category catches an always-required summary)")
    if not spec.how_it_looks.description.strip() and not spec.how_it_looks.key_screens and "design" not in oq_categories:
        gaps.append("how_it_looks")
    if not spec.how_it_works.description.strip() and not spec.how_it_works.key_flows and "technical" not in oq_categories:
        gaps.append("how_it_works")
    if not spec.data_model.entities and "data" not in oq_categories:
        gaps.append("data_model")
    if not spec.acceptance_criteria and "scope" not in oq_categories:
        gaps.append("acceptance_criteria")
    return gaps


def run() -> int:
    schema = json.loads(SPEC_SCHEMA_PATH.read_text(encoding="utf-8"))
    all_ok = True
    print(f"Spec engine eval — {len(CASES)} cases\n")

    # Scoped to a throwaway directory for the duration of this run —
    # finalize_spec() (called by run_spec_engine()) now mints a genuine,
    # gate-verifiable, HMAC-signed approval under the hood (see
    # spec_engine.gate_approval), which by default would create/touch a
    # real key at ~/.tess-os/approval-identity/<user>.key. A standalone
    # eval script run manually or in CI should never touch the invoking
    # user's real machine state for this — same discipline
    # tests/spec_engine/conftest.py applies to the pytest-driven suite.
    with tempfile.TemporaryDirectory(prefix="spec-engine-eval-identity-") as identity_dir:
        for name, filename, source_type in CASES:
            text = (FIXTURES_DIR / filename).read_text(encoding="utf-8")
            spec = run_spec_engine(
                text, source_type, approved_by="eval-harness", identity_dir=identity_dir,
            )

            problems = []
            try:
                validate(spec.to_log_record(), schema)
            except Exception as e:  # noqa: BLE001 -- report, don't crash the eval loop
                problems.append(f"schema validation failed: {e}")

            gaps = _unaccounted_gaps(spec)
            if gaps:
                problems.append(f"unaccounted-for gaps: {gaps}")

            md = render_markdown(spec)
            missing_headers = [h for h in REQUIRED_MD_HEADERS if h not in md]
            if missing_headers:
                problems.append(f"missing markdown headers: {missing_headers}")

            findings = lint(spec)
            error_findings = [f for f in findings if f.severity == "error"]

            ok = not problems
            all_ok = all_ok and ok
            mark = "PASS" if ok else "FAIL"
            print(
                f"[{mark}] {name}: {len(spec.open_questions)} open question(s), "
                f"{len(error_findings)} lint error(s)"
            )
            for p in problems:
                print(f"        {p}")

    print(f"\nOverall: {'PASS' if all_ok else 'FAIL'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(run())
