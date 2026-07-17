#!/bin/bash
# Scheduler-invoked wrapper for the memory-continuity heartbeat.
#
# launchd/cron/systemd all run scheduled jobs with a minimal environment — no
# .zshrc/.bash_profile sourced, no PATH beyond a bare default. This wrapper
# sets exactly the PATH entries the runner needs (gh, git, python3, claude)
# and nothing else, then execs the actual Python entry point. Logs go to the
# runner's configured state dir (default ~/.tess-os/memory-heartbeat/, see
# scripts/heartbeat/config.py), matching the runner's own convention of
# keeping runtime bookkeeping outside the git repo.
#
# NOT wired to any scheduler by default. See scripts/launchd/README.md for
# the one-command activation an operator runs when ready, and
# docs/memory-continuity.md for the full off-by-default posture.

set -euo pipefail

export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# Repo root = two directories up from this script (scripts/heartbeat.sh -> repo root).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Log dir defaults to the same state dir the Python runner resolves
# (TESS_MEMORY_STATE_DIR env override, else heartbeat.config.json's
# state_dir, else ~/.tess-os/memory-heartbeat/) — kept in sync here via the
# same env var so shell-side logs and the runner's own lock/state files land
# in the same place without duplicating the resolution logic in bash.
LOG_DIR="${TESS_MEMORY_STATE_DIR:-$HOME/.tess-os/memory-heartbeat}"
mkdir -p "$LOG_DIR"

cd "$REPO_ROOT"
exec /usr/bin/env python3 "$REPO_ROOT/scripts/heartbeat/run.py" "$@" \
  >> "$LOG_DIR/heartbeat.out.log" 2>> "$LOG_DIR/heartbeat.err.log"
