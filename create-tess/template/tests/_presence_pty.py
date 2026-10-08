"""Shared test helper (v1.0 audit): run a tessctl command on a real
pseudo-terminal and type an answer at its presence prompt.

Commands that make a security-tier file accepted (approve, resolve, override,
reset of changed core, rollback of safety files, update/self-update to an
older release) ask the person at the terminal to type a confirmation. A test
that exercises the confirmed path end to end runs the CLI here.
"""
from __future__ import annotations

import os
import select
import subprocess
import sys
from pathlib import Path

# The assistant-session markers tessctl's presence checks refuse on
# (AGENT_SESSION_MARKERS in .tess/bin/tessctl). The suite may itself run inside
# Claude Code or Codex; a test that plays the operator at a real terminal
# removes them, as the operator's own terminal would not have them.
AGENT_SESSION_MARKERS = ("CODEX_THREAD_ID", "CODEX_SANDBOX", "CODEX_SANDBOX_NETWORK_DISABLED",
                         "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")


def operator_env(**extra) -> dict:
    """os.environ without the assistant-session markers, plus `extra`."""
    env = {k: v for k, v in os.environ.items() if k not in AGENT_SESSION_MARKERS}
    env.update(extra)
    return env


def run_tessctl_in_pty(root, *args, answer: str = "", prompt: bytes = b"> ",
                       timeout: int = 180, env: dict | None = None):
    """(returncode, combined output). Types `answer` + newline the first time
    `prompt` appears in the output; an empty answer types nothing. The child
    runs without the assistant-session markers unless `env` names them."""
    import pty
    root = Path(root)
    master, slave = pty.openpty()
    p = subprocess.Popen([sys.executable, str(root / ".tess" / "bin" / "tessctl"), *args],
                         cwd=str(root), stdin=slave, stdout=slave, stderr=slave,
                         env=env if env is not None else operator_env(TESS_ROOT=str(root)),
                         close_fds=True)
    os.close(slave)
    out, sent = b"", not answer
    while True:
        ready, _, _ = select.select([master], [], [], timeout)
        if not ready:
            break
        try:
            chunk = os.read(master, 4096)
        except OSError:
            break
        if not chunk:
            break
        out += chunk
        if not sent and prompt in out:
            os.write(master, (answer + "\n").encode("utf-8"))
            sent = True
    rc = p.wait(timeout=timeout)
    os.close(master)
    return rc, out.decode("utf-8", "replace")
