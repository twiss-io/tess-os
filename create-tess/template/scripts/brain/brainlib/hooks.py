"""Hook handlers: `tessbrain.py hook session-start|prompt|stop --runtime claude|codex`.

Contract (spec 9.6): always exit 0; log errors to .tess/state/brain/errors.log;
silent in the source repo, without brain/brain.json, and under
TESS_BRAIN_QUIET / TESS_HEADLESS. session-start prints ONLY the snapshot
(<= 4 KB, <= 2 s) and spawns a detached, locked 7-day backfill. prompt
records the redacted turn and prints at most 2 nudge lines. stop records the
transcript path and hands journaling to a detached sync, so it returns fast.
Hooks never run git write commands.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Dict, List, Optional

from . import cues, status, turns
from .config import Config, log_error, quiet_env, read_json, write_json

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tessbrain.py")
DISTILL_EVERY = 10
_INJECTED = __import__("re").compile(r"<channel\s[^>]*>")


def read_stdin(cfg: Config) -> Dict:
    try:
        raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    except (OSError, ValueError) as exc:  # includes UnicodeDecodeError (binary stdin)
        log_error(cfg, "hook: stdin could not be read or decoded", exc)
        return {}
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("hook stdin is not a JSON object")
        return data
    except ValueError as exc:
        log_error(cfg, "hook: unreadable stdin (%d bytes)" % len(raw), exc)
        return {}


def _emit(event: str, text: str, limit: int) -> None:
    text = _fit(text, limit)
    if text:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}},
                         ensure_ascii=False))


def _fit(text: str, limit: int) -> str:
    """Truncate by section priority, never silently: the last line says so."""
    if len(text.encode("utf-8")) <= limit:
        return text
    note = "\n[brain] snapshot truncated; see brain/START-HERE.md and `tessbrain.py status`"
    lines, out = text.splitlines(), []
    for line in lines:
        if len(("\n".join(out + [line]) + note).encode("utf-8")) > limit:
            break
        out.append(line)
    return "\n".join(out) + note


def spawn(args: List[str]) -> None:
    """Detached child (own session), so it outlives the runtime's hook process."""
    try:
        subprocess.Popen([sys.executable, SCRIPT] + args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True)
    except OSError as exc:
        log_error(None, "hook: could not spawn %s" % args, exc)


def session_start(cfg: Config, runtime: str, data: Dict) -> None:
    budget = cfg.budgets["session_start_kib"] * 1024
    text = status.snapshot(cfg, runtime)
    nonce = os.environ.get("TESS_BRAIN_TEST_NONCE")
    if nonce:
        text = "[brain] test nonce: %s\n%s" % (nonce, text)
    _emit("SessionStart", text, budget)
    if not os.environ.get("TESS_BRAIN_NO_BACKFILL"):
        spawn(["--root", str(cfg.root), "sync", "--days", "7", "--no-wait", "--quiet"])


def prompt(cfg: Config, runtime: str, data: Dict) -> None:
    text = str(data.get("prompt") or "")
    if not text.strip() or _INJECTED.search(text):  # plugin-injected text is not the operator typing
        return
    rec = turns.append(cfg, runtime, str(data.get("session_id") or ""), text, "operator")
    from . import sync
    sync.remember_session(cfg, runtime, str(data.get("session_id") or ""), str(data.get("transcript_path") or ""),
                          str(data.get("cwd") or ""))
    lines: List[str] = []
    if rec.get("principal"):
        hits = [h for h in cues.scan_text(rec["text"]) if h.kind in ("decision", "preference", "correction")]
        if hits:
            h = hits[0]
            lines.append('[brain] possible %s: "%s". It is recorded automatically after this turn; if it is not a %s, '
                         'say so.' % (h.kind, h.sentence[:200], h.kind))
    state = read_json(cfg.state / "distill.json", {})
    since = int(state.get("through_turn") or 0)
    n = turns.principal_count_since(cfg, since)
    if rec.get("principal") and n and n % DISTILL_EVERY == 0:
        lines.append("[brain] %d turns since last distill: run brain-distill after answering." % n)
    if lines:
        _emit("UserPromptSubmit", "\n".join(lines[:2]), 1024)


def stop(cfg: Config, runtime: str, data: Dict) -> None:
    """Hand journaling to a detached sync FIRST: `claude -p` ends the session (and may kill an async
    hook) right after Stop fires, so nothing slow may run before the child is spawned."""
    transcript = str(data.get("transcript_path") or "")
    args = ["--root", str(cfg.root), "sync", "--runtime", runtime, "--quiet"]
    if transcript:
        args += ["--transcript", transcript]
    if os.environ.get("TESS_BRAIN_HOOK_INLINE"):
        from . import sync as _s
        _s.run(cfg, runtime=runtime, transcript=transcript or None)
    else:
        spawn(args)
    if runtime == "codex":
        print("{}", flush=True)  # Codex requires JSON (or nothing) from Stop hooks
    from . import sync
    sync.remember_session(cfg, runtime, str(data.get("session_id") or ""), transcript, str(data.get("cwd") or ""))


def dispatch(root, event: str, runtime: str) -> int:
    cfg: Optional[Config] = None
    try:
        cfg = Config(root)
        if quiet_env() or not cfg.active():
            try:
                sys.stdin.read()
            except (OSError, ValueError):
                pass
            if event == "stop" and runtime == "codex":
                print("{}")
            return 0
        data = read_stdin(cfg)
        {"session-start": session_start, "prompt": prompt, "stop": stop}[event](cfg, runtime, data)
    except Exception as exc:  # noqa: BLE001 - a hook must never break the session
        log_error(cfg, "hook %s (%s) failed" % (event, runtime), exc)
    return 0


def mark_distilled(cfg: Config) -> Dict:
    rows = turns.read(cfg, limit=None)
    through = rows[-1]["n"] if rows else 0
    cfg.ensure_state()
    write_json(cfg.state / "distill.json", {"through_turn": through})
    return {"through_turn": through}
