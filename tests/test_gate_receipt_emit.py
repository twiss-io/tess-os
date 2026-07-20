"""
PR-2 — Agent Receipt EMIT wiring: `tessctl gate` auto-emits an Agent Receipt
(via `tools/receipt-emit/`, PR-1) into `.tess/state/receipts/chain.jsonl`
every time it CLEARS a change via a covering signed APPROVE verdict, or a
hard floor via a signed sign-off. Closes DoD B.9 further.

Reuses test_gate_spine.py's `gate_repo` fixture + verdict/sign-off building
blocks VERBATIM (imported, not re-derived) — the same cross-import pattern
test_mcp_serve.py already uses for the identical reason: this suite's own
scenarios must be built from EXACTLY the machinery test_gate_spine.py's own
reference tests already use, never a parallel re-implementation that could
silently drift out of sync with what "the gate clears" actually means.

Coverage (per the dispatch brief's explicit test list):
  * gate clears via a signed covering APPROVE verdict -> receipt auto-emitted
    + independently verifiable (CHAIN INTACT, via the real standalone
    tools/receipt-verify/ CLI, not just tessctl's own self-report)
  * gate clears via a signed hard-floor sign-off -> receipt emitted
  * two separate clearing pushes chain correctly (sequence/prev_receipt_hash)
  * emit-failure (no matching private key in the ambient keyring) is handled
    per the fail-closed + non-silent coupling this PR chose: VISIBLE
    (receipt_gaps, ACCOUNTABILITY GAP text, trace log), never silent, and
    NEVER flips the gate's own blocked/pass decision
  * the emitted receipt carries the honest "signed, NOT trust-anchored"
    label, in both --json and text-mode gate output
  * the .tess/state/receipts/** leak-fence (gitignore / never_touch /
    publish-clean / create-tess scaffold-strip) is covered by parametrized
    additions to the existing .tess/state/** fence test suites (see
    tests/test_gitignore_reconciliation.py, tests/test_publish_clean_gate.py,
    tests/test_write_gate.py, create-tess/test/units.test.js) rather than a
    parallel copy here — this file focuses on the GATE <-> EMIT wiring itself.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO_ROOT

from test_gate_spine import (
    gate_repo,  # noqa: F401  (pytest fixture, made available via import)
    _git, _base_sha, _commit_all, _blob_sha,
    _valid_verdict, _write_verdict, _signed_signoff,
)

RECEIPT_EMIT_SRC = REPO_ROOT / "tools" / "receipt-emit"
RECEIPT_VERIFY_SRC = REPO_ROOT / "tools" / "receipt-verify"
RECEIPT_VERIFY_CLI = RECEIPT_VERIFY_SRC / "receipt_verify.py"

CHAIN_REL = Path(".tess") / "state" / "receipts" / "chain.jsonl"


# ---------------------------------------------------------------------------
# Fixture: gate_repo + a real, committed tools/receipt-emit/ + tools/
# receipt-verify/ copy — the exact shape an adopter project actually has
# (create-tess's whole-tree-minus-exclusions scaffold ships both dirs; see
# GATE_RECEIPT_CHAIN_REL / RECEIPT_EMIT_CLI_REL's own module comment in
# .tess/bin/tessctl for why resolution is against the OPERATING root).
# ---------------------------------------------------------------------------

@pytest.fixture
def gate_repo_with_receipt_emit(gate_repo):  # noqa: F811 (fixture shadow is intentional)
    root = gate_repo
    shutil.copytree(RECEIPT_VERIFY_SRC, root / "tools" / "receipt-verify")
    shutil.copytree(RECEIPT_EMIT_SRC, root / "tools" / "receipt-emit")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "vendor tools/receipt-emit + tools/receipt-verify")
    return root


def _chain_path(root: Path) -> Path:
    return root / CHAIN_REL


def _independent_verify_chain(root: Path, trust_entries: list[tuple[str, str, str]]) -> dict:
    """Runs the REAL, standalone tools/receipt-verify/receipt_verify.py
    verify-chain CLI directly — never tessctl's own self-report — the same
    zero-trust, third-party-facing check an outside auditor would run
    against nothing but the chain file + a pinned public key."""
    args = [sys.executable, str(RECEIPT_VERIFY_CLI), "verify-chain", str(_chain_path(root)), "--json"]
    for name, fpr, keyfile in trust_entries:
        args += ["--trust", name, fpr, keyfile]
    r = subprocess.run(args, capture_output=True, text=True)
    return json.loads(r.stdout)


def _export_pubkey(key, tmp_path: Path, filename: str) -> Path:
    p = tmp_path / filename
    p.write_text(key.pubkey_armored, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# 1) gate clears via a covering signed APPROVE verdict -> receipt auto-emitted
#    + independently verifiable
# ---------------------------------------------------------------------------

def test_ci_clear_via_covering_verdict_auto_emits_verifiable_receipt(
    gate_repo_with_receipt_emit, run_cli, engine, verifier_gpg_keys, tmp_path,
):
    root = gate_repo_with_receipt_emit
    base = _base_sha(root)
    (root / "src" / "prod").mkdir(parents=True)
    (root / "src" / "prod" / "app.py").write_text("print('prod')\n")
    blob = _blob_sha(root, "src/prod/app.py")
    _write_verdict(
        root, "missions/m1/verdicts/prod-src.verdict.md",
        _valid_verdict(
            covers_paths=["src/prod/**"], artifact_hashes={"src/prod/app.py": blob},
            engine=engine, keys=verifier_gpg_keys,
        ),
    )
    head = _commit_all(root, "add prod change + covering verdict")

    r = run_cli(
        root, "gate", "ci", "--base", base, "--head", head, "--json",
        extra_env={"GNUPGHOME": str(verifier_gpg_keys["Reid"].home)},
    )
    assert r.returncode == 0, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    assert payload["blocked"] is False

    # The gate's own report: exactly one receipt emitted, for the rule that
    # actually cleared, no gaps, honest label present.
    assert payload["receipt_gaps"] == []
    assert len(payload["receipts_emitted"]) == 1
    emitted = payload["receipts_emitted"][0]
    assert emitted["rule_id"] == "prod-src"
    assert emitted["decision_kind"] == "verdict"
    assert emitted["trust_status"] == "signed_not_trust_anchored"
    assert isinstance(emitted["receipt_id"], str) and emitted["receipt_id"]
    assert emitted["sequence"] == 0

    # The chain file itself: exactly one line, correct shape, embeds the
    # covering verdict verbatim.
    chain_path = _chain_path(root)
    assert chain_path.exists()
    lines = [ln for ln in chain_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1
    receipt = json.loads(lines[0])
    assert receipt["receipt_schema"] == "tess-os.agent-receipt/1"
    assert receipt["decision_kind"] == "verdict"
    assert receipt["decision"]["verifier"] == "Reid"
    assert receipt["decision"]["disposition"] == "APPROVE"
    assert receipt["policy_decision"]["rule_id"] == "prod-src"
    assert receipt["policy_decision"]["rule_kind"] == "path_rule"
    assert receipt["chain"] == {"sequence": 0, "prev_receipt_hash": "GENESIS"}
    assert receipt["receipt_signature"]["signed_by"] == "Reid"

    # Independent verification via the REAL standalone tools/receipt-verify/
    # CLI — not tessctl's own claim.
    pubkey = _export_pubkey(verifier_gpg_keys["Reid"], tmp_path, "reid.asc")
    result = _independent_verify_chain(root, [("Reid", verifier_gpg_keys["Reid"].fpr, str(pubkey))])
    assert result["chain_intact"] is True, result
    assert result["receipt_count"] == 1


# ---------------------------------------------------------------------------
# 2) gate clears via a hard-floor signed sign-off -> receipt emitted
# ---------------------------------------------------------------------------

def test_ci_clear_via_hard_floor_signoff_emits_receipt(
    gate_repo_with_receipt_emit, run_cli, engine, verifier_gpg_keys, tmp_path,
):
    root = gate_repo_with_receipt_emit
    base = _base_sha(root)
    (root / "payments").mkdir(parents=True)
    (root / "payments" / "charge.py").write_text("refund()\n")
    signoff_dir = root / ".tess" / "gate" / "signoffs"
    signoff_dir.mkdir(parents=True, exist_ok=True)
    # gate_repo's policy registers "Xavier" in signoff_keys, reusing Reid's
    # generated test keypair under that name (test_gate_spine.py's own
    # documented, deliberate choice — see _policy_with_verifier_keys).
    signoff = _signed_signoff(engine, verifier_gpg_keys["Reid"])
    (signoff_dir / "money.signoff.json").write_text(json.dumps(signoff), encoding="utf-8")
    head = _commit_all(root, "payments change + validly-signed human signoff")

    r = run_cli(
        root, "gate", "ci", "--base", base, "--head", head, "--json",
        extra_env={"GNUPGHOME": str(verifier_gpg_keys["Reid"].home)},
    )
    assert r.returncode == 0, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    assert payload["blocked"] is False
    assert payload["receipt_gaps"] == []
    assert len(payload["receipts_emitted"]) == 1
    emitted = payload["receipts_emitted"][0]
    assert emitted["rule_id"] == "money"
    assert emitted["decision_kind"] == "signoff"
    assert emitted["trust_status"] == "signed_not_trust_anchored"

    chain_path = _chain_path(root)
    lines = [ln for ln in chain_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1
    receipt = json.loads(lines[0])
    assert receipt["decision_kind"] == "signoff"
    assert receipt["decision"]["authorized_by"] == "Xavier"
    assert receipt["policy_decision"]["rule_id"] == "money"
    assert receipt["policy_decision"]["rule_kind"] == "hard_floor_rule"

    pubkey = _export_pubkey(verifier_gpg_keys["Reid"], tmp_path, "xavier.asc")
    result = _independent_verify_chain(root, [("Xavier", verifier_gpg_keys["Reid"].fpr, str(pubkey))])
    assert result["chain_intact"] is True, result


# ---------------------------------------------------------------------------
# 3) two separate clearing pushes chain correctly
# ---------------------------------------------------------------------------

def test_two_clearing_pushes_chain_correctly(
    gate_repo_with_receipt_emit, run_cli, engine, verifier_gpg_keys, tmp_path,
):
    root = gate_repo_with_receipt_emit
    env = {"GNUPGHOME": str(verifier_gpg_keys["Reid"].home)}

    base1 = _base_sha(root)
    (root / "src" / "prod").mkdir(parents=True)
    (root / "src" / "prod" / "app.py").write_text("print('prod')\n")
    blob = _blob_sha(root, "src/prod/app.py")
    _write_verdict(
        root, "missions/m1/verdicts/prod-src.verdict.md",
        _valid_verdict(
            covers_paths=["src/prod/**"], artifact_hashes={"src/prod/app.py": blob},
            engine=engine, keys=verifier_gpg_keys,
        ),
    )
    head1 = _commit_all(root, "first clearing push")
    r1 = run_cli(root, "gate", "ci", "--base", base1, "--head", head1, "--json", extra_env=env)
    assert r1.returncode == 0, r1.stdout + r1.stderr
    assert json.loads(r1.stdout)["receipt_gaps"] == []

    base2 = head1
    (root / "payments").mkdir(parents=True)
    (root / "payments" / "charge.py").write_text("refund()\n")
    signoff_dir = root / ".tess" / "gate" / "signoffs"
    signoff_dir.mkdir(parents=True, exist_ok=True)
    signoff = _signed_signoff(engine, verifier_gpg_keys["Reid"])
    (signoff_dir / "money.signoff.json").write_text(json.dumps(signoff), encoding="utf-8")
    head2 = _commit_all(root, "second clearing push")
    r2 = run_cli(root, "gate", "ci", "--base", base2, "--head", head2, "--json", extra_env=env)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    payload2 = json.loads(r2.stdout)
    assert payload2["receipt_gaps"] == []
    assert payload2["receipts_emitted"][0]["sequence"] == 1

    lines = [ln for ln in _chain_path(root).read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2
    first, second = json.loads(lines[0]), json.loads(lines[1])
    assert first["chain"]["sequence"] == 0
    assert second["chain"]["sequence"] == 1
    assert second["chain"]["prev_receipt_hash"] != "GENESIS"

    pubkey = _export_pubkey(verifier_gpg_keys["Reid"], tmp_path, "reid.asc")
    result = _independent_verify_chain(
        root, [("Reid", verifier_gpg_keys["Reid"].fpr, str(pubkey)), ("Xavier", verifier_gpg_keys["Reid"].fpr, str(pubkey))],
    )
    assert result["chain_intact"] is True, result
    assert result["receipt_count"] == 2


# ---------------------------------------------------------------------------
# 4) emit-failure is handled per the fail-closed + non-silent coupling:
#    VISIBLE (receipt_gaps / ACCOUNTABILITY GAP text / trace log), never
#    silent, and NEVER flips the gate's own blocked/pass decision.
# ---------------------------------------------------------------------------

def test_emit_failure_is_visible_never_silent_never_blocks(
    gate_repo_with_receipt_emit, run_cli, engine, verifier_gpg_keys, tmp_path,
):
    root = gate_repo_with_receipt_emit
    base = _base_sha(root)
    (root / "src" / "prod").mkdir(parents=True)
    (root / "src" / "prod" / "app.py").write_text("print('prod')\n")
    blob = _blob_sha(root, "src/prod/app.py")
    _write_verdict(
        root, "missions/m1/verdicts/prod-src.verdict.md",
        _valid_verdict(
            covers_paths=["src/prod/**"], artifact_hashes={"src/prod/app.py": blob},
            engine=engine, keys=verifier_gpg_keys,
        ),
    )
    head = _commit_all(root, "add prod change + covering verdict")

    # An EMPTY, freshly-generated GNUPGHOME with no keys at all — Reid's
    # covering verdict signature still verifies fine (that check runs
    # against the REGISTERED public key bundled in the repo, not the
    # process's own keyring), but receipt-emit's own SIGNING step (which
    # needs Reid's PRIVATE key present) has nothing to sign with.
    empty_gnupg_home = tmp_path / "empty-gnupg"
    empty_gnupg_home.mkdir(mode=0o700)

    r = run_cli(
        root, "gate", "ci", "--base", base, "--head", head, "--json",
        extra_env={"GNUPGHOME": str(empty_gnupg_home)},
    )
    # The SHIP decision is unaffected: this push is genuinely, fully
    # governed (a valid covering, signed APPROVE verdict exists) — a
    # receipt-emit failure must never turn that into a block.
    assert r.returncode == 0, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    assert payload["blocked"] is False
    assert payload["reasons"] == []

    # But the gap is NEVER silent: reported back as a structured, visible
    # entry, never as if a receipt exists.
    assert payload["receipts_emitted"] == []
    assert payload["receipt_gaps"] == [
        {"rule_id": "prod-src", "decision_kind": "verdict", "reason_code": "RECEIPT_EMIT_FAILED"},
    ]
    # No partial/corrupt chain file was left behind either.
    assert not _chain_path(root).exists()

    # Text-mode output says so LOUDLY, not silently.
    r_text = run_cli(
        root, "gate", "ci", "--base", base, "--head", head,
        extra_env={"GNUPGHOME": str(empty_gnupg_home)},
    )
    assert r_text.returncode == 0
    assert "ACCOUNTABILITY GAP" in r_text.stdout
    assert "prod-src" in r_text.stdout
    assert "RECEIPT_EMIT_FAILED" in r_text.stdout


def test_emit_tool_entirely_missing_is_also_a_visible_gap_not_a_crash(
    gate_repo, run_cli, engine, verifier_gpg_keys,
):
    """A checkout that never vendored tools/receipt-emit/ at all (an older
    instance, a manually-pruned tree) must degrade to a visible gap, never a
    crash and never a silent 'nothing happened.'"""
    root = gate_repo
    base = _base_sha(root)
    (root / "src" / "prod").mkdir(parents=True)
    (root / "src" / "prod" / "app.py").write_text("print('prod')\n")
    blob = _blob_sha(root, "src/prod/app.py")
    _write_verdict(
        root, "missions/m1/verdicts/prod-src.verdict.md",
        _valid_verdict(
            covers_paths=["src/prod/**"], artifact_hashes={"src/prod/app.py": blob},
            engine=engine, keys=verifier_gpg_keys,
        ),
    )
    head = _commit_all(root, "add prod change + covering verdict, no tools/receipt-emit/ vendored")

    r = run_cli(root, "gate", "ci", "--base", base, "--head", head, "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    assert payload["blocked"] is False
    assert payload["receipts_emitted"] == []
    assert payload["receipt_gaps"] == [
        {"rule_id": "prod-src", "decision_kind": "verdict", "reason_code": "RECEIPT_EMIT_FAILED"},
    ]


# ---------------------------------------------------------------------------
# 5) a mixed push (one rule cleared, a DIFFERENT rule blocked) never emits
#    a receipt for the partially-cleared rule — "gate CLEARS a change" means
#    the push as a whole, not a per-rule partial pass inside an overall block.
# ---------------------------------------------------------------------------

def test_mixed_push_still_blocked_overall_emits_no_receipts(
    gate_repo_with_receipt_emit, run_cli, engine, verifier_gpg_keys,
):
    root = gate_repo_with_receipt_emit
    base = _base_sha(root)
    (root / "src" / "prod").mkdir(parents=True)
    (root / "src" / "prod" / "app.py").write_text("print('prod')\n")
    blob = _blob_sha(root, "src/prod/app.py")
    _write_verdict(
        root, "missions/m1/verdicts/prod-src.verdict.md",
        _valid_verdict(
            covers_paths=["src/prod/**"], artifact_hashes={"src/prod/app.py": blob},
            engine=engine, keys=verifier_gpg_keys,
        ),
    )
    # A hard floor match with NO sign-off at all -> this push is BLOCKED.
    (root / "payments").mkdir(parents=True)
    (root / "payments" / "charge.py").write_text("refund()\n")
    head = _commit_all(root, "covered prod change + UNCOVERED hard floor")

    r = run_cli(
        root, "gate", "ci", "--base", base, "--head", head, "--json",
        extra_env={"GNUPGHOME": str(verifier_gpg_keys["Reid"].home)},
    )
    assert r.returncode == 1
    payload = json.loads(r.stdout)
    assert payload["blocked"] is True
    # No receipt fields at all on a block — never even attempted.
    assert "receipts_emitted" not in payload
    assert "receipt_gaps" not in payload
    assert not _chain_path(root).exists()


# ---------------------------------------------------------------------------
# 6) policy.yaml is never modified by any of this
# ---------------------------------------------------------------------------

def test_policy_yaml_untouched_by_receipt_emission(
    gate_repo_with_receipt_emit, run_cli, engine, verifier_gpg_keys,
):
    root = gate_repo_with_receipt_emit
    policy_path = root / "core" / "policy" / "policy.yaml"
    before = policy_path.read_bytes()

    base = _base_sha(root)
    (root / "src" / "prod").mkdir(parents=True)
    (root / "src" / "prod" / "app.py").write_text("print('prod')\n")
    blob = _blob_sha(root, "src/prod/app.py")
    _write_verdict(
        root, "missions/m1/verdicts/prod-src.verdict.md",
        _valid_verdict(
            covers_paths=["src/prod/**"], artifact_hashes={"src/prod/app.py": blob},
            engine=engine, keys=verifier_gpg_keys,
        ),
    )
    head = _commit_all(root, "add prod change + covering verdict")
    r = run_cli(
        root, "gate", "ci", "--base", base, "--head", head, "--json",
        extra_env={"GNUPGHOME": str(verifier_gpg_keys["Reid"].home)},
    )
    assert r.returncode == 0
    assert policy_path.read_bytes() == before
