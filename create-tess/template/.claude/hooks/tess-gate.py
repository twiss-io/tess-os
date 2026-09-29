#!/usr/bin/env python3
"""tess-gate.py — the Tess tool-call safety gate for runtimes where Tess cannot
configure the native permission layer (Codex first; runs in Claude Code too).

Wired for Codex by `.codex/config.toml` (rendered by `tessctl render --target
codex` from `.tess/core/templates/agents-md/codex-config.toml.tpl`) as a
PreToolUse hook, always through `.claude/hooks/run-pinned.py --on-fail block`,
so this file runs only when it matches the sha pinned for the release.

What it stops (each check says in plain English what the user can do instead):

  * secret-shaped values in a dispatch (`spawn_agent`/`Agent`/`Task`: the full
    vault-dispatch-scan.py pattern set) or in a shell command (the specific
    token formats only: PEM, GitHub, Stripe, Slack, AWS, age);
  * writes to Tess's security-tier and enforcement files, through `apply_patch`
    / Edit / Write, a write-shaped MCP tool, or a shell writer (`>`, `tee`,
    `sed -i`, `rm`, `mv`, `cp`, ...): the files `.tess/tess.lock` tags
    `tier: security`, plus PROTECTED_GLOBS below;
  * git hook bypasses: `--no-verify` (and `git commit -n`), any
    `core.hooksPath` override (`-c`, `--config-env`, `git config`, GIT_CONFIG_*
    env), and shell writes under `.git/hooks/` or to `.git/config`;
  * `gh auth token` / `gh auth status --show-token` (prints a live credential
    into the transcript);
  * a `git push` whose commits carry brain/ or clients/ data to a public or
    unverifiable remote: the SAME check as the git pre-push hook
    (`tessctl doctor --publish-remote`), run before the push so it also holds
    when the pre-push hook is not installed.

It asks (Claude Code) or denies (Codex, and Claude's no-prompt modes) for:
force pushes, remote add/set-url/rename/remove, and repository visibility
changes. Codex does not support a PreToolUse "ask": it fails the hook and RUNS
the command (learn.chatgpt.com/docs/hooks.md, "Unsupported PreToolUse
features"), so every ask is sent as a deny whose reason tells the user to run
the command themselves. A payload carrying `turn_id` is treated as Codex even
without `--runtime codex` (same test as the machine-level git-guard).

Fail closed: unreadable input or an internal error denies the call.

Audit trail: every deny/ask is appended (redacted, one JSON line) to
$TESS_GATE_LOG, default ${XDG_CACHE_HOME:-~/.cache}/tess/gate-decisions.log
(rotated at 1 MB). Logging is best effort and never changes a decision.

v1.0.0 security review (M1) also denies: pointing git at another config file
(GIT_CONFIG_GLOBAL / GIT_CONFIG_SYSTEM / GIT_CONFIG_PARAMETERS in the
environment), writing `include.*` / `includeIf.*` / `alias.*` git config
(`git config` or `git -c`), shell writes after a `cd` into a protected
directory (the cwd is tracked across `cd`/`pushd`; a `cd` whose target is
computed at run time makes later relative writes a deny), and, best effort,
an inline interpreter program (`python -c`, `node -e`, a heredoc fed to one)
that names a protected path and calls a write-shaped API.

Known limits (adapters/CONFORMANCE.md, Codex row): the shell checks read the
command text, so a write assembled at run time (`$(...)`, variables), a
script file run by an interpreter, or an interpreter write this pattern
match misses is not seen; hosted tools never reach hooks; Codex `write_stdin`
(typed input to an already-open unified-exec shell) never reaches
PreToolUse; a hook that times out or crashes in the host fails open for that
call. The ship-gate in git/CI stays the wall; this gate is the in-session
guard in front of it.
"""

from __future__ import annotations

import fnmatch
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

ALLOW, ASK, DENY = 0, 1, 2
NO_PROMPT_MODES = {"bypassPermissions", "dontAsk"}
SCAN_REL = ".claude/hooks/vault-dispatch-scan.py"
LAUNCHER_REL = ".claude/hooks/run-pinned.py"
TESSCTL_REL = ".tess/bin/tessctl"

# Enforcement surfaces on top of the tess.lock `tier: security` live paths.
# Kept in step with core/policy/policy.yaml rule tess-os-security-tier-doctrine
# plus the files that switch a runtime's enforcement on or off.
PROTECTED_GLOBS = (
    "conductor/guardrails.md", "conductor/verification-routing.md",
    "conductor/channel-guardrails.md", "conductor/dispatch-brief.md",
    "core/contracts/**", "core/policy/**",
    ".tess/bin/**", "tessctl", ".tess/core/**", ".tess/core/policy/policy.yaml",
    ".tess/tess.lock",
    ".tess/keys/**", ".tess/gate/**", ".github/workflows/**",
    ".claude/hooks/**", ".claude/settings.json", "scripts/brain/**",
    "CLAUDE.md", "AGENTS.md", "GEMINI.md", ".gemini/settings.json",
    ".codex/config.toml", ".codex/hooks.json", ".codex/rules/**",
    ".git/hooks/**", ".git/config", ".gitleaks.toml",
)

