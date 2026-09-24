"""`onboard.py hook session-start`: the onboarding-pending / restore line only.

Frozen contract (spec section 9.6): prints SessionStart JSON
{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ...}}
of at most 4 KB, or nothing; always exits 0; finishes well inside 2 s.
Silent in the source repo, under TESS_BRAIN_QUIET / TESS_HEADLESS, and once
onboarding is complete, skipped, or deferred before its remind_after. The
learning snapshot is a different hook (tessbrain.py); this one never prints it.
"""
from __future__ import annotations

import json
import os
import select
import sys
from pathlib import Path
from typing import Optional

from . import answers, state

MAX_BYTES = 4096


def _drain_stdin() -> None:
    """Consume the hook payload if one is waiting; never block on a TTY."""
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return
        ready, _, _ = select.select([sys.stdin], [], [], 0.2)
        if ready:
            sys.stdin.read(65536)
    except (OSError, ValueError):
        pass


def restore_needed(root: Path, brain: dict) -> bool:
    """operator/profile.json is gitignored, so a fresh clone lacks it."""
    return not state.read_operator_profile(root) and bool((brain.get("identity") or {}).get("operator_name"))


def message(root: Path) -> Optional[str]:
    st = state.status_of(root)
    status = st["status"]
    brain = state.load_brain(root) if status != "source-repo" else None
    if status in ("pending", "in_progress"):
        who = ((brain or {}).get("identity") or {}).get("assistant_name") \
            or state.read_operator_profile(root).get("assistant_name") or "Tess"
        step = st.get("step") or 1
        text = ("ONBOARDING PENDING (step %d/%d): greet the operator as %s and continue the "
                "brain-onboard interview before anything else (skill brain-onboard; run "
                "`python3 scripts/brain/onboard.py status --json` first)."
                % (step, state.TOTAL_STEPS, who))
        text += " Next question: " + answers.question_for(step, brain or {})
        return text
    if status in ("complete", "skipped") and brain is not None and restore_needed(root, brain):
        return ("BRAIN RESTORE NEEDED: operator/profile.json is missing (fresh clone?). Run "
                "`python3 scripts/brain/onboard.py restore` before `./tessctl render`, so the "
                "rendered names stay those in brain/brain.json.")
    return None


def session_start(root: Path, runtime: str) -> int:
    _drain_stdin()
    if os.environ.get("TESS_BRAIN_QUIET") or os.environ.get("TESS_HEADLESS"):
        return 0
    try:
        text = message(root)
    except state.BrainError as exc:
        state.log_error(root, "hook session-start: %s" % exc, runtime)
        return 0
    if not text:
        return 0
    nonce = os.environ.get("TESS_BRAIN_TEST_NONCE")
    if nonce:
        text += " (test nonce: %s)" % nonce
    text = text.encode("utf-8")[: MAX_BYTES - 200].decode("utf-8", "ignore")
    out = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}
    sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
    return 0
