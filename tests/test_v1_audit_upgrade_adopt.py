"""v1.0 integration pass 3: what a verified `tessctl update` adopts beyond core.

The round-2 upgrade e2e (tests/test_v1_r6_upgrade_e2e.py) found that a 0.2.0
install upgraded to 1.0.0 did not get `.codex/rules/tess.rules` or
`.agents/skills/security-audit/**` (its tess.manifest.json did not own them)
and never got the SSH release trust root, so later updates still needed gpg.
These unit tests pin the rules of the fix:

  * only owned_globs the signed release's own manifest lists are added, never
    a catch-all, never one the operator's own never_touch keeps;
  * the SSH release pin and allowed_signers file are ADDED only when this very
    tag carries a valid SSH signature by that key; an existing SSH pin is never
    replaced, and the OpenPGP pin is never touched;
  * the push gate accepts a lock change that adds exactly the proven release's
    SSH pin, and nothing else.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

PIN = "SHA256:" + "A" * 43
OTHER = "SHA256:" + "B" * 43
PGP = "EBEABC618C11B6A7340A7D1601DD637667B8CC89"
SIGNERS = b'twiss-release namespaces="tess-release" ssh-ed25519 AAAA\n'


def _sha(b: bytes) -> str:
    return "sha256:" + hashlib.sha256(b).hexdigest()


@pytest.fixture
def staged(engine, tmp_path, monkeypatch):
    root = tmp_path / "inst"
    (root / ".tess" / "staging" / "upstream-trust").mkdir(parents=True)
    table = {}

    def stage(rel: str, data: bytes):
        p = root / ".tess" / "staging" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        table[rel] = _sha(data)

    monkeypatch.setitem(engine._STAGING_STATE, "verified", table)
    monkeypatch.setitem(engine._STAGING_STATE, "root", str(Path(root).resolve()))
    monkeypatch.setitem(engine._RELEASE_TRUST_STATE, "ssh", None)
    return root, stage


def _manifest(root: Path, owned, never):
    (root / "tess.manifest.json").write_text(json.dumps({"owned_globs": owned,
                                                         "never_touch": never}))


def test_only_the_releases_new_owned_globs_are_added(engine, staged):
    root, stage = staged
    _manifest(root, ["CLAUDE.md"], [".agents/**", "mine/**"])
    stage(engine.STAGED_RELEASE_MANIFEST, json.dumps({
        "owned_globs": ["CLAUDE.md", ".codex/rules/tess.rules", ".agents/skills/security-audit/**",
                        "mine/stuff/**", "**", "../outside/**", "/etc/**"],
        "never_touch": [".agents/**"]}).encode())
    journal: dict = {}
    added = engine._update_adopt_owned_globs(root, journal)
    assert added == [".codex/rules/tess.rules", ".agents/skills/security-audit/**"]
    owned = json.loads((root / "tess.manifest.json").read_text())["owned_globs"]
    assert owned == ["CLAUDE.md", ".codex/rules/tess.rules", ".agents/skills/security-audit/**"]
    assert "mine/stuff/**" not in owned, "the operator's own never_touch wins"
    assert engine.MANIFEST_FILE in journal, "the pre-image is journaled for rollback"


def test_a_changed_staged_manifest_is_refused(engine, staged):
    root, stage = staged
    _manifest(root, ["CLAUDE.md"], [])
    stage(engine.STAGED_RELEASE_MANIFEST, json.dumps({"owned_globs": ["CLAUDE.md"]}).encode())
    (root / ".tess/staging" / engine.STAGED_RELEASE_MANIFEST).write_text(
        json.dumps({"owned_globs": ["**/*"]}))
    with pytest.raises(SystemExit) as exc:
        engine._update_adopt_owned_globs(root, {})
    assert "no longer the signed release" in str(exc.value.code)


def _lock(pin=None):
    fw = {"version": "1.0.0", "trusted_key_fingerprint": PGP}
    if pin is not None:
        fw["trusted_ssh_key_fingerprint"] = pin
    return {"framework": fw, "files": {}}


def _trust(engine, stage, reason=""):
    stage(engine.STAGED_RELEASE_SIGNERS, SIGNERS)
    engine._RELEASE_TRUST_STATE["ssh"] = {"pin": PIN, "reason": reason,
                                          "signers_sha": _sha(SIGNERS)}


def test_the_ssh_pin_and_signers_are_added_and_the_openpgp_pin_kept(engine, staged):
    root, stage = staged
    _trust(engine, stage)
    lock, journal = _lock(), {}
    assert engine._update_adopt_release_trust(root, lock, journal) == PIN
    assert lock["framework"]["trusted_ssh_key_fingerprint"] == PIN
    assert lock["framework"]["trusted_key_fingerprint"] == PGP
    assert (root / engine.RELEASE_SSH_SIGNERS_FILE).read_bytes() == SIGNERS
    assert journal == {engine.RELEASE_SSH_SIGNERS_FILE: None}


def test_an_existing_ssh_pin_is_never_swapped(engine, staged):
    root, stage = staged
    _trust(engine, stage)
    lock = _lock(OTHER)
    assert engine._update_adopt_release_trust(root, lock, {}) is None
    assert lock["framework"]["trusted_ssh_key_fingerprint"] == OTHER
    assert not (root / engine.RELEASE_SSH_SIGNERS_FILE).exists()


def test_no_pin_without_a_valid_ssh_signature_on_this_tag(engine, staged):
    root, stage = staged
    _trust(engine, stage, reason="ssh_signature_invalid")
    lock = _lock()
    assert engine._update_adopt_release_trust(root, lock, {}) is None
    assert "trusted_ssh_key_fingerprint" not in lock["framework"]
    assert not (root / engine.RELEASE_SSH_SIGNERS_FILE).exists()


def test_a_different_installed_signers_file_is_kept(engine, staged):
    root, stage = staged
    _trust(engine, stage)
    target = root / engine.RELEASE_SSH_SIGNERS_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"someone else\n")
    lock = _lock()
    assert engine._update_adopt_release_trust(root, lock, {}) is None
    assert target.read_bytes() == b"someone else\n"
    assert "trusted_ssh_key_fingerprint" not in lock["framework"]


class _Resolve:
    def __init__(self, release_lock_text: str):
        self._text = release_lock_text.encode()

    def release_bytes(self, rel):
        return self._text if rel == ".tess/tess.lock" else None

    def __call__(self, rel):
        return None


def _release_lock_text(pin: str) -> str:
    return (f"schema: 1\nframework:\n  version: 1.0.0\n  trusted_key_fingerprint: {PGP}\n"
            f"  trusted_ssh_key_fingerprint: {pin}\nfiles: {{}}\n")


@pytest.mark.parametrize("head_pin,ok", [(PIN, True), (OTHER, False), ("", True)])
def test_push_gate_accepts_only_the_proven_releases_ssh_pin(engine, head_pin, ok):
    base = {"schema": 1, "framework": {"version": "1.0.0", "upstream_ref": "v1.0.0",
                                       "trusted_key_fingerprint": PGP},
            "files": {}}
    head = json.loads(json.dumps(base))
    if head_pin:
        head["framework"]["trusted_ssh_key_fingerprint"] = head_pin
    why = engine._gate_release_lock_change_ok(base, head, "v1.0.0", "c" * 40,
                                              _Resolve(_release_lock_text(PIN)),
                                              lambda rel: None, lambda rel: None)
    assert (why is None) is ok, why


def test_push_gate_still_refuses_a_changed_openpgp_pin(engine):
    base = {"schema": 1, "framework": {"version": "1.0.0", "trusted_key_fingerprint": PGP,
                                       "trusted_ssh_key_fingerprint": PIN}, "files": {}}
    head = json.loads(json.dumps(base))
    head["framework"]["trusted_key_fingerprint"] = "F" * 40
    why = engine._gate_release_lock_change_ok(base, head, "v1.0.0", "c" * 40,
                                              _Resolve(_release_lock_text(PIN)),
                                              lambda rel: None, lambda rel: None)
    assert why and "trusted_key_fingerprint" in why
    head = json.loads(json.dumps(base))
    head["framework"]["trusted_ssh_key_fingerprint"] = OTHER
    why = engine._gate_release_lock_change_ok(base, head, "v1.0.0", "c" * 40,
                                              _Resolve(_release_lock_text(OTHER)),
                                              lambda rel: None, lambda rel: None)
    assert why and "trusted_ssh_key_fingerprint" in why, "an existing SSH pin is never swapped"
