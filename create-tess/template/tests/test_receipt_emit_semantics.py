"""
tools/receipt-emit/{assemble,policy_lookup,chain_atomic}.py — unit-level
coverage. CLI-level (subprocess, real GPG, real self-verify) round-trip
coverage lives in its own file, `tests/test_receipt_emit_cli.py`, mirroring
`tests/test_receipt_verify_semantics.py` / `tests/test_receipt_verify_cli.py`'s
own split.

Coverage:
  * policy_lookup: a path_rule and a hard_floor_rule are each copied
    VERBATIM; an unknown rule id, a rule id present in BOTH lists, and a
    rule entry missing a required field are all refused; the policy file
    itself is never modified by a lookup.
  * assemble.infer_decision_kind: a verdict-shaped decision, a
    signoff-shaped decision, and a decision matching neither are each
    classified correctly.
  * assemble.validate_decision_or_refuse: a non-APPROVE verdict is refused
    (FAIL-CLOSED item 1); a structurally incomplete signoff is refused
    (the same item, "rejected"/incomplete signoff case); a valid decision
    returns its own identity.
  * assemble.validate_policy_pairing_or_refuse: guardrails.md Rule 18
    pairing is enforced both directions.
  * assemble.identity_consistency_or_refuse: a FORCED signer/decision
    identity mismatch is refused (FAIL-CLOSED item 2), proving the
    defense-in-depth guard actually fires, not just that it can never be
    reached through the normal CLI flow.
  * chain_atomic.next_chain_link / append_receipt_atomically: genesis vs.
    chained sequencing; a verify_fn refusal and a simulated crash between
    the candidate write and the atomic rename BOTH leave the target file
    untouched and no temp file behind (FAIL-CLOSED item 3).
  * gpg_sign.resolve_fingerprint — PR #135 review regression (Reid
    CRITICAL, reproduced end-to-end): a REALISTIC, subkey-bearing key
    (unlike every other test key in this suite, which is deliberately
    sign-only/subkey-less) must resolve to exactly its PRIMARY
    fingerprint, not be refused as "matches more than one distinct key".
"""

from __future__ import annotations

import copy
import json

import pytest

from _receipt_emit_fixtures import (
    EmitRefused,
    assemble,
    chain_atomic,
    gpg_sign,
    policy_lookup,
    subkey_bearing_gpg_key,  # noqa: F401  (pytest fixture, requested by name below)
    write_test_policy,
)
from _agent_receipt_fixtures import base_signoff, base_verdict

# ---------------------------------------------------------------------------
# policy_lookup.load_policy_rule
# ---------------------------------------------------------------------------


def test_path_rule_is_copied_verbatim(tmp_path):
    policy_path = write_test_policy(tmp_path)
    decision = policy_lookup.load_policy_rule(str(policy_path), "demo-docs-review")
    assert decision == {
        "source": str(policy_path),
        "rule_id": "demo-docs-review",
        "rule_kind": "path_rule",
        "classification": ["prod_touching"],
        "description": "Doc change requires review.",
    }


def test_hard_floor_rule_is_copied_verbatim(tmp_path):
    policy_path = write_test_policy(tmp_path)
    decision = policy_lookup.load_policy_rule(str(policy_path), "money-movement")
    assert decision == {
        "source": str(policy_path),
        "rule_id": "money-movement",
        "rule_kind": "hard_floor_rule",
        "category": "money_movement",
        "description": "Hard floor: money movement requires sign-off.",
    }


def test_unknown_rule_id_is_refused(tmp_path):
    policy_path = write_test_policy(tmp_path)
    with pytest.raises(EmitRefused, match="no rule with id"):
        policy_lookup.load_policy_rule(str(policy_path), "does-not-exist")


def test_rule_id_present_in_both_lists_is_refused(tmp_path):
    policy_path = write_test_policy(tmp_path, """\
policy:
  version: 1
  rules:
    - id: dupe
      description: "d"
      globs: []
      classification: [prod_touching]
      require_verdict: true
      allowed_verifiers: [Reid]
  hard_floor_rules:
    - id: dupe
      category: money_movement
      description: "d"
      globs: []
""")
    with pytest.raises(EmitRefused, match="appears in BOTH"):
        policy_lookup.load_policy_rule(str(policy_path), "dupe")


def test_rule_missing_required_field_is_refused(tmp_path):
    policy_path = write_test_policy(tmp_path, """\
policy:
  version: 1
  rules:
    - id: incomplete
      globs: []
      classification: [prod_touching]
  hard_floor_rules: []
""")
    with pytest.raises(EmitRefused, match="missing required field"):
        policy_lookup.load_policy_rule(str(policy_path), "incomplete")


