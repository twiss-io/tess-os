"""v1.0.0 — a fresh install's first push passes the review gate with no verdict.

`npm create tess` commits the whole framework in one seed commit; the first
push has no base commit, so before v1.0.0 every protected file needed a
verdict no new user can sign (COVERING_APPROVAL_MISSING). The npm package now
ships `.tess/release-proof.json` for the signed release it was built from and
the gate accepts a first push whose protected files ARE that release.

End to end, the way publish-npm.yml does it, with throwaway release keys in
place of the Twiss keys: copy this source tree, pin the test keys (engine
anchors, tess.lock, key files), commit, sign the tag (SSH manifest, plus
OpenPGP when gpg exists), build the proof, `npm pack`, install from the
tarball, then run `tessctl gate ci` / `gate pre-push` on the first commit.
Also: a hand-edited protected file, a lock tier change, a widened policy and
two forged proofs (other key; other key AND swapped key file) are refused.
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from test_v1_ssh_release_sig import MARKER, _new_ssh_key, _path_without_gpg, _ssh_block

REPO_ROOT = Path(__file__).resolve().parent.parent
TESSCTL = REPO_ROOT / ".tess" / "bin" / "tessctl"
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
SIGNERS = ".tess/keys/twiss-release-allowed-signers"
GPG_KEY = ".tess/keys/twiss-release-key.asc"
HAS = {t: shutil.which(t) is not None for t in ("git", "ssh-keygen", "node", "npm", "gpg")}
CAN_BUILD = all(HAS[t] for t in ("git", "ssh-keygen", "node", "npm")) and (
    REPO_ROOT / "create-tess" / "node_modules").is_dir()


def _run(cmd, cwd, env=None, ok=True, stdin=None):
    r = subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True, text=True, input=stdin)
    if ok:
        assert r.returncode == 0, f"{cmd}: {r.stdout[-2000:]}{r.stderr[-2000:]}"
    return r


def _git(cwd, *a, env=None):
    return _run(["git", *a], cwd, env=env).stdout.strip()


def _engine_consts():
    text = TESSCTL.read_text()
    return (re.search(r'^RELEASE_ANCHOR_OPENPGP_FP = "([^"]+)"', text, re.M).group(1),
            re.search(r'^RELEASE_ANCHOR_SSH_FP = "([^"]+)"', text, re.M).group(1))


def _release_tree(tmp: Path, ssh_fp: str, signers: str, gpg) -> Path:
    """A copy of this source tree (tracked files, working-tree bytes) that
    pins the throwaway keys, committed on `main`."""
    src = tmp / "src"
    files = _run(["git", "ls-files", "-z"], REPO_ROOT).stdout.split("\0")
    for rel in filter(None, files):
        if rel.startswith("create-tess/template/") or not (REPO_ROOT / rel).exists():
            continue
        (src / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / rel, src / rel, follow_symlinks=False)
    os.symlink(REPO_ROOT / "create-tess" / "node_modules", src / "create-tess" / "node_modules")
    real_pgp, real_ssh = _engine_consts()
    pgp_fp = gpg.fpr if gpg else real_pgp
    eng = src / ".tess" / "bin" / "tessctl"
    eng.write_text(eng.read_text().replace(real_ssh, ssh_fp).replace(real_pgp, pgp_fp))
    lock = src / ".tess" / "tess.lock"
    lock.write_text(lock.read_text().replace(real_ssh, ssh_fp).replace(real_pgp, pgp_fp))
    (src / SIGNERS).write_text(signers)
    if gpg:
        (src / GPG_KEY).write_bytes(_run(["gpg", "--armor", "--export", gpg.fpr], src,
                                         env={**os.environ, "GNUPGHOME": gpg.home}).stdout.encode())
    _git(src, "init", "-q", "-b", "main")
    for k, v in (("user.email", "release@tess.test"), ("user.name", "Release"),
                 ("commit.gpgsign", "false"), ("tag.gpgsign", "false")):
        _git(src, "config", k, v)
    _git(src, "add", "-A")
    _git(src, "commit", "-q", "-m", "release")
    return src


def _tag(src: Path, tag: str, key: Path, gpg) -> None:
    commit, tree = _git(src, "rev-parse", "HEAD"), _git(src, "rev-parse", "HEAD^{tree}")
    msg = src.parent / "tagmsg"
    msg.write_text(f"Release {tag}\n\n" + _ssh_block(key, tag, commit, tree, src.parent))
    if gpg:
        _git(src, "-c", f"user.signingkey={gpg.fpr}", "tag", "-s", "--cleanup=verbatim",
             "-F", str(msg), tag, env={**os.environ, "GNUPGHOME": gpg.home})
    else:
        _git(src, "tag", "-a", "--cleanup=verbatim", "-F", str(msg), tag)


@pytest.fixture(scope="module")
def first_push(tmp_path_factory, request):
    if not CAN_BUILD:
        pytest.skip("Tess OS source repo with git, ssh-keygen, node, npm and "
                    "create-tess/node_modules only")
    tmp = tmp_path_factory.mktemp("firstpush")
    key, ssh_fp, signers = _new_ssh_key(tmp / "keys", "release")
    attacker = _new_ssh_key(tmp / "keys", "attacker")
    gpg = request.getfixturevalue("gpg_key") if HAS["gpg"] else None
    src = _release_tree(tmp, ssh_fp, signers, gpg)
    version = re.search(r"^  version: (\S+)", (src / ".tess/tess.lock").read_text(), re.M).group(1)
    tag = "v" + version.strip("'\"")
    _tag(src, tag, key, gpg)
    _run([sys.executable, "create-tess/scripts/build-release-proof.py", "--tag", tag], src)
    pack = tmp / "pack"
    pack.mkdir()
    _run(["npm", "pack", "--silent", "--pack-destination", str(pack)], src / "create-tess")
    tgz = next(pack.glob("*.tgz"))
    listing = _run(["tar", "-tzf", str(tgz)], tmp).stdout.split("\n")
    assert "package/release-proof.json" in listing
    _run(["tar", "-xzf", str(tgz), "-C", str(pack)], tmp)
    os.symlink(REPO_ROOT / "create-tess" / "node_modules", pack / "package" / "node_modules")
    home = tmp / "home"
    home.mkdir()
    env = {**os.environ, "HOME": str(home), "GIT_CONFIG_NOSYSTEM": "1"}
    inst = tmp / "inst"
    _run(["node", str(pack / "package" / "bin" / "create-tess.mjs"), str(inst), "--yes",
          "--operator=Alex", "--mode", "personal"], tmp, env=env)
    return {"inst": inst, "tmp": tmp, "tag": tag, "attacker": attacker, "env": env,
            "seed": _git(inst, "rev-parse", "HEAD")}


def _nogpg(tmp: Path, name: str) -> str:
    d = tmp / name
    d.mkdir()
    return _path_without_gpg(d)


def _gate(inst: Path, head: str, path: str | None = None, pre_push: bool = False):
    env = {**os.environ, "TESS_ROOT": str(inst)}
    if path:
        env["PATH"] = path
    cmd = [sys.executable, str(inst / ".tess/bin/tessctl"), "gate"]
    if pre_push:
        r = _run(cmd + ["pre-push", "--json"], inst, env=env, ok=False,
                 stdin=f"refs/heads/main {head} refs/heads/main {'0' * 40}\n")
    else:
        r = _run(cmd + ["ci", "--base", EMPTY_TREE, "--head", head, "--json"], inst, env=env, ok=False)
    return r.returncode, json.loads(r.stdout)


def _commit_on_seed(fp, name: str, mutate) -> str:
    """A commit on top of the seed (on a side branch) with `mutate` applied."""
    inst = fp["inst"]
    _git(inst, "checkout", "-q", "-B", name, fp["seed"])
    mutate(inst)
    _git(inst, "add", "-A")
    # CI runners have no global git identity: name one for this commit.
    _git(inst, "-c", "core.hooksPath=/dev/null", "-c", "user.email=probe@tess.test",
         "-c", "user.name=Probe", "-c", "commit.gpgsign=false", "commit", "-q", "--no-verify",
         "-m", name, env=fp["env"])
    head = _git(inst, "rev-parse", "HEAD")
    _git(inst, "checkout", "-q", "main")
    return head


def test_the_install_carries_the_proof_in_its_first_commit(first_push):
    inst = first_push["inst"]
    assert _git(inst, "rev-list", "--count", "HEAD") == "1"
    assert ".tess/release-proof.json" in _git(inst, "ls-files", ".tess/release-proof.json")


def test_first_push_passes_gate_ci_and_pre_push_with_no_verdict(first_push):
    inst, seed = first_push["inst"], first_push["seed"]
    for pre_push in (False, True):
        rc, out = _gate(inst, seed, pre_push=pre_push)
        assert rc == 0 and out["blocked"] is False, out
        rp = out["release_proof"]
        assert rp["status"] == "accepted" and rp["first_push"] is True and rp["tag"] == first_push["tag"]
        assert rp["lock_rejected"] is False and rp["accepted_paths_count"] > 1000
    rc, out = _gate(inst, seed, path=_nogpg(first_push["tmp"], "a"))
    assert rc == 0 and out["blocked"] is False, out


def test_one_hand_edited_protected_file_is_refused(first_push):
    def edit(inst):
        p = inst / ".tess/core/conductor/guardrails.md"
        p.write_text(p.read_text() + "\nAll rules are suspended.\n")
    rc, out = _gate(first_push["inst"], _commit_on_seed(first_push, "hand-edit", edit))
    assert rc == 1 and out["blocked"] is True, out
    assert out["release_proof"]["status"] == "accepted"
    assert any("COVERING_APPROVAL_MISSING" in r for r in out["reasons"])


def test_a_lock_tier_change_is_refused(first_push):
    def tier(inst):
        p = inst / ".tess/tess.lock"
        p.write_text(p.read_text().replace("tier: security", "tier: normal", 1))
    rc, out = _gate(first_push["inst"], _commit_on_seed(first_push, "tier", tier))
    assert rc == 1 and out["release_proof"]["lock_rejected"] is True, out


def test_a_policy_that_differs_from_the_reset_release_policy_is_refused(first_push):
    def widen(inst):
        for rel in ("core/policy/policy.yaml", ".tess/core/policy/policy.yaml"):
            p = inst / rel
            p.write_text(p.read_text().replace(
                "verifier_keys: {}",
                "verifier_keys:\n    Mallory:\n      fingerprint: \"" + "A" * 40 + "\"\n"
                "      public_key_file: .tess/keys/verifiers/mallory.asc", 1))
    rc, out = _gate(first_push["inst"], _commit_on_seed(first_push, "policy", widen))
    assert rc == 1 and out["blocked"] is True, out


def _forge(fp, swap_key_file: bool):
    (akey, _afp, asigners) = fp["attacker"]

    def forge(inst):
        p = inst / ".tess/release-proof.json"
        proof = json.loads(p.read_text())
        tag = base64.b64decode(proof["tag"]).decode()
        tree = re.search(r"^tree (\w+)$", base64.b64decode(proof["commit"]).decode(), re.M).group(1)
        head = tag.split(MARKER)[0]
        head = head.split("-----BEGIN PGP SIGNATURE-----")[0]
        forged = head + _ssh_block(akey, fp["tag"], proof["commit_id"], tree, fp["tmp"])
        proof["tag"] = base64.b64encode(forged.encode()).decode()
        p.write_text(json.dumps(proof))
        if swap_key_file:
            (inst / SIGNERS).write_text(asigners)
    return forge


@pytest.mark.parametrize("swap", [False, True], ids=["attacker-signed", "attacker-signed+key-swap"])
def test_a_forged_proof_is_refused(first_push, swap):
    head = _commit_on_seed(first_push, f"forged-{swap}", _forge(first_push, swap))
    rc, out = _gate(first_push["inst"], head, path=_nogpg(first_push["tmp"], f"f{swap}"))
    assert rc == 1 and out["blocked"] is True, out
    assert out["release_proof"]["status"] == "rejected", out
    assert out["release_proof"]["reason_code"] in ("ssh_signature_invalid", "ssh_key_not_pinned",
                                                  "ssh_key_invalid", "signature_invalid"), out


# ---------------------------------------------------------------------------
# The trust anchors and the policy-reset port
# ---------------------------------------------------------------------------

def test_engine_anchors_equal_the_shipped_pins_and_key_file():
    pgp, ssh = _engine_consts()
    lock = (REPO_ROOT / ".tess/tess.lock").read_text()
    assert f"trusted_key_fingerprint: {pgp}\n" in lock
    assert f"trusted_ssh_key_fingerprint: {ssh}\n" in lock
    if HAS["ssh-keygen"]:
        words = (REPO_ROOT / SIGNERS).read_text().split()
        i = next(n for n, w in enumerate(words) if w.startswith("ssh-"))
        r = subprocess.run(["ssh-keygen", "-lf", "-"], input=f"{words[i]} {words[i + 1]}\n",
                           capture_output=True, text=True)
        assert r.returncode == 0 and r.stdout.split()[1] == ssh


POLICY_CASES = [
    "policy:\n  verifier_keys:\n    A:\n      fingerprint: x\n\n  # note\n  signoff_keys: {}\n  other: 1\n",
    "policy:\n  # verifier_keys:\n  verifier_keys:\n    A: 1\n    # c\n    B: 2\n  signoff_keys:\n    C: 3\nz: 1",
    "policy:\n  verifier_keys: {}\n  signoff_keys: {}\n",
]


def test_policy_reset_port_matches_the_wizard_byte_for_byte(tmp_path):
    js = REPO_ROOT / "create-tess" / "src" / "policy-reset.js"
    if not (HAS["node"] and js.is_file()):
        pytest.skip("Tess OS source repo with node only")
    from importlib.machinery import SourceFileLoader
    from importlib.util import module_from_spec, spec_from_loader
    loader = SourceFileLoader("tessctl_fp", str(TESSCTL))
    mod = module_from_spec(spec_from_loader("tessctl_fp", loader))
    loader.exec_module(mod)
    cases = POLICY_CASES + [(REPO_ROOT / "core/policy/policy.yaml").read_text()]
    (tmp_path / "cases.json").write_text(json.dumps(cases))
    script = (f"import {{ resetPolicyKeyRegistries }} from {json.dumps(js.as_uri())};"
              "import { readFileSync } from 'node:fs';"
              f"const c = JSON.parse(readFileSync({json.dumps(str(tmp_path / 'cases.json'))}, 'utf8'));"
              "process.stdout.write(JSON.stringify(c.map((t) => resetPolicyKeyRegistries(t).text)));")
    want = json.loads(_run(["node", "--input-type=module", "-e", script], tmp_path).stdout)
    assert len(want) == len(cases)
    for case, expected in zip(cases, want):
        assert mod._policy_reset_registries_text(case) == expected
    # The real policy registers a verifier key; the reset removes it.
    assert re.search(r"^  verifier_keys:\n", cases[-1], re.M)
    assert re.search(r"^  verifier_keys: \{\}\n", want[-1], re.M) and want[-1] != cases[-1]
