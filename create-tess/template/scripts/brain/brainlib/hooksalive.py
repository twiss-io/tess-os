"""Hook heartbeat: proof that Tess's runtime hooks ran in a given session.

Codex runs a project's hooks only after the operator approves them in `/hooks`,
and asks again after every change to the hook text (so after every Tess
update). Until then nothing tells the operator the safety checks are off. The
SessionStart and UserPromptSubmit hooks call beat(); `scripts/tess
hooks-status` reads the file and tells the assistant, in one plain line,
whether the hooks ran in the CURRENT session (CODEX_THREAD_ID /
CLAUDE_CODE_SESSION_ID). The AGENTS.md / CLAUDE.md BOOT block has the
assistant run it at its first reply.

The file is a detection aid, not a security boundary: it is gitignored, not
protected, and holds no operator data (runtime, session id, event, time).
Keep the path and layout in step with scripts/tess (a stdlib-only reader).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Dict

REL = Path(".tess") / "state" / "hooks-alive.json"
KEEP = 20  # sessions remembered per runtime (concurrent sessions each find their own id)
RUNTIMES = ("claude", "codex")


def path(root) -> Path:
    return Path(root) / REL


def beat(root, runtime: str, data: Dict, event: str) -> None:
    """Record that `event` ran for this runtime/session. Never raises."""
    try:
        sid = str((data or {}).get("session_id") or "").strip()
        if runtime not in RUNTIMES or not sid or not (Path(root) / ".tess").is_dir():
            return  # not a Tess OS folder: never create .tess/ in someone else's tree
        p = path(root)
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(doc, dict):
                doc = {}
        except (OSError, ValueError):
            doc = {}
        rows = [r for r in doc.get(runtime) or [] if isinstance(r, dict) and r.get("session_id") != sid]
        rows.insert(0, {"session_id": sid, "event": event,
                        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        doc[runtime] = rows[:KEEP]
        doc["schema"] = 1
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name("%s.%d.tmp" % (p.name, os.getpid()))
        tmp.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(str(tmp), str(p))
    except Exception:  # noqa: BLE001 - a heartbeat must never break a hook
        return