DISPATCH_TOOLS = {"Agent", "Task", "spawn_agent"}
SHELL_TOOLS = {"Bash", "shell", "exec_command", "local_shell", "unified_exec"}
EDIT_TOOLS = {"apply_patch", "Edit", "Write", "MultiEdit", "NotebookEdit"}
MCP_WRITE_WORDS = ("write", "edit", "create", "move", "rename", "delete",
                   "remove", "patch", "append", "save", "upload")
MCP_PATH_KEYS = {"path", "file_path", "filepath", "filename", "file",
                 "destination", "dest", "target", "source", "new_path", "old_path"}

SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
WRAPPERS = {"env", "command", "exec", "nohup", "time", "nice", "sudo", "doas", "builtin"}
WRITERS = {"rm", "mv", "cp", "tee", "truncate", "chmod", "chown", "chflags", "ln",
           "install", "touch", "dd", "rsync", "unlink", "rmdir", "shred", "patch"}
INPLACE = {"sed", "gsed", "perl"}
READERS_OK_FOR_GIT_DIR = {"ls", "cat", "head", "tail", "stat", "file", "test", "[",
                          "grep", "rg", "wc", "shasum", "sha256sum", "diff", "less"}
OPERATORS = {";", "&&", "||", "|", "&", "(", ")", "\n", "|&", ";;"}
REDIRECTS = {">", ">>", ">|", "&>", "&>>", "<>"}
GIT_VALUE_OPTS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace",
                  "--exec-path", "--config-env", "--super-prefix", "--list-cmds"}
PUSH_VALUE_OPTS = {"-o", "--push-option", "--repo", "--receive-pack", "--exec"}
ZERO = "0" * 40
_PATCH_FILE = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+?)\s*$|^\*\*\* Move to: (.+?)\s*$",
                         re.MULTILINE)
_URL_CREDS = re.compile(r"(//)[^/@\s]+@")
# git reads another config file (which can set core.hooksPath, an alias or an
# include) from these; any assignment of them is a deny.
GIT_CONFIG_FILE_ENV = {"GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_PARAMETERS",
                       "GIT_CONFIG"}
# An empty config (the usual test isolation, GIT_CONFIG_GLOBAL=/dev/null) sets nothing.
_EMPTY_CONFIG = {"/dev/null", "", "''", '""'}
# Config keys that pull in other config (include) or define commands (alias).
_GIT_CONFIG_INDIRECT = re.compile(r"^(include|includeif\.[^=]*|alias)\.", re.IGNORECASE)
INTERPRETERS = re.compile(r"^(python[0-9.]*|pypy[0-9.]*|node|nodejs|deno|bun|perl|ruby|php|osascript)$")
_INTERP_WRITE = re.compile(
    r"write_text|write_bytes|\.write\(|writeFile|appendFile|createWriteStream|\bunlink|"
    r"\bos\.(remove|rename|replace|system|symlink|chmod|truncate|popen|makedirs)|rmtree|"
    r"\bshutil\.|\bsubprocess\b|child_process|execSync|spawnSync|rmSync|\.rename\(|\.symlink_to\(|"
    r"\.chmod\(|\.touch\(|File\.(write|open|delete|rename)|\bsystem\(|open\([^)]*['\"][rwxa]?[wxa+]",
)
_INTERP_TOKEN = re.compile(r"[A-Za-z0-9_./~+-]+")
PROTECTED_DIR_ROOTS = {".tess", ".git", ".claude", ".codex", ".gemini", ".github",
                       ".git/hooks", ".claude/hooks", ".github/workflows", "core/policy",
                       "core/contracts", "scripts/brain", ".tess/core", ".tess/bin", ".tess/keys"}


# --------------------------------------------------------------------------- helpers

def _root() -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    return Path(env) if env else Path(__file__).resolve().parent.parent.parent


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _scanner(root: Path):
    """vault-dispatch-scan.py, loaded only after run-pinned.py verifies its sha."""
    launcher = _load(root / LAUNCHER_REL, "tess_run_pinned")
    path = launcher.verify(root, SCAN_REL, None)
    return _load(path, "tess_vault_scan")


def _leak_pattern_names(root: Path, text: str, specific_only: bool) -> list:
    """Descriptions of the scanner patterns `text` matches (for example
    "GitHub personal access token (ghp_)"). Never the matched text itself."""
    mod = _scanner(root)
    hits = []
    for pattern, desc in mod._PATTERNS:
        if specific_only and desc.startswith("generic"):
            continue
        if pattern.search(text) and desc not in hits:
            hits.append(desc)
    return hits


