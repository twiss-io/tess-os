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


def read_stdin(cfg: Optional[Config]) -> Dict:
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


# Runtime programs whose nesting marks an agent-started session (see automation_reason).
_RUNTIME_EXES = ("claude", "codex", "gemini")


def _ancestry(limit: int = 40) -> List[str]:
    """Lower-cased program names of this process's ancestors, parent first ([] when `ps` is unavailable)."""
    try:
        out = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,comm="], capture_output=True, text=True,
                             timeout=3).stdout
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    procs = {}
    for line in out.splitlines():
        parts = line.split(None, 2)
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            procs[int(parts[0])] = (int(parts[1]), parts[2].strip())
    names: List[str] = []
    pid, seen = os.getppid(), set()
    while pid in procs and pid not in seen and len(names) < limit:
        seen.add(pid)
        pid, comm = procs[pid]
        names.append(os.path.basename(comm).lower())
    return names


def nested_runtime(names: Optional[List[str]] = None) -> str:
    """'' unless this hook's runtime was itself started from inside another agent session: two separate
    runs of runtime programs (claude, codex, gemini) with something else (the agent's shell) between them."""
    groups: List[str] = []
    prev = False
    for n in (_ancestry() if names is None else names):
        cur = n in _RUNTIME_EXES
        if cur and not prev:
            groups.append(n)
        prev = cur
    if len(groups) < 2:
        return ""
    return "a %s session started from inside a %s session" % (groups[0], groups[1])


def automation_reason(runtime: str, data: Dict) -> str:
    """Why this session is run by automation, not typed by the operator ('' when it is the operator).

    v1.0.0 audit (headless prompts attributed to the operator): `claude -p`, the Agent SDK, `codex exec`, and
    a runtime an agent started from its own shell send prompts a program or an agent chose. Signals: Claude
    Code's entrypoint for this process, the session's own transcript markers (parsers), and a runtime
    running inside another runtime's session (process ancestry)."""
    ep = os.environ.get("CLAUDE_CODE_ENTRYPOINT", "").strip()
    if runtime == "claude" and ep.startswith("sdk"):
        return "Claude Code entrypoint %s (claude -p or the Agent SDK)" % ep
    path = str(data.get("transcript_path") or "")
    if path and os.path.isfile(path):
        from .parsers import transcript_automation
        why = transcript_automation(runtime, path)
        if why:
            return why
    return nested_runtime()


def _mark_automation(cfg: Config, runtime: str, data: Dict, why: str) -> None:
    from . import provenance
    provenance.mark_automation(cfg, runtime, str(data.get("session_id") or ""), str(data.get("transcript_path") or ""),
                               why)


def spawn_argv(args: List[str]) -> List[str]:
    """The detached child goes back through the pinned launcher when this instance ships one, so the
    sync it runs is sha-verified again (the hook that spawns it was verified moments earlier).
    Isolated interpreter either way: no PYTHONPATH, no user site, no .pyc written."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(SCRIPT)))
    launcher = os.path.join(root, ".claude", "hooks", "run-pinned.py")
    if os.path.isfile(launcher) and not os.path.islink(launcher):
        return [sys.executable, "-I", "-B", launcher, "--on-fail", "warn", "--closure", "scripts/brain", "--",
                "scripts/brain/tessbrain.py"] + args
    return [sys.executable, "-I", "-B", SCRIPT] + args


def spawn(args: List[str]) -> None:
    """Detached child (own session), so it outlives the runtime's hook process."""
    try:
        env = dict(os.environ)
        env.pop("CLAUDE_PROJECT_DIR", None)  # the launcher then roots at its own location
        subprocess.Popen(spawn_argv(args), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True, env=env)
    except OSError as exc:
        log_error(None, "hook: could not spawn %s" % args, exc)


def session_start(cfg: Config, runtime: str, data: Dict) -> None:
    budget = cfg.budgets["session_start_kib"] * 1024
    # the provenance key and the external project state were made in dispatch (provenance.prepare): Codex runs
    # the agent's shell in a sandbox that can read ~/.config/tess but not create files there
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
    why = automation_reason(runtime, data)
    if why:  # recorded before the turn, so the Stop hook's sync already journals it as automation
        _mark_automation(cfg, runtime, data, why)
    rec = turns.append(cfg, runtime, str(data.get("session_id") or ""), text, "automation" if why else "operator")
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
    ep = os.environ.get("CLAUDE_CODE_ENTRYPOINT", "").strip()
    if runtime == "claude" and ep.startswith("sdk"):  # cheap; the prompt hook already checked the rest
        _mark_automation(cfg, runtime, data, "Claude Code entrypoint %s (claude -p or the Agent SDK)" % ep)
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
        data = read_stdin(cfg)
        if event in ("session-start", "prompt"):  # proof the hooks run, before onboarding too
            from . import hooksalive
            hooksalive.beat(cfg.root, runtime, data, event)
        if quiet_env() or not cfg.active():
            if event == "stop" and runtime == "codex":
                print("{}")
            return 0
        from . import provenance  # hooks run outside the agent's sandbox: drain what a sandboxed shell queued
        provenance.prepare(cfg)
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
