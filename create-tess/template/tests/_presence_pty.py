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


def run_tessctl_in_pty(root, *args, answer: str = "", prompt: bytes = b"> ",
                       timeout: int = 180):
    """(returncode, combined output). Types `answer` + newline the first time
    `prompt` appears in the output; an empty answer types nothing."""
    import pty
    root = Path(root)
    master, slave = pty.openpty()
    p = subprocess.Popen([sys.executable, str(root / ".tess" / "bin" / "tessctl"), *args],
                         cwd=str(root), stdin=slave, stdout=slave, stderr=slave,
                         env={**os.environ, "TESS_ROOT": str(root)}, close_fds=True)
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