def _redact(root: Path, text: str) -> str:
    text = _URL_CREDS.sub(r"\1***@", text)
    try:
        for pattern, _desc in _scanner(root)._PATTERNS:
            text = pattern.sub("[REDACTED]", text)
    except Exception:  # redaction must never be the reason a message is lost
        text = re.sub(r"[A-Za-z0-9_\-]{32,}", "[REDACTED]", text)
    return text


def _short(root: Path, cmd: str) -> str:
    one = " ".join(cmd.split())
    one = _redact(root, one)
    return one if len(one) <= 200 else one[:197] + "..."


def _security_tier_paths(root: Path) -> set:
    """live_path of every tess.lock `files:` entry tagged tier: security.

    A line scanner, not a YAML parser (hooks run under the system python3,
    which may not have PyYAML); same approach as run-pinned.py."""
    try:
        text = (root / ".tess" / "tess.lock").read_text(encoding="utf-8")
    except OSError:
        return set()
    entries: dict = {}
    section = key = None
    for raw in text.splitlines():
        if raw and not raw.startswith((" ", "#")):
            section, key = raw.split(":", 1)[0].strip(), None
            continue
        if section != "files":
            continue
        m = re.match(r"^  (\S[^:]*):\s*$", raw)
        if m:
            key = m.group(1).strip("'\"")
            entries[key] = {}
            continue
        m = re.match(r"^    (tier|live_path):\s*(.*?)\s*$", raw)
        if m and key is not None:
            entries[key][m.group(1)] = m.group(2).strip("'\"")
    return {e["live_path"] for e in entries.values()
            if e.get("tier") == "security" and e.get("live_path") not in (None, "", "null", "~")}


def _glob_hit(rel: str, globs) -> str | None:
    low = rel.lower()  # macOS/Windows file systems are case-insensitive
    for g in globs:
        gl = g.lower()
        if gl.endswith("/**"):
            base = gl[:-3]
            if low == base or low.startswith(base + "/"):
                return g
        elif fnmatch.fnmatchcase(low, gl):
            return g
        # A directory that CONTAINS a protected file (rm -rf .claude, mv .tess x).
        base = gl[:-3] if gl.endswith("/**") else gl
        if "*" not in base and base.startswith(low + "/"):
            return g
    return None


def _rel_to_root(root: Path, cwd: str, path: str) -> str | None:
    if not path:
        return None
    path = os.path.expanduser(path)
    full = path if os.path.isabs(path) else os.path.join(cwd or str(root), path)
    real = os.path.realpath(full)
    base = os.path.realpath(str(root))
    if real != base and not real.startswith(base + os.sep):
        return None
    return os.path.relpath(real, base).replace(os.sep, "/")


def protected_hit(root: Path, cwd: str, path: str) -> str | None:
    rel = _rel_to_root(root, cwd, path)
    if rel is None or rel == ".":
        return None
    return _glob_hit(rel, tuple(sorted(_security_tier_paths(root))) + PROTECTED_GLOBS)


# --------------------------------------------------------------------------- shell parsing

def _tokens(cmd: str) -> list:
    lx = shlex.shlex(cmd, posix=True, punctuation_chars=";&|()<>\n")
    lx.whitespace = " \t\r"
    lx.whitespace_split = True
    lx.commenters = ""
    return list(lx)


def _segments(cmd: str) -> list:
    """[[argv...], ...] split on shell operators. Redirection tokens stay in argv."""
    segs, cur = [], []
    for tok in _tokens(cmd):
        if tok in OPERATORS:
            if cur:
                segs.append(cur)
            cur = []
        else:
            cur.append(tok)
    if cur:
        segs.append(cur)
    return segs


def _strip_prefix(argv: list) -> tuple:
    """Drop VAR=val assignments and wrappers (env, command, sudo...). Returns (env, argv)."""
    env = {}
    i = 0
    while i < len(argv):
        tok = argv[i]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tok):
            k, v = tok.split("=", 1)
            env[k] = v
            i += 1
        elif os.path.basename(tok) in WRAPPERS:
            i += 1
            while i < len(argv) and argv[i].startswith("-"):
                i += 1
        else:
            break
    return env, argv[i:]


ADVICE = {
    "noverify": "Commit or push without --no-verify and fix what the hook reports.",
    "hookspath": "Leave core.hooksPath unset. If you really need another hooks directory, "
                 "set it yourself outside the agent.",
    "protected": "Protected Tess files change only through a reviewed release. If you mean to "
                 "change one, do it yourself outside the agent; the ship gate will ask for a "
                 "signed verdict.",
    "token": "Run gh commands directly (gh reads the token itself), or use "
             "`tessctl vault exec` for a secret.",
    "secret": "Keep secrets out of commands and dispatches: read them from the environment, "
              "`tessctl vault exec`, or a vault:// reference.",
    "push": "Push to a private remote, or follow the steps above.",
    "error": "Try a simpler command. If it keeps failing, run `./tessctl doctor`, or run the "
             "command yourself outside the agent.",
    "operator": "Ask the operator to run it in their own terminal and type the answer "
                "themselves (for an update: `./tessctl update`, then `accept <version>`).",
}

