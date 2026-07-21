#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Twiss
"""receipt_verify — standalone Agent Receipt verifier.

Verifies an Agent Receipt (docs/AGENT_RECEIPT_SPEC.md,
core/contracts/agent-receipt.schema.json) INDEPENDENTLY of the rest of the
Tess OS install: no `tessctl` import, no `spec_engine` import, no
`core/policy/policy.yaml`, no mission tree. All it needs is this directory
(`canonical.py`, `gpg_verify.py`, `hmac_verify.py`, `checks.py`,
`receipt_verify.py`), the stdlib, and (for `verdict`/`signoff` receipts
only) the system `gpg` binary — a `local_approval` receipt verifies with
pure Python, no `gpg` binary required.

Usage:
    python3 receipt_verify.py verify RECEIPT.json \\
        --trust NAME FINGERPRINT KEY_FILE [--trust ...] \\
        [--prev PREV_RECEIPT.json] [--json]

    python3 receipt_verify.py verify-chain CHAIN.jsonl \\
        --trust NAME FINGERPRINT KEY_FILE [--trust ...] \\
        [--json]

`--trust` is repeatable, one per identity the caller is willing to trust —
mirroring core/contracts/policy.schema.json's `VerifierKeyEntry` shape
(fingerprint + key file) but supplied directly on the command line,
since a third party verifying a receipt has no reason to hold this
project's core/policy/policy.yaml at all. A signature from an identity with
no matching --trust entry never verifies — fail-closed, not fail-open.

★ `--trust`'s KEYFILE argument means TWO DIFFERENT THINGS depending on the
receipt's `decision_kind` — read this before treating it as always a safe
public key: for a `verdict`/`signoff` decision it is a GPG PUBLIC key
(safe to hand to anyone; that is the whole point of asymmetric signing).
For a `local_approval` decision (wedge-loop epic addition) it is instead
the SAME raw SECRET local approval-identity key that produced the
signature in the first place (normally
`~/.tess-os/approval-identity/<username>.key`) — there is no "public
half" for an HMAC scheme. Anyone able to supply that file to `--trust`
can also FORGE a new, equally-valid `local_approval` signature under that
identity; verifying a `local_approval` receipt is NOT a lower-privilege
operation than signing one. Treat a `local_approval` KEYFILE with the same
care as any other secret credential. See `hmac_verify.py`'s module
docstring and docs/AGENT_RECEIPT_SPEC.md for the full disclosure.

Exit code 0 means every check passed (or, for verify-chain, the whole chain
is intact). Any other exit code means at least one receipt failed at least
one check; see the printed reasons for exactly which one.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from checks import verify_receipt  # noqa: E402  (sys.path must be set first)


def _load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_trust(entries: list) -> dict:
    """entries: list of [NAME, FINGERPRINT, KEYFILE] triples from argparse.
    Returns {NAME: {"fingerprint": FPR, "key_bytes": bytes}}. `key_bytes`
    is deliberately a neutral name (not `public_key_bytes`): for a
    `verdict`/`signoff` identity KEYFILE is a GPG public key; for a
    `local_approval` identity it is the local HMAC SECRET key instead —
    see this module's own docstring "★" note and hmac_verify.py."""
    trust = {}
    for name, fingerprint, keyfile in entries or []:
        trust[name] = {
            "fingerprint": fingerprint,
            "key_bytes": Path(keyfile).read_bytes(),
        }
    return trust


def _print_result(label: str, ok: bool, reasons: list, as_json: bool) -> None:
    if as_json:
        print(json.dumps({"label": label, "valid": ok, "reasons": reasons}, sort_keys=True))
        return
    status = "VALID" if ok else "INVALID"
    print(f"{label}: {status}")
    for reason in reasons:
        print(f"  - {reason}")


def cmd_verify(args) -> int:
    receipt = _load_json(args.receipt)
    prev_receipt = _load_json(args.prev) if args.prev else None
    trust = _load_trust(args.trust)
    reasons = verify_receipt(receipt, trust, prev_receipt=prev_receipt)
    _print_result(f"receipt {args.receipt}", not reasons, reasons, args.json_out)
    return 0 if not reasons else 1


def _read_chain_records(path: str) -> list:
    records = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def cmd_verify_chain(args) -> int:
    records = _read_chain_records(args.chain)
    trust = _load_trust(args.trust)
    all_reasons = []
    prev = None
    for i, receipt in enumerate(records):
        reasons = verify_receipt(receipt, trust, prev_receipt=prev)
        if reasons:
            all_reasons.append({"index": i, "receipt_id": receipt.get("receipt_id"), "reasons": reasons})
        prev = receipt
    ok = not all_reasons
    if args.json_out:
        print(json.dumps({
            "chain": args.chain, "receipt_count": len(records),
            "chain_intact": ok, "failures": all_reasons,
        }, sort_keys=True))
    elif ok:
        print(f"CHAIN INTACT ({len(records)} receipts) — {args.chain}")
    else:
        print(f"CHAIN BROKEN — {args.chain}")
        for failure in all_reasons:
            print(f"  receipt[{failure['index']}] ({failure['receipt_id']}):")
            for reason in failure["reasons"]:
                print(f"    - {reason}")
    return 0 if ok else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    verify_p = sub.add_parser("verify", help="verify a single Agent Receipt")
    verify_p.add_argument("receipt", help="path to the receipt JSON file")
    verify_p.add_argument("--prev", default=None, help="path to the previous receipt in the chain, if any")
    verify_p.add_argument(
        "--trust", action="append", nargs=3, metavar=("NAME", "FINGERPRINT", "KEY_FILE"),
        help="a trusted identity's exact fingerprint + key file (repeatable) — "
             "a GPG PUBLIC key for a verdict/signoff identity, or the local "
             "HMAC SECRET key for a local_approval identity (see module docstring)",
    )
    verify_p.add_argument("--json", dest="json_out", action="store_true", help="emit JSON instead of text")
    verify_p.set_defaults(func=cmd_verify)

    chain_p = sub.add_parser("verify-chain", help="verify every receipt in a JSONL chain file, in order")
    chain_p.add_argument("chain", help="path to a JSONL file, one Agent Receipt per line, in sequence order")
    chain_p.add_argument(
        "--trust", action="append", nargs=3, metavar=("NAME", "FINGERPRINT", "KEY_FILE"),
        help="a trusted identity's exact fingerprint + key file (repeatable) — "
             "a GPG PUBLIC key for a verdict/signoff identity, or the local "
             "HMAC SECRET key for a local_approval identity (see module docstring)",
    )
    chain_p.add_argument("--json", dest="json_out", action="store_true", help="emit JSON instead of text")
    chain_p.set_defaults(func=cmd_verify_chain)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
