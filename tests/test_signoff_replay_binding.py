"""P0 hard-floor sign-off v2 revision/replay binding.

These tests exercise topology, immutable-tree loading, exact scope binding,
and time validity without GPG so the fail-closed decision surface remains
fully testable in environments that cannot start gpg-agent.  Real GPG,
including revoked immutable-BASE key bytes, is covered separately in
test_signoff_revoked_base_e2e.py and is mandatory whenever GPG is available.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest


MONEY_RULE = {
    "id": "money",
    "category": "money_movement",
    "description": "test money floor",
    "globs": ["payments/**"],
}
CREDENTIALS_RULE = {
    "id": "credentials",
    "category": "credentials",
    "description": "test credential floor",
    "globs": ["secrets/**"],
}
TEST_POLICY = {
    "policy": {
        "version": 1,
        "repository_id": "test/tess-os",
        "rules": [],
        "hard_floor_rules": [MONEY_RULE, CREDENTIALS_RULE],
        "signoff_keys": {},
    }
}


def _git(root: Path, *args: str, input_text: str | None = None) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@tess.invalid",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@tess.invalid",
    }
    result = subprocess.run(
        ["git", "-C", str(root), *args], input=input_text,
        capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _init_repo(root: Path) -> None:
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "user.email", "test@tess.invalid")
    _git(root, "config", "commit.gpgsign", "false")


def _commit(root: Path, message: str, *, amend: bool = False) -> str:
    _git(root, "add", "-A")
    args = ["commit", "-q"]
    if amend:
        args.extend(["--amend", "--no-edit"])
    else:
        args.extend(["-m", message])
    _git(root, *args)
    return _git(root, "rev-parse", "HEAD")


def _strict_signature(engine, data: dict) -> dict:
    canonical = engine.signoff_canonical_bytes(data)
    return {
        "algorithm": engine.SIGNOFF_SIGNATURE_ALGORITHM,
        "signed_content_sha256": hashlib.sha256(canonical).hexdigest(),
        "signature_armored": "unit-test-signature-not-used-by-mocked-crypto",
    }


def _matches(rule_paths: dict[str, list[str]]) -> dict:
    rules = {"money": MONEY_RULE, "credentials": CREDENTIALS_RULE}
    return {
        path: [rules[rule_id]]
        for rule_id, paths in rule_paths.items()
        for path in paths
    }


def _signoff_data(
    engine, *, rule: dict, paths: list[str], root: Path, base: str,
    payload: str, repository_id: str = "test/tess-os",
) -> dict:
    hard_matches = {path: [rule] for path in paths}
    contexts, reasons = engine._gate_hard_floor_rule_contexts(hard_matches)
    assert reasons == []
    context = contexts[rule["id"]]
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    data = {
        "schema_version": 2,
        "repository_id": repository_id,
        "rule_id": rule["id"],
        "category": rule["category"],
        "effective_rule_sha256": context["effective_rule_sha256"],
        "base_sha": base,
        "payload_head_sha": payload,
        "artifact_hashes": {
            path: _git(root, "rev-parse", f"{payload}:{path}") for path in paths
        },
        "authorized_by": "Xavier",
        "rationale": "Reviewed the exact immutable payload.",
        "authorized_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": (now + datetime.timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
    }
    data["signature"] = _strict_signature(engine, data)
    return data


def _write_signoff(root: Path, rule_id: str, data: dict) -> Path:
    path = root / ".tess" / "gate" / "signoffs" / f"{rule_id}.signoff.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        path.unlink()
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def _case(
    tmp_path: Path, engine, *, two_rules: bool = False,
    parent_signoff_symlink: bool = False, two_money_paths: bool = False,
) -> SimpleNamespace:
    root = tmp_path / "repo"
    _init_repo(root)
    (root / "README.md").write_text("base\n", encoding="utf-8")
    base = _commit(root, "base")

    (root / "payments").mkdir()
    (root / "payments" / "charge.py").write_text("refund()\n", encoding="utf-8")
    rule_paths = {"money": ["payments/charge.py"]}
    if two_money_paths:
        (root / "payments" / "refund.py").write_text("void()\n", encoding="utf-8")
        rule_paths["money"].append("payments/refund.py")
    if two_rules:
        (root / "secrets").mkdir()
        (root / "secrets" / "rotate.env").write_text("rotate=true\n", encoding="utf-8")
        rule_paths["credentials"] = ["secrets/rotate.env"]
    if parent_signoff_symlink:
        signoff_path = root / ".tess" / "gate" / "signoffs" / "money.signoff.json"
        signoff_path.parent.mkdir(parents=True)
        signoff_path.symlink_to("../../../payments/charge.py")
    payload = _commit(root, "payload")

    signoffs = {}
    for rule_id, paths in rule_paths.items():
        rule = MONEY_RULE if rule_id == "money" else CREDENTIALS_RULE
        signoffs[rule_id] = _signoff_data(
            engine, rule=rule, paths=paths, root=root, base=base, payload=payload,
        )
        _write_signoff(root, rule_id, signoffs[rule_id])
    head = _commit(root, "signoff-only attestation")
    return SimpleNamespace(
        root=root, base=base, payload=payload, head=head,
        rule_paths=rule_paths, matches=_matches(rule_paths), signoffs=signoffs,
    )


def _report(engine, case, *, head: str | None = None, heads: list[str] | None = None):
    return engine._gate_hard_floor_gap_report(
        case.root, case.matches, TEST_POLICY, TEST_POLICY, case.base,
        [case.base], heads if heads is not None else [head or case.head], {}, {},
    )


@pytest.fixture
def crypto_ok(engine, monkeypatch):
    calls = []

    def verify(*args, **kwargs):
        calls.append((args, kwargs))
        return True, None

    monkeypatch.setattr(engine, "_gate_verify_signoff_signature", verify)
    return calls


def test_valid_single_parent_signoff_only_attestation_passes(engine, tmp_path, crypto_ok):
    case = _case(tmp_path, engine)
    assert _report(engine, case) == []
    assert len(crypto_ok) == 1


def test_exact_exemption_paths_publish_only_after_all_signoffs_validate(
    engine, tmp_path, crypto_ok,
):
    case = _case(tmp_path, engine, two_rules=True)
    validated = set()
    reasons = engine._gate_hard_floor_gap_report(
        case.root, case.matches, TEST_POLICY, TEST_POLICY, case.base,
        [case.base], [case.head], {}, {}, validated,
    )
    assert reasons == []
    assert validated == {
        ".tess/gate/signoffs/money.signoff.json",
        ".tess/gate/signoffs/credentials.signoff.json",
    }


def test_partial_multi_signoff_success_publishes_no_exemption(
    engine, tmp_path, monkeypatch,
):
    case = _case(tmp_path, engine, two_rules=True)

    def verify(_root, _policy, data, **_kwargs):
        return (True, None) if data["rule_id"] == "money" else (False, "forced invalid signature")

    monkeypatch.setattr(engine, "_gate_verify_signoff_signature", verify)
    validated = set()
    reasons = engine._gate_hard_floor_gap_report(
        case.root, case.matches, TEST_POLICY, TEST_POLICY, case.base,
        [case.base], [case.head], {}, {}, validated,
    )
    assert any("forced invalid signature" in reason for reason in reasons)
    assert validated == set()


def test_candidate_added_rule_cannot_expand_attestation_path_exemption(
    engine, tmp_path, crypto_ok,
):
    case = _case(tmp_path, engine)
    candidate_rule = {
        "id": "candidate-created",
        "category": "money_movement",
        "description": "candidate cannot authorize this rule yet",
        "globs": ["payments/**"],
    }
    candidate_policy = json.loads(json.dumps(TEST_POLICY))
    candidate_policy["policy"]["hard_floor_rules"].append(candidate_rule)
    candidate_matches = {"payments/charge.py": [candidate_rule]}
    validated = set()
    reasons = engine._gate_hard_floor_gap_report(
        case.root, candidate_matches, candidate_policy, TEST_POLICY, case.base,
        [case.base], [case.head], {}, {}, validated,
    )
    assert any("candidate-added hard-floor" in reason for reason in reasons)
    assert validated == set()
    assert crypto_ok == []


def test_multiple_required_signoffs_must_be_atomic_in_one_child(engine, tmp_path, crypto_ok):
    case = _case(tmp_path, engine, two_rules=True)
    assert _report(engine, case) == []
    assert len(crypto_ok) == 2


def test_missing_one_of_multiple_required_signoffs_fails_topology(engine, tmp_path, crypto_ok):
    case = _case(tmp_path, engine, two_rules=True)
    (case.root / ".tess/gate/signoffs/credentials.signoff.json").unlink()
    head = _commit(case.root, "remove one attestation", amend=True)
    reasons = _report(engine, case, head=head)
    assert any("missing=" in reason and "credentials.signoff.json" in reason for reason in reasons)
    assert crypto_ok == []


def test_attestation_commit_rejects_any_extra_file(engine, tmp_path, crypto_ok):
    case = _case(tmp_path, engine)
    (case.root / "extra.txt").write_text("not signoff-only\n", encoding="utf-8")
    head = _commit(case.root, "extra", amend=True)
    reasons = _report(engine, case, head=head)
    assert any("extra=['extra.txt']" in reason for reason in reasons)
    assert crypto_ok == []


def test_signoff_directory_prefix_never_grants_wildcard_exemption(engine, tmp_path, crypto_ok):
    case = _case(tmp_path, engine)
    extra = case.root / ".tess/gate/signoffs/candidate-extra.signoff.json"
    extra.write_text("{}\n", encoding="utf-8")
    head = _commit(case.root, "extra signoff-looking path", amend=True)
    validated = set()
    reasons = engine._gate_hard_floor_gap_report(
        case.root, case.matches, TEST_POLICY, TEST_POLICY, case.base,
        [case.base], [head], {}, {}, validated,
    )
    assert any("candidate-extra.signoff.json" in reason and "extra=" in reason for reason in reasons)
    assert validated == set()
    assert crypto_ok == []


def test_attestation_commit_rejects_rename(engine, tmp_path, crypto_ok):
    case = _case(tmp_path, engine)
    (case.root / "notes-old.txt").write_text("payload note\n", encoding="utf-8")
    # Put the source in the payload parent, then reconstruct the attestation.
    _git(case.root, "reset", "--hard", case.payload)
    (case.root / "notes-old.txt").write_text("payload note\n", encoding="utf-8")
    payload = _commit(case.root, "payload plus rename source")
    case.payload = payload
    case.signoffs["money"] = _signoff_data(
        engine, rule=MONEY_RULE, paths=case.rule_paths["money"], root=case.root,
        base=case.base, payload=payload,
    )
    _write_signoff(case.root, "money", case.signoffs["money"])
    _git(case.root, "mv", "notes-old.txt", "notes-new.txt")
    case.head = _commit(case.root, "attestation plus rename")
    reasons = _report(engine, case)
    assert any("notes-old.txt" in reason and "notes-new.txt" in reason for reason in reasons)
    assert crypto_ok == []


def test_attestation_signoff_symlink_is_rejected(engine, tmp_path, crypto_ok):
    case = _case(tmp_path, engine)
    path = case.root / ".tess/gate/signoffs/money.signoff.json"
    path.unlink()
    path.symlink_to("../../../payments/charge.py")
    head = _commit(case.root, "symlink signoff", amend=True)
    reasons = _report(engine, case, head=head)
    assert any("mode 100644" in reason and "symlink" in reason for reason in reasons)
    assert crypto_ok == []


def test_attestation_rejects_parent_type_swap(engine, tmp_path, crypto_ok):
    case = _case(tmp_path, engine, parent_signoff_symlink=True)
    reasons = _report(engine, case)
    assert any("replaces a non-regular parent" in reason for reason in reasons)
    assert crypto_ok == []


def test_merge_commit_cannot_be_attestation_head(engine, tmp_path, crypto_ok):
    case = _case(tmp_path, engine)
    tree = _git(case.root, "rev-parse", f"{case.head}^{{tree}}")
    merge = _git(
        case.root, "commit-tree", tree, "-p", case.payload, "-p", case.base,
        input_text="synthetic merge attestation\n",
    )
    reasons = _report(engine, case, head=merge)
    assert any("merge commits are rejected" in reason for reason in reasons)
    assert crypto_ok == []


def test_multi_head_admission_fails_closed(engine, tmp_path, crypto_ok):
    case = _case(tmp_path, engine)
    reasons = _report(engine, case, heads=[case.head, case.head])
    assert any("multi-ref/multi-head" in reason for reason in reasons)
    assert crypto_ok == []


def _capture_ship_check_attestation_heads(engine, monkeypatch, tmp_path, supplied):
    captured = {}
    monkeypatch.setattr(
        engine, "_gate_renderer_admission_prepare",
        lambda _root, paths, *_args: (paths, []),
    )
    monkeypatch.setattr(engine, "_gate_validate_contracts", lambda *_args: [])
    monkeypatch.setattr(engine, "_gate_load_policy", lambda *_args: (TEST_POLICY, []))
    monkeypatch.setattr(
        engine, "_gate_load_policy_at_base_with_ref",
        lambda *_args: (TEST_POLICY, "base-sha"),
    )
    monkeypatch.setattr(engine, "_gate_governed_transition_gap_report", lambda *_args: [])
    monkeypatch.setattr(
        engine, "_gate_load_baseline_signoff_key_blobs",
        lambda *_args: ({}, {}),
    )

    def capture_gap(*args):
        captured["base_shas"] = args[5]
        captured["attestation_head_shas"] = args[6]
        return ["sentinel hard-floor block"]

    monkeypatch.setattr(engine, "_gate_hard_floor_gap_report", capture_gap)
    result = engine._gate_run_ship_check(
        tmp_path, ["payments/charge.py"], None,
        ["event-evaluation-merge"], ["base-sha"],
        engine._GATE_ADMISSION_SOURCE_CI_EVENT, supplied,
    )
    assert result["blocked"] is True
    assert "sentinel hard-floor block" in result["reasons"]
    return captured


def test_authoritative_event_head_is_never_aliased_as_attestation_head(
    engine, monkeypatch, tmp_path,
):
    captured = _capture_ship_check_attestation_heads(
        engine, monkeypatch, tmp_path, None,
    )
    assert captured == {
        "base_shas": ["base-sha"],
        "attestation_head_shas": [],
    }


def test_explicit_attestation_head_is_forwarded_separately_from_event_head(
    engine, monkeypatch, tmp_path,
):
    captured = _capture_ship_check_attestation_heads(
        engine, monkeypatch, tmp_path, ["attestation-head"],
    )
    assert captured == {
        "base_shas": ["base-sha"],
        "attestation_head_shas": ["attestation-head"],
    }


@pytest.mark.parametrize(
    ("field", "bad_value", "needle"),
    [
        ("repository_id", "other/repo", "repository_id"),
        ("rule_id", "credentials", "rule_id"),
        ("category", "credentials", "category"),
        ("effective_rule_sha256", "f" * 64, "effective_rule_sha256"),
        ("base_sha", "f" * 40, "base_sha"),
        ("payload_head_sha", "e" * 40, "payload_head_sha"),
    ],
)
def test_wrong_scalar_binding_fails_before_crypto(
    engine, tmp_path, monkeypatch, field, bad_value, needle,
):
    case = _case(tmp_path, engine)
    data = dict(case.signoffs["money"])
    data[field] = bad_value
    data["signature"] = _strict_signature(engine, data)
    _write_signoff(case.root, "money", data)
    head = _commit(case.root, "wrong binding", amend=True)

    def forbidden(*args, **kwargs):
        raise AssertionError("binding mismatch must be rejected before GPG")

    monkeypatch.setattr(engine, "_gate_verify_signoff_signature", forbidden)
    reasons = _report(engine, case, head=head)
    assert any(needle in reason and "binding mismatch" in reason for reason in reasons)


@pytest.mark.parametrize("mutation,needle", [
    ("missing", "missing=['payments/charge.py']"),
    ("extra", "extra=['payments/extra.py']"),
    ("wrong-blob", "immutable payload"),
])
def test_artifact_manifest_must_have_exact_paths_and_blobs(
    engine, tmp_path, crypto_ok, mutation, needle,
):
    case = _case(tmp_path, engine, two_money_paths=(mutation == "missing"))
    data = dict(case.signoffs["money"])
    hashes = dict(data["artifact_hashes"])
    if mutation == "missing":
        hashes.pop("payments/charge.py")
    elif mutation == "extra":
        hashes["payments/extra.py"] = "a" * 40
    else:
        hashes["payments/charge.py"] = "b" * 40
    data["artifact_hashes"] = hashes
    data["signature"] = _strict_signature(engine, data)
    _write_signoff(case.root, "money", data)
    head = _commit(case.root, "bad artifact manifest", amend=True)
    reasons = _report(engine, case, head=head)
    assert any(needle in reason for reason in reasons)
    assert crypto_ok == []


def test_v1_unversioned_signoff_is_rejected(engine, tmp_path, crypto_ok):
    case = _case(tmp_path, engine)
    legacy = {
        "rule_id": "money", "category": "money_movement", "authorized_by": "Xavier",
        "rationale": "legacy", "authorized_at": "2026-07-16T00:00:00Z",
    }
    _write_signoff(case.root, "money", legacy)
    head = _commit(case.root, "legacy signoff", amend=True)
    reasons = _report(engine, case, head=head)
    assert any("v1/unversioned" in reason for reason in reasons)
    assert crypto_ok == []


def test_replayed_stale_payload_parent_is_rejected(engine, tmp_path, crypto_ok):
    case = _case(tmp_path, engine)
    data = dict(case.signoffs["money"])
    data["payload_head_sha"] = case.base
    data["signature"] = _strict_signature(engine, data)
    _write_signoff(case.root, "money", data)
    head = _commit(case.root, "stale payload replay", amend=True)
    reasons = _report(engine, case, head=head)
    assert any("payload_head_sha" in reason and "binding mismatch" in reason for reason in reasons)
    assert crypto_ok == []


def test_changing_signoff_in_a_subsequent_child_invalidates_it(engine, tmp_path, crypto_ok):
    case = _case(tmp_path, engine)
    data = dict(case.signoffs["money"])
    data["rationale"] = "changed after the attestation child"
    data["signature"] = _strict_signature(engine, data)
    _write_signoff(case.root, "money", data)
    later_head = _commit(case.root, "later signoff edit")
    reasons = _report(engine, case, head=later_head)
    assert any("payload_head_sha" in reason and "binding mismatch" in reason for reason in reasons)
    assert crypto_ok == []


def test_any_subsequent_unrelated_commit_invalidates_attestation(engine, tmp_path, crypto_ok):
    case = _case(tmp_path, engine)
    (case.root / "later.txt").write_text("later\n", encoding="utf-8")
    later_head = _commit(case.root, "subsequent unrelated commit")
    reasons = _report(engine, case, head=later_head)
    assert any("later.txt" in reason and "missing=" in reason for reason in reasons)
    assert crypto_ok == []


def _shape_data(engine, now: datetime.datetime) -> dict:
    data = {
        "schema_version": 2,
        "repository_id": "test/tess-os",
        "rule_id": "money",
        "category": "money_movement",
        "effective_rule_sha256": "a" * 64,
        "base_sha": "1" * 40,
        "payload_head_sha": "2" * 40,
        "artifact_hashes": {"payments/charge.py": "3" * 40},
        "authorized_by": "Xavier",
        "rationale": "exact payload reviewed",
        "authorized_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": (now + datetime.timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
    }
    data["signature"] = _strict_signature(engine, data)
    return data


@pytest.mark.parametrize(
    ("mutation", "needle"),
    [
        ("offset", "strict RFC3339 UTC"),
        ("future-skew", "future"),
        ("expired", "expired"),
        ("reverse", "strictly later"),
        ("over-24h", "24 hours"),
    ],
)
def test_timestamp_skew_expiry_and_ttl_fail_closed(engine, mutation, needle):
    now = datetime.datetime(2026, 7, 16, 12, 0, tzinfo=datetime.timezone.utc)
    data = _shape_data(engine, now)
    if mutation == "offset":
        data["authorized_at"] = "2026-07-16T20:00:00+08:00"
    elif mutation == "future-skew":
        data["authorized_at"] = "2026-07-16T12:05:01Z"
        data["expires_at"] = "2026-07-16T13:05:01Z"
    elif mutation == "expired":
        data["authorized_at"] = "2026-07-16T10:00:00Z"
        data["expires_at"] = "2026-07-16T11:00:00Z"
    elif mutation == "reverse":
        data["expires_at"] = data["authorized_at"]
    else:
        data["expires_at"] = "2026-07-17T12:00:01Z"
    ok, reason = engine._gate_validate_signoff_v2_shape_and_time(data, now=now)
    assert ok is False
    assert needle in reason


def test_sign_cli_applies_one_hour_default_without_unsigned_metadata(
    engine, tmp_path, monkeypatch,
):
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    data = _shape_data(engine, now)
    data.pop("expires_at")
    data.pop("signature")
    path = tmp_path / "money.signoff.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    def fake_run(command, *args, **kwargs):
        if "--detach-sign" in command:
            return SimpleNamespace(returncode=0, stdout=b"armored-signature", stderr=b"")
        if "--list-secret-keys" in command:
            fpr = "fpr:::::::::AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA:\n"
            return SimpleNamespace(returncode=0, stdout=fpr.encode(), stderr=b"")
        raise AssertionError(command)

    monkeypatch.setattr(engine.subprocess, "run", fake_run)
    engine._cmd_gate_signoff_sign(
        SimpleNamespace(
            file=str(path), key_id="test-key", gnupg_home=None, output=None,
        ),
        tmp_path,
    )
    signed = json.loads(path.read_text(encoding="utf-8"))
    authorized, _ = engine._gate_parse_signoff_time(signed["authorized_at"], "authorized_at")
    expires, _ = engine._gate_parse_signoff_time(signed["expires_at"], "expires_at")
    assert (expires - authorized).total_seconds() == engine.SIGNOFF_DEFAULT_TTL_SECONDS == 3600
    assert set(signed["signature"]) == {
        "algorithm", "signed_content_sha256", "signature_armored",
    }
