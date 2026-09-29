"""Runtime transcript parsers -> one neutral Session model.

A parser never interprets meaning; it only extracts human turns, the final
assistant text per turn, tool names, touched files and session metadata.
Unknown record types are skipped, never fatal (rollout formats are "not a
stable interface"). Only complete lines count, so a transcript that is being
written right now is read up to its last newline.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterator, List, Optional, Tuple

EXTERNAL_TOOLS = {"WebFetch", "WebSearch", "web_search", "web_fetch", "google_web_search"}
FILE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit", "write_file", "replace"}
# Paths whose content must never reach a committed (shared) conversation note:
# any `.private/` folder, the private overlay `clients/<X>/` (not brain/clients/,
# which is the committed brain; not clients/_template/), and the root `kb/`.
PRIVATE_PATH = re.compile(r"(?:^|[^A-Za-z0-9_.-])\.private(?:/|\b)"
                          r"|(?<!brain/)(?<![A-Za-z0-9_.-])clients/(?!_template(?:/|\b))"
                          r"|(?<!brain/)(?<![A-Za-z0-9_.-])kb/")


_MARKER = re.compile(r"\.private|clients/|kb/")
_LEAD, _TAIL, MAX_WINDOWS = 1024, 256, 5000


def is_private_path(text: str) -> bool:
    """True when `text` names a private path (see PRIVATE_PATH)."""
    return bool(text) and bool(PRIVATE_PATH.search(str(text)))


class Msg:
    """One journal-worthy item: a human message or a final assistant reply."""

    __slots__ = ("ordinal", "at", "role", "raw_speaker", "channel", "text")

    def __init__(self, ordinal: int, at: str, role: str, raw_speaker: str, channel: str, text: str):
        self.ordinal = ordinal
        self.at = at
        self.role = role  # "human" | "assistant"
        self.raw_speaker = raw_speaker  # "operator" | a principal slug/alias (journal note) | "assistant"
        self.channel = channel  # "cli" | "note" | "reply"
        self.text = text


class Session:
    def __init__(self, runtime: str, path: Path):
        self.runtime = runtime
        self.path = Path(path)
        self.runtime_version = ""
        self.session_id = ""
        self.started_at = ""
        self.cwd = ""
        self.git_branch = ""
        self.msgs: List[Msg] = []
        self.files: List[str] = []
        self.external_context = False
        self.tool_inputs: List[str] = []  # every place a tool input names a private-path marker (bounded)
        self.inspection_incomplete = False  # the bound was hit: the journal withholds replies
        self.last_ordinal = 0
        self.prefix_sha256 = ""
        self._seen: set = set()

    def note_tool_input(self, payload: Any) -> None:
        """Keep, for the journal's private-path check, every stretch of a tool input that could name one.

        PRIVATE_PATH can only match where `.private`, `clients/` or `kb/` occurs, so only those places are
        kept: a window around each occurrence (with enough lead-in for the journal to strip the instance
        root), across the WHOLE input. Codex review finding 5: inputs were cut at 8,192 characters and calls
        after the 5,000th were dropped, so `cat clients/acme/...` past either bound escaped and the reply
        was journaled. When the bound on kept windows is hit, inspection_incomplete withholds the replies."""
        try:
            text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            text = str(payload)
        if not text or self.inspection_incomplete:
            return
        for m in _MARKER.finditer(text):
            window = text[max(0, m.start() - _LEAD):m.end() + _TAIL]
            if window in self._seen:
                continue
            if len(self.tool_inputs) >= MAX_WINDOWS:
                self.inspection_incomplete = True
                return
            self._seen.add(window)
            self.tool_inputs.append(window)

    def add_file(self, path: Any) -> None:
        if isinstance(path, str) and path and path not in self.files:
            self.files.append(path)


def read_lines(path: Path, upto: Optional[int] = None) -> Tuple[List[Tuple[int, Any]], int, str]:
    """Parse complete JSONL lines -> ([(ordinal, obj)], last_ordinal, sha256 of prefix).

    Ordinal == 1-based line number. A trailing line without a newline is
    ignored (still being written). Bad JSON lines are skipped, not fatal.
    """
    data = Path(path).read_bytes()
    end = data.rfind(b"\n")
    data = data[: end + 1] if end >= 0 else b""
    lines = data.split(b"\n")[:-1] if data else []
    if upto is not None:
        lines = lines[:upto]
        data = b"".join(l + b"\n" for l in lines)
    out: List[Tuple[int, Any]] = []
    for i, raw in enumerate(lines, 1):
        try:
            out.append((i, json.loads(raw.decode("utf-8", "replace"))))
        except ValueError:
            continue
    return out, len(lines), hashlib.sha256(data).hexdigest()


def count_lines(path: Path) -> int:
    try:
        data = Path(path).read_bytes()
    except OSError:
        return 0
    return data.count(b"\n")


def iter_text_blocks(content: Any, kinds=("text", "input_text", "output_text")) -> Iterator[str]:
    if isinstance(content, str):
        yield content
    elif isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") in kinds and isinstance(item.get("text"), str):
                yield item["text"]