# v1.0.0 (release integration, item a): `tessctl update` (new safety rules) and
# `tessctl approve` ask a person at a terminal to type the answer. An agent
# must not fake that terminal or type the answer for them.
_PTY_WRAPPER = re.compile(r"(?i)(?<![\w.-])(script|expect|unbuffer|socat|pexpect|ptyprocess|openpty|"
                          r"pty\.spawn|import\s+pty|from\s+pty)(?![\w.-])")
_TYPED_APPROVAL = re.compile(r"(?i)\baccept\s+v\d")


def _check_operator_only(cmd: str, v) -> None:
    if not re.search(r"(?i)tessctl", cmd):
        return
    if _PTY_WRAPPER.search(cmd) or _TYPED_APPROVAL.search(cmd):
        v.add(DENY, "only the operator can answer Tess's approval prompts; this command would "
                    "fake a terminal or type the approval for them", "operator")


class Verdict:
    def __init__(self):
        self.level = ALLOW
        self.reasons: list = []
        self.advice: list = []

    def add(self, level: int, reason: str, advice: str | None = None):
        if reason not in self.reasons:
            self.reasons.append(reason)
        if advice and ADVICE[advice] not in self.advice:
            self.advice.append(ADVICE[advice])
        self.level = max(self.level, level)


def _short_flags(args: list) -> str:
    return "".join(a[1:] for a in args if re.match(r"^-[A-Za-z]+$", a))


def _commit_no_verify(args: list) -> bool:
    for a in args:
        if a == "--":
            break
        if re.match(r"^-[A-Za-z]+$", a):
            for ch in a[1:]:
                if ch == "n":
                    return True
                if ch in "mFCctS":  # takes a value: the rest of the cluster is that value
                    break
    return False


def _check_git(root: Path, cwd: str, env: dict, argv: list, v: Verdict, raw: str):
    args = argv[1:]
    cfg, i, gcwd = [], 0, cwd
    while i < len(args) and args[i].startswith("-"):
        a = args[i]
        if a in GIT_VALUE_OPTS and i + 1 < len(args):
            if a == "-c" or a == "--config-env":
                cfg.append(args[i + 1])
            if a == "-C":
                gcwd = os.path.join(gcwd or str(root), os.path.expanduser(args[i + 1]))
            i += 2
            continue
        if a.startswith("--config-env=") or a.startswith("-c") and len(a) > 2:
            cfg.append(a.split("=", 1)[1] if a.startswith("--config-env=") else a[2:])
        i += 1
    sub = args[i] if i < len(args) else ""
    rest = args[i + 1:]
    hooks_env = any("hookspath" in (k + "=" + val).lower() for k, val in env.items()
                    if k.startswith("GIT_CONFIG"))
    if hooks_env or any(c.lower().startswith("core.hookspath") for c in cfg):
        v.add(DENY, "it points git at a different hooks directory (core.hooksPath), which "
                    "switches off Tess's git hooks (secret scan, ship gate, public-remote guard)", "hookspath")
    if any(_GIT_CONFIG_INDIRECT.match(c) for c in cfg):
        v.add(DENY, "it sets a git include or alias on the command line, which can switch off "
                    "Tess's git hooks or run another command", "hookspath")
    if sub == "config":
        keys = [a.lower() for a in rest]
        reading = any(k in ("--get", "--get-all", "--list", "-l", "--get-regexp", "get", "list")
                      for k in keys)
        if any(k == "core.hookspath" or k.startswith("core.hookspath=") for k in keys) and not reading:
            v.add(DENY, "it changes core.hooksPath, which switches off Tess's git hooks", "hookspath")
        if any(k == "--file" or k == "-f" for k in keys) and any("hook" in k for k in keys):
            v.add(DENY, "it edits git hook configuration directly", "hookspath")
        if not reading and any(_GIT_CONFIG_INDIRECT.match(k) for k in keys):
            v.add(DENY, "it writes a git include or alias, which can switch off Tess's git hooks "
                        "or run another command in place of a git one", "hookspath")
    if sub in ("commit", "merge", "am", "rebase", "cherry-pick", "revert", "push", "pull",
               "commit-tree", "notes") and "--no-verify" in rest:
        v.add(DENY, "--no-verify skips Tess's git hooks (secret scan and ship gate)", "noverify")
    if sub == "commit" and _commit_no_verify(rest):
        v.add(DENY, "`git commit -n` is --no-verify: it skips Tess's git hooks", "noverify")
    if sub == "remote" and rest and rest[0] in ("add", "set-url", "rename", "remove", "rm"):
        v.add(ASK, "it changes where this repository pushes (git remote " + rest[0] + ")")
    if sub in ("rm", "mv"):
        for a in rest:
            hit = not a.startswith("-") and protected_hit(root, gcwd, a)
            if hit:
                v.add(DENY, f"it removes or moves {a}, a protected Tess path ({hit})", "protected")
    if sub == "push":
        _check_push(root, gcwd, rest, v)


