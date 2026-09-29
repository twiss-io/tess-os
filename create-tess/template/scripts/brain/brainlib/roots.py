"""Extra transcript roots: which OTHER folders' conversations count as this instance's.

GPT-6 review round 2, R6: `capture.also_cwd` in brain/brain.json was read as a
list of extra session folders. brain.json is a repo file, so a planted
`"also_cwd": ["/"]` (or another client's path) journaled every project's
conversations into this brain as the operator's words. brain.json's value is
now ignored. The operator adds a root with

    python3 scripts/brain/tessbrain.py roots add <path>

at a real terminal (an agent's shell has no TTY): the command shows what the
root grants and asks for "yes". Roots are stored in the per-project state
OUTSIDE the repo (extstate.py, roots.json, 0600). Refused: relative paths, `/`,
the home folder or anything above it, anything outside the home folder, a
folder that contains this instance (it would take in its neighbours), and a
folder that holds or sits inside another Tess instance.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

from . import extstate
from .config import Config, log_error

FILE = "roots.json"
WALK_DIRS = 4000


def _real(p: str) -> str:
    return os.path.realpath(os.path.expanduser(str(p)))


def _inside(child: str, parent: str) -> bool:
    return child == parent or child.startswith(parent.rstrip(os.sep) + os.sep)


def _is_instance(d: str) -> bool:
    return os.path.isfile(os.path.join(d, "brain", "brain.json"))


def _other_instance(real: str, root: str) -> str:
    """A Tess instance other than this one at, above or below `real` ('' when none)."""
    up = real
    while True:
        if up != root and _is_instance(up):
            return up
        parent = os.path.dirname(up)
        if parent == up:
            break
        up = parent
    seen = 0
    for base, dirs, _ in os.walk(real):
        seen += 1
        if seen > WALK_DIRS:
            return "(too many folders to check under %s)" % real
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "node_modules"]
        if base != root and _is_instance(base):
            return base
        if base.count(os.sep) - real.count(os.sep) >= 4:
            dirs[:] = []
    return ""


def problem(cfg: Config, path: str, strict: bool = True) -> str:
    """'' when `path` may be an extra root of this instance, else why not. strict = at `roots add` time."""
    if not path or not os.path.isabs(os.path.expanduser(str(path))):
        return "not an absolute path"
    real, home, root = _real(path), _real("~"), _real(str(cfg.root))
    if real == os.sep:
        return "the filesystem root would take in every project on this computer"
    if _inside(home, real):
        return "your home folder (or a folder above it) would take in every project in it"
    if _inside(root, real):
        return "it contains this instance, so it would take in the projects next to it"
    if _inside(real, root):
        return "it is inside this instance already"
    if strict:
        if not _inside(real, home):
            return "it is outside your home folder (%s)" % home
        other = _other_instance(real, root)
        if other:
            return "it holds another Tess instance: %s" % other
    return ""


def _path(cfg: Config):
    d = extstate.project_dir(cfg)
    return (d / FILE) if d is not None else None


def extra(cfg: Config) -> List[str]:
    """The operator's extra roots (outside the repo), each re-checked; never brain.json."""
    p = _path(cfg)
    if p is None or not p.is_file():
        return []
    from .provenance import _owned_private
    why = _owned_private(p, 0o077)
    if why:
        log_error(cfg, "roots: ignoring %s: %s" % (p, why))
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log_error(cfg, "roots: unreadable %s" % p, exc)
        return []
    out = []
    for r in (data.get("roots") if isinstance(data, dict) else None) or []:
        why = problem(cfg, str(r), strict=False)
        if why:
            log_error(cfg, "roots: ignoring %s: %s" % (r, why))
        else:
            out.append(_real(str(r)))
    return out


def save(cfg: Config, paths: List[str]) -> None:
    p = _path(cfg)
    if p is None:
        raise OSError("the brain's private state folder is unavailable (run this outside any sandbox)")
    tmp = p.with_name(FILE + ".tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump({"roots": sorted(set(paths))}, fh, indent=2)
    os.replace(str(tmp), str(p))


def _codex_sessions_under(real: str) -> int:
    from .parsers import codex
    try:
        return len(codex.discover(Path(real), None, [], 90, time.time() + 5))
    except Exception:  # noqa: BLE001 - only an estimate for the prompt
        return -1


def cmd_roots(cfg: Config, a) -> Tuple[int, Dict]:
    action, path = a.roots_cmd, getattr(a, "path", "")
    if action == "list":
        ignored = (cfg.data.get("capture") or {}).get("also_cwd")
        out: Dict = {"roots": extra(cfg)}
        if ignored:
            out["ignored"] = "brain.json capture.also_cwd is ignored; add roots with `roots add <path>`"
        return 0, out
    if action == "remove":
        save(cfg, [r for r in extra(cfg) if r != _real(path)])
        return 0, {"roots": extra(cfg)}
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return 1, {"error": "roots add must be run by you at a terminal (it widens whose conversations this "
                            "brain treats as yours); an agent or a pipe cannot do it"}
    why = problem(cfg, path, strict=True)
    if why:
        return 1, {"error": "refused %s: %s" % (path, why)}
    real = _real(path)
    n = _codex_sessions_under(real)
    print("This lets conversations whose working folder is inside\n  %s\nbe journaled into THIS brain (%s) as "
          "your own words, and count as your decisions and confirmations." % (real, cfg.root))
    if n >= 0:
        print("Codex sessions from the last 90 days found there now: %d" % n)
    try:
        answer = input('Type "yes" to allow it: ').strip().lower()
    except EOFError:
        answer = ""
    if answer != "yes":
        return 1, {"error": "not added"}
    save(cfg, extra(cfg) + [real])
    return 0, {"added": real, "roots": extra(cfg),
               "note": "conversations under %s will be journaled here from the next sync" % real}
