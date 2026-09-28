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
    this launcher, `vault-dispatch-scan.py`, and every `scripts/brain/**/*.py`
    file the onboarding hook can import.

`--closure DIR` additionally verifies every `*.py` under DIR (recursive,
`__pycache__` skipped) against the pin list and refuses if any is unpinned
or changed: the entry script imports its siblings, and an extra module such
as `DIR/json.py` would shadow the standard library.

Fail closed. On any mismatch, missing file, symlink or parse error the
script is NOT run. `--on-fail warn` (default) prints a visible warning and
exits 0 so the session keeps working; `--on-fail block` exits 2 so Claude
Code blocks the tool call (used for the dispatch secret scan, whose whole
job is to block).

Python targets run with `-I -B -X pycache_prefix=<empty temp dir>`: no
PYTHONPATH/user-site injection, and no stale or planted `.pyc` from the
working tree is ever loaded.

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

from __future__ import annotations

import hashlib
import json
import os
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
PIN_SET_FILES = (SELF_REL, ".claude/hooks/vault-dispatch-scan.py")
PIN_SET_TREES = ("scripts/brain",)
PINS_HEADER = (
    "# pinned-scripts.sha256 — hook-executed scripts with no .tess/core master.\n"
    "# Pinned by tess.lock (this file's own base_sha); read by .claude/hooks/run-pinned.py.\n"
    "# Regenerate: python3 .claude/hooks/run-pinned.py --regen-pins, then\n"
    "#   ./tessctl lock --regen --only .tess/core/pinned-scripts.sha256\n"
)
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


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


def _tree_py(root: Path, tree: str) -> list:
    base = root / tree
    out = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
        for name in sorted(filenames):
            if name.endswith(".py"):
                out.append(Path(dirpath, name).relative_to(root).as_posix())
    return out


def verify(root: Path, target: str, closure: str | None) -> Path:
    """Return the verified target path, or raise PinError."""
    entries = _lock_entries(root)
    pins = _pins(root, entries)
    _check(root, SELF_REL, entries, pins)
    if closure:
        for rel in _tree_py(root, closure):
            _check(root, rel, entries, pins)
        for rel in pins:
            if rel.startswith(closure.rstrip("/") + "/"):
                _safe_rel(root, rel)
    return _check(root, target, entries, pins)


def regen_pins(root: Path) -> None:
    rels = list(PIN_SET_FILES)
    for tree in PIN_SET_TREES:
        rels += _tree_py(root, tree)
    body = "".join(f"{_sha256(root / rel)}  {rel}\n" for rel in rels)
    (root / PINS_REL).write_text(PINS_HEADER + body, encoding="utf-8")
    print(f"wrote {PINS_REL} ({len(rels)} scripts). Now run: "
          f"./tessctl lock --regen --only {PINS_REL}")


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


def _run(path: Path, args: list) -> int:
    if path.suffix == ".py":
        with tempfile.TemporaryDirectory(prefix="tess-hook-") as tmp:
            cmd = [sys.executable, "-I", "-B", "-X", f"pycache_prefix={tmp}/none", str(path), *args]
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
        path = verify(root, target, closure)
        return _run(path, rest)
    except PinError as exc:
        return _fail(mode, target, str(exc))
    except Exception as exc:  # fail closed on anything unexpected
        return _fail(mode, target, f"verification errored ({type(exc).__name__}: {exc})")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
