#!/usr/bin/env python3
"""
gate-arena/bypass/run_bypass_corpus.py — Layer A orchestrator.

Runs all 12 attack classes in `attacks.py` against fresh fixture repos (real
git, real gpg, the real `.tess/bin/tessctl` engine copied verbatim from this
checkout), and writes:
  - gate-arena/results/bypass-scorecard.json  (raw, machine-readable)
  - gate-arena/results/bypass-scorecard.md    (rendered table)

Usage: python3 gate-arena/bypass/run_bypass_corpus.py
(No API calls, no cost — this is Layer A, pure deterministic adversarial
software testing. Requires `git` and `gpg` on PATH.)
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import traceback
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402
from attacks import ALL_ATTACKS  # noqa: E402

ARENA_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ARENA_ROOT / "results"


def main():
    engine = lib.load_engine()
    base_dir = Path(tempfile.mkdtemp(prefix="gate-arena-bypass-"))
    print(f"[bypass] scratch dir: {base_dir}")

    outcomes = []
    for fn in ALL_ATTACKS:
        name = fn.__name__
        print(f"[bypass] running {name} ...", flush=True)
        try:
            result = fn(base_dir, engine)
        except Exception as e:  # noqa: BLE001 — a raised exception IS a finding (attack setup failed)
            result = {
                "id": name, "name": name, "description": "(attack raised an exception during setup/run)",
                "blocked": False, "mechanism": f"EXCEPTION: {e}",
                "evidence": {"traceback": traceback.format_exc()},
            }
        status = "BLOCKED" if result["blocked"] else "SLIPPED THROUGH"
        print(f"[bypass]   {result['id']}: {status}")
        outcomes.append(result)

    blocked_count = sum(1 for o in outcomes if o["blocked"])
    total = len(outcomes)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    raw = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_attacks": total,
        "blocked": blocked_count,
        "slipped_through": total - blocked_count,
        "outcomes": outcomes,
    }
    (RESULTS_DIR / "bypass-scorecard.json").write_text(json.dumps(raw, indent=2), encoding="utf-8")

    lines = []
    lines.append("# Layer A — Bypass Corpus Scorecard\n")
    lines.append(f"Generated: {raw['generated_at']}\n")
    lines.append(
        f"**{blocked_count}/{total} attacks BLOCKED** "
        f"({total - blocked_count} slipped through). "
        f"Every attack ran the real `.tess/bin/tessctl` engine, real `git`, real `gpg`, "
        f"against a fixture policy forked verbatim from this repo's own shipped "
        f"`core/policy/policy.yaml`.\n"
    )
    lines.append("| ID | Attack | Result | Mechanism |")
    lines.append("|---|---|---|---|")
    for o in outcomes:
        status = "BLOCKED" if o["blocked"] else "**SLIPPED THROUGH**"
        mech = o["mechanism"].replace("\n", " ").replace("|", "\\|")
        lines.append(f"| {o['id']} | {o['name']} | {status} | {mech} |")
    lines.append("")
    lines.append("## Full mechanism detail\n")
    for o in outcomes:
        lines.append(f"### {o['id']} — {o['name']}\n")
        lines.append(f"{o['description']}\n")
        lines.append(f"**Result:** {'BLOCKED' if o['blocked'] else 'SLIPPED THROUGH'}\n")
        lines.append(f"**Mechanism:** {o['mechanism']}\n")
    (RESULTS_DIR / "bypass-scorecard.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"\n[bypass] {blocked_count}/{total} blocked — wrote {RESULTS_DIR / 'bypass-scorecard.md'}")
    shutil.rmtree(base_dir, ignore_errors=True)
    # A scorecard with a slipped attack is evidence of a security regression,
    # not a successful test run. Preserve the complete honest artifact, then
    # fail the invoking CI/job so a green process status cannot mask it.
    return 0 if blocked_count == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
