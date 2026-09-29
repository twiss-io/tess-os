#!/usr/bin/env python3
"""run-pinned.py — the only way a Tess OS Claude Code hook runs a script.

Why this exists (v0.2.1, 2026-09-29 security review, MEDIUM "hooks run
agent-editable code"): hooks fire automatically on every session start,
prompt and tool call. Before v0.2.1 they executed whatever bytes sat at
`.claude/hooks/*.sh` or `scripts/brain/*.py`, so an agent (or anything else
that can write the working tree) could change what runs outside any review.
This launcher runs a hook script ONLY when the script exists and its sha256
matches the value pinned by `.tess/tess.lock`:

  * directly, when tess.lock has a core-managed entry whose live_path is the
    script (the `.claude/hooks/*.sh` guards: their `.tess/core/hooks/*`
    masters are pinned there); or
  * through `.tess/core/pinned-scripts.sha256`, a core file that tess.lock
    itself pins (base_sha). It lists scripts that have no `.tess/core` master:
    this launcher, `vault-dispatch-scan.py`, `tess-gate.py` (the Codex
    PreToolUse safety gate, v1.0), and every `scripts/brain/**/*.py` file the
    onboarding hook can import.

`--closure DIR` additionally verifies every `*.py` under DIR (recursive)
against the pin list and refuses if any is unpinned or changed: the entry
script imports its siblings, and an extra module such as `DIR/json.py` would
shadow the standard library. v1.0.1 (GPT-6 review round 2, HIGH): it also
refuses while DIR holds ANY other importable artifact, because Python's
import system prefers some of them over the verified source and none of them
is hashed: a native extension (`brainlib/__init__.so`, `.pyd`, `.dylib`, any
suffix from importlib.machinery.all_suffixes()), a sourceless `.pyc`/`.pyo`
outside `__pycache__`, a `.pth` file, or a symlink anywhere in the tree.
`__pycache__` directories are tolerated only as plain directories of plain
files: every target runs with `-X pycache_prefix=<empty temp dir>`, so
Python never reads them, and a `.pyc` inside `__pycache__` is never imported
without its source. Data directories without `__init__.py` (templates,
schemas) are allowed: once every code file in them is rejected they are at
most an empty namespace package, which ranks below any regular module.

Fail closed. On any mismatch, missing file, symlink or parse error the
script is NOT run. `--on-fail warn` (default) prints a visible warning and
exits 0 so the session keeps working; `--on-fail block` exits 2 so Claude
Code blocks the tool call (used for the dispatch secret scan, whose whole
job is to block).

Python targets run with `-I -B -X pycache_prefix=<empty temp dir>`: no
PYTHONPATH/user-site injection, and no stale or planted `.pyc` from the
working tree is ever loaded. The target's own bytes are read ONCE, hashed,
and those captured bytes are what the interpreter executes (a private temp
copy fed to a fixed `-c` bootstrap), so swapping the target file after the
check changes nothing. Sibling modules are still read from disk at import
time (see Known limits).

Maintainers: after a deliberate, reviewed change to a pinned script run
  python3 .claude/hooks/run-pinned.py --regen-pins
  ./tessctl lock --regen --only .tess/core/pinned-scripts.sha256
Both paths are security-tier (core/policy/policy.yaml), so the change needs
a covering signed verdict at the gate.

Known limits (documented in docs/HARNESS_HARDENING.md): this launcher is the
trust root and cannot verify itself against a tampered copy of itself; a
change made between the hash check and the interpreter reading the file
(a race) is not detected; tess.lock is committed, so an actor who can edit
both a script and tess.lock and pass the gate can re-pin.
"""

# Isolation first (v1.0.1, 2026-09-29 Codex review, HIGH "launcher startup
# imports planted modules"): run un-isolated, Python puts this file's own
# directory first on sys.path, so a planted `.claude/hooks/hashlib.py` or
# `json.py` would run the moment the imports below execute, before any pin
# is checked. Every shipped hook command already starts this launcher as
# `python3 -I -B` (no script directory or user site on sys.path, PYTHON*
# variables ignored, no .pyc written); a caller that forgets is re-executed
# that way here. Only `os` and `sys`, which the interpreter has loaded before
# any user code runs, are touched until then. (No `from __future__` import:
# it is a real import too.)
import os
import sys