def test_load_policy_rule_never_modifies_the_policy_file(tmp_path):
    policy_path = write_test_policy(tmp_path)
    before = policy_path.read_text(encoding="utf-8")
    before_mtime = policy_path.stat().st_mtime_ns
    policy_lookup.load_policy_rule(str(policy_path), "demo-docs-review")
    assert policy_path.read_text(encoding="utf-8") == before
    assert policy_path.stat().st_mtime_ns == before_mtime


# ---------------------------------------------------------------------------
# assemble.infer_decision_kind
# ---------------------------------------------------------------------------


def test_infer_decision_kind_verdict():
    assert assemble.infer_decision_kind(base_verdict("Reid")) == "verdict"


def test_infer_decision_kind_signoff():
    # checks.SIGNOFF_REQUIRED_KEYS (unlike VERDICT_REQUIRED_KEYS) includes
    # "signature" itself — an unsigned signoff-shaped dict is correctly
    # classified as neither kind (see test_infer_decision_kind_neither_is_none
    # below), so a genuinely-shaped signoff for THIS test needs one present.
    signoff = base_signoff("Xavier")
    signoff["signature"] = {"algorithm": "gpg-detached-armor", "signed_content_sha256": "0" * 64, "signature_armored": "x"}
    assert assemble.infer_decision_kind(signoff) == "signoff"


def test_infer_decision_kind_neither_is_none():
    assert assemble.infer_decision_kind({"some": "thing"}) is None
    assert assemble.infer_decision_kind("not-a-dict") is None
    # An unsigned signoff (missing the "signature" key SIGNOFF_REQUIRED_KEYS
    # requires) is deliberately classified as neither — never guessed.
    assert assemble.infer_decision_kind(base_signoff("Xavier")) is None


# ---------------------------------------------------------------------------
# assemble.validate_decision_or_refuse — FAIL-CLOSED item 1
# ---------------------------------------------------------------------------


def test_non_approve_verdict_is_refused():
    verdict = base_verdict("Reid")
    verdict["disposition"] = "BLOCK"
    verdict["signature"] = {"algorithm": "gpg-detached-armor", "signed_content_sha256": "0" * 64, "signature_armored": "x"}
    with pytest.raises(EmitRefused, match="not 'APPROVE'"):
        assemble.validate_decision_or_refuse("verdict", verdict)


def test_incomplete_signoff_is_refused():
    """A signoff missing its own `signature` block (never actually
    completed/authorized, in the sense this tool's FAIL-CLOSED item 1
    covers for the signoff case) is refused, the same as a rejected
    verdict."""
    signoff = base_signoff("Xavier")
    # No `signature` key at all — never actually signed/authorized.
    with pytest.raises(EmitRefused, match="signature"):
        assemble.validate_decision_or_refuse("signoff", signoff)


def test_valid_verdict_returns_its_identity():
    verdict = base_verdict("Reid")
    verdict["signature"] = {"algorithm": "gpg-detached-armor", "signed_content_sha256": "0" * 64, "signature_armored": "x"}
    assert assemble.validate_decision_or_refuse("verdict", verdict) == "Reid"


def test_valid_signoff_returns_its_identity():
    signoff = base_signoff("Xavier")
    signoff["signature"] = {"algorithm": "gpg-detached-armor", "signed_content_sha256": "0" * 64, "signature_armored": "x"}
    assert assemble.validate_decision_or_refuse("signoff", signoff) == "Xavier"


# ---------------------------------------------------------------------------
# assemble.validate_policy_pairing_or_refuse — guardrails.md Rule 18
# ---------------------------------------------------------------------------


def test_hard_floor_rule_paired_with_verdict_is_refused():
    policy_decision = {"rule_kind": "hard_floor_rule", "category": "money_movement"}
    with pytest.raises(EmitRefused, match="Rule 18"):
        assemble.validate_policy_pairing_or_refuse(policy_decision, "verdict")


def test_path_rule_paired_with_signoff_is_refused():
    policy_decision = {"rule_kind": "path_rule", "classification": ["prod_touching"]}
    with pytest.raises(EmitRefused, match="path_rule"):
        assemble.validate_policy_pairing_or_refuse(policy_decision, "signoff")


def test_correctly_paired_rules_pass():
    assemble.validate_policy_pairing_or_refuse({"rule_kind": "path_rule"}, "verdict")
    assemble.validate_policy_pairing_or_refuse({"rule_kind": "hard_floor_rule"}, "signoff")


