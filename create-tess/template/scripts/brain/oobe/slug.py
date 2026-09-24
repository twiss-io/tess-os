"""Slugs and small text helpers shared by the onboarding modules."""
from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

_NON_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(name: str, max_len: int = 48) -> str:
    """ASCII kebab-case slug: 'Acme Pte. Ltd.' -> 'acme-pte-ltd'.

    Never returns an empty string (falls back to 'item'), never contains a
    path separator, and never starts with a dot, so a slug is always safe to
    use as one path segment under brain/.
    """
    norm = unicodedata.normalize("NFKD", str(name))
    ascii_only = norm.encode("ascii", "ignore").decode("ascii").lower()
    slug = _NON_SLUG.sub("-", ascii_only).strip("-")
    slug = slug[:max_len].strip("-")
    return slug or "item"


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
