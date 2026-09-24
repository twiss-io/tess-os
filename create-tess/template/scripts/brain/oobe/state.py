"""brain/brain.json v1 (spec section 9.1): root discovery, atomic I/O, status.

Stdlib only (python3 >= 3.9). Every write is atomic (tmp file + os.replace in
the same directory). Errors go to stderr and to .tess/state/brain/errors.log;
the first write there also creates .tess/state/brain/.gitignore = '*', so
local state can never ride along in a `git add -A`.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

SCHEMA = 1
TOTAL_STEPS = 7
BRAIN_JSON = "brain/brain.json"
STATE_DIR = ".tess/state/brain"
STATUSES = ("pending", "in_progress", "complete", "deferred", "skipped")
JOURNAL_POLICIES = ("commit-redacted", "stub-only", "local", "off")
FRAMEWORK_REMOTE_PATTERNS = ["github.com[:/]twiss-io/tess-os"]
BUDGETS = {
    "start_here_lines": 150, "start_here_kib": 12, "entity_agents_kib": 6,
    "entity_agents_lines": 100, "index_lines": 150, "profile_kib": 12,
    "learned_entries": 100, "agents_chain_kib": 24, "session_start_kib": 4,
}


class BrainError(Exception):
    """A user-facing failure: message is printed, exit code is carried."""

    def __init__(self, message: str, code: int = 2):
        super().__init__(message)
        self.code = code


def find_root() -> Path:
    """The Tess root this tool operates on.

    TESS_BRAIN_ROOT wins (tests, tooling); otherwise the repo the script
    ships in (scripts/brain/oobe/state.py -> three levels up), which is also
    $CLAUDE_PROJECT_DIR when a hook runs it.
    """
    env = os.environ.get("TESS_BRAIN_ROOT")
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[3]


def is_source_repo(root: Path) -> bool:
    """The Tess OS framework repo itself: never onboarded, hooks stay silent."""
    return (root / "create-tess" / "package.json").exists() and not (root / BRAIN_JSON).exists()


# ---------------------------------------------------------------- time ------

def detect_timezone() -> str:
    """Best-effort IANA name: $TZ, then /etc/localtime's zoneinfo target."""
    tz = os.environ.get("TZ", "").lstrip(":")
    if "/" in tz and not tz.startswith("/"):
        return tz
    try:
        target = os.path.realpath("/etc/localtime")
        if "zoneinfo/" in target:
            return target.split("zoneinfo/", 1)[1]
    except OSError:
        pass
    return "UTC"


def tzinfo_for(name: Optional[str]):
    """A tzinfo for an IANA name, or None when zoneinfo/tzdata is missing."""
    if not name:
        return None
    try:
        from zoneinfo import ZoneInfo  # py3.9+
        return ZoneInfo(name)
    except Exception:  # unknown zone or no tz database on this host
        return None


def valid_timezone(name: str) -> bool:
    return name == "UTC" or tzinfo_for(name) is not None


def now_iso(tz_name: Optional[str] = None) -> str:
    tz = tzinfo_for(tz_name)
    now = _dt.datetime.now(tz) if tz else _dt.datetime.now().astimezone()
    return now.replace(microsecond=0).isoformat()


def parse_iso(text: str) -> Optional[_dt.datetime]:
    if not text:
        return None
    try:
        value = _dt.datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    return value if value.tzinfo else value.astimezone()


def in_tz(moment: _dt.datetime, tz_name: Optional[str]) -> _dt.datetime:
    tz = tzinfo_for(tz_name)
    return moment.astimezone(tz) if tz else moment


# ------------------------------------------------------------ file I/O ------

def atomic_write(path: Path, text: str) -> bool:
    """Write text atomically. Returns False (and writes nothing) if unchanged."""
    path = Path(path)
    if path.exists():
        try:
            if path.read_text(encoding="utf-8") == text:
                return False
        except (OSError, UnicodeDecodeError):
            pass
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, str(path))
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return True


