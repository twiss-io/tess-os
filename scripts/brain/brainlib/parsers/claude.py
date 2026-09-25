"""Claude Code transcript parser (~/.claude/projects/<slug>/<session>.jsonl).

Kept: what the operator typed in the session (typed, -p/sdk, queued) and the
final assistant text per turn. Skipped: tool_result records, isMeta
injections, system reminders, local command output, task notifications,
compaction summaries, injected AGENTS.md / CLAUDE.md text, and any message a
plugin injected through a `<channel>` wrapper (not typed in this session; the
base harness attributes no external channel).
Hand-written notes (`tessbrain.py journal note`) carry their speaker in
`tessSpeaker`.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List, Optional

from . import EXTERNAL_TOOLS, FILE_TOOLS, Msg, Session, iter_text_blocks, read_lines

_INJECTED_CHANNEL = re.compile(r"<channel\s[^>]*>", re.S)
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
    if _INJECTED_CHANNEL.search(text) or rec.get("isMeta") or rec.get("promptSource") == "system":
        return []  # injected by the runtime or a plugin: not typed in this session
    cleaned = _clean_human(text)
    if cleaned is None:
        return []
    speaker = str(rec.get("tessSpeaker") or "")
    return [Msg(ordinal, at, "human", speaker or "operator", "note" if speaker else "cli", cleaned)]


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


def _first_cwd(path: Path) -> str:
    import json
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for _ in range(200):
                raw = fh.readline()
                if not raw:
                    break
                try:
                    rec = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(rec, dict) and rec.get("cwd"):
                    return str(rec["cwd"])
    except OSError:
        return ""
    return ""


def _inside(cwd: str, root: Path) -> bool:
    r, c = os.path.realpath(str(root)), os.path.realpath(cwd) if cwd else ""
    return bool(c) and (c == r or c.startswith(r + os.sep))


def subdir_transcripts(root: Path) -> List[Path]:
    """Sessions started in a SUBDIRECTORY of the instance (`cd clients/acme && claude`):
    their slug is <slug(root)>-..., so keep only those whose recorded cwd is inside root."""
    base = default_dirs(root)[0].parent
    out: List[Path] = []
    for p in {project_slug(str(root)), project_slug(os.path.realpath(str(root)))}:
        for d in sorted(base.glob(p + "-*")) if base.is_dir() else []:
            if d.is_dir():
                out.extend(t for t in sorted(d.glob("*.jsonl")) if t.is_file() and _inside(_first_cwd(t), root))
    return out


def discover(root: Path, claude_dir: Optional[Path], known: List[str]) -> List[Path]:
    """Transcripts for this project: a given dir, the project slug dirs (root and
    subdirectories), hook-reported paths."""
    dirs = [Path(claude_dir)] if claude_dir else default_dirs(root)
    found: List[Path] = []
    for d in dirs:
        if d.is_dir():
            found.extend(sorted(p for p in d.glob("*.jsonl") if p.is_file()))
    if not claude_dir:
        found.extend(p for p in subdir_transcripts(root) if p not in found)
    for k in known:
        p = Path(k)
        if p.suffix == ".jsonl" and p.is_file() and p not in found:
            found.append(p)
    return found
