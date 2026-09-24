"""A credential in a remote URL must never reach brain.json (security review F2).

The token is generated at runtime, so no secret-shaped literal lives in the repo.
"""
from __future__ import annotations

import secrets
import sys

import pytest

import _brain_oobe_helpers as h

sys.path.insert(0, str(h.BRAIN_TOOLS))
from oobe import answers, state  # noqa: E402


def _token() -> str:
    return "tok" + secrets.token_hex(16)


def _cred_urls(tok: str):
    return ["https://user:%s@github.com/o/brain.git" % tok,
            "https://%s@github.com/o/brain.git" % tok,
            "ssh://git:%s@example.invalid/o/brain.git" % tok]


def test_remote_url_with_userinfo_is_refused():
    tok = _token()
    for url in _cred_urls(tok):
        with pytest.raises(state.BrainError) as err:
            answers.parse_value("remote_url", url, {})
        assert "use SSH or a credential helper" in str(err.value)
        assert tok not in str(err.value)


@pytest.mark.parametrize("url", ["git@github.com:o/brain.git", "https://github.com/o/brain.git",
                                 "ssh://example.invalid/o/brain.git", "later"])
def test_plain_and_ssh_remotes_are_allowed(url):
    answers.parse_value("remote_url", url, {})


def test_quote_containing_a_credential_url_is_never_stored():
    tok = _token()
    brain: dict = {}
    with pytest.raises(state.BrainError):
        answers.record(brain, "remote_url", "later", "push to %s" % _cred_urls(tok)[0], runtime="cli")
    assert tok not in repr(brain)


def test_cli_refuses_and_writes_nothing(tmp_path):
    root = h.mini_instance(tmp_path)
    tok = _token()
    done = h.onboard(root, "answer", "--step", "1", "--field", "mode", "--value", "agency",
                     "--quote", "agency, remote is %s" % _cred_urls(tok)[0])
    assert done.returncode != 0
    assert "use SSH or a credential helper" in done.stdout + done.stderr
    assert tok not in done.stdout + done.stderr
    brain_json = root / "brain" / "brain.json"
    assert not brain_json.exists() or tok not in brain_json.read_text()