def _check_push(root: Path, cwd: str, rest: list, v: Verdict):
    flags = _short_flags(rest)
    opts = [a for a in rest if a.startswith("--")]
    if "--dry-run" in opts or "n" in flags:
        return
    if ("f" in flags or any(o == "--force" or o.startswith("--force-with-lease")
                            or o in ("--force-if-includes", "--mirror", "--prune") for o in opts)
            or any(a.startswith("+") for a in rest if not a.startswith("-"))):
        v.add(ASK, "it is a force push, which can overwrite commits on the remote")
    pos, i = [], 0
    while i < len(rest):
        a = rest[i]
        if a in PUSH_VALUE_OPTS:
            i += 2
            continue
        if not a.startswith("-") or a == "-":
            pos.append(a)
        i += 1
    try:
        _publish_remote_check(root, cwd, pos, opts, v)
    except Exception as exc:  # fail closed
        v.add(DENY, f"Tess could not check what this push would publish ({type(exc).__name__})", "error")


def _git(cwd: str, *args, check=False) -> str | None:
    r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        if check:
            raise RuntimeError(f"git {' '.join(args[:2])} failed")
        return None
    return r.stdout.strip()


def _publish_remote_check(root: Path, cwd: str, pos: list, opts: list, v: Verdict):
    top = _git(cwd or str(root), "rev-parse", "--show-toplevel")
    if not top:
        return  # not a repository: the push itself will fail
    branch = _git(top, "symbolic-ref", "--quiet", "--short", "HEAD") or ""
    if pos:
        remote = pos[0]
    else:
        remote = ((branch and _git(top, "config", "--get", f"branch.{branch}.pushRemote"))
                  or _git(top, "config", "--get", "remote.pushDefault")
                  or (branch and _git(top, "config", "--get", f"branch.{branch}.remote"))
                  or "origin")
    looks_url = "://" in remote or remote.startswith(("/", ".", "~")) or re.match(r"^[^/]+@[^:]+:", remote)
    url = remote if looks_url else (_git(top, "remote", "get-url", "--push", remote) or remote)
    refs = []
    if any(o in ("--all", "--branches", "--mirror") for o in opts) or any("*" in p for p in pos[1:]):
        out = _git(top, "for-each-ref", "--format=%(refname) %(objectname)", "refs/heads", check=True)
        refs += [ln.split() for ln in out.splitlines() if ln.strip()]
    if any(o in ("--tags", "--mirror", "--follow-tags") for o in opts):
        out = _git(top, "for-each-ref", "--format=%(refname) %(objectname)", "refs/tags", check=True)
        refs += [ln.split() for ln in out.splitlines() if ln.strip()]
    for spec in pos[1:]:
        if "*" in spec:
            continue
        src = spec.lstrip("+").split(":", 1)[0]
        if not src:
            continue  # a deletion carries no data
        sha = _git(top, "rev-parse", "--verify", "--quiet", src)
        if not sha:
            raise RuntimeError("unresolvable ref")
        refs.append([src, sha])
    if not refs:
        sha = _git(top, "rev-parse", "--verify", "--quiet", "HEAD")
        if not sha:
            return
        refs.append(["HEAD", sha])
    stdin = "".join(f"{r} {s} {r} {ZERO}\n" for r, s in refs)
    tessctl = root / TESSCTL_REL
    if not tessctl.is_file():
        v.add(DENY, f"{TESSCTL_REL} is missing, so Tess cannot check what this push would publish", "error")
        return
    env = dict(os.environ, TESS_ROOT=top)
    # -I -B: the engine lives in the working tree, and a planted
    # .tess/bin/argparse.py (or yaml.py) beside it must never run inside this hook.
    r = subprocess.run([sys.executable, "-I", "-B", str(tessctl), "doctor", "--publish-remote",
                        remote, url],
                       input=stdin, capture_output=True, text=True, cwd=top, env=env, timeout=90)
    if r.returncode != 0:
        detail = (r.stderr.strip() or r.stdout.strip() or "tess-remote-guard refused the push")
        v.add(DENY, "the public-remote guard refused it: " + _redact(root, detail), "push")


def _check_gh(argv: list, v: Verdict):
    args = argv[1:]
    if args[:2] == ["auth", "token"]:
        v.add(DENY, "`gh auth token` prints your live GitHub token into this session", "token")
    if args[:2] == ["auth", "status"] and ("--show-token" in args or "-t" in args):
        v.add(DENY, "`gh auth status --show-token` prints your live GitHub token into this session", "token")
    if args[:2] == ["repo", "edit"] and any(a.startswith("--visibility") for a in args):
        v.add(ASK, "it changes a repository's visibility")
    if args[:2] == ["repo", "create"] and "--public" in args:
        v.add(ASK, "it creates a PUBLIC repository")
    if args[:1] == ["api"] and any(re.search(r"(visibility|private)=", a) for a in args):
        v.add(ASK, "it changes a repository's visibility through the GitHub API")


