"""Command-line wrapper for the advisory adapter-manifest validator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from .adapter_manifest_validator import validate_repository


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate local advisory adapter manifests without changing the checkout."
    )
    parser.add_argument("--root", default=".", help="repository root to inspect (default: current directory)")
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the stable advisory JSON record (the only output format)",
    )
    args = parser.parse_args(argv)
    findings = validate_repository(Path(args.root))
    payload = {"advisory": True, "findings": findings, "valid": not findings}
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
