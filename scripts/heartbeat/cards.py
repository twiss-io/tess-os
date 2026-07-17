"""Read and (narrowly) write memory/projects/*.md cards.

Reads use `yaml.safe_load` on the isolated frontmatter block — robust,
no reason to hand-parse YAML we can parse correctly.

Writes are deliberately NOT a full YAML re-serialize-and-dump. A full
round-trip through `yaml.dump` would reformat every field on the card —
re-flowing the `resume:` block scalar, re-quoting `gates:` list items,
changing key order — turning a 3-field mechanical update into a
whole-card diff that's hard to review and risks corrupting hand-authored
prose. Instead, writes replace exactly one scalar line at a time via a
scoped regex, byte-for-byte identical elsewhere. This is the same
discipline the design applies to the registry itself (mechanical
evidence refresh vs. human/LLM-authored narrative).

Only six leaf fields are writable at all (see WRITABLE_FIELDS) — anything
else (next_move, resume, gates, body prose) requires a human/agent session:
this runner only CHECKS and queues; any actual resume WORK is dispatched
through the operator's own dispatch mechanism, never done by the runner
itself.

Ported unchanged from the reference implementation — this module operates
purely on the card schema and has no org/client-specific content.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

FRONTMATTER_RE = re.compile(r"^---\n(.*?\n)---\n", re.DOTALL)

WRITABLE_FIELDS = {
    "heartbeat.last_activity",
    "heartbeat.activity_proof",
    "stall.stalled",
    "stall.reason",
    "stall.since",
    "facts_last_verified",
}
# Deliberately NOT writable by this runner: heartbeat.cadence, heartbeat.stall_after,
# next_move, resume, gates, title/state/owner/priority, and all body prose — those
# are human/agent-authored judgment calls, not mechanical evidence refresh.

# Bare (unquoted) keys — booleans, null, and the stall.reason enum, which
# cards write unquoted (e.g. `reason: attention-shift`, `reason: null`,
# `stalled: false`). Everything else is a quoted string.
_BARE_KEYS = {"stalled", "reason"}


class CardError(Exception):
    pass


@dataclass
class Card:
    path: Path
    slug: str
    frontmatter: Dict[str, Any]
    raw_frontmatter: str
    body: str

    @property
    def repo(self) -> str:
        return self.frontmatter["repo"]

    @property
    def priority(self) -> str:
        return self.frontmatter.get("priority", "P3")

    @property
    def owner(self) -> str:
        return self.frontmatter.get("owner", "unassigned")

    @property
    def title(self) -> str:
        return self.frontmatter.get("title", self.slug)

    @property
    def state(self) -> str:
        return self.frontmatter.get("state", "UNKNOWN")

    @property
    def heartbeat(self) -> Dict[str, Any]:
        return self.frontmatter.get("heartbeat", {}) or {}

    @property
    def stall(self) -> Dict[str, Any]:
        return self.frontmatter.get("stall", {}) or {}

    @property
    def last_activity(self) -> Optional[datetime]:
        raw = self.heartbeat.get("last_activity")
        if not raw:
            return None
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))

    @property
    def is_stalled(self) -> bool:
        return bool(self.stall.get("stalled"))

    @property
    def stall_reason(self) -> Optional[str]:
        return self.stall.get("reason")

    @property
    def stall_since(self) -> Optional[datetime]:
        raw = self.stall.get("since")
        if not raw:
            return None
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))


def list_card_paths(projects_dir: Path) -> list:
    return sorted(
        p for p in projects_dir.glob("*.md")
        if p.name not in {"EXAMPLE.md", "README.md"}
    )


def read_card(path: Path) -> Card:
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise CardError(f"{path}: no YAML frontmatter block found")
    raw_frontmatter = match.group(1)
    body = text[match.end():]
    try:
        parsed = yaml.safe_load(raw_frontmatter) or {}
    except yaml.YAMLError as exc:
        raise CardError(f"{path}: frontmatter did not parse as YAML: {exc}") from exc
    for required in ("id", "title", "state", "owner", "priority", "repo"):
        if required not in parsed:
            raise CardError(f"{path}: missing required field '{required}'")
    return Card(
        path=path,
        slug=parsed["id"],
        frontmatter=parsed,
        raw_frontmatter=raw_frontmatter,
        body=body,
    )


def _yaml_scalar(key: str, value: Any) -> str:
    """Render `value` the way this card family already writes it."""
    if key in _BARE_KEYS:
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)  # e.g. an enum token like attention-shift
    if value is None:
        return "null"
    # Strings (timestamps, activity_proof prose) — quote like the existing
    # cards do, using JSON string syntax (a valid subset of YAML
    # double-quoted scalars) so embedded quotes/backslashes stay safe.
    # ensure_ascii=False: keep any literal em-dashes/curly quotes as-authored
    # instead of escaping them, so diffs stay readable.
    return json.dumps(str(value), ensure_ascii=False)


def _replace_scalar_line(text: str, leaf_key: str, new_value: str) -> str:
    """Replace the single `leaf_key: ...` line in `text`. Requires exactly
    one match — a schema drift (0 or 2+ matches) is a hard stop, not a
    silent partial write."""
    pattern = re.compile(rf"^([ \t]*){re.escape(leaf_key)}:.*$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise CardError(
            f"expected exactly one '{leaf_key}:' line, found {len(matches)}"
        )
    indent = matches[0].group(1)
    return pattern.sub(lambda m: f"{indent}{leaf_key}: {new_value}", text, count=1)


def apply_updates(card: Card, updates: Dict[str, Any]) -> str:
    """Returns the new full file text with `updates` applied. Does not
    write to disk — caller decides whether/when (dry-run never writes).
    `updates` keys must be in WRITABLE_FIELDS, e.g. {"heartbeat.last_activity": "..."}.
    """
    unknown = set(updates) - WRITABLE_FIELDS
    if unknown:
        raise CardError(f"refusing to write non-whitelisted fields: {unknown}")
    text = card.raw_frontmatter
    for dotted_key, value in updates.items():
        leaf_key = dotted_key.split(".")[-1]
        text = _replace_scalar_line(text, leaf_key, _yaml_scalar(leaf_key, value))
    return f"---\n{text}---\n{card.body}"