# ---------------------------------------------------------------------------
# assemble.identity_consistency_or_refuse — FAIL-CLOSED item 2
# (a direct, synthetic proof the guard fires on a FORCED mismatch — see
# assemble.py's own docstring for why this can never happen through the
# normal CLI flow, and why the guard exists anyway.)
# ---------------------------------------------------------------------------


def test_forced_signer_identity_mismatch_is_refused():
    verdict = base_verdict("Reid")
    verdict["signature"] = {"algorithm": "gpg-detached-armor", "signed_content_sha256": "0" * 64, "signature_armored": "x"}
    receipt = {
        "decision_kind": "verdict",
        "decision": verdict,
        "receipt_signature": {
            "algorithm": "gpg-detached-armor",
            "signed_by": "Cyra",  # decision says Reid — a forced mismatch
            "signed_content_sha256": "1" * 64,
            "signature_armored": "y",
        },
    }
    with pytest.raises(EmitRefused, match="does not match the embedded"):
        assemble.identity_consistency_or_refuse(receipt)


def test_matching_signer_identity_passes():
    verdict = base_verdict("Reid")
    verdict["signature"] = {"algorithm": "gpg-detached-armor", "signed_content_sha256": "0" * 64, "signature_armored": "x"}
    receipt = {
        "decision_kind": "verdict",
        "decision": verdict,
        "receipt_signature": {
            "algorithm": "gpg-detached-armor",
            "signed_by": "Reid",
            "signed_content_sha256": "1" * 64,
            "signature_armored": "y",
        },
    }
    assemble.identity_consistency_or_refuse(receipt)  # must not raise


# ---------------------------------------------------------------------------
# chain_atomic.next_chain_link
# ---------------------------------------------------------------------------


def test_next_chain_link_genesis_on_missing_file(tmp_path):
    sequence, prev_hash = chain_atomic.next_chain_link(tmp_path / "chain.jsonl", lambda r: "unused")
    assert (sequence, prev_hash) == (0, "GENESIS")


def test_next_chain_link_genesis_on_empty_file(tmp_path):
    chain_path = tmp_path / "chain.jsonl"
    chain_path.write_text("", encoding="utf-8")
    sequence, prev_hash = chain_atomic.next_chain_link(chain_path, lambda r: "unused")
    assert (sequence, prev_hash) == (0, "GENESIS")


def test_next_chain_link_increments_from_last_line(tmp_path):
    chain_path = tmp_path / "chain.jsonl"
    chain_path.write_text(json.dumps({"chain": {"sequence": 4}}) + "\n", encoding="utf-8")
    sequence, prev_hash = chain_atomic.next_chain_link(chain_path, lambda r: "computed-hash")
    assert (sequence, prev_hash) == (5, "computed-hash")


# ---------------------------------------------------------------------------
# chain_atomic.append_receipt_atomically — FAIL-CLOSED item 3
# ---------------------------------------------------------------------------


def test_atomic_append_happy_path(tmp_path):
    chain_path = tmp_path / "chain.jsonl"
    seen = []

    def verify_fn(candidate_path):
        seen.append(candidate_path.read_text(encoding="utf-8"))

    chain_atomic.append_receipt_atomically(chain_path, {"a": 1}, verify_fn)

    assert chain_path.read_text(encoding="utf-8") == json.dumps({"a": 1}, sort_keys=True) + "\n"
    assert seen == [json.dumps({"a": 1}, sort_keys=True) + "\n"]  # verify_fn saw the CANDIDATE, pre-commit


def test_atomic_append_appends_a_second_line_onto_existing_content(tmp_path):
    chain_path = tmp_path / "chain.jsonl"
    chain_path.write_text(json.dumps({"a": 1}, sort_keys=True) + "\n", encoding="utf-8")

    chain_atomic.append_receipt_atomically(chain_path, {"a": 2}, lambda p: None)

    lines = chain_path.read_text(encoding="utf-8").splitlines()
    assert lines == [json.dumps({"a": 1}, sort_keys=True), json.dumps({"a": 2}, sort_keys=True)]


def test_atomic_append_verify_failure_leaves_no_file_and_no_orphan(tmp_path):
    chain_path = tmp_path / "chain.jsonl"

    def verify_fn(candidate_path):
        raise EmitRefused(["simulated self-verify failure"])

    with pytest.raises(EmitRefused):
        chain_atomic.append_receipt_atomically(chain_path, {"a": 1}, verify_fn)

    assert not chain_path.exists()
    assert list(tmp_path.glob(".receipt-emit-*")) == []