if __name__ == "__main__" and not (sys.flags.isolated and sys.flags.dont_write_bytecode):
    try:
        os.execv(sys.executable, [sys.executable, "-I", "-B", os.path.abspath(__file__), *sys.argv[1:]])
    except OSError as _exc:
        sys.stderr.write("TESS HOOK NOT RUN: could not restart the hook launcher in isolated "
                         "mode (%s).\n" % _exc)
        sys.exit(2)

import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

LOCK_REL = ".tess/tess.lock"
PINS_REL = ".tess/core/pinned-scripts.sha256"
SELF_REL = ".claude/hooks/run-pinned.py"
# What --regen-pins writes: scripts that hooks run but that have no .tess/core master.
PIN_SET_FILES = (SELF_REL, ".claude/hooks/vault-dispatch-scan.py", ".claude/hooks/tess-gate.py")
PIN_SET_TREES = ("scripts/brain",)
PINS_HEADER = (
    "# pinned-scripts.sha256 — hook-executed scripts with no .tess/core master.\n"
    "# Pinned by tess.lock (this file's own base_sha); read by .claude/hooks/run-pinned.py.\n"
    "# Regenerate: python3 .claude/hooks/run-pinned.py --regen-pins, then\n"
    "#   ./tessctl lock --regen --only .tess/core/pinned-scripts.sha256\n"
)
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
# The only Python files allowed beside this launcher. Anything else importable
# there (a planted `hashlib.py`, a sourceless `.pyc`, a native module, a
# package directory) would shadow the standard library for any interpreter
# started without -I, so the launcher refuses to run while one exists.
BESIDE_ALLOWED = frozenset({"run-pinned.py", "vault-dispatch-scan.py", "tess-gate.py"})
_IMPORTABLE_SUFFIXES = (".py", ".pyc", ".pyo", ".pyw", ".so", ".pyd", ".dylib")
# Anything Python could load as code from a closure directory, on any
# platform (the current interpreter's own suffixes are added at check time).
_CLOSURE_CODE_SUFFIXES = (".py", ".pyc", ".pyo", ".pyw", ".so", ".pyd", ".dylib", ".dll", ".pth")
# The fixed program a Python target runs under: it executes the verified
# bytes captured by the launcher (argv[1], a file in the launcher's private
# temp dir) as __main__, with __file__ and argv naming the real script.
_BOOTSTRAP = (
    "import sys\n"
    "_tess_src_path, _tess_file = sys.argv[1], sys.argv[2]\n"
    "with open(_tess_src_path, 'rb') as _tess_fh:\n"
    "    _tess_code = compile(_tess_fh.read(), _tess_file, 'exec')\n"
    "sys.argv[:] = sys.argv[2:]\n"
    "__file__ = _tess_file\n"
    "del _tess_src_path, _tess_file, _tess_fh\n"
    "exec(_tess_code)\n"
)


class PinError(Exception):
    """Verification failed; the message is shown to the operator."""


def _root() -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    return Path(env) if env else Path(__file__).resolve().parent.parent.parent


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _lock_entries(root: Path) -> dict:
    """{core_key: {"base_sha": hex, "live_path": str|None}} from tess.lock's files: map.

    A line scanner, not a YAML parser: hooks run under the system python3,
    which may not have PyYAML. It reads only the two fields it needs and
    fails closed if the file is missing or yields nothing."""
    path = root / LOCK_REL
    if not path.is_file():
        raise PinError(f"{LOCK_REL} not found, so no hook script can be verified")
    entries: dict = {}
    section = None
    key = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw and not raw.startswith(" ") and not raw.startswith("#"):
            section = raw.split(":", 1)[0].strip()
            key = None
            continue
        if section != "files":
            continue
        m = re.match(r"^  (\S[^:]*):\s*$", raw)
        if m:
            key = m.group(1).strip().strip("'\"")
            entries[key] = {"base_sha": None, "live_path": None}
            continue
        if key is None:
            continue
        m = re.match(r"^    base_sha:\s*'?sha256:([0-9a-f]{64})'?\s*$", raw)
        if m:
            entries[key]["base_sha"] = m.group(1)
            continue
        m = re.match(r"^    live_path:\s*(.*?)\s*$", raw)
        if m:
            val = m.group(1).strip("'\"")
            entries[key]["live_path"] = None if val in ("", "null", "~") else val
    if not entries:
        raise PinError(f"{LOCK_REL} has no files entries, so no hook script can be verified")
    return entries


