"""Single-instance guard so overlapping scheduled ticks (e.g. a slow `gh`
network call still running when the next tick fires) never run two
heartbeat passes concurrently against the same cards.

Uses `fcntl.flock` (POSIX advisory lock) on a lockfile under the runner's
configured state dir (`config.resolved_state_dir()`, default
`~/.tess-os/memory-heartbeat/`) — deliberately outside the git repo so
runtime bookkeeping never shows up as repo diff noise. The state dir is
configurable (`state_dir` in heartbeat.config.json, or `TESS_MEMORY_STATE_DIR`)
so it can be relocated on non-macOS/non-single-operator setups.
"""

from __future__ import annotations

import fcntl
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from . import config as config_mod


@contextmanager
def single_instance(state_dir: Optional[Path] = None):
    state_dir = state_dir or config_mod.load().resolved_state_dir()
    lock_path = state_dir / "heartbeat.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_path, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        print(
            f"[heartbeat] another instance holds {lock_path} — exiting without work",
            file=sys.stderr,
        )
        yield False
        return
    try:
        yield True
    finally:
        fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()