def _write_targets(argv: list) -> list:
    """Paths a shell segment writes (redirect targets, writer args)."""
    out = []
    for i, tok in enumerate(argv):
        if tok in REDIRECTS or re.match(r"^\d*>{1,2}\|?$", tok):
            if i + 1 < len(argv) and argv[i + 1] not in REDIRECTS and argv[i + 1] != "&":
                out.append(argv[i + 1])
    name = os.path.basename(argv[0]) if argv else ""
    args = [a for a in argv[1:] if a not in REDIRECTS]
    if name in WRITERS:
        out += [a for a in args if not a.startswith("-")]
    elif name in INPLACE and any(re.match(r"^-[A-Za-z]*i", a) or a.startswith("--in-place") for a in args):
        out += [a for a in args if not a.startswith("-")]
    return out


def _interp_code(argv: list, raw: str) -> str:
    """The program an interpreter segment runs from the command text: the
    -c/-e argument, else (stdin / heredoc) the whole command text."""
    for j, a in enumerate(argv[1:], 1):
        if a in ("-c", "-e", "-E", "--eval", "-p", "--print", "-r") and j + 1 < len(argv):
            return argv[j + 1]
        if re.match(r"^-[A-Za-z]*[ceE]$", a) and j + 1 < len(argv):
            return argv[j + 1]
    return raw


def _check_interpreter(root: Path, cwd: str, argv: list, v: Verdict, raw: str):
    """Best effort (M1): an inline program that names a protected path and
    calls a write-shaped API. A script FILE is not read; the ship gate stays
    the wall."""
    code = _interp_code(argv, raw)
    if not _INTERP_WRITE.search(code):
        return
    for tok in _INTERP_TOKEN.findall(code):
        t = tok[2:] if tok.startswith("./") else tok
        hit = (t.rstrip("/") in PROTECTED_DIR_ROOTS and t.rstrip("/"))
        if not hit and ("/" in t or "." in t):
            hit = protected_hit(root, cwd, t)
        if hit:
            v.add(DENY, f"an inline {os.path.basename(argv[0])} program writes near {tok}, a "
                        f"protected Tess path ({hit})", "protected")
            return


def _check_segment(root: Path, cwd: str | None, argv: list, v: Verdict, raw: str, depth: int):
    env, argv = _strip_prefix(argv)
    for k, val in env.items():
        if k in GIT_CONFIG_FILE_ENV and val not in _EMPTY_CONFIG:
            v.add(DENY, f"it sets {k}, which makes git read another config file (that file can "
                        "switch off Tess's git hooks)", "hookspath")
    if not argv:
        return
    name = os.path.basename(argv[0])
    if cwd is None:
        # a `cd` earlier in this command went somewhere Tess cannot resolve
        if any(not os.path.isabs(os.path.expanduser(t)) for t in _write_targets(argv)):
            v.add(DENY, "it writes to a relative path after a `cd` whose target is only known "
                        "at run time, so Tess cannot check it against the protected list", "protected")
        cwd = str(root)
    if INTERPRETERS.match(name):
        _check_interpreter(root, cwd, argv, v, raw)
    if name in SHELLS and depth < 4:
        for j, a in enumerate(argv[1:], 1):
            if re.match(r"^-[a-z]*c[a-z]*$", a) and j + 1 < len(argv):
                check_command(root, cwd, argv[j + 1], v, depth + 1)
                return
    if name == "eval" and depth < 4:
        check_command(root, cwd, " ".join(argv[1:]), v, depth + 1)
        return
    if name in ("export", "declare", "typeset", "setenv") and any(
            "hookspath" in a.lower() for a in argv[1:]):
        v.add(DENY, "it sets core.hooksPath through the environment, which switches off "
                    "Tess's git hooks", "hookspath")
    if name in ("export", "declare", "typeset", "setenv") and any(
            re.split(r"[=\s]", a, 1)[0] in GIT_CONFIG_FILE_ENV
            and a.partition("=")[2] not in _EMPTY_CONFIG for a in argv[1:]):
        v.add(DENY, "it points git at another config file through the environment, which can "
                    "switch off Tess's git hooks", "hookspath")
    if name == "git":
        _check_git(root, cwd, env, argv, v, raw)
    elif name == "gh":
        _check_gh(argv, v)
    for target in _write_targets(argv):
        hit = protected_hit(root, cwd, target)
        if hit:
            v.add(DENY, f"it writes to {target}, a protected Tess path ({hit})", "protected")
    if name not in READERS_OK_FOR_GIT_DIR and name != "git":
        for a in argv[1:]:
            if re.search(r"(^|/)\.git/(hooks(/|$)|config$)", a):
                v.add(DENY, f"it touches {a}; Tess's git hooks and git config are off limits", "hookspath")


