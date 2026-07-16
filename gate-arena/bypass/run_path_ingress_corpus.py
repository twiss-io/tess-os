#!/usr/bin/env python3
"""Run the no-key A13 path-ingress adversarial regression corpus.

This corpus is intentionally separate from the historical GPG-backed A1-A12
scorecard.  It exercises only raw Git path ingress and transition denial and
does not generate, register, sign with, or verify any private key/verdict.
Every pytest outcome, including skips and failures, is recorded; only actual
passes contribute to the numerator.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree


REPO_ROOT = Path(__file__).resolve().parents[2]
RESULT_JSON = REPO_ROOT / "gate-arena" / "results" / "path-ingress-scorecard.json"
RESULT_MD = REPO_ROOT / "gate-arena" / "results" / "path-ingress-scorecard.md"
TEST_TARGETS = (
    "tests/test_gate_path_ingress.py",
    "tests/test_gate_type_swaps.py",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _case_outcomes(xml_path: Path) -> list[dict]:
    root = ElementTree.parse(xml_path).getroot()
    outcomes = []
    for case in root.iter("testcase"):
        status = "passed"
        detail = None
        for child_status in ("failure", "error", "skipped"):
            child = case.find(child_status)
            if child is not None:
                status = child_status
                detail = (child.get("message") or child.text or "").strip()
                break
        outcomes.append({
            "id": f"{case.get('classname', '')}::{case.get('name', '')}",
            "status": status,
            "detail": detail,
        })
    return outcomes


def _markdown(scorecard: dict) -> str:
    failures = [case for case in scorecard["cases"] if case["status"] != "passed"]
    lines = [
        "# Gate Arena — A13 path-ingress scorecard",
        "",
        f"Measured: `{scorecard['measured_at']}`",
        "",
        f"**Result: {scorecard['passed']}/{scorecard['total']} tests passed.** "
        f"Failures: {scorecard['failed']}; errors: {scorecard['errors']}; "
        f"skips: {scorecard['skipped']}.",
        "",
        "## Scope",
        "",
        "The no-key corpus covers strict NUL-delimited raw-diff parsing; SHA-1 "
        "and SHA-256 object IDs; malformed status/mode/OID tuples; deletion and "
        "rename-away; executable-bit and type transitions; symlink and gitlink "
        "states; newline, tab, NFC, NFD, and non-UTF-8 paths; staged, explicit-ref, "
        "pre-push stdin, installed-hook, CI, and MCP ingress; and the regular-file "
        "A/M controls that must still proceed to normal review.",
        "",
        "## Trust-boundary disclosure",
        "",
        "This run performed no GPG/key generation, verifier registration, verdict "
        "signing, sign-off signing, or trust bootstrap. The shipped empty verifier "
        "registry remains untouched. Reviewable governed controls therefore pass "
        "this corpus only when they reach the expected fail-closed `no covering "
        "APPROVE verdict` result; they do not clear the ship-gate.",
        "",
        "This score is separate from the historical A1-A12 `12/12` GPG-backed "
        "bypass scorecard. The numbers are not added together and do not prove "
        "that the gate is unbypassable.",
        "",
        "## Reproduce",
        "",
        "```sh",
        "python3 gate-arena/bypass/run_path_ingress_corpus.py",
        "```",
        "",
        f"Engine SHA-256: `{scorecard['engine_sha256']}`",
        "",
        "## Non-passing cases",
        "",
    ]
    if not failures:
        lines.append("None.")
    else:
        lines += ["| Case | Outcome | Detail |", "|---|---|---|"]
        for case in failures:
            detail = (case.get("detail") or "").replace("|", "\\|").replace("\n", " ")
            lines.append(f"| `{case['id']}` | **{case['status'].upper()}** | {detail} |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="tess-path-ingress-") as temp_dir:
        junit_path = Path(temp_dir) / "junit.xml"
        command = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            *TEST_TARGETS,
            f"--junitxml={junit_path}",
        ]
        run = subprocess.run(command, cwd=REPO_ROOT, text=True)
        if not junit_path.exists():
            print("path-ingress corpus: pytest produced no JUnit result", file=sys.stderr)
            return run.returncode or 2
        cases = _case_outcomes(junit_path)

    counts = {name: sum(case["status"] == name for case in cases) for name in (
        "passed", "failure", "error", "skipped",
    )}
    scorecard = {
        "schema": 1,
        "corpus": "A13-path-ingress-no-key",
        "measured_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "command": "python3 -m pytest -q " + " ".join(TEST_TARGETS),
        "engine_sha256": _sha256(REPO_ROOT / ".tess" / "bin" / "tessctl"),
        "trust_operations": {
            "key_generation": False,
            "key_registration": False,
            "verdict_signing": False,
            "signoff_signing": False,
        },
        "total": len(cases),
        "passed": counts["passed"],
        "failed": counts["failure"],
        "errors": counts["error"],
        "skipped": counts["skipped"],
        "cases": cases,
    }
    RESULT_JSON.write_text(json.dumps(scorecard, indent=2) + "\n", encoding="utf-8")
    RESULT_MD.write_text(_markdown(scorecard), encoding="utf-8")
    print(
        f"path-ingress corpus: {scorecard['passed']}/{scorecard['total']} passed; "
        f"failures={scorecard['failed']} errors={scorecard['errors']} "
        f"skips={scorecard['skipped']}"
    )
    return 0 if run.returncode == 0 and counts["passed"] == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
