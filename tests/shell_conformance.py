"""
Real-shell conformance harness for the Tess gate (v1.0.x round 4).

Several reviews found commands where the gate's model of the shell differs
from what bash or zsh really do (B1, G1, G2, X). This harness compares the
two directly: every command the gate ALLOWS is run in real bash and zsh inside
a disposable sandbox project, and the protected control files must be
unchanged afterwards.

Safety (the harness never touches the real repo, the home directory or any
user config):
  * Everything happens under one fresh `tempfile.mkdtemp()` folder (the
    sandbox). The Tess instance in it is a copy; the real repo is only read.
  * Each command runs with a scrubbed environment (`env -i` style): HOME,
    XDG_CONFIG_HOME, TMPDIR and ZDOTDIR point into the sandbox, `bash
    --noprofile --norc` and `zsh -f` read no startup files, stdin is
    /dev/null, and a PATH-first folder of stubs replaces programs that reach
    outside a folder (network, the macOS preference and launch services,
    agent CLIs, package managers, sudo).
  * The shells run inside an OS-level jail that allows writes only below the
    sandbox and blocks the network: `sandbox-exec` on macOS, `bwrap` on
    Linux. With neither available the replay is skipped (or fails when
    TESS_CONFORMANCE_REQUIRED=1, as in CI). `confinement_self_test()` proves
    the jail refuses a write outside the sandbox before anything runs.
  * Each command gets a fresh copy of the pristine sandbox, a timeout, and its
    own process group, which is the only thing ever signalled.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
import json
import os
import platform
import shutil
import signal
import stat
import subprocess
import tarfile
import io
import tempfile
import time
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TIMEOUT = 10
# Programs that act outside a folder no matter where they run.
STUBS = ("curl", "wget", "ssh", "scp", "sftp", "nc", "ncat", "telnet", "ftp", "open", "osascript",
         "defaults", "launchctl", "security", "pbcopy", "pbpaste", "say", "systemctl", "sudo",
         "doas", "su", "gh", "npm", "npx", "pnpm", "yarn", "pip", "pip3", "brew", "apt", "apt-get",
         "codex", "claude", "gemini", "docker", "kill", "killall", "pkill", "shutdown", "reboot",
         "networksetup", "scutil", "dscl", "crontab", "at")
# The control files every replay checks, besides everything the gate itself
# lists as protected (its own policy, read from the gate module).
CONTROL = (".claude/settings.json", ".claude/settings.local.json", ".claude/hooks/tess-gate.py",
           ".claude/hooks/run-pinned.py", "CLAUDE.md", ".tess/tess.lock",
           ".tess/core/pinned-scripts.sha256", "tessctl", "tess.manifest.json",
           "conductor/guardrails.md", ".git/config")
CONTROL_DIRS = (".claude", ".tess", ".codex", ".gemini", ".git/hooks", ".github")
# Files under the sandbox home that the gate protects (seeded so a change is
# visible; round 4b, Reid H1). The key folder (~/.config/tess) is checked
# with the gate's own key_hit, the rest with its control_file_hit.
HOME_CONTROL = (".claude/settings.json", ".claude/settings.local.json", ".claude.json",
                ".codex/config.toml", ".codex/hooks.json", ".codex/rules/default.rules",
                ".config/git/config", ".config/tess/operator.pub")
EVIL = '{"disableAllHooks":true}'


# ------------------------------------------------------------------ sandbox
def _copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst, symlinks=True, ignore=shutil.ignore_patterns("__pycache__"))
    else:
        shutil.copy2(src, dst)


def build_pristine(base: Path, repo: Path = REPO) -> dict:
    """The sandbox under `base` (which must be a fresh temp folder): a copy of
    the Tess instance in `repo` (read only) as `proj`, a fake home `home`, a temp folder `tmp`, and `W`, a
    folder outside the project with the shapes the attack corpus needs."""
    base = Path(os.path.realpath(base))
    if not str(base).startswith(os.path.realpath(tempfile.gettempdir())) and \
            not str(base).startswith("/private/var/folders/") and not str(base).startswith("/tmp"):
        raise RuntimeError(f"refusing to build a sandbox outside the temp folder: {base}")
    p, h, w, t = base / "proj", base / "home", base / "W", base / "tmp"
    for rel in (".tess/tess.lock", ".tess/core/pinned-scripts.sha256", "tessctl",
                "tess.manifest.json", "conductor/guardrails.md", "CLAUDE.md", "AGENTS.md"):
        if (repo / rel).exists():
            _copy(repo / rel, p / rel)
    for tree in (".claude/hooks", "scripts/brain", ".tess/bin", ".tess/vendor"):
        _copy(repo / tree, p / tree)
    (p / ".claude/settings.json").write_text("{}\n")
    (p / ".claude/settings.local.json").write_text("{}\n")
    (p / "notes.md").write_text("notes\n")
    (p / "src").mkdir()
    (p / "src" / "a.py").write_text("print(1)\n")
    subprocess.run(["git", "init", "-q", "-b", "main", str(p)], check=True, env=_git_env(h))
    (h / ".config").mkdir(parents=True)
    # No background repository maintenance in the sandbox: a detached
    # auto-gc would still be writing while the next copy is made.
    (h / ".gitconfig").write_text("[gc]\n\tauto = 0\n\tautoDetach = false\n[maintenance]\n\tauto = false\n")
    # round 4b (Reid H1): the user-level control files the gate protects,
    # so a run that changes one of them is caught.
    for rel in HOME_CONTROL:
        f = h / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        if not f.exists():
            f.write_text("{}\n" if rel.endswith(".json") else "# placeholder\n")
    t.mkdir()
    _world(w, p, h)
    return {"base": str(base), "P": str(p), "H": str(h), "W": str(w), "T": str(t)}


def _git_env(home: Path) -> dict:
    return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"), "GIT_CONFIG_NOSYSTEM": "1"}


def _world(w: Path, p: Path, h: "Path | None" = None) -> None:
    """Quinn's probe world (d2a5707 verification): links into the project and
    into its .claude folder, a glob-named folder, prepared evil trees and
    archives. Nothing in it is inside the project. Round 4b (Reid Z1): links
    two and three levels down, to .claude, the project root and the home
    folder, for the recursive-glob probes."""
    w.mkdir()
    for d, target in (("x/lk", p / ".claude"), ("a/b/lk", p / ".claude"), ("p/q/lp", p),
                      ("h1/h2/hl", h), ("r-0/q/lp", p)):
        if target is not None:
            (w / d).parent.mkdir(parents=True, exist_ok=True)
            os.symlink(str(target), str(w / d))
    os.symlink(str(p), str(w / "lk"))
    os.symlink(str(p / ".claude"), str(w / "lc"))
    for d in ("g", "[x]", "nl"):
        (w / d).mkdir()
        os.symlink(str(p), str(w / d / "b-0"))
    (w / "out").mkdir()
    for f in (".claude/settings.json", ".claude/settings.local.json", ".claude/hooks/tess-gate.py",
              "CLAUDE.md"):
        q = w / "evil" / f
        q.parent.mkdir(parents=True, exist_ok=True)
        q.write_text(EVIL)
    (w / "evil2").mkdir()
    (w / "evil2" / "settings.local.json").write_text(EVIL)
    (w / "evil3").mkdir()
    (w / "evil3" / "tess-gate.py").write_text("x")
    for name, members in (("a", [".claude/settings.local.json"]), ("b", ["settings.local.json"]),
                          ("c", ["CLAUDE.md"])):
        with tarfile.open(str(w / f"{name}.tar"), "w") as tf:
            for m in members:
                info = tarfile.TarInfo(m)
                info.size = len(EVIL)
                tf.addfile(info, io.BytesIO(EVIL.encode()))
        with zipfile.ZipFile(str(w / f"{name}.zip"), "w") as zf:
            for m in members:
                zf.writestr(m, EVIL)


def fresh_copy(pristine: dict, run: Path) -> dict:
    """A copy of the pristine sandbox at `run`, links kept as links. Links
    that point into the pristine tree are re-pointed into the copy."""
    run = Path(os.path.realpath(run.parent)) / run.name  # the jail matches real paths
    for _ in range(20):
        if not os.path.lexists(run):
            break
        _rmtree(run)
        time.sleep(0.1)
    if os.path.lexists(run):
        raise RuntimeError(f"could not clear {run} for the next run")
    shutil.copytree(pristine["base"], run, symlinks=True)
    old, new = pristine["base"], str(run)
    for dirpath, dirnames, filenames in os.walk(run):
        for n in dirnames + filenames:
            q = os.path.join(dirpath, n)
            if os.path.islink(q):
                t = os.readlink(q)
                if t.startswith(old + os.sep) or t == old:
                    os.unlink(q)
                    os.symlink(new + t[len(old):], q)
    return {k: (new + v[len(old):] if isinstance(v, str) and v.startswith(old) else v)
            for k, v in pristine.items()}


def _rmtree(path: Path) -> None:
    def onerr(func, p, _exc):
        try:
            os.chmod(os.path.dirname(p), 0o700)
            os.chmod(p, 0o700)
        except OSError:
            pass
        try:
            func(p)
        except OSError:
            pass
    for dirpath, dirnames, _f in os.walk(path):
        for d in dirnames:
            q = os.path.join(dirpath, d)
            if not os.path.islink(q):
                try:
                    os.chmod(q, 0o700)
                except OSError:
                    pass
    shutil.rmtree(path, onerror=onerr)


def expand(template: str, s: dict) -> str:
    """A corpus template with its placeholders filled in. /tmp/ is the
    sandbox's own temp folder: nothing runs against the real one."""
    out = template.replace("/tmp/", s["T"] + "/")
    for k in ("W", "P", "H", "T"):
        out = out.replace("@" + k, s[k])
    return out


