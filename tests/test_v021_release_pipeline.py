"""v0.2.1 release pipeline: publish only from a signed tag, fail on version drift.

publish-npm.yml: create-tess-v* tags only (no workflow_dispatch), the tag must be
signed by the pinned release key, the job runs in the `npm-publish` environment,
npm is pinned to the same version a CI leg tests with. release.yml: tag, both
package.json files, tess.lock and CHANGELOG must agree (fail, not warn), and it
runs npm test, tessctl doctor/verify and the packed-tarball e2e. Every
third-party action is pinned to a commit SHA.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
WF = ROOT / ".github" / "workflows"
SCRIPTS = ROOT / ".github" / "scripts"
PINNED = "EBEABC618C11B6A7340A7D1601DD637667B8CC89"


def load(name: str) -> dict:
    return yaml.safe_load((WF / name).read_text(encoding="utf-8"))


def triggers(wf: dict) -> dict:
    return wf.get("on", wf.get(True))  # PyYAML reads a bare `on:` key as True


def steps_text(wf: dict) -> str:
    return "\n".join(str(s.get("run", "")) for job in wf["jobs"].values() for s in job.get("steps", []))


def test_publish_triggers_only_on_create_tess_tags():
    on = triggers(load("publish-npm.yml"))
    assert set(on) == {"push"}, "no workflow_dispatch or any other trigger may publish"
    assert on["push"] == {"tags": ["create-tess-v*"]}


def test_publish_runs_in_the_npm_publish_environment_with_a_verified_tag():
    wf = load("publish-npm.yml")
    job = wf["jobs"]["publish"]
    assert job["environment"] == "npm-publish"
    assert job["permissions"] == {"contents": "read", "id-token": "write"}
    names = [s.get("name", "") for s in job["steps"]]
    verify = names.index("Verify the tag is signed by the pinned release key")
    assert verify < names.index("npm publish (Trusted Publishing / OIDC)")
    assert ".github/scripts/verify_release_tag.sh \"$TAG\"" in job["steps"][verify]["run"]


def test_publish_npm_is_pinned_and_the_same_npm_is_tested_in_ci():
    text = (WF / "publish-npm.yml").read_text(encoding="utf-8")
    assert "npm@latest" not in text
    version = load("publish-npm.yml")["env"]["NPM_VERSION"]
    assert re.fullmatch(r"\d+\.\d+\.\d+", version)
    include = load("ci.yml")["jobs"]["create-tess"]["strategy"]["matrix"]["include"]
    assert {"node-version": "24", "npm-version": version} in include


def test_every_third_party_action_is_pinned_by_sha():
    for name in ("ci.yml", "release.yml", "publish-npm.yml"):
        for line in (WF / name).read_text(encoding="utf-8").splitlines():
            if "uses:" in line:
                assert re.search(r"uses: [\w.-]+/[\w.-]+@[0-9a-f]{40} # v\d+\.\d+\.\d+$", line), (name, line)


def test_release_gates_versions_and_runs_every_install_check():
    wf = load("release.yml")
    assert wf["jobs"]["release"]["permissions"] == {"contents": "write"}
    run = steps_text(wf)
    for needle in ("release_version_gate.py \"$TAG\"", "verify_release_tag.sh \"$TAG\"",
                   ".tess/bin/tessctl doctor", ".tess/bin/tessctl verify", "npm test",
                   "TESS_BRAIN_E2E=1", "TESS_E2E_TARBALL"):
        assert needle in run, needle
    assert "::warning::no CHANGELOG" not in run and "::error::no CHANGELOG section" in run


def test_ci_has_a_stock_macos_leg_and_a_tarball_e2e():
    jobs = load("ci.yml")["jobs"]
    mac = jobs["macos"]
    assert mac["runs-on"] == "macos-latest"
    assert mac["strategy"]["matrix"]["python-version"] == ["3.9", "3.12"]
    mac_run = "\n".join(str(s.get("run", "")) + str(s.get("env", "")) for s in mac["steps"])
    assert "/usr/bin/python3" in mac_run and "python -m pytest" in mac_run and "npm test" in mac_run
    assert "TESS_E2E_TARBALL" in mac_run
    assert "TESS_BRAIN_E2E=1" in "\n".join(str(s.get("run", "")) for s in jobs["fresh-install-e2e"]["steps"])


def test_pinned_fingerprint_matches_tess_lock():
    lock = yaml.safe_load((ROOT / ".tess" / "tess.lock").read_text(encoding="utf-8"))
    assert lock["framework"]["trusted_key_fingerprint"] == PINNED
    assert 'PINNED_FPR="%s"' % PINNED in (SCRIPTS / "verify_release_tag.sh").read_text(encoding="utf-8")


def _gate(tag: str, root: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPTS / "release_version_gate.py"), tag, "--root", str(root)],
                          capture_output=True, text=True)


def _fixture(tmp: Path, root_v="1.2.3", ct_v="1.2.3", lock_v="1.2.3", changelog="## [1.2.3] - 2026-09-29\n") -> Path:
    (tmp / "create-tess").mkdir(parents=True)
    (tmp / ".tess").mkdir()
    (tmp / "package.json").write_text(json.dumps({"version": root_v}))
    (tmp / "create-tess" / "package.json").write_text(json.dumps({"version": ct_v}))
    (tmp / ".tess" / "tess.lock").write_text("schema: 1\nframework:\n  track: v2\n  version: %s\nfiles: {}\n" % lock_v)
    (tmp / "CHANGELOG.md").write_text("# Changelog\n\n" + changelog)
    return tmp


def test_version_gate_passes_only_when_everything_agrees(tmp_path):
    assert _gate("v1.2.3", _fixture(tmp_path / "ok")).returncode == 0
    for name, kw in [("root", {"root_v": "1.2.2"}), ("ct", {"ct_v": "1.2.4"}), ("lock", {"lock_v": "1.2.2"}),
                     ("log", {"changelog": "## [1.2.2]\n"})]:
        done = _gate("v1.2.3", _fixture(tmp_path / name, **kw))
        assert done.returncode == 1 and "::error::version gate:" in done.stdout, (name, done.stdout)
    assert _gate("release-1.2.3", _fixture(tmp_path / "badtag")).returncode == 1


def test_version_gate_accepts_this_repo_at_its_own_version():
    version = json.loads((ROOT / "package.json").read_text())["version"]
    done = _gate("v" + version, ROOT)
    assert done.returncode == 0, done.stdout


needs_gpg = pytest.mark.skipif(shutil.which("gpg") is None, reason="gpg not installed")


def _tag_repo(tmp: Path) -> tuple:
    """A repo with a tag signed by a throwaway key; returns (repo, env, exported public key)."""
    # gpg-agent's socket path must stay short (macOS limit ~104 bytes), so not under tmp_path.
    home = Path(tempfile.mkdtemp(prefix="tessgpg", dir="/tmp"))
    env = dict(os.environ, GNUPGHOME=str(home), GIT_CONFIG_NOSYSTEM="1", HOME=str(tmp),
               GIT_AUTHOR_NAME="T", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="T", GIT_COMMITTER_EMAIL="t@example.invalid")
    subprocess.run(["gpg", "--batch", "--pinentry-mode", "loopback", "--passphrase", "", "--quick-gen-key",
                    "Throwaway <t@example.invalid>", "ed25519", "sign", "never"],
                   env=env, check=True, capture_output=True)
    fpr = [ln.split(":")[9] for ln in subprocess.run(["gpg", "--with-colons", "--fingerprint"], env=env,
           capture_output=True, text=True).stdout.splitlines() if ln.startswith("fpr")][0]
    pub = tmp / "throwaway.asc"
    pub.write_text(subprocess.run(["gpg", "--armor", "--export", fpr], env=env, capture_output=True,
                                  text=True, check=True).stdout)
    repo = tmp / "repo"
    repo.mkdir()
    for args in (["init", "-q"], ["commit", "-q", "--allow-empty", "-m", "x"],
                 ["-c", "user.signingkey=" + fpr, "tag", "-s", "-m", "signed", "v9.9.9"],
                 ["tag", "-a", "-m", "unsigned", "v9.9.8"], ["tag", "v9.9.7"]):
        subprocess.run(["git", "-C", str(repo)] + args, env=env, check=True, capture_output=True)
    subprocess.run(["gpgconf", "--kill", "gpg-agent"], env=env, capture_output=True)
    shutil.rmtree(str(home), ignore_errors=True)  # signing is done; verification uses its own GNUPGHOME
    return repo, env, pub


@needs_gpg
def test_verify_release_tag_refuses_any_other_signer(tmp_path):
    repo, env, pub = _tag_repo(tmp_path)
    script = str(SCRIPTS / "verify_release_tag.sh")
    key = str(ROOT / ".tess" / "keys" / "twiss-release-key.asc")

    def verify(tag, key_file):
        return subprocess.run([script, tag], cwd=str(repo), capture_output=True, text=True,
                              env=dict(env, RELEASE_KEY_FILE=key_file))
    for tag in ("v9.9.9", "v9.9.8"):  # signed by another key / not signed at all
        done = verify(tag, key)
        assert done.returncode == 1 and "no valid signature from the release key" in done.stdout, done.stdout
    assert "not an annotated tag" in verify("v9.9.7", key).stdout
    wrong = verify("v9.9.9", str(pub))  # a VALID signature, but not the pinned fingerprint
    assert wrong.returncode == 1 and "not the pinned release key" in wrong.stdout, wrong.stdout


@needs_gpg
def test_verify_release_tag_accepts_the_real_signed_release_tag():
    tag = "v0.2.0"
    kind = subprocess.run(["git", "-C", str(ROOT), "cat-file", "-t", "refs/tags/" + tag], capture_output=True, text=True)
    if kind.stdout.strip() != "tag":
        pytest.skip("annotated %s not fetched in this checkout" % tag)
    done = subprocess.run([str(SCRIPTS / "verify_release_tag.sh"), tag], cwd=str(ROOT), capture_output=True, text=True)
    assert done.returncode == 0 and PINNED in done.stdout, done.stdout + done.stderr
