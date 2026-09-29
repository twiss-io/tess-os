"""v1.0.1 (2026-09-29 Codex review, MEDIUM): a base-less push (a new
repository's first push) must get a trusted gate engine in CI without ever
running the pushed tree's engine.

v3 of .github/workflows/tess-gate.yml mapped the zero base SHA to the empty
tree and then required an engine AT that base, so every fresh install's first
CI run failed. v4 reads the tag name from the pushed release proof, fetches
that tag from the release repository, checks its OpenPGP and SSH signatures
against fingerprints written into the workflow, and only then runs the
release's engine. These tests EXECUTE the committed workflow step (not a
reimplementation) against a local "release repository" signed with
throwaway keys; only the repository URL and the two pinned fingerprints are
substituted.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from test_v1_ssh_release_sig import _new_ssh_key, _ssh_block

REPO = Path(__file__).resolve().parent.parent
WORKFLOW = REPO / ".github" / "workflows" / "tess-gate.yml"
ENGINE = REPO / ".tess" / "bin" / "tessctl"
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
EXTRACT = "Extract trusted gate engine (base ref only — never the pushed tree)"
REAL_URL = "https://github.com/twiss-io/tess-os.git"
needs_tools = pytest.mark.skipif(not all(shutil.which(t) for t in ("git", "gpg", "ssh-keygen")),
                                 reason="git, gpg and ssh-keygen required")


def _steps() -> dict:
    return {s["name"]: s for s in yaml.safe_load(WORKFLOW.read_text())["jobs"]["ship-gate"]["steps"]}


def _anchors() -> tuple:
    text = ENGINE.read_text()
    return (re.search(r'^RELEASE_ANCHOR_OPENPGP_FP = "([^"]+)"', text, re.M).group(1),
            re.search(r'^RELEASE_ANCHOR_SSH_FP = "([^"]+)"', text, re.M).group(1))


def _git(cwd: Path, *args: str, env=None) -> str:
    r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def _init(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-q", "-b", "main")
    for k, v in (("user.email", "t@tess.test"), ("user.name", "T"), ("commit.gpgsign", "false"),
                 ("tag.gpgsign", "false")):
        _git(path, "config", k, v)
    return path


def test_workflow_file_is_the_engine_template_and_pins_the_engine_anchors():
    text = WORKFLOW.read_text()
    assert text.startswith("# tess-gate-ci v4\n")
    pgp, ssh = _anchors()
    run = _steps()[EXTRACT]["run"]
    assert f'PGP_FP = "{pgp}"' in run and f'SSH_FP = "{ssh}"' in run
    assert f'TESS_RELEASE_REPO="{REAL_URL}"' in run
    boot = run.split("<<'TESS_BOOTSTRAP_PY'", 1)[1].split("\nTESS_BOOTSTRAP_PY\n", 1)[0]
    # The only engine the base-less branch ever reads is the signed tag's.
    assert boot.count(".tess/bin/tessctl") == 1 and 'rel, "cat-file", "blob", commit + ":.tess/bin/tessctl"' in boot
    assert 'python3 -I -B "${{ steps.trusted_engine.outputs.engine_path }}" gate ci' in _steps()[
        "tessctl gate ci (trusted base-ref engine; untrusted pushed tree)"]["run"]


@pytest.fixture(scope="module")
def release(tmp_path_factory, gpg_key):
    """A release repository whose tag v1.0.1 carries an OpenPGP signature
    (throwaway gpg key) and an SSH release signature (throwaway ssh key)."""
    tmp = tmp_path_factory.mktemp("bootstrap")
    key, ssh_fp, signers = _new_ssh_key(tmp / "keys", "release")
    attacker_key, _, attacker_signers = _new_ssh_key(tmp / "keys", "attacker")
    env = {**os.environ, "GNUPGHOME": gpg_key.home}
    up = _init(tmp / "upstream")
    (up / ".tess/bin").mkdir(parents=True)
    (up / ".tess/keys").mkdir(parents=True)
    (up / ".tess/bin/tessctl").write_text("import sys\nprint('TRUSTED RELEASE ENGINE', sys.argv[1:])\n")
    (up / ".tess/keys/twiss-release-key.asc").write_text(
        subprocess.run(["gpg", "--armor", "--export", gpg_key.fpr], capture_output=True, text=True,
                       env=env).stdout)

    def tag(name: str, allowed: str, ssh_key: Path, pgp: bool = True) -> None:
        (up / ".tess/keys/twiss-release-allowed-signers").write_text(allowed)
        _git(up, "add", "-A")
        _git(up, "commit", "-q", "--allow-empty", "-m", name)
        commit, tree = _git(up, "rev-parse", "HEAD"), _git(up, "rev-parse", "HEAD^{tree}")
        msg = tmp / f"msg-{name}"
        msg.write_text(f"Release {name}\n\n" + _ssh_block(ssh_key, name, commit, tree, tmp))
        sign = ["-c", f"user.signingkey={gpg_key.fpr}", "tag", "-s"] if pgp else ["tag", "-a"]
        _git(up, *sign, "--cleanup=verbatim", "-F", str(msg), name, env=env)

    tag("v1.0.1", signers, key)
    tag("v1.0.2", attacker_signers, attacker_key)       # SSH-signed by a key that is not pinned
    tag("v1.0.3", signers, key, pgp=False)              # no OpenPGP signature
    tag("v0.9.0", signers, key)                         # older than the workflow accepts
    return {"tmp": tmp, "up": up, "pgp": gpg_key.fpr, "ssh": ssh_fp}


def _candidate(release: dict, name: str, tag_name) -> tuple:
    """A fresh repository whose ONE commit carries a release proof naming
    `tag_name` (None: no proof) and a hostile engine that drops a sentinel."""
    cand = _init(release["tmp"] / f"cand-{name}")
    sentinel = release["tmp"] / f"SENTINEL-{name}"
    (cand / ".tess/bin").mkdir(parents=True)
    (cand / ".tess/bin/tessctl").write_text(f"open({str(sentinel)!r}, 'w').close()\nprint('CANDIDATE ENGINE')\n")
    if tag_name is not None:
        (cand / ".tess/release-proof.json").write_text(json.dumps({"tag_name": tag_name}))
    _git(cand, "add", "-A")
    _git(cand, "commit", "-q", "-m", "seed")
    return cand, sentinel


def _run_first_push(release: dict, cand: Path):
    pgp, ssh = _anchors()
    steps = _steps()
    script = (steps[EXTRACT]["run"].replace("${{ steps.refs.outputs.base }}", EMPTY_TREE)
              .replace(REAL_URL, "file://" + str(release["up"]))
              .replace(pgp, release["pgp"]).replace(ssh, release["ssh"]))
    out = cand.parent / f"gh-output-{cand.name}"
    out.write_text("")
    env = {**os.environ, "GITHUB_OUTPUT": str(out), "HEAD_SHA": _git(cand, "rev-parse", "HEAD")}
    r = subprocess.run(["bash", "-c", script], cwd=str(cand), env=env, capture_output=True, text=True)
    if r.returncode != 0:
        return r, None
    engine = dict(ln.split("=", 1) for ln in out.read_text().splitlines())["engine_path"]
    final = (steps["tessctl gate ci (trusted base-ref engine; untrusted pushed tree)"]["run"]
             .replace("${{ steps.trusted_engine.outputs.engine_path }}", engine)
             .replace("${{ steps.refs.outputs.base }}", EMPTY_TREE)
             .replace("${{ steps.refs.outputs.head }}", env["HEAD_SHA"]))
    return r, subprocess.run(["bash", "-c", final], cwd=str(cand), capture_output=True, text=True,
                             env={**os.environ, "TESS_ROOT": str(cand)})


@needs_tools
def test_first_push_runs_the_signed_release_engine_never_the_pushed_one(release):
    cand, sentinel = _candidate(release, "ok", "v1.0.1")
    extract, gate = _run_first_push(release, cand)
    assert extract.returncode == 0, extract.stdout + extract.stderr
    assert "OpenPGP + SSH verified" in extract.stdout
    assert gate.returncode == 0 and "TRUSTED RELEASE ENGINE" in gate.stdout, gate.stdout + gate.stderr
    assert "'gate', 'ci', '--base', '%s'" % EMPTY_TREE in gate.stdout
    assert not sentinel.exists(), "the pushed tree's engine ran"


@needs_tools
@pytest.mark.parametrize("name,tag_name,reason", [
    ("noproof", None, "no .tess/release-proof.json"),
    ("wrongssh", "v1.0.2", "not the pinned Tess OS release key"),
    ("nopgp", "v1.0.3", "no single OpenPGP signature"),
    ("old", "v0.9.0", "older than the oldest release"),
    ("inject", "v1.0.1;touch${IFS}pwned", "not a Tess OS release version"),
    ("missing", "v9.9.9", "git fetch failed"),
])
def test_first_push_fails_closed_without_a_verified_release(release, name, tag_name, reason):
    cand, sentinel = _candidate(release, name, tag_name)
    extract, gate = _run_first_push(release, cand)
    assert extract.returncode != 0 and gate is None
    assert reason in extract.stdout, extract.stdout + extract.stderr
    assert not sentinel.exists() and not (cand / "pwned").exists()