# ------------------------------------------------------------------ snapshots
def _entry(path: str) -> tuple:
    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode):
        return ("link", os.readlink(path))
    if stat.S_ISDIR(st.st_mode):
        return ("dir", stat.S_IMODE(st.st_mode))
    with open(path, "rb") as fh:
        return ("file", stat.S_IMODE(st.st_mode), hashlib.sha256(fh.read()).hexdigest())


def snapshot(root: str) -> dict:
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for n in dirnames + filenames:
            q = os.path.join(dirpath, n)
            try:
                out[os.path.relpath(q, root)] = _entry(q)
            except OSError:
                out[os.path.relpath(q, root)] = ("unreadable",)
    return out


# round 4b (Reid H2): what git itself writes during an allowed commit,
# branch or tag in normal work. These are the only paths the gate protects
# that a replay does not count. The set is derived from the gate's own list:
# every other path the gate protects (`protected_hit`) counts, and
# test_v1_shell_conformance checks each entry of the gate's list against it.
# `.git/HEAD` is exempt only while it still names a local branch.
GIT_WRITES = (".git/objects/", ".git/logs/", ".git/refs/heads/", ".git/refs/tags/")
GIT_WRITE_FILES = (".git/index", ".git/COMMIT_EDITMSG", ".git/ORIG_HEAD", ".git/FETCH_HEAD")