def check_command(root: Path, cwd: str, cmd: str, v: Verdict, depth: int = 0):
    _check_operator_only(cmd, v)
    try:
        segs = _segments(cmd)
    except ValueError:
        # Unparseable (unbalanced quotes). The shell may still run it: a quote
        # inside a `# comment` (`rm .claude/hooks/tess-gate.py # it's`) breaks
        # shlex but not bash. Never fail open here (v1.0 code review, HIGH):
        # check the raw text, then re-parse with shell comments, and if the
        # command is still undecidable ask (Claude) -- decide() turns that ask
        # into a deny for Codex and the no-prompt modes.
        low = cmd.lower()
        if "--no-verify" in low or "hookspath" in low or re.search(r"\.git/(hooks|config\b)", low):
            v.add(DENY, "the command could not be parsed and mentions a git hook bypass", "error")
        for word in re.findall(r"[^\s;&|()<>'\"`]+", cmd):
            hit = protected_hit(root, cwd, word)
            if hit:
                v.add(DENY, f"the command could not be parsed and names {word}, a protected "
                            f"Tess path ({hit})", "protected")
        if re.search(r"\bgit\b[^\n;&|]*\bpush\b", low):
            v.add(DENY, "the command could not be parsed, so Tess cannot check what this push "
                        "would publish", "error")
        if re.search(r"\bgit\b[^\n;&|]*\bremote\s+(add|set-url|rename|remove|rm)\b", low):
            v.add(ASK, "the command could not be parsed and changes where this repository pushes")
        if re.search(r"\bgh\b[^\n;&|]*\b(auth\s+token|--show-token)", low):
            v.add(DENY, "the command could not be parsed and prints your GitHub token", "token")
        if re.search(r"\bgh\b[^\n;&|]*\b(repo\s+(edit|create)|api)\b", low):
            v.add(ASK, "the command could not be parsed and may change a repository's visibility")
        try:
            lx = shlex.shlex(cmd, posix=True, punctuation_chars=";&|()<>\n")
            lx.whitespace, lx.whitespace_split, lx.commenters = " \t\r", True, "#"
            toks, cur, segs = list(lx), [], []
        except ValueError:
            v.add(ASK, "the command could not be parsed (unbalanced quotes), so Tess cannot check it")
            return
        for tok in toks + [";"]:
            if tok in OPERATORS:
                segs, cur = (segs + [cur] if cur else segs), []
            else:
                cur.append(tok)
        for argv in segs:
            _check_segment(root, cwd, argv, v, cmd, depth)
        return
    cur = cwd or str(root)
    for argv in segs:
        _check_segment(root, cur, argv, v, cmd, depth)
        cur = _next_cwd(root, cur, argv)


def _next_cwd(root: Path, cur: str | None, argv: list) -> str | None:
    """Track `cd` / `pushd` across the segments of one command (M1), so
    `cd .git/hooks && echo x > pre-commit` is checked as a write to
    .git/hooks/pre-commit. None = moved somewhere only known at run time."""
    _, argv = _strip_prefix(argv)
    if not argv or os.path.basename(argv[0]) not in ("cd", "pushd", "chdir"):
        return cur
    args = [a for a in argv[1:] if a not in ("-L", "-P", "-e", "--")]
    if not args or args[0] in ("~",):
        return os.path.expanduser("~")
    target = args[0]
    if target == "-" or any(c in target for c in "$`*?[") or cur is None:
        return None
    target = os.path.expanduser(target)
    return target if os.path.isabs(target) else os.path.join(cur, target)


def _command_text(tool_input) -> str:
    cmd = tool_input.get("command") if isinstance(tool_input, dict) else tool_input
    if isinstance(cmd, list):
        if len(cmd) >= 3 and os.path.basename(str(cmd[0])) in SHELLS and str(cmd[1]).startswith("-"):
            return str(cmd[2])
        return shlex.join(str(c) for c in cmd)
    return cmd if isinstance(cmd, str) else ""


def _strings(obj) -> list:
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [s for val in obj.values() for s in _strings(val)]
    if isinstance(obj, list):
        return [s for val in obj for s in _strings(val)]
    return []


# --------------------------------------------------------------------------- evaluate

