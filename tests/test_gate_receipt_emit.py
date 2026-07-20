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

Reid CRITICAL (PR #137 review) closures, added after the initial build:
  * a HOSTILE `tools/receipt-emit/receipt_emit.py` planted in the SAME push
    as an otherwise-legitimate, fully-covered change is NEVER executed —
    the gate runs the trusted BASE-ref extraction instead
    (`_gate_extract_trusted_receipt_tooling`), proven both negatively (the
    hostile script's own observable side effect never happens) and
    positively (a REAL receipt, from the REAL tool, still gets emitted)
  * a malformed (non-dict) emit-tool JSON payload degrades to a structured
    gap, never an AttributeError crash (`payload.get(...)` bug fix)
  * no immutable BASE ref available (bootstrap: the very first push
    introducing policy.yaml) -> receipt emission fails closed as a gap,
    never falls back to trusting the pushed tree's own tooling
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
    _commit_money_payload, _commit_signoff_attestation,
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
    gate_repo_with_receipt_emit, run_cli, engine, verifier_gpg_keys, signoff_gpg_key, tmp_path,
):
    root = gate_repo_with_receipt_emit
    base = _base_sha(root)
    # #76 (source-bound admission topology): a hard-floor sign-off is no
    # longer a shape+signature check against whatever sits at HEAD — it must
    # be an exact schema-v2 artifact, bound to this base/payload/artifact
    # content, delivered in a SEPARATE, signoff-only attestation commit that
    # is the immediate child of the reviewed payload commit. Build that
    # topology with the same two helpers test_gate_spine.py's own hard-floor
    # tests already use, rather than a flat single commit.
    payload_head, artifact_hashes = _commit_money_payload(root)
    # gate_repo's policy registers "Xavier" in signoff_keys, backed by the
    # dedicated `signoff_gpg_key` fixture — a seventh, human-operator-only
    # identity distinct from every AI verifier's own key (see
    # `_policy_with_verifier_keys`/`signoff_gpg_key`'s own docstring in
    # test_gate_spine.py / conftest.py: "instead of aliasing Reid's
    # certificate").
    signoff = _signed_signoff(
        engine, signoff_gpg_key, base_sha=base,
        payload_head_sha=payload_head, artifact_hashes=artifact_hashes,
    )
    head = _commit_signoff_attestation(
        root, signoff, "payments change + validly-signed human signoff",
    )

    r = run_cli(
        root, "gate", "ci", "--base", base, "--head", head, "--json",
        extra_env={"GNUPGHOME": str(signoff_gpg_key.home)},
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

    pubkey = _export_pubkey(signoff_gpg_key, tmp_path, "xavier.asc")
    result = _independent_verify_chain(root, [("Xavier", signoff_gpg_key.fpr, str(pubkey))])
    assert result["chain_intact"] is True, result


# ---------------------------------------------------------------------------
# 3) two separate clearing pushes chain correctly
# ---------------------------------------------------------------------------

def test_two_clearing_pushes_chain_correctly(
    gate_repo_with_receipt_emit, run_cli, engine, verifier_gpg_keys, signoff_gpg_key, tmp_path,
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
    # #76 (source-bound admission topology): the hard-floor sign-off must be
    # a schema-v2 artifact bound to this base/payload/artifact content,
    # delivered as a separate signoff-only attestation commit — the same
    # topology test_gate_spine.py's own hard-floor tests already build.
    # `signoff_gpg_key` (not a reused `verifier_gpg_keys["Reid"]") is the
    # identity actually registered under "Xavier" in policy.signoff_keys —
    # see `_policy_with_verifier_keys`/`signoff_gpg_key`'s own docstring.
    payload_head, artifact_hashes = _commit_money_payload(root)
    signoff = _signed_signoff(
        engine, signoff_gpg_key, base_sha=base2,
        payload_head_sha=payload_head, artifact_hashes=artifact_hashes,
    )
    head2 = _commit_signoff_attestation(root, signoff, "second clearing push")
    # Receipt-emit signs with the CLEARING identity's own private key
    # (Xavier's, for a hard-floor sign-off) — a different GNUPGHOME than the
    # first (verdict/Reid) push above.
    env2 = {"GNUPGHOME": str(signoff_gpg_key.home)}
    r2 = run_cli(root, "gate", "ci", "--base", base2, "--head", head2, "--json", extra_env=env2)
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

    reid_pubkey = _export_pubkey(verifier_gpg_keys["Reid"], tmp_path, "reid.asc")
    xavier_pubkey = _export_pubkey(signoff_gpg_key, tmp_path, "xavier.asc")
    result = _independent_verify_chain(
        root, [("Reid", verifier_gpg_keys["Reid"].fpr, str(reid_pubkey)), ("Xavier", signoff_gpg_key.fpr, str(xavier_pubkey))],
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


# ---------------------------------------------------------------------------
# 7) ★ SECURITY (Reid CRITICAL, PR #137 review) — a HOSTILE receipt_emit.py
#    planted in the SAME push as an otherwise-legitimate, fully-covered
#    change must NEVER be executed. The gate must run the TRUSTED BASE-ref
#    extraction instead (_gate_extract_trusted_receipt_tooling), mirroring
#    the SAME "trusted base-ref engine, untrusted pushed tree" invariant
#    .github/workflows/tess-gate.yml's own "Extract trusted gate engine"
#    step already enforces for .tess/bin/tessctl itself
#    (honesty-capstone-audit-2026-07-08 §3-c).
# ---------------------------------------------------------------------------

def test_hostile_pushed_receipt_emit_is_never_executed_base_ref_wins(
    gate_repo_with_receipt_emit, run_cli, engine, verifier_gpg_keys, tmp_path,
):
    root = gate_repo_with_receipt_emit
    base = _base_sha(root)  # base already has the REAL, good tools/receipt-emit/

    # Plant a HOSTILE receipt_emit.py replacement in the SAME push as an
    # otherwise-legitimate, fully covered change — exactly the attack
    # Reid's review flagged: smuggle a modified tool alongside an unrelated,
    # real clearance. If this ever runs, it writes an observable marker
    # AND forges a fake "success" payload distinguishable from a real one.
    marker_path = tmp_path / "HOSTILE_EXECUTED.marker"
    hostile_script = (
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "from pathlib import Path\n"
        f"Path({str(marker_path)!r}).write_text('HOSTILE receipt_emit.py EXECUTED')\n"
        "print('{\"emitted\": true, \"receipt_id\": \"HOSTILE-FORGED\", \"sequence\": 999, "
        "\"trust_status\": \"signed_not_trust_anchored\"}')\n"
        "sys.exit(0)\n"
    )
    (root / "tools" / "receipt-emit" / "receipt_emit.py").write_text(hostile_script, encoding="utf-8")

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
    head = _commit_all(root, "legit covered change + HOSTILE receipt_emit.py in the SAME push")

    r = run_cli(
        root, "gate", "ci", "--base", base, "--head", head, "--json",
        extra_env={"GNUPGHOME": str(verifier_gpg_keys["Reid"].home)},
    )
    assert r.returncode == 0, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    assert payload["blocked"] is False  # the underlying change is still legitimately governed

    # The hostile code NEVER ran — the single most important assertion here.
    assert not marker_path.exists(), (
        "the hostile PUSHED-TREE receipt_emit.py was EXECUTED by the gate — "
        "critical security regression (base-ref extraction did not hold)"
    )

    # The BASE-ref (real, trusted) tool ran instead: a REAL receipt was
    # emitted, never the hostile forged payload.
    assert payload["receipt_gaps"] == []
    assert len(payload["receipts_emitted"]) == 1
    emitted = payload["receipts_emitted"][0]
    assert emitted["receipt_id"] != "HOSTILE-FORGED"
    assert emitted["sequence"] == 0
    assert emitted["trust_status"] == "signed_not_trust_anchored"

    chain_path = _chain_path(root)
    lines = [ln for ln in chain_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1
    receipt = json.loads(lines[0])
    assert receipt["receipt_id"] != "HOSTILE-FORGED"
    assert receipt["decision"]["verifier"] == "Reid"

    # Independently verify the REAL emitted receipt via the standalone tool
    # (from THIS repo's own real tools/receipt-verify/, never the fixture's).
    pubkey = _export_pubkey(verifier_gpg_keys["Reid"], tmp_path, "reid.asc")
    result = _independent_verify_chain(root, [("Reid", verifier_gpg_keys["Reid"].fpr, str(pubkey))])
    assert result["chain_intact"] is True, result


def test_extract_trusted_tooling_no_baseline_ref_fails_closed(engine, gate_repo_with_receipt_emit):
    """Direct unit test of `_gate_extract_trusted_receipt_tooling`'s own
    fail-closed branch. NOTE on reachability: today, `cov_cleared`/
    `hf_cleared` can only ever be non-empty when a real baseline ref exists
    in the first place — `_gate_verify_verdict_signature`/`_gate_verify_
    signoff_signature` both require BASELINE key BYTES
    (`trusted_verifier_key_blobs`/`trusted_signoff_key_blobs`), which
    `_gate_load_baseline_{verifier,signoff}_key_blobs` return empty for
    whenever `baseline_ref` is falsy — so NEITHER a covering verdict NOR a
    hard-floor sign-off can ever actually clear anything with no baseline
    at all, and `_gate_emit_receipts_on_clear` is never invoked with a
    falsy `baseline_policy_ref` through the real end-to-end gate flow as it
    exists today. This function's own `if not baseline_ref` branch is
    therefore defense-in-depth for that invariant, not dead code exercised
    only here — proven directly, in isolation, exactly like the CI
    workflow's own "no trusted engine at BASE -> fail closed" bootstrap
    branch is a deliberate safeguard even where today's callers are not
    expected to reach it in practice."""
    root = gate_repo_with_receipt_emit
    tool_root, reason = engine._gate_extract_trusted_receipt_tooling(root, None)
    assert tool_root is None
    assert reason is not None and "no immutable BASE ref" in reason

    tool_root2, reason2 = engine._gate_extract_trusted_receipt_tooling(root, "")
    assert tool_root2 is None
    assert reason2 is not None


# ---------------------------------------------------------------------------
# 8) ★ BUG FIX (PR #137 review) — payload.get(...) on non-dict JSON must
#    never raise AttributeError. Direct unit test of _gate_emit_one_receipt
#    against a stub "trusted" tool that returns valid-but-non-dict JSON —
#    no git/gpg harness needed, this exercises the guard in isolation.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("stub_stdout", [
    "[1, 2, 3]",   # a JSON array
    "null",        # JSON null
    '"just a string"',
    "42",
])
def test_malformed_emit_json_output_is_a_gap_never_a_crash(engine, tmp_path, stub_stdout):
    trusted_tool_root = tmp_path / f"trusted-{hash(stub_stdout) & 0xffff}"
    emit_dir = trusted_tool_root / "tools" / "receipt-emit"
    emit_dir.mkdir(parents=True)
    (emit_dir / "receipt_emit.py").write_text(
        "import sys\n"
        f"print({stub_stdout!r})\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )
    payload, ok = engine._gate_emit_one_receipt(
        trusted_tool_root, rule_id="some-rule", decision_kind="verdict",
        decision={"verifier": "Reid"}, fingerprint="DEADBEEF" * 5,
        policy_path=tmp_path / "policy.yaml", head_shas=["abc123"],
        chain_path=tmp_path / "chain.jsonl", trust_entries=[],
    )
    assert payload is None
    assert ok is False
