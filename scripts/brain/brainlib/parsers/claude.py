"""Claude Code transcript parser (~/.claude/projects/<slug>/<session>.jsonl).

Kept: operator prompts (typed, -p/sdk, queued), Telegram channel turns
(attributed to telegram:<user_id>), and the final assistant text per turn.
Skipped: tool_result records, isMeta injections, system reminders, local
command output, task notifications, compaction summaries and injected
AGENTS.md / CLAUDE.md text.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List, Optional

from . import EXTERNAL_TOOLS, FILE_TOOLS, Msg, Session, iter_text_blocks, read_lines

_CHANNEL = re.compile(r"<channel\s+([^>]*)>(.*?)</channel>", re.S)
_ATTR = re.compile(r'([A-Za-z_]+)="([^"]*)"')
_REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)
_COMMAND = re.compile(r"<command-name>(.*?)</command-name>.*?(?:<command-args>(.*?)</command-args>)?", re.S)
_SKIP_PREFIXES = (
    "<local-command-stdout", "<local-command-stderr", "<local-command-caveat",
    "<task-notification", "<system-reminder", "[Request interrupted",
    "This session is being continued from a previous conversation", "Caveat:",
    "# AGENTS.md instructions", "<INSTRUCTIONS>", "<user-prompt-submit-hook>",
)


def project_slug(path: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", path)


def default_dirs(root: Path) -> List[Path]:
    base = Path(os.environ.get("CLAUDE_CONFIG_DIR") or (Path.home() / ".claude")) / "projects"
    seen: List[Path] = []
    for p in (str(root), os.path.realpath(str(root))):
        d = base / project_slug(p)
        if d not in seen:
            seen.append(d)
    return seen


def _channel_msgs(text: str, ordinal: int, at: str) -> List[Msg]:
    out = []
    for attrs, body in _CHANNEL.findall(text):
        a = dict(_ATTR.findall(attrs))
        source = a.get("source", "channel")
        channel = source.split(":")[-1] if ":" in source else source
        who = a.get("user_id") or a.get("user") or "unknown"
        out.append(Msg(ordinal, a.get("ts") or at, "human", "%s:%s" % (channel, who), channel, body.strip()))
    return out


def _human_text(rec: Dict) -> Optional[str]:
    content = (rec.get("message") or {}).get("content")
    if isinstance(content, list) and any(isinstance(i, dict) and i.get("type") == "tool_result" for i in content):
        return None
    text = "\n".join(iter_text_blocks(content))
    return text if text.strip() else None


def _clean_human(text: str) -> Optional[str]:
    text = _REMINDER.sub("", text).strip()
    if not text or text.startswith(_SKIP_PREFIXES):
        return None
    m = _COMMAND.match(text)
    if m and text.startswith("<command-name>"):
        args = (m.group(2) or "").strip()
        return (m.group(1).strip() + (" " + args if args else "")).strip() or None
    if text.startswith("<command-message>"):
        return None
    return text


def _user(rec: Dict, ordinal: int, sess: Session) -> List[Msg]:
    text = _human_text(rec)
    if text is None:
        return []
    at = rec.get("timestamp") or ""
    if "<channel" in text:
        return _channel_msgs(text, ordinal, at)
    if rec.get("isMeta") or rec.get("promptSource") == "system":
        return []
    cleaned = _clean_human(text)
    if cleaned is None:
        return []
    return [Msg(ordinal, at, "human", "operator", "cli", cleaned)]


def _assistant(rec: Dict, ordinal: int, sess: Session) -> Optional[Msg]:
    content = (rec.get("message") or {}).get("content")
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict) or item.get("type") != "tool_use":
                continue
            name = str(item.get("name") or "")
            if name in EXTERNAL_TOOLS or name.startswith("mcp__"):
                sess.external_context = True
            if name in FILE_TOOLS:
                inp = item.get("input") or {}
                sess.add_file(inp.get("file_path") or inp.get("notebook_path"))
    text = "\n".join(iter_text_blocks(content, ("text",))).strip()
    if not text:
        return None
    return Msg(ordinal, rec.get("timestamp") or "", "assistant", "assistant", "reply", text)


def parse(path: Path, upto: Optional[int] = None) -> Session:
    sess = Session("claude", path)
    rows, sess.last_ordinal, sess.prefix_sha256 = read_lines(path, upto)
    pending_reply: Optional[Msg] = None
    for ordinal, rec in rows:
        if not isinstance(rec, dict) or rec.get("isSidechain"):
            continue
        sess.session_id = sess.session_id or str(rec.get("sessionId") or "")
        if rec.get("type") in ("user", "assistant"):
            sess.cwd = sess.cwd or str(rec.get("cwd") or "")
            sess.git_branch = str(rec.get("gitBranch") or sess.git_branch)
            sess.runtime_version = str(rec.get("version") or sess.runtime_version)
            if not sess.started_at and rec.get("timestamp"):
                sess.started_at = rec["timestamp"]
        if rec.get("type") == "user":
            msgs = _user(rec, ordinal, sess)
            if msgs and pending_reply is not None:
                sess.msgs.append(pending_reply)
                pending_reply = None
            sess.msgs.extend(msgs)
        elif rec.get("type") == "assistant":
            reply = _assistant(rec, ordinal, sess)
            if reply is not None:
                pending_reply = reply  # keep only the final text of the turn
    if pending_reply is not None:
        sess.msgs.append(pending_reply)
    if not sess.session_id:
        sess.session_id = Path(path).stem
    return sess


def discover(root: Path, claude_dir: Optional[Path], known: List[str]) -> List[Path]:
    """Transcripts for this project: a given dir, the project slug dirs, hook-reported paths."""
    dirs = [Path(claude_dir)] if claude_dir else default_dirs(root)
    found: List[Path] = []
    for d in dirs:
        if d.is_dir():
            found.extend(sorted(p for p in d.glob("*.jsonl") if p.is_file()))
    for k in known:
        p = Path(k)
        if p.suffix == ".jsonl" and p.is_file() and p not in found:
            found.append(p)
    return found