def evaluate(data: dict, root: Path) -> Verdict:
    v = Verdict()
    tool = str(data.get("tool_name") or "")
    tin = data.get("tool_input")
    tin = tin if tin is not None else {}
    cwd = str(data.get("cwd") or root)
    if tool in DISPATCH_TOOLS:
        hits = _leak_pattern_names(root, json.dumps(tin, ensure_ascii=False), specific_only=False)
        if hits:
            v.add(DENY, "the dispatch carries secret-shaped value(s): " + ", ".join(hits)
                  + ". Pass a vault:// reference instead (conductor/vault.md)", "secret")
    elif tool in SHELL_TOOLS:
        cmd = _command_text(tin)
        hits = _leak_pattern_names(root, cmd, specific_only=True)
        if hits:
            v.add(DENY, "the command contains secret-shaped value(s): " + ", ".join(hits)
                  + ". Read the secret from the environment or `tessctl vault exec` instead", "secret")
        check_command(root, cwd, cmd, v)
    elif tool in EDIT_TOOLS:
        paths = []
        if isinstance(tin, dict):
            paths += [tin[k] for k in ("file_path", "notebook_path", "path") if isinstance(tin.get(k), str)]
        for text in _strings(tin):
            for m in _PATCH_FILE.finditer(text):
                paths.append(m.group(1) or m.group(2))
        if not paths:
            v.add(DENY, "Tess could not tell which files this edit changes, so it cannot check "
                        "them against the protected list", "error")
        for p in paths:
            hit = protected_hit(root, cwd, p)
            if hit:
                v.add(DENY, f"it edits {p}, a protected Tess path ({hit})", "protected")
    elif tool.startswith("mcp__") and any(w in tool.lower() for w in MCP_WRITE_WORDS):
        if isinstance(tin, dict):
            for k, val in tin.items():
                if k.lower() in MCP_PATH_KEYS and isinstance(val, str):
                    hit = protected_hit(root, cwd, val)
                    if hit:
                        v.add(DENY, f"it writes to {val}, a protected Tess path ({hit})", "protected")
    return v


def decide(data: dict, root: Path, runtime: str) -> tuple:
    """(permissionDecision or None, reason) after the Codex ask->deny conversion."""
    v = evaluate(data, root)
    if v.level == ALLOW:
        return None, ""
    tool = str(data.get("tool_name") or "")
    cmd = _command_text(data.get("tool_input") or {}) if tool in SHELL_TOOLS else ""
    is_codex = runtime == "codex" or "turn_id" in data
    why = "; ".join(v.reasons)
    if v.level == ASK and (is_codex or data.get("permission_mode") in NO_PROMPT_MODES):
        where = "Codex" if is_codex else f"{data.get('permission_mode')} mode"
        reason = (f"TESS GATE: blocked because this needs your approval and {where} cannot pause "
                  f"to ask: {why}. If you want it, run it yourself in your own terminal"
                  + (f": {_short(root, cmd)}" if cmd else "") + ".")
        return "deny", reason
    if v.level == ASK:
        return "ask", f"TESS GATE: {why}. Approve only if you meant to."
    fix = " ".join(v.advice)
    return "deny", f"TESS GATE: blocked because {why}." + (f" What to do: {fix}" if fix else "")


def _log(root: Path, data: dict, runtime: str, decision: str, reason: str) -> None:
    try:
        default = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "tess" / "gate-decisions.log"
        path = Path(os.environ.get("TESS_GATE_LOG") or default)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if path.exists() and path.stat().st_size > 1_000_000:
            os.replace(path, str(path) + ".1")
        tool = str(data.get("tool_name") or "")
        cmd = _command_text(data.get("tool_input") or {}) if tool in SHELL_TOOLS else ""
        # Every free-text field passes through _redact here, at the one place the
        # log is written, so a reason that quotes a path or value from the tool
        # input (an edit target, an MCP path argument) cannot carry a
        # credential into the log even if its builder did not redact it.
        def _clean(val):
            return _redact(root, val) if isinstance(val, str) else None

        entry = {"ts": __import__("time").strftime("%Y-%m-%dT%H:%M:%S%z"), "runtime": runtime,
                 "codex": "turn_id" in data, "session_id": _clean(data.get("session_id")),
                 "turn_id": _clean(data.get("turn_id")), "project": str(root),
                 "tool": _redact(root, tool), "decision": decision,
                 "reason": _redact(root, reason)[:600], "command": _short(root, cmd)}
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except Exception as exc:  # never let logging change or lose a decision
        sys.stderr.write(f"tess-gate: could not write the decision log ({type(exc).__name__})\n")


def _emit(decision: str, reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason,
    }}))


def main(argv: list) -> int:
    runtime = "claude"
    if len(argv) >= 2 and argv[0] == "--runtime":
        runtime = argv[1]
    root = _root()
    try:
        data = json.loads(sys.stdin.read())
        if not isinstance(data, dict):
            raise ValueError("payload is not an object")
    except Exception as exc:
        _emit("deny", f"TESS GATE: blocked because the tool-call JSON was unreadable "
                      f"({type(exc).__name__}), so the safety check could not run.")
        return 0
    try:
        decision, reason = decide(data, root, runtime)
    except Exception as exc:  # fail closed
        decision, reason = "deny", (
            f"TESS GATE: blocked because the safety check errored ({type(exc).__name__}). "
            f"Check `./tessctl doctor`; if it keeps failing, run the command yourself.")
    if decision:
        _log(root, data, runtime, decision, reason)
        _emit(decision, reason)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
