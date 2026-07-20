#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Twiss
"""receipt_emit — Agent Receipt EMIT CLI.

The write-side counterpart to `tools/receipt-verify/` (verify-only,
standalone, zero third-party dependency). This tool PRODUCES an
[Agent Receipt](../../docs/AGENT_RECEIPT_SPEC.md) from an ALREADY-SIGNED
verdict or hard-floor sign-off. It never invents a decision, never signs
one on an operator's behalf, and never writes `core/policy/policy.yaml`
(read-only lookup only — see `policy_lookup.py`).

★ ARCHITECTURE — attaches to System B, never System A. This tool wraps a
REAL, GPG-signed verdict (`core/contracts/verdict.schema.json`) or
hard-floor sign-off (`.tess/gate/signoffs/<rule-id>.signoff.json` shape) —
"System B" in this project's own accountability model, the GPG
verdict/sign-off loop `tools/receipt-verify/` already verifies standalone.
It is explicitly NOT a wrapper for the `run_pipeline` HMAC approval
("System A") — that approval is a single-OS-account mechanism, not a
receipt `decision_kind` this schema recognizes, and wrapping it here would
overstate the trust an Agent Receipt is supposed to represent. `--decision`
must structurally match a `verdict.schema.json` instance (disposition:
APPROVE) or a `SignoffArtifact`; anything else — including, deliberately,
anything shaped like a System A HMAC approval — is refused before any file
is touched (see `assemble.infer_decision_kind`).

Usage:
    python3 receipt_emit.py emit \\
        --decision path/to/signed-verdict-or-signoff.json \\
        --rule-id <policy-rule-id> \\
        [--policy core/policy/policy.yaml] \\
        --actor <name> --summary <text> \\
        --key-id <gpg-key-id-or-fingerprint> \\
        --chain path/to/chain.jsonl \\
        [--gnupg-home path/to/homedir] \\
        [--trust NAME FINGERPRINT PUBLIC_KEY_FILE ...] \\
        [--json]

Exit code 0 means the receipt was assembled, signed, self-verified (a real
`tools/receipt-verify ... verify-chain` subprocess call against the
candidate chain reports CHAIN INTACT), and atomically committed to
`--chain`. Any other exit code means the emit was REFUSED — see the
printed reasons — and `--chain` is guaranteed byte-for-byte unchanged (see
`chain_atomic.py`'s own header for exactly how).

★ HONEST LABEL — printed on every successful emit (and included in `--json`
output as `trust_status`): the emitted receipt is genuinely GPG-signed and
tamper/chain-evident, but is NOT trust-anchored — `core/policy/policy.yaml`'s
`verifier_keys` / `signoff_keys` registries ship empty by design
(`docs/TRUST_BOOTSTRAP_SECURITY_DESIGN.md`), and registering a real
signer's key there is a separate, Xavier-gated key-ceremony decision this
tool does not perform. A self-verify PASS means "this receipt is genuine
and unaltered" — it never means "a trusted party's approval is enforced by
policy."

## Two deliberate, documented deviations from a literal CLI sketch

- **`--chain` is REQUIRED, not defaulted.** Where the receipt chain
  belongs by default (a new `.tess/state/**` subsystem? a plain top-level
  directory?) is a real repository-convention decision — the SAME
  four-layer fence (`never_touch`, `.gitignore`, the publish-clean gate,
  `create-tess` scaffold-strip) `docs/STATE_LAYER.md` documents for every
  existing `.tess/state/**` subsystem would need to extend to cover it, and
  that fence's enforcement layer lives in `.tess/bin/tessctl` — explicitly
  out of this PR's scope. Requiring `--chain` explicitly avoids silently
  picking a convention inside a narrowly-scoped emit-tool PR; the operator
  always states where their receipt journal lives.
- **`--trust NAME FINGERPRINT PUBLIC_KEY_FILE` (repeatable, optional) is an
  ADDED flag**, not in the original sketch. It exists solely so this
  tool's own self-verify step can literally satisfy "verify-chain must
  return CHAIN INTACT" for a chain whose EARLIER receipts were signed by a
  DIFFERENT identity than this emit's own `--key-id` (e.g. an AI verdict
  followed by a human sign-off, mirroring `examples/receipt-demo/`). The
  current signer's identity/fingerprint/exported key is ALWAYS included in
  self-verify automatically; `--trust` supplies any ADDITIONAL identities
  already present earlier in the chain. It is used ONLY for this emit's
  own self-verify subprocess call — never embedded in the receipt itself,
  never a substitute for a real key-ceremony registration.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
_RECEIPT_VERIFY_DIR = _THIS_DIR.parent / "receipt-verify"
sys.path.insert(0, str(_THIS_DIR))
sys.path.insert(0, str(_RECEIPT_VERIFY_DIR))

import canonical  # noqa: E402  (tools/receipt-verify/canonical.py — reused, not reimplemented)

import assemble  # noqa: E402
import chain_atomic  # noqa: E402
import gpg_sign  # noqa: E402
import policy_lookup  # noqa: E402
from errors import EmitRefused  # noqa: E402

RECEIPT_VERIFY_CLI = _RECEIPT_VERIFY_DIR / "receipt_verify.py"

HONEST_LABEL = (
    "This receipt is genuinely GPG-signed and tamper/chain-evident, but is "
    "NOT trust-anchored until the signer's key is registered in "
    "core/policy/policy.yaml (verifier_keys / signoff_keys — currently "
    "empty). Key-ceremony registration is Xavier-gated and is not "
    "performed by this tool. A self-verify PASS proves the receipt is "
    "genuine and unaltered; it does not mean a trusted party's approval "
    "is enforced by policy."
)


def _load_decision_json(path: str) -> dict:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as e:
        raise EmitRefused([f"could not read --decision file {path!r}: {e}"])
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise EmitRefused([f"--decision file {path!r} is not valid JSON: {e}"])


def _self_verify(tmp_chain_path: Path, trust_entries: list[tuple[str, str, str]]) -> None:
    """Runs the REAL, independent tools/receipt-verify/receipt_verify.py
    verify-chain as a subprocess against the CANDIDATE chain file — the
    same way examples/receipt-demo/build_demo.py already runs it, and the
    same way any external party would. Raises EmitRefused unless the
    result is chain_intact: true."""
    args = [sys.executable, str(RECEIPT_VERIFY_CLI), "verify-chain", str(tmp_chain_path), "--json"]
    for name, fingerprint, keyfile in trust_entries:
        args += ["--trust", name, fingerprint, keyfile]
    result = subprocess.run(args, capture_output=True, text=True)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise EmitRefused([
            f"self-verify (verify-chain) did not return valid JSON "
            f"(exit {result.returncode}): {(result.stdout or result.stderr).strip()}"
        ])
    if not payload.get("chain_intact"):
        reasons = []
        for failure in payload.get("failures", []):
            reasons.extend(f"receipt[{failure.get('index')}]: {r}" for r in failure.get("reasons", []))
        raise EmitRefused(reasons or ["self-verify (verify-chain) did not report CHAIN INTACT"])


def run_emit(args: argparse.Namespace) -> dict:
    """The full emit pipeline: infer + validate the decision, look up the
    fired policy rule, resolve the signing key, assemble + sign the
    envelope, self-verify the candidate chain, and only then atomically
    commit it. Returns a result dict on success; raises `EmitRefused`
    (with NOTHING written to disk) on any refusal."""
    decision = _load_decision_json(args.decision)

    decision_kind = assemble.infer_decision_kind(decision)
    if decision_kind is None:
        raise EmitRefused([
            "--decision does not structurally match a verdict.schema.json "
            "instance (every field in checks.VERDICT_REQUIRED_KEYS) or a "
            "hard-floor signoff artifact (every field in "
            "checks.SIGNOFF_REQUIRED_KEYS) — refusing rather than guessing "
            "which kind of decision this is"
        ])
    identity = assemble.validate_decision_or_refuse(decision_kind, decision)

    policy_decision = policy_lookup.load_policy_rule(args.policy, args.rule_id)
    assemble.validate_policy_pairing_or_refuse(policy_decision, decision_kind)

    if args.gnupg_home is None and gpg_sign.which_gpg() is None:
        raise EmitRefused(["the 'gpg' binary is not installed or not on PATH"])
    fingerprint = gpg_sign.resolve_fingerprint(args.key_id, args.gnupg_home)
    pubkey_armored = gpg_sign.export_public_key_armored(fingerprint, args.gnupg_home)

    chain_path = Path(args.chain)
    sequence, prev_hash = chain_atomic.next_chain_link(chain_path, canonical.receipt_content_hash)

    receipt = assemble.build_envelope(
        actor=args.actor, summary=args.summary, policy_decision=policy_decision,
        decision_kind=decision_kind, decision=decision,
        sequence=sequence, prev_hash=prev_hash,
    )
    receipt = assemble.sign_envelope(
        receipt, signed_by=identity, key_id=args.key_id, gnupg_home=args.gnupg_home,
        sign_fn=gpg_sign.detached_sign,
    )

    extra_trust = [tuple(t) for t in (args.trust or []) if t[0] != identity]
    with tempfile.TemporaryDirectory(prefix="receipt-emit-selfverify-") as tmp_dir:
        pubkey_path = Path(tmp_dir) / "signer-public.asc"
        pubkey_path.write_text(pubkey_armored, encoding="utf-8")
        all_trust = [(identity, fingerprint, str(pubkey_path))] + extra_trust

        def verify_fn(tmp_chain_path: Path) -> None:
            _self_verify(tmp_chain_path, all_trust)

        chain_atomic.append_receipt_atomically(chain_path, receipt, verify_fn)

    return {
        "receipt_id": receipt["receipt_id"],
        "chain": str(chain_path),
        "sequence": receipt["chain"]["sequence"],
        "signed_by": identity,
        "fingerprint": fingerprint,
        "trust_status": "signed_not_trust_anchored",
        "honest_label": HONEST_LABEL,
    }


def cmd_emit(args: argparse.Namespace) -> int:
    try:
        result = run_emit(args)
    except EmitRefused as e:
        if args.json_out:
            print(json.dumps({"emitted": False, "reasons": e.reasons}, sort_keys=True))
        else:
            print("REFUSED — no receipt written, --chain left unchanged:")
            for reason in e.reasons:
                print(f"  - {reason}")
        return 1

    if args.json_out:
        print(json.dumps({"emitted": True, **result}, sort_keys=True))
    else:
        print(f"EMITTED receipt {result['receipt_id']} (sequence {result['sequence']}) -> {result['chain']}")
        print(f"signed_by: {result['signed_by']}  fingerprint: {result['fingerprint']}")
        print("self-verify: CHAIN INTACT")
        print()
        print(HONEST_LABEL)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    emit_p = sub.add_parser("emit", help="assemble, sign, self-verify, and atomically append one Agent Receipt")
    emit_p.add_argument("--decision", required=True, help="path to an already-signed verdict or hard-floor signoff JSON file")
    emit_p.add_argument("--rule-id", required=True, help="the core/policy/policy.yaml rule id that required this approval")
    emit_p.add_argument("--policy", default="core/policy/policy.yaml", help="path to the READ-ONLY policy instance to copy the fired rule from (default: core/policy/policy.yaml)")
    emit_p.add_argument("--actor", required=True, help="the agent/persona who proposed the action")
    emit_p.add_argument("--summary", required=True, help="human-readable description of what was proposed")
    emit_p.add_argument("--key-id", required=True, help="the GPG key id/fingerprint to sign the receipt envelope with")
    emit_p.add_argument("--chain", required=True, help="JSONL chain file to atomically append this receipt to (created if missing) — see this file's docstring for why this is required, not defaulted")
    emit_p.add_argument("--gnupg-home", default=None, help="GNUPGHOME to use for --key-id (default: the ambient/default keyring)")
    emit_p.add_argument(
        "--trust", action="append", nargs=3, metavar=("NAME", "FINGERPRINT", "PUBLIC_KEY_FILE"),
        help="an ADDITIONAL identity's pinned fingerprint + public key file, needed only if --chain "
             "already contains a receipt signed by an identity other than this emit's own --key-id; "
             "used solely for this emit's own self-verify step, never embedded in the receipt (repeatable)",
    )
    emit_p.add_argument("--json", dest="json_out", action="store_true", help="emit JSON instead of text")
    emit_p.set_defaults(func=cmd_emit)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
