"""Slugs and small text helpers shared by the onboarding modules."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any

_NON_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(name: str, max_len: int = 48) -> str:
    """ASCII kebab-case slug: 'Acme Pte. Ltd.' -> 'acme-pte-ltd'.

    Letters with no ASCII form (Chinese, Japanese, Cyrillic, Arabic, ...) are
    not silently dropped: the slug then ends in 8 hex digits of sha1(NFC name),
    so '北京咨询' -> 'e-<hash>' and '上海贸易' gets a different one. Never
    returns an empty string ('item' for an empty name), never contains a path
    separator, never starts with a dot: always safe as one path segment.
    """
    norm = unicodedata.normalize("NFKD", str(name))
    ascii_only = norm.encode("ascii", "ignore").decode("ascii").lower()
    slug = _NON_SLUG.sub("-", ascii_only).strip("-")
    dropped = any(ch.isalnum() and ord(ch) > 127 for ch in norm)
    if dropped:
        nfc = unicodedata.normalize("NFC", str(name)).strip()
        digest = hashlib.sha1(nfc.encode("utf-8")).hexdigest()[:8]
        head = slug[: max_len - 9].strip("-")
        return "%s-%s" % (head, digest) if head else "e-%s" % digest
    slug = slug[:max_len].strip("-")
    return slug or "item"


def name_key(name: str) -> str:
    """Identity of a display name: NFC, case-folded, letters and digits only.

    'Acme Pte. Ltd.' and 'ACME Pte Ltd' are the same entity; 'Acme' and
    'Acme Labs' are not, even where their slugs would collide.
    """
    folded = unicodedata.normalize("NFC", str(name)).casefold()
    return "".join(ch for ch in folded if ch.isalnum())


def cell(text: str) -> str:
    """Make a value safe inside one Markdown table cell."""
    return str(text).replace("\\", "\\\\").replace("|", "\\|")


def yq(value: Any) -> str:
    """Render a value as a YAML flow scalar/sequence.

    JSON is a subset of YAML 1.2 flow syntax, so a JSON-encoded string or
    list is always a valid, correctly escaped YAML value. Used for every
    user-supplied value written into front matter.
    """
    return json.dumps(value, ensure_ascii=False)


def one_line(text: str, limit: int = 300) -> str:
    """Collapse whitespace so a user answer can sit on one Markdown line."""
    flat = " ".join(str(text).split())
    if len(flat) > limit:
        flat = flat[: limit - 3].rstrip() + "..."
    return flat
