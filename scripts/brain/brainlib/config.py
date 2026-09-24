"""Instance configuration: brain/brain.json v1 (read-only here), paths, time.

ws-learn reads only the brain.json fields frozen in spec section 9.1:
identity, principals, timezone, modes, entity_roots, onboarding.status,
capture, save, remote, framework_remote_patterns, state_cards, budgets.
The one write is onboarding answer re-verification (see sync.py).
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_BUDGETS = {
    "start_here_lines": 150, "start_here_kib": 12, "entity_agents_kib": 6,
    "entity_agents_lines": 100, "index_lines": 150, "profile_kib": 12,
    "learned_entries": 100, "agents_chain_kib": 24, "session_start_kib": 4,
}
STATE_REL = ".tess/state/brain"
CONSENT_YES = ("shared", "yes", "true", "granted", "local")


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def quiet_env() -> bool:
    """TESS_BRAIN_QUIET / TESS_HEADLESS silence every hook."""
    return _truthy_env("TESS_BRAIN_QUIET") or _truthy_env("TESS_HEADLESS")


def default_root() -> Path:
    env = os.environ.get("TESS_BRAIN_ROOT")
    if env:
        return Path(env).resolve()
    # scripts/brain/tessbrain.py -> repo root is two levels above scripts/
    return Path(__file__).resolve().parents[3]


class Config:
    """Loaded view of one instance. Missing brain.json => not onboarded."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.brain = self.root / "brain"
        self.state = self.root / STATE_REL
        self.path = self.brain / "brain.json"
        self.data: Dict[str, Any] = {}
        self.load_error: Optional[str] = None
        if self.path.is_file():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                self.load_error = "brain.json unreadable: %s" % exc

    # -- instance state -------------------------------------------------
    @property
    def exists(self) -> bool:
        return bool(self.data)

    def is_source_repo(self) -> bool:
        """The Tess OS framework repo itself: create-tess/ present, no brain."""
        return (self.root / "create-tess" / "package.json").is_file() and not self.path.is_file()

    def active(self) -> bool:
        """Capture and learning run only in an instance that has a brain.json."""
        return self.exists and not self.is_source_repo()

    @property
    def onboarding_status(self) -> str:
        return str((self.data.get("onboarding") or {}).get("status") or "pending")

    # -- identity / principals -----------------------------------------
    @property
    def principals(self) -> List[Dict[str, Any]]:
        return [p for p in (self.data.get("principals") or []) if isinstance(p, dict) and p.get("slug")]

    @property
    def operator_slug(self) -> str:
        ident = self.data.get("identity") or {}
        if ident.get("operator_slug"):
            return str(ident["operator_slug"])
        for p in self.principals:
            if p.get("role") == "owner":
                return str(p["slug"])
        return str(self.principals[0]["slug"]) if self.principals else "operator"

    def principal(self, slug: str) -> Optional[Dict[str, Any]]:
        for p in self.principals:
            if p.get("slug") == slug:
                return p
        return None

    def local_speaker(self) -> Optional[str]:
        """Who types in this machine's runtime sessions.

        The principal whose `git_emails` holds this clone's `git config user.email`.
        When no principal lists any git email (a fresh install), the operator.
        When emails are listed but this clone's matches none, nobody (None): the
        words are omitted rather than credited to the wrong person; status says so.
        """
        if not hasattr(self, "_local_speaker"):
            email = _git_email(self.root)
            listed = [p for p in self.principals if p.get("git_emails")]
            hit = [p for p in listed if email and email.lower() in [str(e).lower() for e in p["git_emails"]]]
            self._local_speaker = (str(hit[0]["slug"]) if hit else None) if listed else self.operator_slug
            self.git_email = email
        return self._local_speaker

    def resolve_speaker(self, raw: str) -> Optional[str]:
        """Map a raw speaker id ('operator' = this machine's user, a slug or an alias) to a principal slug."""
        if raw in ("operator", "", None):
            return self.local_speaker()
        if self.principal(raw):
            return raw
        for p in self.principals:
            if raw in (p.get("aliases") or []) or raw in (p.get("git_emails") or []):
                return str(p["slug"])
        return None

    def consents(self, slug: str) -> bool:
        """Only an explicit yes journals a principal's words ('unknown' is not consent)."""
        p = self.principal(slug)
        return bool(p) and str(p.get("journal_consent", "shared")).lower() in CONSENT_YES

    # -- policy knobs --------------------------------------------------
    @property
    def journal_policy(self) -> str:
        return str((self.data.get("capture") or {}).get("journal") or "commit-redacted")

    @property
    def budgets(self) -> Dict[str, int]:
        out = dict(DEFAULT_BUDGETS)
        out.update({k: v for k, v in (self.data.get("budgets") or {}).items() if isinstance(v, int)})
        return out

    @property
    def also_cwd(self) -> List[str]:
        """capture.also_cwd (optional): earlier paths of this repo whose Codex/Gemini sessions belong here."""
        return [str(x) for x in ((self.data.get("capture") or {}).get("also_cwd") or []) if x]

    @property
    def entity_roots(self) -> List[str]:
        return [str(x) for x in (self.data.get("entity_roots") or [])]

    @property
    def state_cards(self) -> str:
        return str(self.data.get("state_cards") or "memory/projects")

    @property
    def autopush(self) -> bool:
        return bool((self.data.get("save") or {}).get("autopush"))

    @property
    def remote(self) -> Dict[str, Any]:
        return dict(self.data.get("remote") or {})

    @property
    def framework_patterns(self) -> List[str]:
        return [str(x) for x in (self.data.get("framework_remote_patterns") or ["github.com[:/]twiss-io/tess-os"])]

    # -- time ------------------------------------------------------------
    @property
    def tz(self) -> _dt.tzinfo:
        name = str(self.data.get("timezone") or "UTC")
        try:
            from zoneinfo import ZoneInfo  # py3.9+
            return ZoneInfo(name)
        except Exception:  # noqa: BLE001 - no tzdata: fall back to UTC, logged
            return _dt.timezone.utc

    def local(self, iso: str) -> _dt.datetime:
        return parse_iso(iso).astimezone(self.tz)

    def now(self) -> _dt.datetime:
        fixed = os.environ.get("TESS_BRAIN_NOW")  # tests pin the clock
        if fixed:
            return parse_iso(fixed).astimezone(self.tz)
        return _dt.datetime.now(self.tz)

    # -- local state -------------------------------------------------------
    def ensure_state(self) -> Path:
        """Create .tess/state/brain/ with a self-ignoring .gitignore ('*')."""
        self.state.mkdir(parents=True, exist_ok=True)
        gi = self.state / ".gitignore"
        if not gi.exists():
            gi.write_text("*\n", encoding="utf-8")
        return self.state

    def rel(self, path: Path) -> str:
        return Path(path).resolve().relative_to(self.root).as_posix()