def test_atomic_append_simulated_crash_before_rename_leaves_existing_content_untouched(tmp_path, monkeypatch):
    """Simulates a kill AFTER the candidate has been fully written and
    verified, but BEFORE the atomic rename commits it — the exact window
    the task brief's 'mid-emit kill' scenario targets. Old content must
    survive byte-for-byte and no temp file may be left behind."""
    chain_path = tmp_path / "chain.jsonl"
    chain_path.write_text("PRE-EXISTING-LINE\n", encoding="utf-8")

    def boom(*_args, **_kwargs):
        raise OSError("simulated kill mid-emit, right before the atomic rename")

    monkeypatch.setattr(chain_atomic.os, "replace", boom)

    with pytest.raises(OSError):
        chain_atomic.append_receipt_atomically(chain_path, {"a": 1}, lambda p: None)

    assert chain_path.read_text(encoding="utf-8") == "PRE-EXISTING-LINE\n"
    assert list(tmp_path.glob(".receipt-emit-*")) == []


def test_atomic_append_simulated_crash_during_write_leaves_no_file_and_no_orphan(tmp_path, monkeypatch):
    """A second flavor of 'mid-emit kill' — the crash happens WHILE writing
    the temp file (before it is even complete), not at the rename step."""
    chain_path = tmp_path / "chain.jsonl"

    real_fdopen = chain_atomic.os.fdopen

    def boom_fdopen(fd, *args, **kwargs):
        f = real_fdopen(fd, *args, **kwargs)

        class _BoomWriter:
            def write(self, data):
                f.close()
                raise OSError("simulated kill mid-write")

            def flush(self):
                pass

            def fileno(self):
                return -1

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        return _BoomWriter()

    monkeypatch.setattr(chain_atomic.os, "fdopen", boom_fdopen)

    with pytest.raises(OSError):
        chain_atomic.append_receipt_atomically(chain_path, {"a": 1}, lambda p: None)

    assert not chain_path.exists()
    assert list(tmp_path.glob(".receipt-emit-*")) == []


# ---------------------------------------------------------------------------
# canonical.py sanity — proves receipt-emit's envelope really does share
# the SAME canonicalization tools/receipt-verify checks against (not a
# re-derived, possibly-drifting copy).
# ---------------------------------------------------------------------------


def test_build_envelope_signing_bytes_exclude_receipt_signature(tmp_path):
    from _receipt_emit_fixtures import canonical

    policy_decision = policy_lookup.load_policy_rule(str(write_test_policy(tmp_path)), "demo-docs-review")
    verdict = base_verdict("Reid")
    verdict["signature"] = {"algorithm": "gpg-detached-armor", "signed_content_sha256": "0" * 64, "signature_armored": "x"}
    receipt = assemble.build_envelope(
        actor="Ada", summary="s", policy_decision=policy_decision,
        decision_kind="verdict", decision=verdict, sequence=0, prev_hash="GENESIS",
    )
    assert "receipt_signature" not in receipt
    canon = canonical.receipt_signing_bytes(receipt)
    assert b"receipt_signature" not in canon
    # sanity: a deep copy produces byte-identical canonical bytes (pure function)
    assert canonical.receipt_signing_bytes(copy.deepcopy(receipt)) == canon


# ---------------------------------------------------------------------------
# gpg_sign.resolve_fingerprint — PR #135 review regression (Reid CRITICAL)
#
# Every OTHER GPG identity anywhere in this test suite is deliberately
# sign-only / subkey-less (see _receipt_emit_fixtures.py's own header
# comment on `subkey_bearing_gpg_key`), so the original bug — collecting
# EVERY `fpr:` line from `gpg --with-colons --list-keys`, including the
# ones that belong to subkeys, not just the primary — never had a second
# `fpr:` line to trip over anywhere else in this suite. This test uses a
# REALISTIC key (a default encryption subkey present, the actual
# `gpg --quick-generate-key` / `--full-generate-key` shape) specifically
# so it exercises the exact key shape the original bug refused.
# ---------------------------------------------------------------------------


def test_resolve_fingerprint_returns_exactly_the_primary_for_a_subkey_bearing_key(subkey_bearing_gpg_key):
    key = subkey_bearing_gpg_key
    resolved = gpg_sign.resolve_fingerprint(key.email, str(key.home))
    assert resolved == key.fpr
    # Also resolvable by the full fingerprint itself, not just the email —
    # the review's own reproduction noted "passing the full primary
    # fingerprint doesn't help" on the buggy version.
    assert gpg_sign.resolve_fingerprint(key.fpr, str(key.home)) == key.fpr
