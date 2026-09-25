"""Gemini CLI chat parser ($HOME/.gemini/tmp/<project>/chats/session-*.jsonl).

Verified 2026-09-24 against a real Gemini CLI 0.61.0 run in a scratch HOME:
~/.gemini/projects.json maps the project root to a short directory name,
~/.gemini/tmp/<name>/.project_root holds the root path, and each session is
a JSONL file whose first line is a header (sessionId, projectHash =
sha256(project root), startTime) followed by message records
(`type: user|gemini`, `content`) and `{"$set": {...}}` updates. The injected
`<session_context>` preamble is skipped. Unknown record types are tolerated.
The older `tmp/<sha256 of root>/chats/*.json` layout is also swept.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Dict, List, Optional

from . import EXTERNAL_TOOLS, FILE_TOOLS, Msg, Session, read_lines


def gemini_dir(home: Optional[str] = None) -> Path:
    return Path(home or os.environ.get("GEMINI_CLI_HOME") or Path.home()) / ".gemini"


def _roots(root: Path, also: List[str]) -> List[str]:
    return [os.path.realpath(str(p)) for p in [root] + list(also)]


def _inside(child: str, parents: List[str]) -> bool:
    c = os.path.realpath(child)
    return any(c == p or c.startswith(p.rstrip(os.sep) + os.sep) for p in parents)


def _project_dirs(base: Path, parents: List[str]) -> List[Path]:
    tmp = base / "tmp"
    if not tmp.is_dir():
        return []
    hashes = {hashlib.sha256(p.encode("utf-8")).hexdigest() for p in parents}
    out = []
    for d in sorted(tmp.iterdir()):
        if not d.is_dir():
            continue
        marker = d / ".project_root"
        try:
            owner = marker.read_text(encoding="utf-8").strip() if marker.is_file() else ""
        except OSError:
            owner = ""
        if (owner and _inside(owner, parents)) or d.name in hashes:
            out.append(d)
    return out


def discover(root: Path, home: Optional[str], also_cwd: List[str]) -> List[Path]:
    parents = _roots(root, also_cwd)
    found: List[Path] = []
    for d in _project_dirs(gemini_dir(home), parents):
        chats = d / "chats"
        if chats.is_dir():
            found.extend(sorted(p for p in chats.glob("session-*.json*") if p.is_file()))
    return found


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(c["text"] for c in content if isinstance(c, dict) and isinstance(c.get("text"), str))
    return ""


def _tools(rec: Dict, sess: Session) -> None:
    for call in rec.get("toolCalls") or []:
        if not isinstance(call, dict):
            continue
        name = str(call.get("name") or "")
        if name in EXTERNAL_TOOLS or name.startswith("mcp_"):
            sess.external_context = True
        if name in FILE_TOOLS:
            args = call.get("args") or {}
            sess.add_file(args.get("file_path") or args.get("absolute_path"))


def _message(rec: Dict, ordinal: int, sess: Session, seen: set) -> Optional[Msg]:
    kind = rec.get("type")
    mid = str(rec.get("id") or "")
    if kind not in ("user", "gemini") or (mid and mid in seen):
        return None
    if mid:
        seen.add(mid)
    at = str(rec.get("timestamp") or "")
    if kind == "gemini":
        _tools(rec, sess)
        text = _text(rec.get("content")).strip()
        return Msg(ordinal, at, "assistant", "assistant", "reply", text) if text else None
    text = _text(rec.get("content")).strip()
    if not text or text.startswith("<"):  # <session_context> and other injected preambles
        return None
    return Msg(ordinal, at, "human", "operator", "cli", text)


def parse(path: Path, upto: Optional[int] = None) -> Session:
    sess = Session("gemini", path)
    rows, sess.last_ordinal, sess.prefix_sha256 = read_lines(path, upto)
    seen: set = set()
    items: List[Msg] = []
    for ordinal, rec in rows:
        if not isinstance(rec, dict):
            continue
        if "sessionId" in rec and "startTime" in rec and not sess.session_id:
            sess.session_id = str(rec.get("sessionId") or "")
            sess.started_at = str(rec.get("startTime") or "")
            continue
        batch = (rec.get("$set") or {}).get("messages") if isinstance(rec.get("$set"), dict) else None
        for r in (batch if isinstance(batch, list) else [rec]):
            if isinstance(r, dict):
                m = _message(r, ordinal, sess, seen)
                if m is not None:
                    items.append(m)
    sess.msgs = _final_replies(items)
    if not sess.session_id:
        sess.session_id = Path(path).stem[-8:]
    if not sess.started_at and sess.msgs:
        sess.started_at = sess.msgs[0].at
    return sess


def _final_replies(items: List[Msg]) -> List[Msg]:
    out: List[Msg] = []
    pending: Optional[Msg] = None
    for m in items:
        if m.role == "assistant":
            pending = m
            continue
        if pending is not None:
            out.append(pending)
            pending = None
        out.append(m)
    if pending is not None:
        out.append(pending)
    return out