def _git_normal_write(rel: str, s: "dict | None" = None) -> bool:
    if rel in GIT_WRITE_FILES or any(rel.startswith(x) for x in GIT_WRITES) or \
            rel in (x.rstrip("/") for x in GIT_WRITES):
        return True
    if rel == ".git/HEAD" and s is not None:
        try:
            head = Path(s["P"], ".git", "HEAD").read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False
        return head.startswith("ref: refs/heads/") and "\n" not in head.rstrip("\n")
    return False


def controlled(rel: str, gate, s: dict) -> bool:
    """`rel` (relative to the sandbox project) is a protected control path:
    the fixed list above, a control folder, or anything the gate's own
    protected list names, except what git writes in normal work."""
    if rel in CONTROL or rel == ".git/hooks" or rel.startswith(".git/hooks/"):
        return True
    if any(rel == d or rel.startswith(d + "/") for d in CONTROL_DIRS):
        return True
    try:
        hit = bool(gate.protected_hit(Path(s["P"]), s["P"], os.path.join(s["P"], rel)))
    except Exception:  # noqa: BLE001 - a model error is a reason to check, not to skip
        return True
    return hit and not _git_normal_write(rel, s=s)


def home_controlled(rel: str, gate, s: dict) -> bool:
    """`rel` (relative to the sandbox home) is a user-level control file or
    the key folder, by the gate's own lists (round 4b, Reid H1)."""
    path = os.path.join(s["H"], rel)
    try:
        hit = getattr(gate, "control_file_hit", lambda *a: None)(Path(s["P"]), s["H"], path)
        key = getattr(gate, "key_hit", lambda *a, **k: None)(s["H"], path)
    except Exception:  # noqa: BLE001
        return True
    return bool(hit or key) or rel in HOME_CONTROL