def _pins(root: Path, entries: dict) -> dict:
    """{live_rel: hex} from the pin list, after checking the list against tess.lock."""
    core_key = PINS_REL
    want = (entries.get(core_key) or {}).get("base_sha")
    path = root / PINS_REL
    if not want:
        raise PinError(f"{LOCK_REL} does not pin {PINS_REL}")
    if not path.is_file() or path.is_symlink():
        raise PinError(f"{PINS_REL} is missing (or is a symlink)")
    if _sha256(path) != want:
        raise PinError(f"{PINS_REL} does not match the sha pinned in {LOCK_REL}")
    pins: dict = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2 or not _HEX64.match(parts[0]):
            raise PinError(f"{PINS_REL} has a malformed line: {line[:80]!r}")
        pins[parts[1].strip()] = parts[0]
    return pins


def _expected(rel: str, entries: dict, pins: dict) -> str:
    for attrs in entries.values():
        if attrs.get("live_path") == rel and attrs.get("base_sha"):
            return attrs["base_sha"]
    if rel in pins:
        return pins[rel]
    raise PinError(f"{rel} is not pinned by {LOCK_REL}")


def _safe_rel(root: Path, rel: str) -> Path:
    if not rel or rel.startswith("/") or ".." in Path(rel).parts:
        raise PinError(f"refusing a script path outside the project: {rel!r}")
    path = root / rel
    if path.is_symlink():
        raise PinError(f"{rel} is a symlink; hook scripts must be regular files")
    if not path.is_file():
        raise PinError(f"{rel} does not exist")
    return path


def _check(root: Path, rel: str, entries: dict, pins: dict) -> Path:
    path = _safe_rel(root, rel)
    if _sha256(path) != _expected(rel, entries, pins):
        raise PinError(f"{rel} does not match the sha pinned in {LOCK_REL} (edited since release?)")
    return path


def _check_capture(root: Path, rel: str, entries: dict, pins: dict) -> bytes:
    """The target's bytes, read once and verified; these exact bytes are run."""
    path = _safe_rel(root, rel)
    fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as fh:
        data = fh.read()
    if hashlib.sha256(data).hexdigest() != _expected(rel, entries, pins):
        raise PinError(f"{rel} does not match the sha pinned in {LOCK_REL} (edited since release?)")
    return data


def _code_suffixes() -> tuple:
    try:
        import importlib.machinery as _m  # stdlib; safe: we run with -I
        extra = tuple(s.lower() for s in _m.all_suffixes())
    except Exception:  # fail closed: the static list still applies
        extra = ()
    return tuple(sorted(set(_CLOSURE_CODE_SUFFIXES + extra)))


def _check_closure(root: Path, closure: str, entries: dict, pins: dict) -> None:
    """Refuse unless every importable artifact under `closure` is a pinned,
    unchanged `.py` file (see the module docstring)."""
    rel_top = closure.strip("/")
    if not rel_top or rel_top.startswith("/") or ".." in Path(rel_top).parts:
        raise PinError(f"refusing a closure outside the project: {closure!r}")
    base = root / rel_top
    for part in range(1, len(Path(rel_top).parts) + 1):
        if (root / Path(*Path(rel_top).parts[:part])).is_symlink():
            raise PinError(f"{rel_top} passes through a symlink; hook code must be regular files")
    if not base.is_dir():
        raise PinError(f"{rel_top} does not exist")
    suffixes = _code_suffixes()
    bad = []
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        here = Path(dirpath)
        in_cache = here.name == "__pycache__"
        for name in sorted(dirnames + filenames):
            path = here / name
            rel = path.relative_to(root).as_posix()
            if os.path.islink(path) or not (os.path.isdir(path) or os.path.isfile(path)):
                bad.append(f"{rel} (symlink or special file)")
                continue
            if os.path.isdir(path):
                if in_cache:
                    bad.append(f"{rel} (directory inside __pycache__)")
                continue
            if in_cache:
                continue  # plain files in a plain __pycache__: never read (pycache_prefix)
            low = name.lower()
            if low.endswith(suffixes) or ".cpython-" in low or ".abi3." in low:
                if name.endswith(".py"):
                    _check(root, rel, entries, pins)  # raises when unpinned or changed
                else:
                    bad.append(f"{rel} (importable code that is not a pinned .py file)")
        dirnames[:] = sorted(d for d in dirnames if not os.path.islink(here / d))
    if bad:
        raise PinError(
            f"{rel_top} holds code Tess did not ship and cannot verify ("
            + ", ".join(bad[:5]) + ("" if len(bad) <= 5 else ", ...")
            + "); Python could load it instead of the verified scripts. Move or delete it")