def ensure_local_dir(path: Path) -> Path:
    """Create a never-committed local directory with a self-ignoring .gitignore."""
    path.mkdir(parents=True, exist_ok=True)
    marker = path / ".gitignore"
    if not marker.exists():
        atomic_write(marker, "*\n")
    return path


def log_error(root: Path, message: str, context: str = "") -> None:
    """stderr + .tess/state/brain/errors.log (never raises)."""
    line = "onboard: %s%s" % (message, (" [%s]" % context) if context else "")
    print(line, file=sys.stderr)
    if os.environ.get("TESS_BRAIN_NO_ERRORLOG"):
        return
    try:
        state = ensure_local_dir(root / STATE_DIR)
        with open(state / "errors.log", "a", encoding="utf-8") as fh:
            fh.write("%s %s\n" % (now_iso(), line))
    except OSError:
        pass


# ---------------------------------------------------------- brain.json ------

def default_brain(root: Path) -> Dict[str, Any]:
    tz = detect_timezone()
    now = now_iso(tz)
    ident = read_operator_profile(root)
    return {
        "schema": SCHEMA, "kind": "tess-brain", "created_at": now, "timezone": tz,
        "identity": {"operator_name": ident.get("operator_name", ""), "operator_slug": "",
                     "assistant_name": ident.get("assistant_name", "Tess"),
                     "pathway": ident.get("pathway", "chief-of-staff")},
        "principals": [], "modes": [], "primary_mode": "", "presets": [], "packs": [],
        "entity_roots": [],
        "onboarding": {"status": "pending", "step": 1, "total": TOTAL_STEPS, "answers": {},
                       "started_at": None, "completed_at": None, "remind_after": None},
        "runtimes": ["claude-code", "codex", "gemini"],
        "capture": {"journal": "commit-redacted", "since": now},
        "save": {"autopush": False},
        "remote": {"name": "origin", "url": None, "visibility": "unknown", "verified_via": None},
        "framework_remote_patterns": list(FRAMEWORK_REMOTE_PATTERNS),
        "state_cards": "memory/projects",
        "budgets": dict(BUDGETS),
    }


def read_operator_profile(root: Path) -> Dict[str, Any]:
    path = root / "operator" / "profile.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def load_brain(root: Path) -> Optional[Dict[str, Any]]:
    path = root / BRAIN_JSON
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise BrainError("brain/brain.json is not valid JSON (%s); fix or restore it from git" % exc, 2)
    if not isinstance(data, dict) or data.get("kind") != "tess-brain":
        raise BrainError("brain/brain.json is not a tess-brain v1 file", 2)
    return data


def save_brain(root: Path, data: Dict[str, Any]) -> bool:
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    return atomic_write(root / BRAIN_JSON, text)


# -------------------------------------------------------------- status ------

def status_of(root: Path) -> Dict[str, Any]:
    """The one status object every command and hook reads."""
    if is_source_repo(root):
        return {"status": "source-repo", "step": None, "total": TOTAL_STEPS,
                "ready_to_apply": False,
                "hint": "npm create tess@latest <folder>, or say 'convert this clone'"}
    brain = load_brain(root)
    if brain is None:
        return {"status": "pending", "step": 1, "total": TOTAL_STEPS, "ready_to_apply": False}
    onb = brain.get("onboarding") or {}
    status = onb.get("status", "pending")
    if status == "deferred" and _due(onb.get("remind_after")):
        status = "pending"
    from . import answers as _answers  # local import: answers imports state
    step = _answers.next_step(brain)
    out = {"status": status, "step": step, "total": TOTAL_STEPS,
           "ready_to_apply": status == "in_progress" and _answers.all_answered(brain),
           "modes": brain.get("modes", []), "presets": brain.get("presets", []),
           "remind_after": onb.get("remind_after")}
    if status in ("complete", "skipped"):
        out["step"] = None
    return out


def _due(remind_after: Optional[str]) -> bool:
    when = parse_iso(remind_after or "")
    if when is None:
        return True
    return _dt.datetime.now(when.tzinfo) >= when


def status_line(st: Dict[str, Any]) -> str:
    s = st["status"]
    if s == "in_progress":
        return "in_progress(%s)" % st.get("step")
    return s

