"""Text helpers shared by the cue pass, the verifier and the indexes."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import List

_SMART = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"',
}
_WS = re.compile(r"\s+")
_SENT = re.compile(r"(?<=[.!?])\s+(?=\S)")


def normalize(text: str) -> str:
    """The only normalisation V1 allows: NFKC, smart quotes, whitespace."""
    s = unicodedata.normalize("NFKC", text or "")
    for k, v in _SMART.items():
        s = s.replace(k, v)
    return _WS.sub(" ", s).strip()


def contains(haystack: str, needle: str) -> bool:
    n = normalize(needle)
    return bool(n) and n in normalize(haystack)


def sentences(text: str) -> List[str]:
    """Split a message into sentences (line breaks also end a sentence)."""
    out: List[str] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        out.extend(p.strip() for p in _SENT.split(line) if p.strip())
    return out


def slugify(text: str, words: int = 6, limit: int = 48) -> str:
    s = unicodedata.normalize("NFKD", normalize(text)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "-", s.lower().replace("'", "")).strip("-")
    parts = [p for p in s.split("-") if p][:words]
    return ("-".join(parts)[:limit].strip("-")) or "item"


def sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def statement_hash(text: str) -> str:
    s = normalize(text).lower().rstrip(".!")
    return sha256_text(re.sub(r"[^a-z0-9 ]+", "", s))[:16]


def clip(text: str, limit: int) -> str:
    t = normalize(text)
    return t if len(t) <= limit else t[: max(0, limit - 1)].rstrip() + "…"


def glob_match(pattern: str, path: str) -> bool:
    """Anchored glob: `**` any depth, `*` one segment, `dir/**` also matches dir."""
    pattern = pattern.strip().strip("/")
    path = path.strip().strip("/")
    if pattern in ("**", "*" if "/" not in path else "\0"):
        return True
    if pattern.endswith("/**") and path == pattern[:-3]:
        return True
    rx, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            rx += "(?:.*/)?"
            i += 3
        elif pattern.startswith("**", i):
            rx += ".*"
            i += 2
        elif pattern[i] == "*":
            rx += "[^/]*"
            i += 1
        elif pattern[i] == "?":
            rx += "[^/]"
            i += 1
        else:
            rx += re.escape(pattern[i])
            i += 1
    return re.fullmatch(rx, path) is not None