def _tree_py(root: Path, tree: str) -> list:
    base = root / tree
    out = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
        for name in sorted(filenames):
            if name.endswith(".py"):
                out.append(Path(dirpath, name).relative_to(root).as_posix())
    return out


def _check_beside_launcher(here: Path) -> None:
    """Refuse when anything importable other than the pinned hook scripts
    sits in the launcher's own directory (see BESIDE_ALLOWED)."""
    extra = []
    for name in sorted(os.listdir(here)):
        path = here / name
        if name in BESIDE_ALLOWED:
            continue
        if name == "__pycache__" and path.is_dir() and not path.is_symlink():
            continue  # never read: every interpreter here runs with -I -B
        if path.is_dir() or name.lower().endswith(_IMPORTABLE_SUFFIXES):
            extra.append(name)
    if extra:
        raise PinError(
            "unexpected Python code sits beside the hook launcher in .claude/hooks/ ("
            + ", ".join(extra[:5]) + ("" if len(extra) <= 5 else ", ...")
            + "); it could replace standard modules the launcher loads. Move or delete it")


def verify(root: Path, target: str, closure: "str | None") -> Path:
    """Return the verified target path, or raise PinError."""
    _check_beside_launcher(Path(__file__).resolve().parent)
    entries = _lock_entries(root)
    pins = _pins(root, entries)
    _check(root, SELF_REL, entries, pins)
    if closure:
        _check_closure(root, closure, entries, pins)
        for rel in pins:
            if rel.startswith(closure.rstrip("/") + "/"):
                _safe_rel(root, rel)
    return _check(root, target, entries, pins)


def verify_capture(root: Path, target: str, closure: "str | None") -> "tuple[Path, bytes | None]":
    """verify(), plus the target's captured bytes when it is a Python file."""
    path = verify(root, target, closure)
    if path.suffix != ".py":
        return path, None
    entries = _lock_entries(root)
    return path, _check_capture(root, target, entries, _pins(root, entries))


def regen_pins(root: Path) -> None:
    rels = list(PIN_SET_FILES)
    for tree in PIN_SET_TREES:
        rels += _tree_py(root, tree)
    body = "".join(f"{_sha256(root / rel)}  {rel}\n" for rel in rels)
    (root / PINS_REL).write_text(PINS_HEADER + body, encoding="utf-8")
    print(f"wrote {PINS_REL} ({len(rels)} scripts). Now run: "
          f"./tessctl lock --regen --only {PINS_REL}")


