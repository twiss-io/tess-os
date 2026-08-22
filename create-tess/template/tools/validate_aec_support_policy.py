"""CLI for the offline advisory AEC support-policy validator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from .aec_support_policy_validator import validate_repository


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the advisory AEC support-policy template without changing the checkout."
    )
    parser.add_argument("--root", default=".", help="repository root (default: current directory)")
    parser.add_argument("--json", action="store_true", help="emit stable advisory JSON")
    args = parser.parse_args(argv)
    findings = validate_repository(Path(args.root))
    payload = {
        "advisory": True,
        "runtime_enforcement": False,
        "findings": findings,
        "valid": not findings,
    }
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
