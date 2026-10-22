"""Broad-access detection for shared conversation notes (v1.0.0 item d, Cyra M-3).

notes.private_read() withholds a session's replies when a tool input NAMES a
private path (`.private/`, `clients/`, `kb/`). A session can also reach
private content without naming it:

- a shell command that `cd`s into a directory under the instance
  (`cd kb && cat plan.md`), or runs with a working directory there;
- a shell command with a glob (`*`, `?`, `[`): `cat */secret.md`;
- a recursive read or search: `grep -r`, `rg`, `find`, `ls -R`, `git grep`, ...;
- a variable-expanded or command-substituted path: `cat $D/x`, `cat $(ls)`;
- a Grep/Glob tool call over `.`, the instance root (or no path: the cwd),
  an ancestor of it, or a private directory (or `brain/`, which holds
  `brain/.private/`).

Any of these marks the whole session: its replies are withheld from the shared
note, and journal.py keeps that sticky across later syncs. This is deliberately
conservative: a withheld reply costs a summary line, a leaked one costs a secret.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

SHELL_TOOLS = {"Bash", "shell", "local_shell", "exec_command", "shell_command", "container.exec",
               "run_shell_command", "unified_exec"}
SEARCH_TOOLS = {"Grep", "Glob", "glob", "grep", "search_file_content", "grep_search", "file_search"}
ALWAYS_BROAD_TOOLS = {"read_many_files"}

_GLOB = re.compile(r"[*?\[]")
_VAR = re.compile(r"\$(?:[A-Za-z_{(]|\d)|`")
_SEP = re.compile(r"\|\|?|&&?|;|\n|\(|\)|`|\$\(")
_RECURSIVE_CMDS = {"rg", "find", "fd", "fdfind", "ag", "ack", "tree", "du"}
_GREP_CMDS = {"grep", "egrep", "fgrep", "zgrep", "ggrep", "rgrep"}
_GREP_LONG = {"--recursive", "--dereference-recursive", "--directories=recurse", "--recurse"}
_CD_CMDS = {"cd", "pushd"}


def _tokens(segment: str) -> List[str]:
    return [t.strip("\"'") for t in segment.split() if t.strip("\"'")]


def _base(tok: str) -> str:
    return tok.rsplit("/", 1)[-1]


def _recursive(toks: List[str]) -> bool:
    for i, tok in enumerate(toks):
        name, rest = _base(tok), toks[i + 1:]
        if name in _RECURSIVE_CMDS or name == "rgrep":
            return True
        if name == "git" and rest[:1] == ["grep"]:
            return True
        if name in _GREP_CMDS:
            for j, a in enumerate(rest):
                if a in _GREP_LONG or (a == "-d" and rest[j + 1:j + 2] == ["recurse"]):
                    return True
                if a.startswith("-") and not a.startswith("--") and re.search(r"[rR]", a[1:]):
                    return True
        if name == "ls":
            if any(a == "--recursive" or (a.startswith("-") and not a.startswith("--") and "R" in a)
                   for a in rest):
                return True
    return False


def _cd_targets(toks: List[str]) -> List[str]:
    out = []
    for i, tok in enumerate(toks):
        if tok not in _CD_CMDS:
            continue
        args = [a for a in toks[i + 1:] if a not in ("-L", "-P", "-e", "-@")]
        if args:
            out.append(args[0])
    return out


def scan_shell(command: str) -> Tuple[bool, List[str]]:
    """(broad, cd targets) for one shell command string. `broad` is decided without the instance root:
    a glob, a variable or command substitution, or a recursive read/search anywhere in the command."""
    text = command or ""
    broad = bool(_GLOB.search(text) or _VAR.search(text))
    targets: List[str] = []
    for seg in _SEP.split(text):
        toks = _tokens(seg)
        broad = broad or _recursive(toks)
        targets += _cd_targets(toks)
    return broad, targets


def _as_obj(payload: Any) -> Any:
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except ValueError:
            return payload
    return payload


def _command_text(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(str(v) for v in value)
    return value if isinstance(value, str) else ""


def classify_call(name: str, payload: Any) -> Tuple[str, Optional[Dict[str, Any]]]:
    """('shell' | 'search' | 'broad' | '', details) for one tool call of any runtime."""
    obj = _as_obj(payload)
    d = obj if isinstance(obj, dict) else {}
    if name in ALWAYS_BROAD_TOOLS:
        return "broad", None
    if name in SEARCH_TOOLS:
        path = d.get("path") or d.get("dir_path") or d.get("directory") or ""
        return "search", {"path": path if isinstance(path, str) else ""}
    cmd = d.get("command", d.get("cmd")) if d else (obj if name in SHELL_TOOLS and isinstance(obj, str) else None)
    if name in SHELL_TOOLS or cmd is not None:
        wd = d.get("workdir") or d.get("cwd") or d.get("directory") or ""
        return "shell", {"command": _command_text(cmd), "workdir": wd if isinstance(wd, str) else ""}
    return "", None


def _norm(base: str, path: str) -> str:
    path = os.path.expanduser(path)
    return os.path.normpath(path if os.path.isabs(path) else os.path.join(base or "/", path))


def _rel_under(path: str, bases: Iterable[str]) -> Optional[str]:
    """`path` relative to the first base it lies in or under ('.' for the base itself), else None."""
    for b in bases:
        if path == b:
            return "."
        if path.startswith(b.rstrip("/") + "/"):
            return path[len(b.rstrip("/")) + 1:]
    return None


def _private_rel(rel: str) -> bool:
    parts = [p for p in rel.split("/") if p and p != "."]
    if not parts:
        return False
    if ".private" in parts or parts[0] == "kb" or parts == ["brain"]:
        return True
    return parts[0] == "clients" and (len(parts) == 1 or parts[1] != "_template")


def cd_is_broad(bases: List[str], cwd: str, target: str) -> bool:
    """A `cd` (or shell workdir) into a directory strictly under the instance; `cd -` is unknowable."""
    if target == "-":
        return True
    rel = _rel_under(_norm(cwd, target), bases)
    return rel is not None and rel != "."


def search_is_broad(bases: List[str], cwd: str, path: str) -> bool:
    """A Grep/Glob over the instance root, an ancestor of it, `brain/`, or a private directory."""
    p = _norm(cwd, path or ".")
    if any(b == p or b.startswith(p.rstrip("/") + "/") for b in bases):
        return True
    rel = _rel_under(p, bases)
    return rel is not None and _private_rel(rel)


def bases_for(root: str, cwd: str) -> List[str]:
    out = []
    for b in (root, os.path.realpath(root) if root else "", cwd):
        if b and b != "/" and os.path.normpath(b) not in out:
            out.append(os.path.normpath(b))
    return out


def broad_access(root: str, cwd: str, broad_shell: bool, cd_targets: List[str], search_paths: List[str]) -> bool:
    if broad_shell:
        return True
    bases = bases_for(root, cwd)
    here = os.path.normpath(cwd) if cwd else (bases[0] if bases else "/")
    return any(cd_is_broad(bases, here, t) for t in cd_targets) or \
        any(search_is_broad(bases, here, p) for p in search_paths)
