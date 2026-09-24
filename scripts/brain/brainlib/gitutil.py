"""Thin git wrappers. Read-only helpers never raise; write helpers return (rc, out).

Hooks never call the write helpers (spec: hooks never write to git).
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

TIMEOUT = 20


def run(root: Path, args: List[str], stdin: Optional[str] = None, timeout: int = TIMEOUT) -> Tuple[int, str, str]:
    try:
        p = subprocess.run(["git", "-C", str(root)] + args, input=stdin, capture_output=True, text=True,
                           timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, "", str(exc)


def is_repo(root: Path) -> bool:
    return run(root, ["rev-parse", "--is-inside-work-tree"])[0] == 0


def head(root: Path) -> str:
    rc, out, _ = run(root, ["rev-parse", "--short=12", "HEAD"])
    return out.strip() if rc == 0 else ""


def branch(root: Path) -> str:
    rc, out, _ = run(root, ["rev-parse", "--abbrev-ref", "HEAD"])
    return out.strip() if rc == 0 else ""


def porcelain(root: Path, paths: List[str]) -> List[Tuple[str, str]]:
    """[(XY status, path)] for the given pathspecs, untracked files included."""
    rc, out, _ = run(root, ["status", "--porcelain=v1", "-z", "--untracked-files=all", "--"] + paths)
    if rc != 0:
        return []
    items = out.split("\0")
    res, i = [], 0
    while i < len(items):
        rec = items[i]
        i += 1
        if len(rec) < 4:
            continue
        xy, path = rec[:2], rec[3:]
        if xy[0] in "RC":
            i += 1  # skip the rename source
        res.append((xy, path))
    return res


def ignored(root: Path, paths: List[str]) -> List[str]:
    if not paths:
        return []
    rc, out, _ = run(root, ["check-ignore", "--no-index", "--stdin", "-z"], stdin="\0".join(paths) + "\0")
    return [p for p in out.split("\0") if p] if rc in (0, 1) else []


def remote_url(root: Path, name: str) -> str:
    rc, out, _ = run(root, ["remote", "get-url", name])
    return out.strip() if rc == 0 else ""


def unpushed(root: Path) -> Tuple[int, str]:
    """(count, note). Commits on HEAD not on its upstream (or on no remote at all)."""
    rc, out, _ = run(root, ["rev-list", "--count", "@{u}..HEAD"])
    if rc == 0:
        return int(out.strip() or 0), ""
    rc, out, _ = run(root, ["rev-list", "--count", "HEAD", "--not", "--remotes"])
    if rc == 0:
        n = int(out.strip() or 0)
        return n, "no upstream" if n else ""
    return 0, "no commits"


def staged_files(root: Path) -> List[str]:
    rc, out, _ = run(root, ["diff", "--cached", "--name-only", "-z"])
    return [p for p in out.split("\0") if p] if rc == 0 else []


def tracked(root: Path, paths: List[str]) -> List[str]:
    rc, out, _ = run(root, ["ls-files", "-z", "--"] + paths)
    return [p for p in out.split("\0") if p] if rc == 0 else []


def hooks_dir(root: Path) -> Optional[Path]:
    rc, out, _ = run(root, ["rev-parse", "--git-path", "hooks"])
    if rc != 0:
        return None
    p = Path(out.strip())
    return p if p.is_absolute() else Path(root) / p