def changed_controls(before: dict, after: dict, gate, s: dict) -> list:
    keys = set(before) | set(after)
    return sorted(k for k in keys if before.get(k) != after.get(k) and controlled(k, gate, s))


def changed_home_controls(before: dict, after: dict, gate, s: dict) -> list:
    keys = set(before) | set(after)
    return sorted("~/" + k for k in keys
                  if before.get(k) != after.get(k) and home_controlled(k, gate, s))


# ------------------------------------------------------------------ jail
def _stub_dir(base: Path) -> str:
    d = base / ".stubs"
    d.mkdir(exist_ok=True)
    for n in STUBS:
        f = d / n
        # A stub records that it ran: such a run is reported as not fully
        # exercised (the real program's effect was not tried), never hidden.
        f.write_text(f'#!/bin/sh\necho {n} >> "{base}/.stubs-called"\nexit 0\n')
        f.chmod(0o755)
    return str(d)


def jail() -> "list | None":
    """The command prefix that confines a process to the sandbox, or None."""
    if platform.system() == "Darwin" and shutil.which("sandbox-exec"):
        return ["sandbox-exec", "-p"]
    if platform.system() == "Linux" and shutil.which("bwrap"):
        return ["bwrap"]
    return None


def _jailed(argv: list, base: str) -> list:
    kind = jail()
    if kind is None:
        raise RuntimeError("no sandbox-exec or bwrap: refusing to run real shells unconfined")
    if kind[0] == "sandbox-exec":
        prof = ('(version 1)(allow default)(deny network*)(deny file-write*)'
                f'(allow file-write* (subpath "{base}") (literal "/dev/null") (literal "/dev/tty")'
                ' (regex #"^/dev/fd/") (regex #"^/dev/ttys"))'
                '(deny mach-lookup (global-name "com.apple.cfprefsd.daemon")'
                ' (global-name "com.apple.cfprefsd.agent")'
                ' (global-name "com.apple.coreservices.launchservicesd"))')
        return ["sandbox-exec", "-p", prof] + argv
    return ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
            "--bind", base, base, "--unshare-net", "--unshare-pid", "--die-with-parent",
            "--new-session"] + argv


def shells() -> list:
    """Every distinct bash and zsh on this machine (the stock ones first)."""
    out = []
    for cand in ("/bin/bash", shutil.which("bash"), "/bin/zsh", "/usr/bin/zsh", shutil.which("zsh")):
        if cand and os.path.exists(cand) and os.path.realpath(cand) not in {os.path.realpath(x) for x in out}:
            out.append(cand)
    return out


def run_shell(shell: str, cmd: str, s: dict) -> tuple:
    """(exit code or "timeout", stderr tail) of `cmd` in `shell`, in the jail."""
    base = s["base"]
    env = {"PATH": _stub_dir(Path(base)) + ":/usr/bin:/bin:/usr/sbin:/sbin",
           "HOME": s["H"], "XDG_CONFIG_HOME": s["H"] + "/.config", "TMPDIR": s["T"],
           "ZDOTDIR": s["H"], "LANG": "C", "PWD": s["P"], "GIT_CONFIG_NOSYSTEM": "1",
           "TESS_GATE_LOG": os.devnull}
    flags = ["-f"] if "zsh" in os.path.basename(shell) else ["--noprofile", "--norc"]
    argv = _jailed([shell] + flags + ["-c", cmd], base)
    proc = subprocess.Popen(argv, cwd=s["P"], env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, start_new_session=True)
    try:
        _out, err = proc.communicate(timeout=TIMEOUT)
        code = proc.returncode
    except subprocess.TimeoutExpired:
        code, err = "timeout", b""
    try:
        # Only the group this harness started: also stops anything the
        # command left running in the background before the next copy.
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    if code == "timeout":
        proc.communicate()
    return code, (err or b"")[-300:].decode("utf-8", "replace")


