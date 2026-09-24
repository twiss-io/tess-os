"""Redaction (spec 10.3). Every planted secret is BUILT at run time: no
secret-shaped literal is committed, so the CI gitleaks job stays green."""
import sys
from pathlib import Path

import pytest

from fixtures.brain_learn import fxlib

sys.path.insert(0, str(Path(fxlib.REPO) / "scripts" / "brain"))
from brainlib import redact  # noqa: E402


def _planted():
    q = "Q" * 36
    return {
        "github": "ghp_" + q,
        "anthropic": "sk-" + "ant-" + "api03-" + "x" * 30,
        "openai": "sk-" + "proj-" + "y" * 30,
        "aws": "AKIA" + "Z" * 16,
        "google": "AIza" + "B" * 35,
        "slack": "xox" + "b-" + "1" * 12 + "-abcdefghij",
        "stripe": "sk_" + "live_" + "c" * 24,
        "jwt": "eyJ" + "h" * 12 + ".eyJ" + "p" * 12 + ".sig",
        "telegram-bot": "123456789:" + "A" * 35,
        "nric": "S" + "1234567" + "D",
    }


@pytest.mark.parametrize("kind", sorted(_planted()))
def test_each_token_kind_is_redacted(kind):
    secret = _planted()[kind]
    out, counts = redact.redact("before %s after" % secret)
    assert secret not in out
    assert "<REDACTED:%s>" % kind in out
    assert counts.get(kind) == 1
    assert out.startswith("before ") and out.endswith(" after")


def test_private_key_block():
    block = "-----BEGIN " + "RSA PRIVATE KEY-----\nMIIabc\n-----END " + "RSA PRIVATE KEY-----"
    out, counts = redact.redact("key:\n%s\ndone" % block)
    assert "MIIabc" not in out and counts["private-key"] == 1


def test_credential_key_value_keeps_the_key():
    out, _ = redact.redact("the password: hunter2 and api_key=abc123def")
    assert out == "the password: <REDACTED:credential> and api_key=<REDACTED:credential>"


def test_already_redacted_is_not_redacted_twice():
    out, counts = redact.redact("token: " + _planted()["github"])
    assert out == "token: <REDACTED:github>"
    assert counts == {"github": 1}


def test_luhn_cards_only():
    assert redact.luhn_ok("4111 1111 1111 1111")
    assert not redact.luhn_ok("4111 1111 1111 1112")
    out, _ = redact.redact("card 4111 1111 1111 1111, order 4111 1111 1111 1112")
    assert "<REDACTED:card>" in out and "4111 1111 1111 1112" in out


def test_labelled_bank_account():
    out, counts = redact.redact("IBAN: GB33BUKB20201555555555")
    assert "20201555555555" not in out and counts.get("bank") == 1
    out, counts = redact.redact("account number is pending")
    assert counts == {}


def test_plain_prose_untouched():
    text = "Decision: let's go with Postgres for the ledger. The task-list is done by Friday."
    assert redact.redact(text) == (text, {})
    assert redact.scan(text) == []