# --------------------------------------------------------------------------- enforcement anchor
# v1.0.0 (final reviews, GPT-6 + Cyra BLOCK "gate rollback"): the pins above
# live in the working tree, so any git route that writes an older or stubbed
# gate together with matching pins (rebase --onto, replace refs, fetch
# --update-head-ok, bisect, archive | tar, sparse-checkout) passed every check
# here. The ANCHOR is the sha256 of every enforcement file, kept OUTSIDE the
# repository: <OS user home>/.config/tess/projects/<project id>/anchor.json.
# It is written only by the create-tess wizard, `tessctl update`/`self-update`
# after a verified signed release, and an interactive `tessctl anchor accept`.
# Before any target runs, every anchored file must still hash to its anchored
# value; otherwise the gate denies every call (block) and every other hook is
# skipped with a warning (warn). A path marker (projects/by-path/<sha>.json)
# records that this checkout HAS an anchor, so deleting or orphaning it (a new
# root commit changes the project id) is a stop too, not a silent pass.
# Known limit: a process running as the same OS user can rewrite the anchor
# (the gate denies it to the agent, but a program built at run time is not
# seen): this turns a silent rollback into a loud stop, not an OS boundary.
ANCHOR_FORMAT = "tess-enforcement-anchor/1"
ANCHOR_FILES = (
    SELF_REL, ".claude/hooks/tess-gate.py", ".claude/hooks/vault-dispatch-scan.py",
    ".claude/hooks/dispatch-guard.sh", ".claude/hooks/task-lock-set.sh",
    ".claude/hooks/task-lock-clear.sh", ".claude/hooks/utc-local-context.sh",
    "scripts/brain/onboard.py", "scripts/brain/tessbrain.py",
    PINS_REL, LOCK_REL, ".claude/settings.json", ".codex/config.toml", ".codex/rules/tess.rules",
    "core/policy/policy.yaml", ".tess/core/policy/policy.yaml", ".tess/bin/tessctl", "tessctl",
)
# Git hooks Tess installs (gate, vault, public-remote and brain guards); anchored
# when present with a Tess marker at anchor time, keyed "git-hooks/<name>".
ANCHOR_GIT_HOOKS = ("pre-commit", "pre-push", "post-merge")
ANCHOR_GIT_PREFIX = "git-hooks/"
ANCHOR_GIT_MARKER = "# tess-"
ANCHOR_STOP = ("Tess's safety files have changed since the last approved install or update, "
               "so Tess has stopped all actions. Run `tessctl restore` to put them back, or "
               "`tessctl anchor accept` if you changed them on purpose.")
ANCHOR_LOST = ("Tess's record of its approved safety files is missing or unreadable, so Tess "
               "has stopped all actions. Run `tessctl anchor accept` in your own terminal to "
               "check and record the current files.")


class AnchorError(PinError):
    """The enforcement files differ from the anchor (message: plain stop line)."""

    def __init__(self, message: str, problems: list):
        super().__init__(message)
        self.problems = problems


def anchor_os_home() -> Path:
    """The home in the OS user record (never $HOME / $XDG_CONFIG_HOME)."""
    try:
        import pwd
        return Path(pwd.getpwuid(os.getuid()).pw_dir)
    except (ImportError, KeyError, AttributeError):
        return Path.home()


def anchor_base() -> Path:
    return anchor_os_home() / ".config" / "tess" / "projects"


def anchor_path_key(root: Path) -> str:
    return hashlib.sha256(os.path.realpath(str(root)).encode("utf-8", "surrogateescape")).hexdigest()


