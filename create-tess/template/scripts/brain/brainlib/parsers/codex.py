"""Codex CLI rollout parser ($CODEX_HOME/sessions/**/rollout-*.jsonl).

Pinned against codex-cli 0.145.0 (tests/fixtures/brain_learn/codexhome).
User text comes from `event_msg` / `user_message`; the reply from
`event_msg` / `agent_message` (last one per turn). Rollouts that carry no
user_message events fall back to `response_item` user messages that are not
injected context. A rollout belongs to this repo when the realpath of
`session_meta.cwd` is inside the repo root (or an --also-cwd path).
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

from . import EXTERNAL_TOOLS, Msg, Session, iter_text_blocks, read_lines

_PATCH_FILE = re.compile(r"^\*\*\* (?:Update|Add|Delete) File: (.+)$", re.M)
_INJECTED = ("<", "# AGENTS.md instructions")


def codex_home(explicit: Optional[str] = None) -> Path:
    return Path(explicit or os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))


def session_cwd(path: Path) -> Optional[str]:
    """cwd from the first session_meta record (reads only the head of the file)."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for _ in range(20):
                line = fh.readline()
                if not line:
                    break
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if isinstance(rec, dict) and rec.get("type") == "session_meta":
                    return str((rec.get("payload") or {}).get("cwd") or "") or None
    except OSError:
        return None
    return None


def _inside(child: str, parents: List[str]) -> bool:
    c = os.path.realpath(child)
    for p in parents:
        rp = os.path.realpath(p)
        if c == rp or c.startswith(rp.rstrip(os.sep) + os.sep):
            return True
    return False


def discover(root: Path, home: Optional[str], also_cwd: List[str], days: Optional[int] = None,
             deadline: Optional[float] = None) -> List[Path]:
    import time
    base = codex_home(home) / "sessions"
    if not base.is_dir():
        return []
    cutoff = time.time() - days * 86400 if days else None
    out: List[Path] = []
    for p in sorted(base.glob("**/rollout-*.jsonl")):
        if deadline is not None and time.monotonic() > deadline:
            break
        try:
            if cutoff and p.stat().st_mtime < cutoff:
                continue
        except OSError:
            continue
        cwd = session_cwd(p)
        if cwd and _inside(cwd, [str(root)] + list(also_cwd)):
            out.append(p)
    return out


def _response_item(p: Dict, ordinal: int, at: str, sess: Session, fallback: List[Msg]) -> None:
    kind = p.get("type")
    if kind in ("function_call", "custom_tool_call"):
        name = str(p.get("name") or "")
        if name in EXTERNAL_TOOLS or name.startswith("mcp__"):
            sess.external_context = True
        body = p.get("input") if isinstance(p.get("input"), str) else str(p.get("arguments") or "")
        for f in _PATCH_FILE.findall(body or ""):
            sess.add_file(f.strip())
    elif kind == "web_search_call":
        sess.external_context = True
    elif kind == "message" and p.get("role") == "user":
        for text in iter_text_blocks(p.get("content"), ("input_text", "text")):
            if text.strip() and not text.lstrip().startswith(_INJECTED):
                fallback.append(Msg(ordinal, at, "human", "operator", "cli", text.strip()))


def _event(p: Dict, ordinal: int, at: str, users: List[Msg]) -> Optional[Msg]:
    kind = p.get("type")
    if kind == "user_message" and isinstance(p.get("message"), str):
        text = p["message"].strip()
        if text and not text.startswith("# AGENTS.md instructions"):
            users.append(Msg(ordinal, at, "human", "operator", "cli", text))
    elif kind == "agent_message" and isinstance(p.get("message"), str) and p["message"].strip():
        return Msg(ordinal, at, "assistant", "assistant", "reply", p["message"].strip())
    return None


def parse(path: Path, upto: Optional[int] = None) -> Session:
    sess = Session("codex", path)
    rows, sess.last_ordinal, sess.prefix_sha256 = read_lines(path, upto)
    users: List[Msg] = []
    fallback: List[Msg] = []
    replies: List[Msg] = []
    for ordinal, rec in rows:
        if not isinstance(rec, dict):
            continue
        p = rec.get("payload") if isinstance(rec.get("payload"), dict) else {}
        at = str(rec.get("timestamp") or "")
        kind = rec.get("type")
        if kind == "session_meta" and not sess.session_id:
            sess.session_id = str(p.get("id") or p.get("session_id") or "")
            sess.cwd = str(p.get("cwd") or "")
            sess.runtime_version = str(p.get("cli_version") or "")
            sess.started_at = str(p.get("timestamp") or at)
            sess.git_branch = str((p.get("git") or {}).get("branch") or "")
        elif kind == "event_msg":
            reply = _event(p, ordinal, at, users)
            if reply is not None:
                replies.append(reply)
        elif kind == "response_item":
            _response_item(p, ordinal, at, sess, fallback)
    humans = users or fallback
    sess.msgs = _final_replies(humans, replies)
    if not sess.session_id:
        sess.session_id = Path(path).stem[-36:]
    return sess


def _final_replies(humans: List[Msg], replies: List[Msg]) -> List[Msg]:
    """Interleave by ordinal, keeping only the last reply before each human turn."""
    items = sorted(humans + replies, key=lambda m: m.ordinal)
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
