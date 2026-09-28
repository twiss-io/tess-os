"""Redaction before ANY write (journal, turns.jsonl, candidates, records).

Every match is replaced with `<REDACTED:type>`. Order matters: specific
token shapes first, then the generic `key: value` credential rule, which
skips values that are already redacted. Card numbers are replaced only when
they pass the Luhn check. The list mirrors docs/brain/LEARNING.md.
"""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

MARK = "<REDACTED:%s>"

_PATTERNS: List[Tuple[str, "re.Pattern[str]"]] = [
    ("private-key", re.compile(
        r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)", re.S)),
    ("aws", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{22,})")),
    ("anthropic", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{10,}")),
    ("openai", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}")),
    ("google", re.compile(r"\bAIza[0-9A-Za-z_-]{35}")),
    ("slack", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("stripe", re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{16,}")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*")),
    ("bot-token", re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b")),
    ("nric", re.compile(r"(?i)\b[STFGM]\d{7}[A-Z]\b")),
    ("slack-webhook", re.compile(r"(?i)https?://hooks\.slack\.com/(?:services|workflows|triggers)/[A-Za-z0-9/_-]+")),
    ("npm", re.compile(r"\bnpm_[A-Za-z0-9]{36}\b")),
    ("sendgrid", re.compile(r"\bSG\.[A-Za-z0-9_-]{16,32}\.[A-Za-z0-9_-]{16,64}")),
    ("twilio", re.compile(r"\bSK[0-9a-fA-F]{32}\b")),
    ("huggingface", re.compile(r"\bhf_[A-Za-z0-9]{30,}")),
    ("uri-userinfo", re.compile(r"(?i)(?<=://)[^\s:@/<>]+:[^\s@/<>]+(?=@)")),
    ("bearer", re.compile(r"(?i)(?<=\bBearer\s)(?!<REDACTED:)[A-Za-z0-9._~+/=-]{16,}")),
]
# Env/config style credentials: DB_PASSWORD=..., GITHUB_TOKEN=..., client_secret: ...,
# aws_secret_access_key = ... (the key may be underscore- or dash-joined, any case).
# The value must be 6+ characters and not start with markup, so prose such as
# "**On the token:** I'm ..." is left alone.
_CREDENTIAL = re.compile(
    r"(?i)(?<![A-Za-z0-9])([A-Za-z0-9_.-]*?(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|"
    r"private[_-]?key|account[_-]?key|shared[_-]?access[_-]?key)"
    r"[A-Za-z0-9_]*)([\"']?\s*[:=]\s*)(?!<REDACTED:)(\"[^\"\n]{6,}\"|'[^'\n]{6,}'|[^\s<*_`\"'][^\s<]{5,})")
# Natural language: "my password is hunter22", "the aws secret is <40 chars>". The value must look
# like a secret (a digit or symbol, or 16+ characters), so "the token is expired" is left alone.
_SAID = re.compile(
    r"(?i)\b((?:password|passwd|passcode|pin|secret(?: access)?(?: key)?|token|api key|access key|private key)"
    r"\s+(?:is|was|=|:)\s+)(?!<REDACTED:)([\"']?)([^\s\"'<]{6,})\2")
_CARD = re.compile(r"(?<![\d-])(?:\d[ -]?){12,18}\d(?![\d-])")
_BANK = re.compile(
    r"(?i)\b(iban|bank account(?: (?:no|number))?|account (?:no|number)|acct(?: no)?)\b"
    r"([\s.:#]*)([A-Z0-9][A-Z0-9 -]{6,32}[A-Z0-9])")


def luhn_ok(digits: str) -> bool:
    nums = [int(c) for c in digits if c.isdigit()]
    if not 13 <= len(nums) <= 19:
        return False
    total = 0
    for i, n in enumerate(reversed(nums)):
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def _sub_counted(pattern, kind: str, text: str, counts: Dict[str, int]) -> str:
    def repl(_m):
        counts[kind] = counts.get(kind, 0) + 1
        return MARK % kind
    return pattern.sub(repl, text)


def redact(text: str) -> Tuple[str, Dict[str, int]]:
    """Return (redacted text, {type: count})."""
    counts: Dict[str, int] = {}
    if not text:
        return text or "", counts
    for kind, pattern in _PATTERNS:
        text = _sub_counted(pattern, kind, text, counts)

    def cred(m):
        counts["credential"] = counts.get("credential", 0) + 1
        return m.group(1) + m.group(2) + MARK % "credential"
    text = _CREDENTIAL.sub(cred, text)

    def said(m):
        value = m.group(3).rstrip(".,;!?")
        if not (re.search(r"[\d\W_]", value) or len(value) >= 16):
            return m.group(0)
        counts["credential"] = counts.get("credential", 0) + 1
        return m.group(1) + MARK % "credential" + m.group(3)[len(value):]
    text = _SAID.sub(said, text)

    def card(m):
        if luhn_ok(m.group(0)):
            counts["card"] = counts.get("card", 0) + 1
            return MARK % "card"
        return m.group(0)
    text = _CARD.sub(card, text)

    def bank(m):
        value = m.group(3)
        if sum(c.isdigit() for c in value) < 6:
            return m.group(0)
        counts["bank"] = counts.get("bank", 0) + 1
        return m.group(1) + m.group(2) + MARK % "bank"
    text = _BANK.sub(bank, text)
    return text, counts


def scan(text: str) -> List[str]:
    """Types of secret-shaped content still present (empty list == clean)."""
    _, counts = redact(text or "")
    return sorted(counts)


def total(counts: Dict[str, int]) -> int:
    return sum(counts.values())
