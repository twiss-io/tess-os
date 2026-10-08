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
        "bot-token": "123456789:" + "A" * 35,
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


def _env_secrets():
    v = "Sup3r" + "S3cret" + "ZZZZValue"
    return {
        "DB_PASSWORD=%s" % v: v,
        "GITHUB_TOKEN=%s" % ("abcdef" + "0123456789abcd"): "abcdef" + "0123456789abcd",
        "client_secret: %s" % ("9f8e7d" + "6c5b4a"): "9f8e7d" + "6c5b4a",
        'MYSQL_ROOT_PASSWORD="%s"' % ("p@ss" + " w0rd!"): "p@ss" + " w0rd!",
        "aws_secret_access_key = %s" % ("wJalr" + "XUtnFEMIabcdef"): "wJalr" + "XUtnFEMIabcdef",
        "postgres://app:%s@db.internal/ledger" % ("pa55" + "word99"): "pa55" + "word99",
        "Authorization: Bearer %s" % ("abcdefgh" + "ijklmnop1234"): "abcdefgh" + "ijklmnop1234",
        "hf token %s" % ("hf_" + "a" * 34): "hf_" + "a" * 34,
    }


@pytest.mark.parametrize("line", sorted(_env_secrets()))
def test_env_and_config_style_credentials_are_redacted(line):
    out, counts = redact.redact(line)
    assert _env_secrets()[line] not in out and "<REDACTED:" in out and counts
    assert redact.scan(line)  # the save/V7 scan sees it too


def test_prose_about_tokens_is_not_mangled():
    for text in ("**On the token:** I'm checking it now.", "the token is short", "secret sauce: none"):
        assert redact.redact(text) == (text, {})