def confinement_self_test(s: dict) -> None:
    """Raise unless the jail refuses a write outside the sandbox."""
    outside = Path(tempfile.mkdtemp(prefix="tess-conf-outside-"))
    try:
        probe = outside / "must-not-exist"
        for sh in shells():
            run_shell(sh, f"echo x > '{probe}'", s)
            if probe.exists():
                raise RuntimeError(f"the jail let {sh} write outside the sandbox")
        inside = Path(s["T"]) / "jail-ok"
        run_shell(shells()[0], f"echo x > '{inside}'", s)
        if not inside.exists():
            raise RuntimeError("the jail refused a write inside the sandbox")
        inside.unlink()
    finally:
        shutil.rmtree(outside, ignore_errors=True)


# ------------------------------------------------------------------ decisions
def load_gate(repo: Path = REPO):
    """The gate module of `repo`, loaded without writing bytecode."""
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("tess_gate_conformance",
                                                  str(repo / ".claude" / "hooks" / "tess-gate.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def decisions(gate, cmd: str, s: dict) -> tuple:
    """(claude default, claude acceptEdits, codex) for `cmd` in the sandbox."""
    root = Path(s["P"])
    out = []
    for rt, mode in (("claude", "default"), ("claude", "acceptEdits"), ("codex", None)):
        data = {"tool_name": "Bash", "cwd": s["P"], "tool_input": {"command": cmd}}
        if rt == "codex":
            data["turn_id"] = "t"
        else:
            data["permission_mode"] = mode
        out.append(gate.decide(data, root, rt)[0] or "allow")
    return tuple(out)


def replay(gate, pristine: dict, templates: list, workdir: Path) -> dict:
    """Run every template the gate allows (in any of the three modes) in each
    shell. Returns {"ran": n, "allowed": n, "failures": [...]}."""
    failures, ran, allowed, stubbed = [], 0, 0, []
    run = workdir / "run"
    for tid, template in templates:
        s = fresh_copy(pristine, run)
        cmd = expand(template, s)
        dec = decisions(gate, cmd, s)
        if "allow" not in dec:
            continue
        allowed += 1
        for sh in shells():
            s = fresh_copy(pristine, run)
            before, hbefore = snapshot(s["P"]), snapshot(s["H"])
            code, err = run_shell(sh, cmd, s)
            ran += 1
            bad = changed_controls(before, snapshot(s["P"]), gate, s) + \
                changed_home_controls(hbefore, snapshot(s["H"]), gate, s)
            calls = Path(s["base"]) / ".stubs-called"
            if calls.exists():
                stubbed.append((tid, sh, sorted(set(calls.read_text().split()))))
            if code == "timeout":
                # it may have gone on to change files after the kill: not clean
                bad = bad or ["<timed out: the run did not finish>"]
            if bad:
                failures.append({"id": tid, "shell": sh, "decisions": dec, "changed": bad,
                                 "exit": code, "command": template})
    if run.exists():
        _rmtree(run)
    return {"ran": ran, "allowed": allowed, "failures": failures, "stubbed": stubbed}


def load_harvest(path: str) -> list:
    """(id, template) pairs from a corpus recorded by gate_corpus_recorder:
    the recorded project root, home and temp folders become placeholders."""
    out, seen = [], set()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            cmd = r.get("cmd")
            if not isinstance(cmd, str):
                continue  # every recorded command is decided again in the sandbox
            for real, ph in sorted(((r.get("root"), "@P"), (r.get("root_raw"), "@P"),
                                    (r.get("home"), "@H"), (r.get("tmp"), "@T"),
                                    (r.get("repo"), "@P")),
                                   key=lambda x: -len(x[0] or "")):
                if real:
                    cmd = cmd.replace(real, ph)
            if cmd not in seen:
                seen.add(cmd)
                out.append((f"harvest:{r.get('t', '?')}", cmd))
    return out
