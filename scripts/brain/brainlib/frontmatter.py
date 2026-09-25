"""Flat-YAML front matter: the subset Obsidian properties use.

Written form: one `key: value` per line. Strings are JSON-quoted (valid YAML),
lists are JSON flow sequences, plus true/false/null and integers. The reader
also accepts plain scalars and `- item` block lists, so hand-written files
from other tools parse too. Nested maps are not supported by design.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple

FENCE = "---"
_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_.-]*):(?:\s(.*))?$")


def _decode(raw: str) -> Any:
    s = raw.strip()
    if s == "":
        return ""
    if s[0] in '"[{':
        try:
            return json.loads(s)
        except ValueError:
            pass
    if s[0] == "[" and s.endswith("]"):  # YAML flow sequence of plain scalars: [a, b]
        inner = s[1:-1].strip()
        return [_decode(x) for x in inner.split(",")] if inner else []
    if s[0] == "'" and s.endswith("'") and len(s) >= 2:
        return s[1:-1].replace("''", "'")
    if s in ("true", "false"):
        return s == "true"
    if s in ("null", "~"):
        return None
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    return s


def encode(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (list, tuple)):
        return json.dumps([v for v in value], ensure_ascii=False)
    return json.dumps(str(value), ensure_ascii=False)


def split(text: str) -> Tuple[str, str]:
    """Return (front-matter block without fences, body). No block => ('', text)."""
    if not text.startswith(FENCE + "\n"):
        return "", text
    end = text.find("\n" + FENCE + "\n", len(FENCE))
    if end < 0:
        if text.endswith("\n" + FENCE):
            return text[len(FENCE) + 1:-len(FENCE) - 1], ""
        return "", text
    return text[len(FENCE) + 1:end], text[end + len(FENCE) + 2:]


def parse(text: str) -> Tuple[Dict[str, Any], str]:
    block, body = split(text)
    data: Dict[str, Any] = {}
    last_key = None
    for line in block.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = _KEY.match(line)
        if m:
            last_key = m.group(1)
            raw = m.group(2) or ""
            data[last_key] = [] if raw.strip() == "" else _decode(raw)
            continue
        item = line.strip()
        if last_key and item.startswith("- "):
            if not isinstance(data.get(last_key), list):
                data[last_key] = []
            data[last_key].append(_decode(item[2:]))
    for key, value in list(data.items()):
        if value == []:
            data[key] = [] if key in ("tags", "also_quoted", "entities", "speakers") else ""
    return data, body


def dump(data: Dict[str, Any], body: str, order: List[str] = None) -> str:
    keys = list(order or []) + [k for k in data if k not in (order or [])]
    lines = [FENCE]
    for key in keys:
        if key in data:
            lines.append("%s: %s" % (key, encode(data[key])))
    lines.append(FENCE)
    return "\n".join(lines) + "\n" + body


def read(path) -> Tuple[Dict[str, Any], str]:
    with open(path, encoding="utf-8") as fh:
        return parse(fh.read())
