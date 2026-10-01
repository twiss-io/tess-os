"""
v1.0 security audit (run-1) — regression tests for writer C's findings:
ship-gate policy, verdict/sign-off signing, publish guards and the vault.

Each test fails on release/v1.0 @ 3eba77d and passes with the fix.

  tessctl:_gate_path_covering_status:any-matched-rule-allowed-verifiers
  tessctl:_gate_validate_signoff:signoff-not-bound-to-change
  tessctl:_gate_git_tree_index:multi-ref-union-coverage
  tessctl:_cmd_verdict_sign:no-signer-role-binding
  tessctl-publish-clean-owned-globs-exempt-hard-tier-private-paths
  tessctl-publish-remote-log-skips-non-commit-ref-targets
  tessctl-vault-prepush-scans-net-tree-diff-not-each-commit
  tessctl:vault-reveal-exec-agent-shell-extraction (tessctl side)
  tessctl:vault-identity-keychain-item-no-app-acl

No test touches a real keychain, the real ~/.config/tess, or the network:
keychain calls are mocked, gpg runs in throwaway GNUPGHOMEs, remotes are
local or `.invalid` URLs.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import select
import shutil
import subprocess
import sys
import tempfile
import types
from pathlib import Path

import pytest
import yaml

from conftest import sign_verdict_for_test
from test_gate_spine import (  # noqa: F401 — gate_repo is a fixture
    REFUND_HASHES, _base_sha, _blob_sha, _commit_all, _git, _signed_signoff, _valid_verdict,
    _write_verdict, gate_repo,
)
from test_m5_vault import SECRET, vault  # noqa: F401 — vault is a fixture
from test_publish_clean_gate import priv_repo  # noqa: F401 — fixture

HAS_GIT = shutil.which("git") is not None
HAS_GPG = shutil.which("gpg") is not None
POSIX = not sys.platform.startswith("win")
ZERO = "0" * 40
AWS_KEY = "AKIA" + "ABCDEFGHIJKLMNOP"  # assembled so this file carries no literal key


def _policy(root: Path) -> dict:
    return yaml.safe_load((root / "core" / "policy" / "policy.yaml").read_text(encoding="utf-8"))


def _write_policy(root: Path, policy: dict) -> None:
    (root / "core" / "policy" / "policy.yaml").write_text(yaml.safe_dump(policy), encoding="utf-8")


def _ci(run_cli, root, base, head):
    r = run_cli(root, "gate", "ci", "--base", base, "--head", head, "--json")
    return r.returncode, json.loads(r.stdout)


def _run_in_pty(argv, cwd, env, answer=None, marker=b"sign> ", timeout=120):
    """Run `argv` on a real pseudo-terminal (stdin AND stdout a TTY), typing
    `answer` after `marker` appears. Returns (rc, output)."""
    import pty
    master, slave = pty.openpty()
    p = subprocess.Popen(argv, cwd=str(cwd), stdin=slave, stdout=slave, stderr=slave,
                         env=env, close_fds=True)
    os.close(slave)
    out, sent = b"", False
    while True:
        ready, _, _ = select.select([master], [], [], timeout)
        if not ready:
            break
        try:
            chunk = os.read(master, 4096)
        except OSError:
            break
        if not chunk:
            break
        out += chunk
        if answer is not None and not sent and marker in out:
            os.write(master, (answer + "\n").encode("utf-8"))
            sent = True
    rc = p.wait(timeout=timeout)
    os.close(master)
    return rc, out.decode("utf-8", "replace")


# ===========================================================================
# 1. _gate_path_covering_status:any-matched-rule-allowed-verifiers
# ===========================================================================

def _prod_change(root, text="print('prod v2')\n"):
    (root / "src" / "prod").mkdir(parents=True, exist_ok=True)
    (root / "src" / "prod" / "app.py").write_text(text)
    return _blob_sha(root, "src/prod/app.py")


@pytest.mark.skipif(not (HAS_GIT and HAS_GPG), reason="git + gpg required")
def test_rule_added_in_same_push_cannot_widen_who_clears_a_protected_path(
        gate_repo, run_cli, engine, verifier_gpg_keys):
    """The base rule `prod-src` allows only Reid. The push adds rule `x` over
    the SAME path allowing Quinn (a verifier the base already registers) and
    ships a Quinn-signed verdict. Before the fix ANY matched rule accepting
    Quinn cleared the path; now every matched rule must be met."""
    base = _base_sha(gate_repo)
    policy = _policy(gate_repo)
    policy["policy"]["rules"].append({
        "id": "x", "description": "added in the same push", "globs": ["src/prod/**"],
        "classification": ["prod_touching"], "require_verdict": True,
        "allowed_verifiers": ["Quinn"],
    })
    _write_policy(gate_repo, policy)
    blob = _prod_change(gate_repo)
    _write_verdict(gate_repo, "missions/m1/verdicts/q.verdict.md", _valid_verdict(
        covers_paths=["src/prod/**"], artifact_hashes={"src/prod/app.py": blob},
        verifier="Quinn", engine=engine, keys=verifier_gpg_keys))
    head = _commit_all(gate_repo, "add rule x + prod change + Quinn verdict")

    rc, payload = _ci(run_cli, gate_repo, base, head)
    assert rc == 1, payload
    assert payload["blocked"] is True
    assert "VERIFIER_NOT_ALLOWED: the covering verdict verifier is not allowed" in payload["reasons"] \
        or any(r.startswith("VERIFIER_NOT_ALLOWED") for r in payload["reasons"]), payload


@pytest.mark.skipif(not (HAS_GIT and HAS_GPG), reason="git + gpg required")
def test_rule_whose_globs_are_widened_in_same_push_cannot_clear_another_rules_path(
        gate_repo, run_cli, engine, verifier_gpg_keys):
    """Variant B: the base has a second rule `qa` (Quinn) over src/qa/**. The
    push widens `qa`'s globs to src/prod/** — a rule the base did not match
    for this path, so it was kept verbatim and its Quinn verdict cleared the
    Reid-only path."""
    policy = _policy(gate_repo)
    policy["policy"]["rules"].append({
        "id": "qa", "description": "qa code", "globs": ["src/qa/**"],
        "classification": ["prod_touching"], "require_verdict": True,
        "allowed_verifiers": ["Quinn"],
    })
    _write_policy(gate_repo, policy)
    base = _commit_all(gate_repo, "base: add qa rule")
    policy["policy"]["rules"][-1]["globs"] = ["src/qa/**", "src/prod/**"]
    _write_policy(gate_repo, policy)
    blob = _prod_change(gate_repo)
    _write_verdict(gate_repo, "missions/m1/verdicts/q.verdict.md", _valid_verdict(
        covers_paths=["src/prod/**"], artifact_hashes={"src/prod/app.py": blob},
        verifier="Quinn", engine=engine, keys=verifier_gpg_keys))
    head = _commit_all(gate_repo, "widen qa globs + prod change + Quinn verdict")

    rc, payload = _ci(run_cli, gate_repo, base, head)
    assert rc == 1 and payload["blocked"] is True, payload


@pytest.mark.skipif(not (HAS_GIT and HAS_GPG), reason="git + gpg required")
def test_every_matched_rule_is_met_by_its_own_allowed_verifier_passes(
        gate_repo, run_cli, engine, verifier_gpg_keys):
    """Control: with a verdict from each rule's own allowed verifier (Reid for
    prod-src, Quinn for the added rule x) the push passes — a rule added in a
    push adds a requirement; it does not make the path unclearable."""
    base = _base_sha(gate_repo)
    policy = _policy(gate_repo)
    policy["policy"]["rules"].append({
        "id": "x", "description": "added", "globs": ["src/prod/**"],
        "classification": ["prod_touching"], "require_verdict": True,
        "allowed_verifiers": ["Quinn"],
    })
    _write_policy(gate_repo, policy)
    blob = _prod_change(gate_repo)
    for who in ("Reid", "Quinn"):
        _write_verdict(gate_repo, f"missions/m1/verdicts/{who.lower()}.verdict.md", _valid_verdict(
            covers_paths=["src/prod/**"], artifact_hashes={"src/prod/app.py": blob},
            verifier=who, engine=engine, keys=verifier_gpg_keys))
    head = _commit_all(gate_repo, "rule x + prod change + Reid and Quinn verdicts")

    rc, payload = _ci(run_cli, gate_repo, base, head)
    assert rc == 0, payload
    assert payload["blocked"] is False


# ===========================================================================
# 2. _gate_validate_signoff:signoff-not-bound-to-change
# ===========================================================================

def _signoff_dir(root):
    d = root / ".tess" / "gate" / "signoffs"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.mark.skipif(not (HAS_GIT and HAS_GPG), reason="git + gpg required")
def test_signoff_does_not_clear_a_later_change_to_the_same_floor(
        gate_repo, run_cli, engine, verifier_gpg_keys):
    """A valid sign-off for `refund()` is committed. A LATER push changes the
    same hard-floor file again and leaves the sign-off untouched. Before the
    fix the old sign-off cleared it; now it covers only the content it names."""
    base0 = _base_sha(gate_repo)
    (gate_repo / "payments").mkdir(parents=True)
    (gate_repo / "payments" / "charge.py").write_text("refund()\n")
    (_signoff_dir(gate_repo) / "money.signoff.json").write_text(
        json.dumps(_signed_signoff(engine, verifier_gpg_keys["Reid"])), encoding="utf-8")
    head1 = _commit_all(gate_repo, "payments + signed sign-off")
    rc, payload = _ci(run_cli, gate_repo, base0, head1)
    assert rc == 0, payload  # the approved change itself still clears

    (gate_repo / "payments" / "charge.py").write_text("refund(everything=True)\n")
    head2 = _commit_all(gate_repo, "later, unapproved payments change")
    rc, payload = _ci(run_cli, gate_repo, head1, head2)
    assert rc == 1, payload
    assert "HARD_FLOOR_UNSATISFIED: a required hard-floor sign-off is not valid" in payload["reasons"]


@pytest.mark.skipif(not (HAS_GIT and HAS_GPG), reason="git + gpg required")
def test_signoff_does_not_clear_a_new_file_it_does_not_name(
        gate_repo, run_cli, engine, verifier_gpg_keys):
    base0 = _base_sha(gate_repo)
    (gate_repo / "payments").mkdir(parents=True)
    (gate_repo / "payments" / "charge.py").write_text("refund()\n")
    (gate_repo / "payments" / "wire.py").write_text("transfer()\n")
    (_signoff_dir(gate_repo) / "money.signoff.json").write_text(
        json.dumps(_signed_signoff(engine, verifier_gpg_keys["Reid"])), encoding="utf-8")
    head = _commit_all(gate_repo, "two payments files, sign-off names one")
    rc, payload = _ci(run_cli, gate_repo, base0, head)
    assert rc == 1, payload
    assert "HARD_FLOOR_UNSATISFIED: a required hard-floor sign-off is not valid" in payload["reasons"]


def test_signoff_without_artifact_hashes_is_rejected(engine, tmp_path):
    p = tmp_path / "money.signoff.json"
    p.write_text(json.dumps({
        "rule_id": "money", "category": "money_movement", "authorized_by": "Xavier",
        "rationale": "x", "authorized_at": "2026-07-07T00:00:00Z",
    }))
    ok, reason, _ = engine._gate_validate_signoff(p, "money", tmp_path, {"policy": {}})
    assert ok is False
    assert "artifact_hashes" in reason


def test_signoff_uncovered_paths_binds_to_content(engine):
    data = {"artifact_hashes": {"a.env": "1" * 40}}
    assert engine._gate_signoff_uncovered_paths(data, ["a.env"], {"a.env": {"1" * 40}}) == []
    assert engine._gate_signoff_uncovered_paths(data, ["a.env"], {"a.env": {"2" * 40}}) == ["a.env"]
    assert engine._gate_signoff_uncovered_paths(data, ["b.env"], {"b.env": {"1" * 40}}) == ["b.env"]
    # no content index (nothing pushed to read): fail closed
    assert engine._gate_signoff_uncovered_paths(data, ["a.env"], None) == ["a.env"]


# ===========================================================================
# 3. _gate_git_tree_index:multi-ref-union-coverage
# ===========================================================================

@pytest.fixture
def two_ref_repo(gate_repo, engine, verifier_gpg_keys):
    """main at M: src/prod/app.py = Y with a signed Reid verdict for Y.
    Branch `other` at M too."""
    blob_y = _prod_change(gate_repo, "print('Y reviewed')\n")
    _write_verdict(gate_repo, "missions/m1/verdicts/prod-src.verdict.md", _valid_verdict(
        covers_paths=["src/prod/**"], artifact_hashes={"src/prod/app.py": blob_y},
        engine=engine, keys=verifier_gpg_keys))
    m = _commit_all(gate_repo, "M: reviewed Y + verdict")
    _git(gate_repo, "branch", "other", m)
    return types.SimpleNamespace(root=gate_repo, m=m)


def _decoy(repo):
    """D = other + an unrelated docs change (P stays at the approved Y)."""
    _git(repo.root, "checkout", "-q", "other")
    (repo.root / "docs").mkdir(exist_ok=True)
    (repo.root / "docs" / "n.md").write_text("decoy\n")
    d = _commit_all(repo.root, "D: decoy")
    _git(repo.root, "checkout", "-q", "main")
    return d


@pytest.mark.skipif(not (HAS_GIT and HAS_GPG), reason="git + gpg required")
def test_multi_ref_push_cannot_borrow_approved_content_from_another_ref(two_ref_repo, run_cli):
    repo = two_ref_repo
    _prod_change(repo.root, "print('Z never reviewed')\n")
    e = _commit_all(repo.root, "E: unreviewed Z")
    d = _decoy(repo)

    alone = f"refs/heads/main {e} refs/heads/main {repo.m}\n"
    r = run_cli(repo.root, "gate", "pre-push", "--json", input_text=alone)
    assert r.returncode == 1, r.stdout  # control: E alone is blocked

    both = alone + f"refs/heads/other {d} refs/heads/other {repo.m}\n"
    r = run_cli(repo.root, "gate", "pre-push", "--json", input_text=both)
    assert r.returncode == 1, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    assert payload["blocked"] is True
    assert "VERDICT_CONTENT_STALE: the covering verdict does not match current content" in payload["reasons"] \
        or any(x.startswith("VERDICT_CONTENT_STALE") for x in payload["reasons"]), payload


@pytest.mark.skipif(not (HAS_GIT and HAS_GPG), reason="git + gpg required")
def test_multi_ref_push_cannot_hide_a_deletion_behind_another_ref(two_ref_repo, run_cli):
    repo = two_ref_repo
    (repo.root / "src" / "prod" / "app.py").unlink()
    e = _commit_all(repo.root, "E: delete protected file")
    d = _decoy(repo)
    both = (f"refs/heads/main {e} refs/heads/main {repo.m}\n"
            f"refs/heads/other {d} refs/heads/other {repo.m}\n")
    r = run_cli(repo.root, "gate", "pre-push", "--json", input_text=both)
    assert r.returncode == 1, r.stdout + r.stderr
    assert json.loads(r.stdout)["blocked"] is True


@pytest.mark.skipif(not (HAS_GIT and HAS_GPG), reason="git + gpg required")
def test_multi_ref_push_of_clean_refs_still_passes(two_ref_repo, run_cli):
    repo = two_ref_repo
    (repo.root / "docs").mkdir(exist_ok=True)
    (repo.root / "docs" / "main.md").write_text("fine\n")
    e = _commit_all(repo.root, "E: docs only")
    d = _decoy(repo)
    both = (f"refs/heads/main {e} refs/heads/main {repo.m}\n"
            f"refs/heads/other {d} refs/heads/other {repo.m}\n")
    r = run_cli(repo.root, "gate", "pre-push", "--json", input_text=both)
    assert r.returncode == 0, r.stdout + r.stderr


# ===========================================================================
# 4. _cmd_verdict_sign:no-signer-role-binding (and gate signoff sign)
# ===========================================================================

def _verdict_file(root, verifier="Reid"):
    p = root / "reviews" / "x.verdict.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(_valid_verdict(
        covers_paths=["src/prod/**"], artifact_hashes={"src/prod/app.py": "1" * 40},
        verifier=verifier)), encoding="utf-8")
    return p


def _sign_args(path, key, verifier="Reid", home=None):
    return argparse.Namespace(file=str(path), verifier=verifier, key_id=key.fpr,
                              gnupg_home=str(home or key.home), output=None)


@pytest.mark.skipif(not (HAS_GIT and HAS_GPG), reason="git + gpg required")
def test_verdict_sign_refuses_without_a_terminal(gate_repo, run_cli, verifier_gpg_keys):
    """What an assistant's tool call looks like: no terminal. Refused, and the
    verdict file is left unsigned."""
    key = verifier_gpg_keys["Reid"]
    path = _verdict_file(gate_repo)
    before = path.read_bytes()
    r = run_cli(gate_repo, "verdict", "sign", str(path), "--verifier", "Reid",
                "--key-id", key.fpr, "--gnupg-home", str(key.home))
    assert r.returncode != 0
    assert "needs a person at a terminal" in r.stderr
    assert path.read_bytes() == before


@pytest.mark.skipif(not (HAS_GIT and HAS_GPG and POSIX), reason="git + gpg + pty required")
def test_verdict_sign_refuses_a_key_without_a_passphrase_even_at_a_terminal(
        gate_repo, verifier_gpg_keys):
    """The registered key has no passphrase, so any program running as the
    user could sign with it silently: refused, even from a real terminal."""
    key = verifier_gpg_keys["Reid"]
    path = _verdict_file(gate_repo)
    before = path.read_bytes()
    rc, out = _run_in_pty(
        [sys.executable, str(gate_repo / ".tess" / "bin" / "tessctl"), "verdict", "sign", str(path),
         "--verifier", "Reid", "--key-id", key.fpr, "--gnupg-home", str(key.home)],
        gate_repo, {**os.environ, "TESS_ROOT": str(gate_repo)}, answer="sign as Reid")
    assert rc != 0, out
    assert "has no passphrase" in out
    assert path.read_bytes() == before


@pytest.mark.skipif(not (HAS_GIT and HAS_GPG), reason="git + gpg required")
def test_verdict_sign_refuses_a_key_not_registered_for_that_verifier(
        gate_repo, engine, verifier_gpg_keys, monkeypatch):
    monkeypatch.setattr(engine, "_signer_is_terminal", lambda: True)
    path = _verdict_file(gate_repo, verifier="Reid")
    with pytest.raises(SystemExit) as exc:
        engine._cmd_verdict_sign(_sign_args(path, verifier_gpg_keys["Quinn"]), gate_repo)
    assert "is not the key registered for 'Reid'" in str(exc.value)
    assert "signature" not in json.loads(path.read_text())


@pytest.mark.skipif(not (HAS_GIT and HAS_GPG), reason="git + gpg required")
def test_verdict_sign_refuses_a_keyring_inside_the_project(
        gate_repo, engine, verifier_gpg_keys, monkeypatch):
    monkeypatch.setattr(engine, "_signer_is_terminal", lambda: True)
    path = _verdict_file(gate_repo)
    inside = gate_repo / ".gnupg"
    inside.mkdir()
    with pytest.raises(SystemExit) as exc:
        engine._cmd_verdict_sign(_sign_args(path, verifier_gpg_keys["Reid"], home=inside), gate_repo)
    assert "inside this project folder" in str(exc.value)


def _protected_key(name="Reid"):
    """A passphrase-protected signing key whose passphrase is PRESET in its
    own throwaway gpg-agent (so gpg signs without pinentry), or None."""
    preset = None
    r = subprocess.run(["gpgconf", "--list-dirs", "libexecdir"], capture_output=True, text=True)
    if r.returncode == 0:
        cand = Path(r.stdout.strip()) / "gpg-preset-passphrase"
        preset = cand if cand.exists() else None
    if preset is None:
        return None
    home = Path(tempfile.mkdtemp(prefix="tessgpgp", dir="/tmp"))
    os.chmod(home, 0o700)
    (home / "gpg-agent.conf").write_text("allow-preset-passphrase\n")
    env = {**os.environ, "GNUPGHOME": str(home)}
    params = home / "params"
    params.write_text("Key-Type: eddsa\nKey-Curve: ed25519\nKey-Usage: sign\n"
                      f"Name-Real: Protected {name}\nName-Email: p{name.lower()}@tess.test\n"
                      "Expire-Date: 0\nPassphrase: correct horse\n%commit\n")
    g = subprocess.run(["gpg", "--batch", "--pinentry-mode", "loopback", "--gen-key", str(params)],
                       capture_output=True, text=True, env=env)
    if g.returncode != 0:
        shutil.rmtree(home, ignore_errors=True)
        return None
    lk = subprocess.run(["gpg", "--batch", "--with-colons", "--with-keygrip", "--list-secret-keys"],
                        capture_output=True, text=True, env=env).stdout.splitlines()
    fpr = next(line.split(":")[9] for line in lk if line.startswith("fpr:"))
    grip = next(line.split(":")[9] for line in lk if line.startswith("grp:"))
    subprocess.run([str(preset), "--preset", "-P", "correct horse", grip],
                   capture_output=True, env=env)
    pub = subprocess.run(["gpg", "--armor", "--export", fpr], capture_output=True, text=True,
                         env=env).stdout
    return types.SimpleNamespace(home=home, fpr=fpr, grip=grip, pubkey_armored=pub)


def _agent_cached(key) -> str:
    r = subprocess.run(["gpg-connect-agent", "--homedir", str(key.home), f"KEYINFO {key.grip}", "/bye"],
                       capture_output=True, text=True, env={**os.environ, "GNUPGHOME": str(key.home)})
    for line in r.stdout.splitlines():
        f = line.split()
        if len(f) >= 8 and f[1] == "KEYINFO":
            return f[6]
    return "?"


@pytest.mark.skipif(not (HAS_GIT and HAS_GPG), reason="git + gpg required")
def test_verdict_sign_with_a_protected_registered_key_after_typed_confirmation(
        gate_repo, engine, monkeypatch, capsys):
    """The one accepted path: a person at a terminal types the confirmation,
    the key is the registered one and has a passphrase. The signature
    verifies, and the passphrase gpg-agent cached is forgotten afterwards."""
    key = _protected_key()
    if key is None:
        pytest.skip("gpg-preset-passphrase unavailable")
    try:
        (gate_repo / ".tess" / "keys" / "verifiers" / "reid.asc").write_text(key.pubkey_armored)
        policy = _policy(gate_repo)
        policy["policy"]["verifier_keys"]["Reid"]["fingerprint"] = key.fpr
        _write_policy(gate_repo, policy)
        _commit_all(gate_repo, "register protected Reid key")
        assert engine._signer_key_protection(key.grip, str(key.home)) == "P"
        path = _verdict_file(gate_repo)
        monkeypatch.setattr(engine, "_signer_is_terminal", lambda: True)

        monkeypatch.setattr(engine.sys, "stdin", io.StringIO("yes\n"))
        with pytest.raises(SystemExit) as exc:
            engine._cmd_verdict_sign(_sign_args(path, key), gate_repo)
        assert "you did not type `sign as Reid`" in str(exc.value)
        assert "signature" not in json.loads(path.read_text())

        assert _agent_cached(key) == "1"
        monkeypatch.setattr(engine.sys, "stdin", io.StringIO("sign as Reid\n"))
        engine._cmd_verdict_sign(_sign_args(path, key), gate_repo)
        signed = json.loads(path.read_text())
        assert "BEGIN PGP SIGNATURE" in signed["signature"]["signature_armored"]
        ok, why = engine._gate_verify_verdict_signature(
            gate_repo, _policy(gate_repo), signed,
            trusted_verifier_key_blobs={"Reid": key.pubkey_armored.encode()})
        assert ok is True, why
        assert _agent_cached(key) != "1"  # the cached passphrase was forgotten
    finally:
        subprocess.run(["gpgconf", "--homedir", str(key.home), "--kill", "gpg-agent"],
                       capture_output=True)
        shutil.rmtree(key.home, ignore_errors=True)


@pytest.mark.skipif(not (HAS_GIT and HAS_GPG), reason="git + gpg required")
def test_signoff_sign_refuses_without_a_terminal_and_needs_artifact_hashes(
        gate_repo, run_cli, verifier_gpg_keys):
    key = verifier_gpg_keys["Reid"]
    p = _signoff_dir(gate_repo) / "money.signoff.json"
    base = {"rule_id": "money", "category": "money_movement", "authorized_by": "Xavier",
            "rationale": "x", "authorized_at": "2026-07-07T00:00:00Z"}
    p.write_text(json.dumps(base))
    r = run_cli(gate_repo, "gate", "signoff", "sign", str(p), "--key-id", key.fpr,
                "--gnupg-home", str(key.home))
    assert r.returncode != 0 and "artifact_hashes" in r.stderr

    p.write_text(json.dumps({**base, "artifact_hashes": dict(REFUND_HASHES)}))
    r = run_cli(gate_repo, "gate", "signoff", "sign", str(p), "--key-id", key.fpr,
                "--gnupg-home", str(key.home))
    assert r.returncode != 0 and "needs a person at a terminal" in r.stderr
    assert "signature" not in json.loads(p.read_text())


# ===========================================================================
# 5. publish-clean: hard-tier private shapes under framework-owned globs
# ===========================================================================

@pytest.mark.parametrize("rel", [
    "conductor/guardrails.local.md",
    "agents/leah.local.md",
    ".claude/agents/cyra.local.md",
    "prompts/help.local.md",
    "conductor/secrets.age",
    "agents/.private/notes.md",
])
def test_publish_clean_blocks_hard_tier_shapes_under_owned_globs(engine, priv_repo, rel):
    p = priv_repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("private overlay\n")
    _git(priv_repo, "add", "-f", rel)
    manifest = engine.load_manifest(priv_repo)
    assert engine.path_matches_globs(rel, manifest["owned_globs"])  # the precondition
    flagged = {v[0] for v in engine._publish_clean_violations(priv_repo, manifest, scope="staged")}
    assert rel in flagged


def test_publish_clean_still_allows_owned_scaffold(engine, priv_repo):
    rel = "clients/_template/CLAUDE.md"
    p = priv_repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("scaffold\n")
    _git(priv_repo, "add", "-f", rel)
    manifest = engine.load_manifest(priv_repo)
    assert rel not in {v[0] for v in engine._publish_clean_violations(priv_repo, manifest)}


# ===========================================================================
# 6. publish-remote: refs that point at a tree, a tag of a tree, or a blob
# ===========================================================================

@pytest.fixture
def data_repo(tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    _git(root, "init", "-b", "main", "-q")
    _git(root, "config", "user.email", "t@tess.test")
    _git(root, "config", "user.name", "T")
    _git(root, "config", "commit.gpgsign", "false")
    _git(root, "config", "tag.gpgsign", "false")
    (root / "brain" / "clients" / "acme").mkdir(parents=True)
    (root / "brain" / "clients" / "acme" / "n.md").write_text("client secret plan\n")
    (root / "README.md").write_text("hi\n")
    commit = _commit_all(root, "client data")
    tree = _git(root, "rev-parse", "HEAD^{tree}").stdout.strip()
    blob = _git(root, "rev-parse", "HEAD:brain/clients/acme/n.md").stdout.strip()
    _git(root, "tag", "-a", "-m", "tree tag", "treetag", tree)
    tag = _git(root, "rev-parse", "treetag").stdout.strip()
    return types.SimpleNamespace(root=root, commit=commit, tree=tree, blob=blob, tag=tag)


@pytest.mark.skipif(not HAS_GIT, reason="git required")
@pytest.mark.parametrize("which", ["tree", "tag"])
def test_publish_remote_lists_data_in_a_pushed_tree(engine, data_repo, which):
    sha = getattr(data_repo, which)
    stdin = f"refs/tags/t {sha} refs/tags/t {ZERO}\n"
    assert engine._publish_remote_data_paths(data_repo.root, stdin) == ["brain/clients/acme/n.md"]


@pytest.mark.skipif(not HAS_GIT, reason="git required")
def test_publish_remote_refuses_a_pushed_blob(engine, data_repo):
    stdin = f"refs/tags/b {data_repo.blob} refs/tags/b {ZERO}\n"
    with pytest.raises(RuntimeError):
        engine._publish_remote_data_paths(data_repo.root, stdin)


@pytest.mark.skipif(not HAS_GIT, reason="git required")
def test_publish_remote_cli_refuses_a_tree_push_to_an_unverifiable_remote(data_repo):
    engine_path = Path(__file__).resolve().parent.parent / ".tess" / "bin" / "tessctl"
    r = subprocess.run(
        [sys.executable, str(engine_path), "doctor", "--publish-remote", "pub",
         "https://git.example.invalid/o/r.git"],
        cwd=data_repo.root, input=f"refs/tags/t {data_repo.tree} refs/tags/t {ZERO}\n",
        capture_output=True, text=True, env={**os.environ, "TESS_ROOT": str(data_repo.root)})
    assert r.returncode == 1, r.stdout + r.stderr


# ===========================================================================
# 7. vault pre-push: every pushed commit is scanned, not only the tip
# ===========================================================================

@pytest.fixture
def hooked_repo(tmp_path, engine):
    root = tmp_path / "v"
    root.mkdir()
    _git(root, "init", "-b", "main", "-q")
    _git(root, "config", "user.email", "t@tess.test")
    _git(root, "config", "user.name", "T")
    _git(root, "config", "commit.gpgsign", "false")
    (root / "README.md").write_text("hi\n")
    _commit_all(root, "init")
    return root


def _install_vault_hooks(engine, root):
    import contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        engine._vault_install_git_hooks(root)


def _vault_prepush(root, stdin):
    return subprocess.run(["bash", str(root / ".git" / "hooks" / "pre-push"), "origin", "/dev/null"],
                          cwd=root, input=stdin, capture_output=True, text=True)


@pytest.mark.skipif(not HAS_GIT, reason="git required")
def test_vault_prepush_catches_a_secret_added_then_removed_in_the_pushed_range(engine, hooked_repo):
    root = hooked_repo
    (root / "notes.txt").write_text(f"aws = {AWS_KEY}\n")
    _commit_all(root, "A: add secret (made where no hook ran)")
    (root / "notes.txt").unlink()
    tip = _commit_all(root, "B: remove it")
    _install_vault_hooks(engine, root)
    r = _vault_prepush(root, f"refs/heads/main {tip} refs/heads/main {ZERO}\n")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "AWS KEY" in r.stderr


@pytest.mark.skipif(not HAS_GIT, reason="git required")
def test_vault_prepush_catches_a_secret_only_in_a_merged_side_branch(engine, hooked_repo):
    root = hooked_repo
    base = _git(root, "rev-parse", "HEAD").stdout.strip()
    _git(root, "checkout", "-q", "-b", "side")
    (root / "side.txt").write_text(f"k={AWS_KEY}\n")
    _commit_all(root, "side: secret")
    (root / "side.txt").unlink()
    _commit_all(root, "side: removed")
    _git(root, "checkout", "-q", "main")
    (root / "m.txt").write_text("main\n")
    _commit_all(root, "main work")
    _git(root, "merge", "-q", "--no-ff", "-m", "merge side", "side")
    tip = _git(root, "rev-parse", "HEAD").stdout.strip()
    _install_vault_hooks(engine, root)
    r = _vault_prepush(root, f"refs/heads/main {tip} refs/heads/main {base}\n")
    assert r.returncode == 1, r.stdout + r.stderr


@pytest.mark.skipif(not HAS_GIT, reason="git required")
def test_vault_prepush_scans_a_pushed_tree(engine, hooked_repo):
    root = hooked_repo
    (root / "cfg.txt").write_text(f"k={AWS_KEY}\n")
    _commit_all(root, "secret")
    tree = _git(root, "rev-parse", "HEAD^{tree}").stdout.strip()
    _install_vault_hooks(engine, root)
    r = _vault_prepush(root, f"refs/tags/t {tree} refs/tags/t {ZERO}\n")
    assert r.returncode == 1, r.stdout + r.stderr


@pytest.mark.skipif(not HAS_GIT, reason="git required")
def test_vault_prepush_clean_history_passes(engine, hooked_repo):
    root = hooked_repo
    base = _git(root, "rev-parse", "HEAD").stdout.strip()
    (root / "ok.txt").write_text("nothing secret\n")
    tip = _commit_all(root, "clean")
    _install_vault_hooks(engine, root)
    r = _vault_prepush(root, f"refs/heads/main {tip} refs/heads/main {base}\n")
    assert r.returncode == 0, r.stdout + r.stderr


# ===========================================================================
# 8. vault reveal / exec (tessctl side)
# ===========================================================================

def _set_secret(run_cli, vault, ref="test/secret", value=SECRET):
    r = run_cli(vault.root, "vault", "set", ref, input_text=value + "\n", extra_env=vault.env)
    assert r.returncode == 0, r.stderr


def _script(vault, name, code):
    p = vault.root / name
    p.write_text(f"#!{sys.executable}\n{code}\n", encoding="utf-8")
    p.chmod(0o755)
    return str(p)


def test_reveal_to_a_pipe_is_refused(vault, run_cli):
    _set_secret(run_cli, vault)
    r = run_cli(vault.root, "vault", "get", "test/secret", "--reveal", "--force", extra_env=vault.env)
    assert r.returncode != 0
    assert SECRET not in r.stdout + r.stderr


@pytest.mark.skipif(not POSIX, reason="needs a pty")
def test_reveal_to_a_person_at_a_terminal_still_works(vault, run_cli):
    _set_secret(run_cli, vault)
    rc, out = _run_in_pty(
        [sys.executable, str(vault.root / ".tess" / "bin" / "tessctl"), "vault", "get",
         "test/secret", "--reveal"],
        vault.root, {**os.environ, **vault.env, "TESS_ROOT": str(vault.root)})
    assert rc == 0, out
    assert SECRET in out


@pytest.mark.parametrize("consumer", [
    ["printenv", "TEST_SECRET"], ["env"], ["/usr/bin/env"], ["sh", "-c", "echo $TEST_SECRET"],
    ["bash", "-c", "true"], ["python3", "-c", "print(1)"], ["python3.12", "-V"],
    ["python3", "-m", "cgi"], ["python3"], ["node", "-e", "1"], ["perl", "-e", "1"],
    ["xargs", "echo"], ["timeout", "5", "printenv"],
])
def test_exec_refuses_printers_shells_and_interpreters_outside_a_terminal(vault, run_cli, consumer):
    _set_secret(run_cli, vault)
    r = run_cli(vault.root, "vault", "exec", "--ref", "test/secret", "--", *consumer,
                extra_env=vault.env)
    assert r.returncode != 0
    assert "refused" in r.stderr and "Nothing was run" in r.stderr
    assert SECRET not in r.stdout + r.stderr


@pytest.mark.parametrize("name", ["BASH_ENV", "bash_env", "ENV", "PROMPT_COMMAND", "LD_PRELOAD",
                                  "DYLD_INSERT_LIBRARIES", "PS1", "BASH_FUNC_x%%", "NODE_OPTIONS",
                                  "GIT_SSH_COMMAND", "PATH"])
def test_exec_refuses_variables_programs_run_or_print(vault, run_cli, name):
    _set_secret(run_cli, vault)
    marker = vault.root / "ran.txt"
    child = _script(vault, "child_ok.py", f"open({str(marker)!r},'w').write('ran')")
    r = run_cli(vault.root, "vault", "exec", "--ref", "test/secret", "--as", name, "--", child,
                extra_env=vault.env)
    assert r.returncode != 0
    assert "Nothing was run" in r.stderr
    assert not marker.exists()


def test_exec_refuses_a_ref_whose_default_name_is_dangerous(vault, run_cli):
    _set_secret(run_cli, vault, ref="bash/env")
    child = _script(vault, "c.py", "print('x')")
    r = run_cli(vault.root, "vault", "exec", "--ref", "bash/env", "--", child, extra_env=vault.env)
    assert r.returncode != 0 and "BASH_ENV" in r.stderr


def test_exec_masks_the_secret_in_a_childs_output(vault, run_cli):
    """A program that echoes its credential (a verbose HTTP client, an error
    message) no longer hands the value to whoever reads the output."""
    _set_secret(run_cli, vault)
    child = _script(vault, "leaky.py",
                    "import os,sys;v=os.environ['TEST_SECRET'];"
                    "print('token='+v);sys.stderr.write('err '+v+'\\n');"
                    "sys.stdout.write(v[:5]);sys.stdout.flush();sys.stdout.write(v[5:]+'\\n')")
    r = run_cli(vault.root, "vault", "exec", "--ref", "test/secret", "--", child, extra_env=vault.env)
    assert r.returncode == 0, r.stderr
    assert SECRET not in r.stdout + r.stderr
    assert "[vault:test/secret hidden]" in r.stdout
    assert "[vault:test/secret hidden]" in r.stderr


def test_exec_allows_an_interpreter_running_a_script_file_with_output_masked(vault, run_cli):
    """`vault exec -- python3 run.py` (the documented pattern) still runs; a
    script that prints the value has it masked."""
    _set_secret(run_cli, vault)
    (vault.root / "run.py").write_text("import os\nprint('got', os.environ['TEST_SECRET'])\n")
    r = run_cli(vault.root, "vault", "exec", "--ref", "test/secret", "--", "python3", "run.py",
                extra_env=vault.env)
    assert r.returncode == 0, r.stderr
    assert "got [vault:test/secret hidden]" in r.stdout
    assert SECRET not in r.stdout + r.stderr


def test_exec_relay_masks_across_read_boundaries(engine):
    secret, mask = b"SECRETVALUE123", b"[hidden]"
    r_fd, w_fd = os.pipe()
    data = b"a" * 65530 + secret + b"tail" + secret
    pid = os.fork() if POSIX else None
    if pid == 0:
        os.close(r_fd)
        os.write(w_fd, data)
        os._exit(0)
    os.close(w_fd)
    out = io.BytesIO()
    with os.fdopen(r_fd, "rb") as src:
        engine._vault_exec_relay(src, out, secret, mask)
    os.waitpid(pid, 0)
    assert out.getvalue() == b"a" * 65530 + mask + b"tail" + mask


# ===========================================================================
# 9. vault identity keychain item: no pre-authorised application
# ===========================================================================

def test_keychain_item_is_created_with_an_empty_trusted_app_list(engine, monkeypatch, capsys):
    """The item is stored with `-T ""` (so every read prompts) after any old
    item is deleted (so an older, open access list cannot survive). The real
    keychain is never touched: `security` is mocked."""
    monkeypatch.setattr(engine.sys, "platform", "darwin")
    priv = "AGE-SECRET-KEY-" + "B" * 59
    calls = []

    def fake_run(argv, *a, **kw):
        calls.append(list(argv))
        if "find-generic-password" in argv:
            return subprocess.CompletedProcess(argv, 0, stdout=(priv + "\n").encode(), stderr=b"")
        return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(engine.subprocess, "run", fake_run)
    assert engine._vault_store_identity_keychain(priv) is True
    verbs = [c[1] for c in calls]
    assert verbs.index("delete-generic-password") < verbs.index("add-generic-password")
    add = next(c for c in calls if c[1] == "add-generic-password")
    i = add.index("-T")
    assert add[i + 1] == ""
    assert "-A" not in add
    assert all(priv not in part for part in add)
    assert "Always Allow" in capsys.readouterr().out


def test_receipt_schema_accepts_a_signoff_bound_to_content(engine):
    """A sign-off now carries `artifact_hashes`; a receipt that embeds it
    must still validate (SignoffArtifact is additionalProperties: false)."""
    from test_agent_receipt_schema import CONTRACTS_DIR, SCHEMA_PATH, _base_receipt, _base_signoff
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    signoff = _base_signoff()
    signoff["artifact_hashes"] = {"payments/charge.py": "1" * 40}
    receipt = _base_receipt("signoff", signoff, rule_kind="hard_floor_rule")
    assert engine.schema_validate(receipt, schema, schema, CONTRACTS_DIR) == []
    signoff["artifact_hashes"] = {"payments/charge.py": "not-a-blob-id"}
    receipt = _base_receipt("signoff", signoff, rule_kind="hard_floor_rule")
    assert engine.schema_validate(receipt, schema, schema, CONTRACTS_DIR) != []


@pytest.mark.skipif(not HAS_GIT, reason="git required")
def test_vault_prepush_scans_a_pushed_blob(engine, hooked_repo):
    root = hooked_repo
    blob = _git(root, "hash-object", "-w", "--stdin", input_text=f"k={AWS_KEY}\n").stdout.strip()
    _install_vault_hooks(engine, root)
    r = _vault_prepush(root, f"refs/tags/b {blob} refs/tags/b {ZERO}\n")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "AWS KEY" in r.stderr