def anchor_project_id(root: Path) -> "str | None":
    """The root commit of HEAD's first-parent history, read with replace refs
    and GIT_* overrides ignored (same id `tessctl` uses for the anchor)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["GIT_NO_REPLACE_OBJECTS"] = "1"
    try:
        r = subprocess.run(["git", "-C", str(root), "-c", "core.fsmonitor=false", "rev-list",
                            "--first-parent", "--max-parents=0", "HEAD", "--"],
                           capture_output=True, text=True, timeout=60, env=env)
    except (OSError, subprocess.SubprocessError):
        return None
    roots = r.stdout.split() if r.returncode == 0 else []
    if len(roots) != 1 or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", roots[0]):
        return None
    return roots[0]


def anchor_git_hooks_dir(root: Path) -> "Path | None":
    """<common git dir>/hooks, read from .git directly (no git call)."""
    dot = root / ".git"
    if dot.is_dir():
        return dot / "hooks"
    try:
        text = dot.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.match(r"^gitdir:\s*(.+?)\s*$", text, re.M)
    if not m:
        return None
    gitdir = Path(m.group(1)) if os.path.isabs(m.group(1)) else root / m.group(1)
    common = gitdir
    try:
        c = (gitdir / "commondir").read_text(encoding="utf-8").strip()
        common = Path(c) if os.path.isabs(c) else gitdir / c
    except OSError:
        pass
    return common / "hooks"


def anchor_file_path(root: Path, rel: str) -> "Path | None":
    if rel.startswith(ANCHOR_GIT_PREFIX):
        hooks = anchor_git_hooks_dir(root)
        return hooks / rel[len(ANCHOR_GIT_PREFIX):] if hooks else None
    return root / rel


def lock_projection(text: str) -> str:
    """sha256 over the enforcement fields of tess.lock: every files: entry's
    base_sha, live_path and tier, and the framework's release-key pins.
    Status, timestamps and render records change in normal use and are left
    out (same line scanner as _lock_entries: no YAML parser in a hook)."""
    files: dict = {}
    fw: dict = {}
    section = key = None
    for raw in text.splitlines():
        if raw and not raw.startswith((" ", "#")):
            section, key = raw.split(":", 1)[0].strip(), None
            continue
        if section == "framework":
            m = re.match(r"^  (trusted_key_fingerprint|trusted_ssh_key_fingerprint):\s*(.*?)\s*$", raw)
            if m:
                fw[m.group(1)] = m.group(2).strip("'\"")
            continue
        if section != "files":
            continue
        m = re.match(r"^  (\S[^:]*):\s*$", raw)
        if m:
            key = m.group(1).strip().strip("'\"")
            files[key] = {}
            continue
        m = re.match(r"^    (base_sha|live_path|tier):\s*(.*?)\s*$", raw)
        if m and key is not None:
            files[key][m.group(1)] = m.group(2).strip("'\"")
    canon = json.dumps({"files": files, "framework": fw}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def anchor_digest(rel: str, data: bytes) -> str:
    if rel == LOCK_REL:
        return lock_projection(data.decode("utf-8", "replace"))
    return hashlib.sha256(data).hexdigest()


def anchor_read_file(path: Path) -> "bytes | None":
    """A regular file's bytes; None when missing, a symlink or unreadable."""
    try:
        if path.is_symlink() or not path.is_file():
            return None
        with path.open("rb") as fh:
            return fh.read()
    except OSError:
        return None


def _anchor_json(path: Path) -> "dict | None":
    """A private JSON file of this user's (0600 or stricter, not a symlink)."""
    try:
        st = os.lstat(path)
    except OSError:
        return None
    import stat as _stat
    if _stat.S_ISLNK(st.st_mode) or not _stat.S_ISREG(st.st_mode):
        raise AnchorError(ANCHOR_LOST, [f"{path} is not a regular file"])
    if hasattr(os, "getuid") and st.st_uid != os.getuid():
        raise AnchorError(ANCHOR_LOST, [f"{path} is not owned by this user"])
    if os.name == "posix" and st.st_mode & 0o022:
        raise AnchorError(ANCHOR_LOST, [f"{path} is writable by other users"])
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AnchorError(ANCHOR_LOST, [f"{path} is unreadable ({type(exc).__name__})"])
    if not isinstance(doc, dict):
        raise AnchorError(ANCHOR_LOST, [f"{path} is not a JSON object"])
    return doc


def anchor_locate(root: Path) -> tuple:
    """(anchor dict | None, where). None with where "" = this checkout was
    never anchored. Raises AnchorError when an anchor is expected but gone."""
    base = anchor_base()
    marker = _anchor_json(base / "by-path" / (anchor_path_key(root) + ".json"))
    if marker is not None:
        pid = str(marker.get("project_id") or "")
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", pid):
            raise AnchorError(ANCHOR_LOST, ["the path marker names no project"])
    else:
        pid = anchor_project_id(root) or ""
        if not pid:
            return None, ""
    pdir = base / pid
    doc = _anchor_json(pdir / "anchor.json")
    if doc is None:
        if marker is not None or _anchor_json(pdir / "expected.json") is not None:
            raise AnchorError(ANCHOR_LOST, [f"{pdir / 'anchor.json'} is missing"])
        return None, ""
    if doc.get("format") != ANCHOR_FORMAT or not isinstance(doc.get("files"), dict):
        raise AnchorError(ANCHOR_LOST, ["the anchor has an unknown format"])
    return doc, str(pdir / "anchor.json")


