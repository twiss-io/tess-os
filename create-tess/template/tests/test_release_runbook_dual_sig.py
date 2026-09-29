"""The release runbook cuts both tags the way the workflows verify them.

v1.0 code review (MEDIUM): conductor/release-process.md told the maintainer to
`git tag -s` the framework tag (OpenPGP only, so release.yml's SSH gate 1d
refuses it) and to cut `create-tess-v*` as an UNSIGNED lightweight tag
(publish-npm.yml refuses it). verify_release_ssh_sig.sh pointed at a signing
helper that tess-os did not ship.
"""
import os
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HELPER = REPO / "scripts" / "release" / "sign-release-tag.sh"
RUNBOOKS = [REPO / "conductor" / "release-process.md", REPO / ".tess" / "core" / "conductor" / "release-process.md"]


def test_both_runbook_copies_sign_both_tags_with_the_helper_on_the_same_commit():
    a, b = (p.read_text() for p in RUNBOOKS)
    assert a == b
    assert 'scripts/release/sign-release-tag.sh v<new-semver> "$M"' in a
    assert 'scripts/release/sign-release-tag.sh create-tess-v<new-semver> "$M"' in a
    assert "verify_release_ssh_sig.sh" in a
    assert not re.search(r"^\s*git\b.*\btag -s\b", a, re.M), "git tag -s makes no SSH signature"
    assert not re.search(r"^\s*git tag create-tess-v", a, re.M), "an unsigned npm tag is refused"
    assert "first v0.2.1 item" not in a


def test_the_helper_ships_in_tess_os_as_a_maintainer_tool_and_not_in_installs():
    assert HELPER.is_file() and os.access(HELPER, os.X_OK)
    text = HELPER.read_text()
    assert "PRIVATE KEY" not in text and "BEGIN PGP" not in text.replace("-----BEGIN PGP SIGNATURE-----", "")
    assert "tess-secrets" not in text, "the tess-os copy must not default to a key path inside a repo"
    ignore = (REPO / "create-tess" / "src" / "ignore.js").read_text()
    assert "'scripts/release/sign-release-tag.sh'," in ignore
    assert not (REPO / "create-tess" / "template" / "scripts" / "release" / "sign-release-tag.sh").exists()
    assert "scripts/release/sign-release-tag.sh" in (REPO / ".github/scripts/verify_release_ssh_sig.sh").read_text()


def test_the_helper_refuses_without_a_named_key_before_touching_anything(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "TESS_RELEASE_SSH_KEY"}
    r = subprocess.run(["bash", str(HELPER), "--repo", str(tmp_path), "v9.9.9"], capture_output=True,
                       text=True, env=env)
    assert r.returncode != 0
    # Either the key check or an earlier trusted-tool check (non-macOS) refuses; never a tag.
    assert "sign-release-tag:" in r.stderr
