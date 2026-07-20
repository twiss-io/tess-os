#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Twiss
"""Runnable Agent Receipt demo: propose -> approve -> sign -> journal -> verify.

Builds two chained Agent Receipts using EPHEMERAL, TEST-ONLY GPG keys
(generated fresh, never registered in core/policy/policy.yaml, destroyed at
exit), writes them to a local, gitignored output directory, then runs the
STANDALONE verifier (tools/receipt-verify/) against them exactly the way an
independent third party would: as a subprocess, given only the receipt
files and the demo's public keys.

  Receipt 0 (genesis)  — an AI-verifier "verdict" approval (docs change)
  Receipt 1 (chained)  — a human-operator "sign-off" approval (hard floor:
                         money movement) that chains from Receipt 0

Also runs one deliberately TAMPERED copy through the verifier to prove the
negative case: a receipt that has been altered after signing is rejected,
not just the happy path.

See examples/receipt-demo/README.md for what this proves and does not prove.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEMO_DIR = Path(__file__).resolve().parent
RECEIPT_VERIFY = REPO_ROOT / "tools" / "receipt-verify" / "receipt_verify.py"

sys.path.insert(0, str(DEMO_DIR))
from demo_keys import destroy_demo_key, generate_demo_key  # noqa: E402
from demo_receipts import build_genesis_receipt, build_second_receipt  # noqa: E402


def _banner(text: str) -> None:
    print(f"\n{'=' * 78}\n{text}\n{'=' * 78}")


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _run_verifier(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(RECEIPT_VERIFY), *args],
        capture_output=True, text=True,
    )


def main() -> int:
    out_dir = DEMO_DIR / ".output"
    out_dir.mkdir(exist_ok=True)

    _banner("STEP 0 — generate ephemeral, demo-only GPG identities")
    print("These keys are generated fresh for this run only. They are NEVER")
    print("registered in core/policy/policy.yaml's verifier_keys/signoff_keys,")
    print("and are destroyed when this script exits. Nothing here creates or")
    print("touches this repository's real trust anchor.")
    reid_key = generate_demo_key("Reid", "reid-demo@agent-receipt.test")
    operator_key = generate_demo_key("demo-operator", "demo-operator@agent-receipt.test")
    print(f"  Reid (demo/test key)           fingerprint: {reid_key.fingerprint}")
    print(f"  demo-operator (demo/test key)  fingerprint: {operator_key.fingerprint}")

    try:
        _banner("STEP 1 — propose + approve + sign: Receipt 0 (AI-verifier 'verdict')")
        receipt0 = build_genesis_receipt(reid_key)
        print(f"  proposed_action.summary : {receipt0['proposed_action']['summary']}")
        print(f"  policy_decision.rule_id : {receipt0['policy_decision']['rule_id']}")
        print(f"  decision_kind           : {receipt0['decision_kind']} (signed by {reid_key.name})")
        print(f"  chain.sequence          : {receipt0['chain']['sequence']} (genesis)")

        _banner("STEP 2 — propose + approve + sign: Receipt 1 (human 'sign-off', hard floor)")
        receipt1 = build_second_receipt(receipt0, operator_key)
        print(f"  proposed_action.summary : {receipt1['proposed_action']['summary']}")
        print(f"  policy_decision.rule_id : {receipt1['policy_decision']['rule_id']} ({receipt1['policy_decision']['category']})")
        print(f"  decision_kind           : {receipt1['decision_kind']} (signed by {operator_key.name})")
        print(f"  chain.sequence          : {receipt1['chain']['sequence']}, chained from Receipt 0")

        _banner("STEP 3 — journal: write the receipt chain + public keys to disk")
        _write_json(out_dir / "receipt-0.json", receipt0)
        _write_json(out_dir / "receipt-1.json", receipt1)
        chain_path = out_dir / "receipt-chain.jsonl"
        chain_path.write_text(
            json.dumps(receipt0, sort_keys=True) + "\n" + json.dumps(receipt1, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (out_dir / "reid-demo-public.asc").write_text(reid_key.public_key_armored, encoding="utf-8")
        (out_dir / "demo-operator-public.asc").write_text(operator_key.public_key_armored, encoding="utf-8")
        print(f"  wrote {chain_path.relative_to(REPO_ROOT)} (2 receipts) + both demo public keys")

        _banner("STEP 4 — verify: run the STANDALONE verifier as an independent third party would")
        result = _run_verifier(
            "verify-chain", str(chain_path),
            "--trust", "Reid", reid_key.fingerprint, str(out_dir / "reid-demo-public.asc"),
            "--trust", operator_key.name, operator_key.fingerprint, str(out_dir / "demo-operator-public.asc"),
        )
        print(result.stdout.strip())
        if result.returncode != 0:
            print(result.stderr, file=sys.stderr)
            print("\nDEMO FAILED: the happy-path chain did not verify. See output above.")
            return 1

        _banner("STEP 5 — negative control: tamper with Receipt 1 and verify AGAIN")
        print("Flipping receipt-1's rationale AFTER it was signed, without re-signing —")
        print("this must be REJECTED, not silently accepted.")
        tampered = json.loads(chain_path.read_text().splitlines()[1])
        tampered["decision"]["rationale"] = "TAMPERED — this text was changed after signing"
        tampered_path = out_dir / "receipt-1-tampered.json"
        _write_json(tampered_path, tampered)
        bad_result = _run_verifier(
            "verify", str(tampered_path), "--prev", str(out_dir / "receipt-0.json"),
            "--trust", operator_key.name, operator_key.fingerprint, str(out_dir / "demo-operator-public.asc"),
        )
        print(bad_result.stdout.strip())
        if bad_result.returncode == 0:
            print("\nDEMO FAILED: a tampered receipt verified as VALID. This must never happen.")
            return 1
        print("\nConfirmed: the tampered receipt was correctly rejected.")

        _banner("DEMO COMPLETE")
        print(f"Artifacts written under: {out_dir.relative_to(REPO_ROOT)}")
        print("CHAIN INTACT for the untampered receipts; the tampered copy was rejected.")
        return 0
    finally:
        destroy_demo_key(reid_key)
        destroy_demo_key(operator_key)


if __name__ == "__main__":
    raise SystemExit(main())