def anchor_problems(root: Path, doc: dict) -> list:
    """Plain lines, one per anchored file that is missing or changed."""
    out = []
    for rel, rec in sorted(doc["files"].items()):
        want = rec.get("sha256") if isinstance(rec, dict) else None
        path = anchor_file_path(root, rel)
        data = anchor_read_file(path) if path else None
        if data is None:
            out.append(f"{rel} is missing")
        elif not want or anchor_digest(rel, data) != want:
            out.append(f"{rel} has changed")
    return out


def anchor_check(root: Path) -> "dict | None":
    """Raise AnchorError unless every anchored file matches; the anchor (or
    None for a checkout that was never anchored)."""
    doc, _where = anchor_locate(root)
    if doc is None:
        return None
    problems = anchor_problems(root, doc)
    if problems:
        raise AnchorError(ANCHOR_STOP, problems)
    return doc


def _fail(mode: str, target: str, reason: str) -> int:
    msg = (f"TESS HOOK NOT RUN: {target} was skipped because {reason}. "
           f"Tess only runs hook scripts that match the release pinned in {LOCK_REL}. "
           f"If you did not change it, restore it (`git checkout -- {target}` or reinstall "
           f"Tess OS); if the change is deliberate, see docs/HARNESS_HARDENING.md.")
    if mode == "block":
        print(msg + " This tool call is blocked until the script is restored.", file=sys.stderr)
        return 2
    print(msg, file=sys.stderr)
    print(json.dumps({"systemMessage": msg}))
    return 0


def _fail_anchor(mode: str, target: str, exc: AnchorError) -> int:
    """The anchor stop: block = deny this call with the one plain line; warn =
    say so and skip the hook (the session keeps its gate, which blocks)."""
    msg = f"TESS STOPPED: {exc}"
    if mode == "block":
        print(msg, file=sys.stderr)
        return 2
    msg = f"TESS HOOK NOT RUN: {target} was skipped. {exc}"
    print(msg, file=sys.stderr)
    print(json.dumps({"systemMessage": msg}))
    return 0


def _run(path: Path, args: list, code: "bytes | None" = None) -> int:
    if path.suffix == ".py":
        with tempfile.TemporaryDirectory(prefix="tess-hook-") as tmp:
            if code is None:
                raise PinError("the verified script bytes were not captured")
            src = Path(tmp) / "verified-source.py"
            fd = os.open(str(src), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as fh:
                fh.write(code)
            cmd = [sys.executable, "-I", "-B", "-X", f"pycache_prefix={tmp}/none", "-c", _BOOTSTRAP,
                   str(src), str(path), *args]
            return subprocess.run(cmd).returncode
    bash = "/bin/bash" if os.path.exists("/bin/bash") else shutil.which("bash")
    if not bash:
        raise PinError("bash was not found")
    return subprocess.run([bash, str(path), *args]).returncode


def main(argv: list) -> int:
    mode, closure = "warn", None
    args = list(argv)
    if args[:1] == ["--regen-pins"]:
        regen_pins(_root())
        return 0
    while args and args[0].startswith("--"):
        flag = args.pop(0)
        if flag == "--":
            break
        if flag == "--on-fail" and args and args[0] in ("warn", "block"):
            mode = args.pop(0)
        elif flag == "--closure" and args:
            closure = args.pop(0)
        else:
            return _fail("block", "run-pinned.py", f"it was called with an unknown flag {flag!r}")
    if not args:
        return _fail(mode, "run-pinned.py", "no script was named")
    target, rest = args[0], args[1:]
    root = _root()
    try:
        anchor_check(root)
    except AnchorError as exc:
        return _fail_anchor(mode, target, exc)
    except Exception as exc:  # fail closed on anything unexpected
        return _fail_anchor(mode, target, AnchorError(ANCHOR_LOST, [f"{type(exc).__name__}: {exc}"]))
    try:
        path, code = verify_capture(root, target, closure)
        return _run(path, rest, code)
    except PinError as exc:
        return _fail(mode, target, str(exc))
    except Exception as exc:  # fail closed on anything unexpected
        return _fail(mode, target, f"verification errored ({type(exc).__name__}: {exc})")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