def _git_email(root: Path) -> str:
    import subprocess
    try:
        p = subprocess.run(["git", "-C", str(root), "config", "user.email"], capture_output=True, text=True, timeout=5)
        return p.stdout.strip() if p.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def parse_iso(value: str) -> _dt.datetime:
    import re
    s = str(value).strip().replace("Z", "+00:00")
    m = re.match(r"^(.*?T\d\d:\d\d(?::\d\d)?)(?:\.(\d+))?(.*)$", s)
    if m:  # py3.9 fromisoformat wants 0, 3 or 6 fractional digits
        frac = (m.group(2) or "")[:6]
        s = m.group(1) + ("." + frac.ljust(6, "0") if frac else "") + m.group(3)
    dt = _dt.datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_dt.timezone.utc)
    return dt


def iso(dt: _dt.datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def log_error(cfg: Optional[Config], context: str, exc: BaseException = None) -> None:
    """Log with context to stderr and, once onboarded, to errors.log."""
    msg = "%s%s" % (context, (": %s: %s" % (type(exc).__name__, exc)) if exc else "")
    print("tessbrain: %s" % msg, file=sys.stderr)
    if cfg is None or not cfg.exists:
        return
    try:
        cfg.ensure_state()
        stamp = _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()
        with open(cfg.state / "errors.log", "a", encoding="utf-8") as fh:
            fh.write("%s %s\n" % (stamp, msg.replace("\n", " ")[:500]))
    except OSError:
        pass


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path: Path, data: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(str(tmp), str(path))


def write_text_if_changed(path: Path, text: str) -> bool:
    path = Path(path)
    try:
        if path.read_text(encoding="utf-8") == text:
            return False
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(str(tmp), str(path))
    return True
