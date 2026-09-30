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

v1.0.0 security review round 2 also:
  * denies git options that write a file or run a helper: `--output`
    (`--output=X`, `--output X`, any unique abbreviation such as `--outp`),
    `--output-directory`, `-o` on the diff/log family, `--no-index`,
    `--ext-diff`, `--textconv`, `git grep -O`, GIT_EXTERNAL_DIFF, and `-c` /
    `git config` of keys whose value is a command git runs (H-A);
  * asks (Claude) / denies (Codex) for anything that changes what Tess
    believes a remote already holds or where it points: `git config`
    remote.*.url / pushurl, url.*.insteadOf, tess.privateRemote,
    `git update-ref refs/remotes/...`, a fetch/push refspec into
    refs/remotes/, and `git push --delete` (H-B);
  * denies reads and writes of the per-user key directory
    (~/.config/tess, $XDG_CONFIG_HOME/tess, $TESS_BRAIN_PROVENANCE_DIR) by
    shell commands, Read/Grep/Glob, edits and (Codex; Claude does not route
    MCP tools to this hook) MCP tools (M-1). This is a
    guard against an agent reading a key by accident or on a planted
    instruction, NOT a boundary: the agent runs as the operator's own user,
    so a program it assembles at run time can still read any file the
    operator can, and whatever holds the key can sign as the operator;
  * matches git's unique-prefix abbreviations of long options
    (`--no-veri`, `--forc`, `--mirr`, `--del`, `--outp`) (M-2);
  * asks only in a known interactive `permission_mode` (default,
    acceptEdits, plan, auto); a missing or unknown mode cannot be trusted to
    pause for the operator, so its ask becomes a deny (L-c).

v1.0.0 security review round 3 also:
  * denies git commands that put back other copies of protected files
    (checkout/restore from a commit other than HEAD, checkout-index --prefix
    or -a, --work-tree / --git-dir / GIT_WORK_TREE / GIT_DIR / GIT_INDEX_FILE
    / core.worktree on a writing command, update-index, read-tree --prefix,
    a patch naming one), and asks (Claude) / denies (Codex) for a switch,
    reset --hard, read-tree -u, stash apply, merge, rebase or cherry-pick
    whose target changes a protected file relative to HEAD (N-1);
  * denies HOME= / XDG_CONFIG_HOME= on git and tessctl commands, and checks
    the key directory under the OS user record's home as well (N-2).
  Restoring from HEAD or the index stays allowed; that is the undo path.
  A whole-tree rollback the operator makes runs that commit's own gate.

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
# Claude Code modes that pause and show the operator an "ask" (L-c). Any other
# value, or none, is treated as a mode that cannot ask.
INTERACTIVE_MODES = {"default", "acceptEdits", "plan", "auto"}
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
    ".claude/hooks/**", ".claude/settings.json", ".claude/settings*.json", "scripts/brain/**",
    "scripts/release/**", ".github/CODEOWNERS",
    "CLAUDE.md", "AGENTS.md", "GEMINI.md", ".gemini/settings.json",
    ".codex/config.toml", ".codex/hooks.json", ".codex/rules/**", ".codex/**",
    ".git/hooks/**", ".git/config", ".gitleaks.toml",
    # v1.0.0 final reviews: what HEAD, the index and history resolve to. A
    # write here (a replace ref, a grafts or sparse-checkout file, a moved
    # branch, a crafted index) changes what the "restore from HEAD" undo puts back.
    ".git/info/**", ".git/refs/**", ".git/HEAD", ".git/packed-refs", ".git/index",
    ".git/objects/**", ".git/worktrees/**",
)

DISPATCH_TOOLS = {"Agent", "Task", "spawn_agent"}
READ_TOOLS = {"Read", "Grep", "Glob", "NotebookRead", "LS"}
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
# --- git option tables (security review round 2) -----------------------------
# git's parse-options accepts any unique prefix of a long option (`--no-veri`
# is `--no-verify`), so each dangerous option is matched as a prefix, not by
# exact string. A prefix git would reject as ambiguous is flagged too, which
# costs nothing. _NOT_ABBREV lists real options that are themselves a prefix
# of a flagged one (git takes an exact match over an abbreviation).
_NOT_ABBREV = {"--text"}
_NO_VERIFY_SUBS = {"commit", "merge", "am", "rebase", "cherry-pick", "revert", "push", "pull",
                   "commit-tree", "notes"}
# Options that make git write its output to a file or run an external helper.
_GIT_FILE_OPTS = ("--output", "--output-directory", "--no-index", "--ext-diff", "--textconv")
# Subcommands whose short -o means "write the output to <file/dir>".
_GIT_SHORT_O_SUBS = {"diff", "log", "show", "format-patch", "whatchanged", "archive", "diff-tree",
                     "diff-index", "diff-files", "range-diff"}
# Short options of the diff/log family that take their value in the same
# cluster (`-Sfoo`, `-U5`, `-M50%`): the rest of the cluster is that value.
_DIFF_VALUE_SHORT = set("SGOUlnMCBXIL")
# Config keys whose value is a command git runs or an external diff/pager (H-A),
# set with -c / --config-env or written by `git config`.
_GIT_CMD_KEYS = re.compile(
    r"^(diff\.external|diff\..+\.(command|textconv)|core\.pager|pager\..+|core\.fsmonitor|"
    r"core\.sshcommand|core\.editor|sequence\.editor|core\.askpass|credential\.helper|"
    r"credential\..+\.helper|gpg\.program|gpg\..+\.program|filter\..+\.(clean|smudge|process)|"
    r"merge\..+\.driver|core\.gitproxy|core\.alternaterefscommand|uploadpack\.packobjectshook|"
    r"remote\..+\.(uploadpack|receivepack)|protocol\..*allow)$", re.IGNORECASE)
_BENIGN_VALUE = re.compile(r"^(cat|less|more|true|:|vi|vim|nano)(\s+-[A-Za-z]+)*$|^$")
# Config keys the public-remote guard trusts to know where a push goes or
# which remote is private (H-B).
_GIT_REMOTE_KEYS = re.compile(r"^(remote\..+\.(url|pushurl)|url\..+\.(insteadof|pushinsteadof)|"
                              r"tess\.privateremote)$", re.IGNORECASE)
# The key directory named in command text (M-1): `~/.config/tess`,
# `$HOME/.config/tess`, `${XDG_CONFIG_HOME}/tess`, the provenance override.
_KEY_TEXT = re.compile(r"(?i)\.config[/\\]+tess(?![\w.-])|\$\{?XDG_CONFIG_HOME\}?[/\\]+tess(?![\w.-])"
                       r"|TESS_BRAIN_PROVENANCE_DIR")
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


# L-b: a whole PEM block (header, base64 body, footer; a missing footer
# redacts to the end of the text), and any long base64 run that is not a
# plain hex object id, are removed before the scanner's own patterns run.
_PEM_BLOCK = re.compile(r"-----BEGIN [A-Z0-9 ]{0,40}-----.*?(?:-----END [A-Z0-9 ]{0,40}-----|\Z)",
                        re.DOTALL)
_B64_RUN = re.compile(r"(?<![A-Za-z0-9+/=_-])[A-Za-z0-9+/_-]{32,}={0,2}(?![A-Za-z0-9+/=_-])")


def _redact_blob(m) -> str:
    s = m.group(0)
    return s if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", s) else "[REDACTED]"


def _redact(root: Path, text: str) -> str:
    text = _URL_CREDS.sub(r"\1***@", text)
    text = _PEM_BLOCK.sub("[REDACTED PEM BLOCK]", text)
    text = _B64_RUN.sub(_redact_blob, text)
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


# --------------------------------------------------------------------------- key directory (M-1)

def _os_home() -> str:
    """The home directory in the OS user record. tessctl locates the operator
    key from here, never from $HOME / $XDG_CONFIG_HOME (round 3, N-2)."""
    try:
        import pwd
        return pwd.getpwuid(os.getuid()).pw_dir
    except (ImportError, KeyError, AttributeError):
        return os.path.expanduser("~")


def _key_dirs() -> list:
    """Real paths of the per-user directories that hold Tess signing keys:
    the brain provenance key and the operator key dir (~/.config/tess), the
    XDG variant, and the provenance override. Same-user files: see the
    module docstring for what this does and does not stop."""
    home = os.path.expanduser("~")
    dirs = [os.path.join(home, ".config", "tess"), os.path.join(_os_home(), ".config", "tess")]
    if os.environ.get("XDG_CONFIG_HOME"):
        dirs.append(os.path.join(os.environ["XDG_CONFIG_HOME"], "tess"))
    if os.environ.get("TESS_BRAIN_PROVENANCE_DIR"):
        dirs.append(os.environ["TESS_BRAIN_PROVENANCE_DIR"])
    return sorted({os.path.realpath(d) for d in dirs})


def _expand(path: str) -> str:
    home = os.path.expanduser("~")
    xdg = os.environ.get("XDG_CONFIG_HOME") or os.path.join(home, ".config")
    for var, val in (("HOME", home), ("XDG_CONFIG_HOME", xdg)):
        path = path.replace("${" + var + "}", val).replace("$" + var, val)
    return os.path.expanduser(path)


def key_hit(cwd: str, path: str, ancestors: bool = False) -> str | None:
    """The key directory `path` reaches (itself, inside it, or through a
    symlink); with `ancestors`, also a directory ABOVE it that a recursive
    search (Grep, `grep -r`) would descend into."""
    if not path or not isinstance(path, str):
        return None
    full = _expand(path)
    full = full if os.path.isabs(full) else os.path.join(cwd or os.getcwd(), full)
    cands = {os.path.normpath(full), os.path.realpath(full)}
    home = os.path.realpath(os.path.expanduser("~")).rstrip(os.sep) + os.sep
    for d in _key_dirs():
        for c in cands:
            if c == d or c.startswith(d.rstrip(os.sep) + os.sep):
                return d
            # A search rooted between the home directory and the key dir
            # (~/.config). A search of the whole home directory or of / is
            # not refused: that is the stated same-user limit, not a boundary.
            if ancestors and c.startswith(home) and d.startswith(c.rstrip(os.sep) + os.sep):
                return d
    return None


def _check_key_text(cwd: str, argv: list, raw: str, v) -> None:
    """Bash: any argument (or `--opt=value` value) that reaches the key
    directory, or command text that names it (an inline `python -c open(...)`)."""
    if _KEY_TEXT.search(raw):
        v.add(DENY, "it reads or writes Tess's key directory (~/.config/tess); the signing keys "
                    "there are for the operator's own tools, not for an agent", "keys")
        return
    name = os.path.basename(argv[0]) if argv else ""
    recursive = name in ("grep", "rg", "find", "tar", "zip", "rsync", "cp", "ln", "fd") or \
        any(re.match(r"^-[A-Za-z]*[rR]", a) for a in argv[1:])
    for a in argv[1:]:
        for part in {a, a.split("=", 1)[-1]}:
            if key_hit(cwd, part, ancestors=recursive) or (
                    any(c in part for c in "*?[") and any(key_hit(cwd, g) for g in _glob(cwd, part))):
                v.add(DENY, f"it reaches {a}, Tess's key directory; the signing keys there are for "
                            "the operator's own tools, not for an agent", "keys")
                return


def _glob(cwd: str, pattern: str) -> list:
    import glob as _g
    pat = _expand(pattern)
    pat = pat if os.path.isabs(pat) else os.path.join(cwd or os.getcwd(), pat)
    try:
        return _g.glob(pat, recursive=False)[:200]
    except Exception:
        return []


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
    "gitfile": "Let git print to the terminal (drop the output-file option), or redirect the "
               "output to a file outside Tess's protected paths yourself.",
    "keys": "Tess's signing keys stay with the operator. Run the tessctl or tessbrain command "
            "that needs the key; it reads the key itself.",
    "rollback": "Protected Tess files come back only from HEAD (`git restore --source=HEAD -- "
                "<path>`) or through a reviewed release (`./tessctl update`). To check out an "
                "older copy on purpose, run the git command yourself outside the agent.",
    "envhome": "Run git and tessctl with your normal HOME and XDG_CONFIG_HOME; Tess finds the "
               "operator's key directory from the OS user record either way.",
    "operator": "Ask the operator to run it in their own terminal and type the answer "
                "themselves (for an update: `./tessctl update`, then `accept <version>`).",
}

# v1.0.0 (release integration, item a): `tessctl update` (new safety rules) and
# `tessctl approve` ask a person at a terminal to type the answer. An agent
# must not fake that terminal or type the answer for them.
# v1.0.0 final review (Cyra A-2): these are matched on the shlex-parsed words of
# every sub-command (quotes and backslashes removed the way the shell removes
# them), plus the command text with quotes and backslashes stripped, so
# `./tess''ctl anchor ac''cept` or `"anchor" "accept"` read as what runs.
_PTY_WRAPPER = re.compile(r"(?i)(?<![\w.-])(script|expect|unbuffer|socat|pexpect|ptyprocess|openpty|"
                          r"forkpty|pty\.spawn|import\s+pty|from\s+pty)(?![\w.-])")
_TYPED_APPROVAL = re.compile(r"(?i)\baccept\W+v?\d|\baccept\W+safety\W+changes\b")
# v1.0.0: the enforcement anchor is written only by the operator (accept) or
# the installer (init); an agent never records its own changes as approved.
_ANCHOR_WRITE = re.compile(r"(?i)\banchor\W+(accept|init)\b")
# Programs that fake a terminal or type into one.
_PTY_PROGRAMS = {"script", "expect", "unbuffer", "socat", "tmux", "screen", "dtach", "zpty",
                 "empty", "ttyexec", "pexpect"}
# Programs that run the command they are given (the tessctl word is theirs to run).
_RUNNERS = _PTY_PROGRAMS | {"timeout", "gtimeout", "xargs", "stdbuf", "caffeinate", "watch",
                            "parallel", "setsid", "arch", "open", "osascript"}
# An interpreter that opens a pseudo-terminal: the word tessctl can be built at
# run time (`'tess' + 'ctl'`), so the pty itself is the signal.
_PTY_CODE = re.compile(r"(?i)\bimport\s+pty\b|\bfrom\s+pty\b|\bpty\.(spawn|fork|openpty)\b|"
                       r"\bos\.(openpty|forkpty)\b|\bpexpect\b|\bptyprocess\b|IO::Pty|node-pty")
# tessctl subcommands that ask the operator to type the answer.
_PROMPT_SUBS = {"update", "self-update", "approve", "anchor"}


def _unquote(text: str) -> str:
    """The command text with shell quoting removed (`tess''ctl` -> `tessctl`)."""
    return re.sub(r"[\"'\\]", "", text)


def _is_tessctl(word: str) -> bool:
    return os.path.basename(_unquote(word).rstrip("/")).lower() in ("tessctl", "tessctl.py")


def _operator_pipelines(cmd: str) -> list | None:
    """[[segment argv, ...] per pipeline] or None when the text does not parse
    either way (the caller then judges the unquoted text alone)."""
    for commenters in ("", "#"):
        try:
            lx = shlex.shlex(cmd, posix=True, punctuation_chars=";&|()<>\n")
            lx.whitespace, lx.whitespace_split, lx.commenters = " \t\r", True, commenters
            toks = list(lx)
        except ValueError:
            continue
        pipes, cur, seg = [], [], []
        for tok in toks + [";"]:
            if tok in ("|", "|&"):
                cur, seg = cur + [seg], []
            elif tok in OPERATORS:
                cur = cur + [seg] if seg else cur
                pipes, cur, seg = (pipes + [cur] if cur else pipes), [], []
            else:
                seg.append(tok)
        return pipes
    return None


def _tessctl_call(argv: list) -> list | None:
    """The words after `tessctl` when this segment runs it (directly, through
    python3 [-I -B ...], or through a runner/pty program); else None."""
    if not argv:
        return None
    name = os.path.basename(argv[0]).lower()
    if _is_tessctl(argv[0]):
        return argv[1:]
    if INTERPRETERS.match(name) or name in SHELLS:
        i = 1
        while i < len(argv) and argv[i].startswith("-") and argv[i] not in ("-c", "-e", "-"):
            i += 2 if argv[i] in ("-W", "-X", "-m") else 1
        if i < len(argv) and _is_tessctl(argv[i]):
            return argv[i + 1:]
        return None
    if name in _RUNNERS:
        for j, a in enumerate(argv[1:], 1):
            if _is_tessctl(a) or re.search(r"(?i)tessctl", _unquote(a)):
                return argv[j + 1:] if _is_tessctl(a) else _unquote(a).split()
    return None


def _check_operator_only(cmd: str, v) -> None:
    flat = _unquote(cmd)
    pipes = _operator_pipelines(cmd)
    calls, fed = [], False
    for pipe in pipes or []:
        for k, seg in enumerate(pipe):
            _, argv = _strip_prefix(seg)
            words = _tessctl_call(argv)
            name = os.path.basename(argv[0]).lower() if argv else ""
            if name in ("tmux", "screen") and any(
                    re.search(r"(?i)\b(accept|anchor)\b", _unquote(a)) for a in argv[1:]):
                v.add(DENY, "only the operator can answer Tess's approval prompts; this command "
                            "would type the approval into a terminal for them", "operator")
            if (INTERPRETERS.match(name) or name in ("-",)) and _PTY_CODE.search(flat):
                v.add(DENY, "it runs interpreter code that opens a pseudo-terminal, which can fake "
                            "the terminal Tess's approval prompts are typed into", "operator")
            if words is None:
                continue
            calls.append((name, [w.lower() for w in words]))
            sub = next((w.lower() for w in words if not w.startswith("-")), "")
            redirected = any(re.match(r"^\d*<", w) for w in words)
            if sub in _PROMPT_SUBS and (k > 0 or redirected):
                fed = True
    tess_text = re.search(r"(?i)tessctl", flat) is not None
    if not calls and not tess_text:
        return
    if (tess_text and _ANCHOR_WRITE.search(flat)) or any(
            "anchor" in w and {"accept", "init"} & set(w[w.index("anchor") + 1:]) for _, w in calls):
        v.add(DENY, "only the operator can record Tess's safety files as approved "
                    "(`tessctl anchor accept`, in their own terminal)", "operator")
    if (fed or any(n in _PTY_PROGRAMS for n, _ in calls)
            or (calls and re.search(r"(?i)\baccept\b", flat))
            or (tess_text and (_PTY_WRAPPER.search(flat) or _TYPED_APPROVAL.search(flat)))):
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


def _check_git(root: Path, cwd: str, env: dict, argv: list, v: Verdict, raw: str, depth: int = 0):
    args = argv[1:]
    cfg, i, gcwd, redirect = [], 0, cwd, None
    while i < len(args) and args[i].startswith("-"):
        a = args[i]
        if a.split("=", 1)[0] in ("--work-tree", "--git-dir"):
            redirect = a.split("=", 1)[0]
        if a in GIT_VALUE_OPTS and i + 1 < len(args):
            if a == "-c" or a == "--config-env":
                cfg.append(args[i + 1])
            if a == "-C":
                # A -C target known only at run time: later path checks cannot resolve it.
                gcwd = None if gcwd is None or any(c in args[i + 1] for c in "$`*?[") else \
                    os.path.join(gcwd or str(root), os.path.expanduser(args[i + 1]))
            i += 2
            continue
        if a.startswith("--config-env=") or a.startswith("-c") and len(a) > 2:
            cfg.append(a.split("=", 1)[1] if a.startswith("--config-env=") else a[2:])
        i += 1
    sub = args[i] if i < len(args) else ""
    rest = args[i + 1:]
    redirect = redirect or next((k for k in env if k in _REDIRECT_ENV), None) or next(
        ("-c " + c.split("=", 1)[0] for c in cfg if re.match(r"(?i)^core\.(worktree|bare)\b", c)), None)
    _check_git_tree_writes(root, gcwd, sub, rest, v, redirect, raw, depth)
    gcwd = gcwd or cwd
    hooks_env = any("hookspath" in (k + "=" + val).lower() for k, val in env.items()
                    if k.startswith("GIT_CONFIG"))
    if hooks_env or any(c.lower().startswith("core.hookspath") for c in cfg):
        v.add(DENY, "it points git at a different hooks directory (core.hooksPath), which "
                    "switches off Tess's git hooks (secret scan, ship gate, public-remote guard)", "hookspath")
    if any(_GIT_CONFIG_INDIRECT.match(c) for c in cfg):
        v.add(DENY, "it sets a git include or alias on the command line, which can switch off "
                    "Tess's git hooks or run another command", "hookspath")
    _check_git_cmd_values(root, gcwd, env, cfg, v, depth)
    if any(_GIT_REMOTE_KEYS.match(c.split("=", 1)[0]) for c in cfg):
        v.add(ASK, "it overrides a remote's URL (or Tess's private-remote list) for one command, "
                   "which changes where a push goes")
    opts = rest[:rest.index("--")] if "--" in rest else rest
    if sub == "config":
        _check_git_config(rest, v)
    _check_git_history_views(root, gcwd, sub, rest, cfg, v, raw, depth)
    if sub in _NO_VERIFY_SUBS and any(_abbrev(a, "--no-verify") for a in opts):
        v.add(DENY, "--no-verify skips Tess's git hooks (secret scan and ship gate)", "noverify")
    if sub == "commit" and _commit_no_verify(rest):
        v.add(DENY, "`git commit -n` is --no-verify: it skips Tess's git hooks", "noverify")
    _check_git_file_opts(sub, opts, v)
    if sub == "remote" and rest and rest[0] in ("add", "set-url", "rename", "remove", "rm"):
        v.add(ASK, "it changes where this repository pushes (git remote " + rest[0] + ")")
    if sub == "update-ref" and any(a == "--stdin" or a.startswith("refs/remotes/") for a in rest):
        v.add(ASK, "it writes a remote-tracking ref (refs/remotes/...), which records what a "
                   "remote holds; a forged one could hide data from the public-remote guard")
    if sub in ("fetch", "push") and any(
            not a.startswith("-") and ":" in a and a.lstrip("+").split(":", 1)[1].startswith(
                ("refs/remotes/", "remotes/")) for a in rest):
        v.add(ASK, "its refspec writes a remote-tracking ref (refs/remotes/...), which records "
                   "what a remote holds")
    if sub in ("rm", "mv"):
        for a in rest:
            hit = not a.startswith("-") and protected_hit(root, gcwd, a)
            if hit:
                v.add(DENY, f"it removes or moves {a}, a protected Tess path ({hit})", "protected")
    if sub == "push":
        _check_push(root, gcwd, rest, v)


_HISTORY_ADVICE = ("git replace refs, sparse checkouts and fetching into the checked-out branch "
                   "change which files git writes without naming them")


def _has_replace_refs(cwd: str) -> bool | None:
    out = _git_ro(cwd, "for-each-ref", "--count=1", "--format=%(refname)", "refs/replace/")
    return None if out is None else bool(out.strip())


def _check_git_history_views(root: Path, cwd: str, sub: str, rest: list, cfg: list,
                             v: Verdict, raw: str, depth: int):
    """v1.0.0 final reviews (GPT-6 + Cyra): git routes that change what HEAD,
    a branch or the working tree resolve to without naming a protected path."""
    if sub == "replace":
        v.add(DENY, "`git replace` makes git read one commit or file as another, so a later "
                    "restore from HEAD could put back a different copy of Tess's gate", "rollback")
    if sub == "update-ref" and any(a.startswith(("refs/replace/", "replace/")) for a in rest):
        v.add(DENY, "it writes a git replace ref (refs/replace/...), which makes git read one "
                    "commit or file as another", "rollback")
    if sub == "update-ref" and "--stdin" in rest:
        v.add(DENY, "`git update-ref --stdin` writes refs Tess cannot see (replace refs "
                    "included)", "rollback")
    if sub in ("fetch", "push", "pull") and any(
            not a.startswith("-") and ":" in a and a.lstrip("+").split(":", 1)[1].startswith(
                ("refs/replace/", "replace/")) for a in rest):
        v.add(DENY, "its refspec writes git replace refs (refs/replace/...), which make git read "
                    "one commit or file as another", "rollback")
    if sub == "fetch" and any(_abbrev(a, "--update-head-ok") or (
            re.match(r"^-[A-Za-z0-9]*u", a) and not a.startswith("--")) for a in rest):
        v.add(DENY, "`git fetch --update-head-ok` (-u) can move the checked-out branch without "
                    "touching the files; a reset or restore from HEAD would then bring in that "
                    "commit's copy of Tess's gate", "rollback")
    if sub == "sparse-checkout" and rest[:1] != ["list"] and "-h" not in rest:
        v.add(DENY, "`git sparse-checkout` can delete Tess's hook configuration from the working "
                    "tree, so the next session would run with no Tess hook at all", "rollback")
    if any(c.split("=", 1)[0].lower().startswith("core.sparsecheckout") for c in cfg):
        v.add(DENY, "it turns on a sparse checkout (-c core.sparseCheckout), which lets git delete "
                    "Tess's hook configuration from the working tree", "rollback")
    if sub == "bisect" and cwd:
        _git_bisect(root, cwd, rest, v, depth)


def _abbrev(arg: str, *targets: str) -> str | None:
    """The flagged long option `arg` names, exactly or as a unique-prefix
    abbreviation git would accept (`--no-veri` -> `--no-verify`)."""
    if not arg.startswith("--") or len(arg) < 3:
        return None
    name = arg.split("=", 1)[0]
    if name in _NOT_ABBREV:
        return None
    return next((t for t in targets if t.startswith(name)), None)


def _check_git_cmd_values(root: Path, cwd: str, env: dict, cfg: list, v: Verdict, depth: int):
    """A command hidden in a git setting (H-A): `-c core.pager='cp x .git/hooks/pre-push'`,
    `GIT_EXTERNAL_DIFF=...`. The value is checked as a command in its own right."""
    values = [c.split("=", 1)[1] for c in cfg
              if "=" in c and _GIT_CMD_KEYS.match(c.split("=", 1)[0])]
    values += [val for k, val in env.items()
               if k in ("GIT_EXTERNAL_DIFF", "GIT_PAGER", "GIT_EDITOR", "GIT_SEQUENCE_EDITOR",
                        "GIT_SSH_COMMAND", "GIT_SSH", "GIT_ASKPASS", "GIT_PROXY_COMMAND")]
    for val in values:
        if depth < 4 and val.strip():
            check_command(root, cwd, val, v, depth + 1)
    if any(c.split("=", 1)[0].lower().startswith("core.fsmonitor") and c.split("=", 1)[-1].lower() not in
           ("false", "0", "", "true", "1", "yes", "no", "on", "off") for c in cfg):
        v.add(DENY, "it points git's fsmonitor at a program, which git runs on every command", "hookspath")


def _check_git_config(rest: list, v: Verdict):
    keys = [a.lower() for a in rest]
    reading = any(k in ("--get", "--get-all", "--list", "-l", "--get-regexp", "get", "list",
                        "--get-urlmatch", "--show-origin", "--show-scope")
                  for k in keys) and not any(k in ("set", "--add", "--replace-all", "unset",
                                                  "--unset", "--unset-all") for k in keys)
    if reading:
        return
    if any(k == "core.hookspath" or k.startswith("core.hookspath=") for k in keys):
        v.add(DENY, "it changes core.hooksPath, which switches off Tess's git hooks", "hookspath")
    if any(re.match(r"^core\.sparsecheckout", k) for k in keys):
        v.add(DENY, "it turns on a sparse checkout (core.sparseCheckout), which lets git delete "
                    "Tess's hook configuration from the working tree", "rollback")
    if any(re.match(r"^core\.(worktree|bare)(=|$)", k) for k in keys):
        v.add(DENY, "it changes core.worktree / core.bare, which points git's file writes at "
                    "another directory (Tess's git hooks included)", "protected")
    if any(k == "--file" or k == "-f" for k in keys) and any("hook" in k for k in keys):
        v.add(DENY, "it edits git hook configuration directly", "hookspath")
    if any(_GIT_CONFIG_INDIRECT.match(k) for k in keys):
        v.add(DENY, "it writes a git include or alias, which can switch off Tess's git hooks "
                    "or run another command in place of a git one", "hookspath")
    words = [a for a in rest if not a.startswith("-") and a not in ("set", "unset")]
    if words and _GIT_CMD_KEYS.match(words[0]) and not (
            len(words) > 1 and _BENIGN_VALUE.match(words[1].strip())):
        v.add(DENY, f"it saves a command in git config ({words[0]}); git would run it later, "
                    "outside Tess's checks", "hookspath")
    if words and _GIT_REMOTE_KEYS.match(words[0]):
        v.add(ASK, f"it changes {words[0]}, which decides where a push goes or which remote Tess "
                   "treats as private")


def _check_git_file_opts(sub: str, opts: list, v: Verdict):
    """H-A: git options that write the command's output to a file (any path,
    hooks and settings included) or run an external diff/text-conversion."""
    for i, a in enumerate(opts):
        hit = _abbrev(a, *_GIT_FILE_OPTS)
        if hit:
            v.add(DENY, f"`{a}` ({hit}) makes git write a file or run an external program; "
                        "git can overwrite any file this way, Tess's hooks and settings included",
                  "gitfile")
        if sub == "grep" and (a.startswith("--op") or re.match(r"^-[A-Za-z]*O", a)):
            v.add(DENY, "`git grep -O` runs a program on the matching files", "gitfile")
        if sub in _GIT_SHORT_O_SUBS and re.match(r"^-[A-Za-z]", a) and not a.startswith("--"):
            for ch in a[1:]:
                if ch == "o":
                    v.add(DENY, f"`{a}` (-o) makes git write its output to a file or directory",
                          "gitfile")
                    break
                if ch in _DIFF_VALUE_SHORT:
                    break


# --------------------------------------------------------------------------- git tree writes (round 3, N-1)
# git itself can rewrite the gate: `git checkout <old> -- .claude/hooks .tess/...`
# brings back an old gate with matching pins, and --work-tree / GIT_WORK_TREE /
# core.worktree / checkout-index --prefix point git's writes at .git/hooks.
# Protected files come back only from HEAD or the index (the documented undo);
# a switch, reset or merge that changes them relative to HEAD needs the operator.

# Subcommands that write the working tree or the index from a commit or patch.
_TREE_WRITE_SUBS = {"checkout", "restore", "checkout-index", "reset", "switch", "read-tree",
                    "stash", "update-index", "merge", "rebase", "cherry-pick", "revert", "pull",
                    "am", "apply", "worktree", "clone", "symbolic-ref", "update-ref"}
_CLONE_VALS = ("--branch", "--origin", "--config", "--upload-pack", "--depth", "--reference",
               "--separate-git-dir", "--template", "--jobs", "--filter", "--shallow-since",
               "--shallow-exclude", "--server-option", "--bundle-uri", "--ref-format",
               "--reference-if-able")
_REDIRECT_ENV = {"GIT_WORK_TREE", "GIT_DIR", "GIT_INDEX_FILE", "GIT_COMMON_DIR"}
_SAME_SOURCE = {"HEAD", "@"}
_EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
_RESUME = ("--abort", "--continue", "--skip", "--quit", "--edit-todo", "--resolved",
           "--show-current-patch")
# Short options that take a value, per subcommand (`cherry-pick -s` is signoff, not a strategy).
_MERGE_SHORT_VALS = {"merge": "msXF", "rebase": "sXx", "cherry-pick": "mX", "revert": "mX"}


def _git_ro(cwd: str, *args) -> str | None:
    """Read-only git for the gate's own questions: no shell, no GIT_* from the
    runtime, fsmonitor off. None when git fails (the caller fails closed)."""
    env = {k: val for k, val in os.environ.items() if not k.startswith("GIT_")}
    env["GIT_NO_REPLACE_OBJECTS"] = "1"  # the gate reads the real objects
    try:
        r = subprocess.run(["git", "-C", cwd, "-c", "core.fsmonitor=false", *args],
                           capture_output=True, text=True, timeout=20, env=env)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def _tree(cwd: str, rev: str) -> str | None:
    if not rev or rev.startswith("-") or "\n" in rev:
        return None
    out = _git_ro(cwd, "rev-parse", "--verify", "--quiet", rev + "^{tree}")
    return out.strip() if out else None


def _protected_globs(root: Path) -> tuple:
    return tuple(sorted(_security_tier_paths(root))) + PROTECTED_GLOBS


def _changed_protected(root: Path, cwd: str, a: str | None, b: str, specs=()) -> list | None:
    """Protected paths whose content differs between tree-ish `a` (None: the
    empty tree) and `b`, limited to `specs`. None: git could not tell."""
    ta = _EMPTY_TREE if a is None else (_tree(cwd, a) or (a == "HEAD" and _unborn_head(cwd)))
    tb = _tree(cwd, b)
    top = _git_ro(cwd, "rev-parse", "--show-toplevel")
    if not ta or not tb or not top:
        return None
    out = _git_ro(cwd, "diff-tree", "-r", "--name-only", "-z", "--no-renames", ta, tb, "--", *specs)
    if out is None:
        return None
    globs, hits = _protected_globs(root), []
    for name in out.split("\0"):
        rel = name and _rel_to_root(root, top.strip(), name)
        if rel and _glob_hit(rel, globs) and rel not in hits:
            hits.append(rel)
    return hits


def _unborn_head(cwd: str) -> str | None:
    """HEAD of a repository with no commit yet reads as the empty tree."""
    return _EMPTY_TREE if _git_ro(cwd, "rev-parse", "--git-dir") is not None else None


def _pathspec_hit(root: Path, cwd: str, spec: str) -> str | None:
    """The protected path a pathspec names, contains, or sits inside (after
    `:(top)` / `:/` magic); "the whole repository" for the top. Exclusions
    (`:!x`, `:(exclude)x`) add nothing."""
    s = spec
    m = re.match(r"^:\(([^)]*)\)(.*)$", s, re.S) or re.match(r"^:([/!^]*):?(.*)$", s, re.S)
    if s.startswith(":") and m:
        magic = m.group(1).lower()
        if "exclude" in magic or "!" in magic or "^" in magic:
            return None
        s = m.group(2)
        if "top" in magic or "/" in magic:
            cwd = str(root)
    rel = _rel_to_root(root, cwd, s or ".")
    if rel is None:
        return None
    if rel == ".":
        return "the whole repository"
    return _glob_hit(rel, _protected_globs(root))


def _parse(rest: list, short_vals: str = "", long_vals: tuple = ()) -> tuple:
    """(options, positionals before --, arguments after --, saw --). An option
    that takes a value keeps it (`-b name`, `-sREV`, `--source REV`)."""
    opts, pos, after, dd, i = {}, [], [], False, 0
    while i < len(rest):
        a = rest[i]
        if dd:
            after.append(a)
        elif a == "--":
            dd = True
        elif a.startswith("--"):
            name, eq, val = a.partition("=")
            full = _abbrev(name, *long_vals) if long_vals else None
            if full and not eq and i + 1 < len(rest):
                opts[full] = rest[i + 1]
                i += 1
            else:
                opts[full or name] = val if eq else True
        elif a.startswith("-") and len(a) > 1:
            for k, ch in enumerate(a[1:], 1):
                if ch in short_vals:
                    val = a[k + 1:]
                    if not val and i + 1 < len(rest):
                        i += 1
                        val = rest[i]
                    opts["-" + ch] = val
                    break
                opts["-" + ch] = True
        else:
            pos.append(a)
        i += 1
    return opts, pos, after, dd


def _rev(a: str) -> str:
    return "@{-1}" if a == "-" else a


def _restore_from(root: Path, cwd: str, source, specs: list, v: Verdict, what: str):
    """Files written from `source` (a commit or tree): only HEAD/the index may
    supply a protected file."""
    if source is None or source is True or source in _SAME_SOURCE or not specs:
        return
    for s in specs:
        hit = _pathspec_hit(root, cwd, s)
        if hit:
            v.add(DENY, f"`{what}` overwrites {s} ({hit}) with the copy from {source}; an older or "
                        "different copy of Tess's gate, pins or rules would then run", "rollback")
            return
    changed = _changed_protected(root, cwd, "HEAD", source, specs)
    if changed is None:
        v.add(DENY, f"`{what}` writes files from {source}, which Tess cannot resolve yet, so it "
                    "cannot check them against the protected list", "rollback")
    elif changed:
        v.add(DENY, f"`{what}` overwrites protected Tess files ({', '.join(changed[:5])}) with the "
                    f"copies from {source}", "rollback")


def _move_to(root: Path, cwd: str, target: str, v: Verdict, what: str, base: str | None = "HEAD"):
    """The working tree becomes `target` (a switch, reset --hard, merge): the
    operator decides when that changes protected files relative to HEAD."""
    if base == "merge-base":
        mb = _git_ro(cwd, "merge-base", "HEAD", target) if not target.startswith("-") else None
        base = mb.strip() if mb else None
        if base is None:
            v.add(ASK, f"`{what}` brings in {target}, and Tess cannot tell what that changes; it may "
                       "replace Tess's own gate or rules")
            return
    changed = _changed_protected(root, cwd, base, target)
    if changed is None:
        v.add(ASK, f"`{what}` switches the working tree to {target}, which Tess cannot resolve yet; "
                   "it may replace Tess's own gate or rules")
    elif changed:
        v.add(ASK, f"`{what}` changes protected Tess files ({', '.join(changed[:5])}): the copy of "
                   f"the gate and rules in {target} would run from then on")


def _dwim(cwd: str, name: str) -> str | None:
    """`git checkout foo` / `git switch foo` with only refs/remotes/*/foo."""
    out = _git_ro(cwd, "for-each-ref", "--format=%(refname)", f"refs/remotes/*/{name}")
    refs = [r for r in (out or "").split("\n") if r]
    return refs[0] if len(refs) == 1 else None


def _git_checkout(root, cwd, rest, v):
    opts, pos, after, dd = _parse(rest, "bB", ("--orphan", "--pathspec-from-file"))
    new = next((opts[k] for k in ("-b", "-B", "--orphan") if k in opts), None)
    pff = opts.get("--pathspec-from-file")
    if dd:
        source = pos[0] if pos else None
        if after or pff:
            if pff and source not in (None, *_SAME_SOURCE):
                v.add(DENY, "`git checkout <commit> --pathspec-from-file` names files Tess cannot "
                            "see", "rollback")
            return _restore_from(root, cwd, source, after, v, "git checkout")
        return source and _move_to(root, cwd, _rev(source), v, "git checkout")
    if not pos:
        return None
    first = _rev(pos[0])
    if new is not None or len(pos) == 1:
        if _tree(cwd, first):
            return _move_to(root, cwd, first, v, "git checkout")
        if new is None and os.path.lexists(os.path.join(cwd, pos[0])):
            return None  # a path, restored from the index
        return _move_to(root, cwd, _dwim(cwd, pos[0]) or first, v, "git checkout")
    if _tree(cwd, first):
        return _restore_from(root, cwd, first, pos[1:], v, "git checkout")
    if all(os.path.lexists(os.path.join(cwd, p)) for p in pos):
        return None  # paths, restored from the index
    return _restore_from(root, cwd, first, pos[1:], v, "git checkout")


def _git_restore(root, cwd, rest, v):
    opts, pos, after, _ = _parse(rest, "s", ("--source", "--pathspec-from-file"))
    source = opts.get("-s", opts.get("--source"))
    if opts.get("--pathspec-from-file") and source not in (None, *_SAME_SOURCE):
        v.add(DENY, "`git restore --source --pathspec-from-file` names files Tess cannot see", "rollback")
    _restore_from(root, cwd, source, pos + after, v, "git restore")


def _git_reset(root, cwd, rest, v):
    opts, pos, after, dd = _parse(rest, "", ("--pathspec-from-file",))
    if dd:
        rev, specs = (pos[0] if pos else "HEAD"), after
    elif pos and _tree(cwd, pos[0]):
        rev, specs = pos[0], pos[1:]
    else:
        rev, specs = "HEAD", pos
    if specs:
        return _restore_from(root, cwd, rev, specs, v, "git reset")
    if rev not in _SAME_SOURCE:
        # --soft / --mixed move HEAD (and the index) without the files; the
        # "restore from HEAD" undo would then bring back the other copy.
        _move_to(root, cwd, rev, v, "git reset")
    return None


def _git_head_ref(root, cwd, sub, rest, v):
    """`git symbolic-ref HEAD <ref>` / `git update-ref HEAD|<current branch> <rev>`
    move HEAD without the files; the HEAD undo would then restore that tree."""
    opts, pos, _, _ = _parse(rest, "m", ("--message",))
    if len(pos) < 2 or "-d" in opts or "--delete" in opts:
        return
    current = (_git_ro(cwd, "symbolic-ref", "-q", "HEAD") or "").strip()
    if pos[0] == "HEAD" or (sub == "update-ref" and current and pos[0] == current):
        _move_to(root, cwd, pos[1], v, f"git {sub}")


def _git_switch(root, cwd, rest, v):
    opts, pos, _, _ = _parse(rest, "cC", ("--create", "--force-create", "--orphan"))
    if "--orphan" in opts:
        return v.add(ASK, "`git switch --orphan` empties the working tree, Tess's gate and rules "
                          "included")
    new = any(k in opts for k in ("-c", "-C", "--create", "--force-create"))
    target = pos[0] if pos else None
    if target is None:
        return None
    target = _rev(target)
    if not new and not _tree(cwd, target):
        target = _dwim(cwd, target) or target
    return _move_to(root, cwd, target, v, "git switch")


def _git_read_tree(root, cwd, rest, v):
    opts, pos, _, _ = _parse(rest)
    if any(k.startswith("--index-output") for k in opts):
        v.add(DENY, "`git read-tree --index-output` writes an index file to a path of its "
                    "choosing", "rollback")
    prefix = opts.get("--prefix")
    if isinstance(prefix, str) and _pathspec_hit(root, cwd, prefix.rstrip("/") or "."):
        v.add(DENY, f"`git read-tree --prefix={prefix}` writes index entries inside a protected "
                    "Tess path", "rollback")
    # Without -u only the index changes, but the "restore from the index" undo
    # would then write that tree's copies.
    for t in pos:
        _move_to(root, cwd, t, v, "git read-tree")


def _git_stash(root, cwd, rest, v):
    if not rest or rest[0] not in ("apply", "pop", "branch"):
        return
    refs = [a for a in rest[1:] if not a.startswith("-")]
    ref = refs[1] if rest[0] == "branch" and len(refs) > 1 else (
        refs[0] if refs and rest[0] != "branch" else "stash@{0}")
    ref = f"stash@{{{ref}}}" if ref.isdigit() else ref
    if ref == "stash@{0}" and _git_ro(cwd, "rev-parse", "--verify", "--quiet", "refs/stash") is None:
        return  # no stash: git reports it and changes nothing
    changed = _changed_protected(root, cwd, ref + "^1", ref)
    if changed is not None and _tree(cwd, ref + "^3"):
        extra = _changed_protected(root, cwd, None, ref + "^3")
        changed = None if extra is None else changed + extra
    if changed is None:
        v.add(ASK, f"`git stash {rest[0]}` applies {ref}, which Tess cannot read")
    elif changed:
        v.add(ASK, f"`git stash {rest[0]}` rewrites protected Tess files ({', '.join(changed[:5])})")


def _git_update_index(root, cwd, rest, v):
    if any(a in ("--index-info", "--stdin") for a in rest):
        v.add(DENY, "`git update-index --index-info/--stdin` writes index entries Tess cannot see",
              "rollback")
    paths, i = [], 0
    while i < len(rest):
        a = rest[i]
        if a == "--cacheinfo" and i + 1 < len(rest):
            if "," in rest[i + 1]:
                paths.append(rest[i + 1].split(",", 2)[-1])
                i += 2
                continue
            paths += rest[i + 3:i + 4]
            i += 4
            continue
        if not a.startswith("-") or a == "-":
            paths.append(a)
        i += 1
    for p in paths:
        hit = _pathspec_hit(root, cwd, p)
        if hit:
            v.add(DENY, f"`git update-index` writes {p} ({hit}) straight into git's index, "
                        "where the next commit would take it from", "rollback")


def _git_merge_like(root, cwd, sub, rest, v, raw, depth):
    if any(_abbrev(a, *_RESUME) for a in rest if a.startswith("--")):
        return
    opts, pos, _, _ = _parse(rest, _MERGE_SHORT_VALS[sub], (
        "--message", "--strategy", "--strategy-option", "--file", "--into-name", "--onto",
        "--exec", "--mainline"))
    for key in ("-x", "--exec"):
        if isinstance(opts.get(key), str) and depth < 4:
            check_command(root, cwd, opts[key], v, depth + 1)
    if sub in ("cherry-pick", "revert"):
        for c in pos:
            if ".." in c:
                a, _, b = c.partition("...") if "..." in c else c.partition("..")
                _move_to(root, cwd, b or "HEAD", v, f"git {sub}", base=a or "HEAD")
            elif sub == "revert":
                _move_to(root, cwd, c + "^", v, "git revert", base=c)
            else:
                _move_to(root, cwd, c, v, "git cherry-pick", base=c + "^")
        return
    if sub == "rebase":
        return _git_rebase(root, cwd, opts, pos, v)
    for t in pos or ["@{upstream}"]:
        _move_to(root, cwd, _rev(t), v, f"git {sub}", base="merge-base")


def _git_rebase(root, cwd, opts, pos, v):
    """v1.0.0 final reviews: judge the tree the rebase PRODUCES against HEAD.
    `git rebase --onto <old> HEAD` replays nothing onto <old>, so comparing
    <old> with its merge-base (the round-3 rule) saw an empty change."""
    onto = opts.get("--onto") if isinstance(opts.get("--onto"), str) else None
    branch = _rev(pos[1]) if len(pos) > 1 else "HEAD"
    if "--root" in opts:
        if onto is None:
            return None  # rewrites the same commits in place
        base = _EMPTY_TREE
        upstream = None
    else:
        upstream = _rev(pos[0]) if pos else "@{upstream}"
        mb = _git_ro(cwd, "merge-base", upstream, branch) if not upstream.startswith("-") else None
        base = mb.strip() if mb else None
    newbase = onto or upstream
    what = "git rebase" + (" --onto" if onto else "")
    out = None
    if base and newbase and not newbase.startswith("-") and not branch.startswith("-"):
        out = _git_ro(cwd, "merge-tree", "--write-tree", "--no-messages",
                      f"--merge-base={base}", newbase, branch)
    result = out.split()[0] if out and out.split() else None
    changed = _changed_protected(root, cwd, "HEAD", result) if result else None
    if changed is None:
        return v.add(ASK, f"`{what}` rewrites the branch onto {newbase}, and Tess cannot work out "
                          "the result; it may replace Tess's own gate or rules")
    if changed:
        return v.add(ASK, f"`{what}` would change protected Tess files ({', '.join(changed[:5])}) "
                          "relative to HEAD: that copy of the gate and rules would run from then on")
    if any(k in opts for k in ("-i", "--interactive", "--edit-todo")) and base:
        touched = _changed_protected(root, cwd, base, branch)
        if touched is None or touched:
            v.add(ASK, "an interactive rebase can drop or edit the commits that changed protected "
                       f"Tess files ({', '.join((touched or ['unknown'])[:5])})")
    return None


def _bisect_terms(cwd: str) -> tuple:
    path = _git_ro(cwd, "rev-parse", "--git-path", "BISECT_TERMS")
    try:
        with open(os.path.join(cwd, path.strip()) if path else "", encoding="utf-8") as fh:
            words = fh.read().split()
        return (words[0], words[1]) if len(words) >= 2 else ("bad", "good")
    except OSError:
        return "bad", "good"


def _git_bisect(root, cwd, rest, v, depth):
    """v1.0.0 final reviews: `git bisect` checks out commits in a range; each
    one must not change protected files relative to HEAD."""
    if not rest or rest[0] in ("help", "log", "visualize", "view", "terms", "-h", "--help"):
        return None
    op, args = rest[0], rest[1:]
    if op == "replay":
        return v.add(ASK, "`git bisect replay` checks out commits from a log Tess cannot read")
    if op == "reset":
        pos = [a for a in args if not a.startswith("-")]
        target = pos[0] if pos else None
        if target is None:
            path = _git_ro(cwd, "rev-parse", "--git-path", "BISECT_START")
            try:
                with open(os.path.join(cwd, path.strip()) if path else "", encoding="utf-8") as fh:
                    target = fh.read().strip() or None
            except OSError:
                target = None
        return target and _move_to(root, cwd, target, v, "git bisect reset")
    new_t, old_t = _bisect_terms(cwd)
    refs = [r for r in (_git_ro(cwd, "for-each-ref", "--format=%(refname)", "refs/bisect/")
                        or "").split("\n") if r]
    bads = [r for r in refs if r == f"refs/bisect/{new_t}"]
    goods = [r for r in refs if r.startswith(f"refs/bisect/{old_t}-")]
    if op == "run":
        if depth < 4 and args:
            check_command(root, cwd, shlex.join(args), v, depth + 1)
    elif op == "start":
        if "--no-checkout" in args:
            return None
        _, pos, _, _ = _parse(args, "", ("--term-new", "--term-bad", "--term-old", "--term-good"))
        bads, goods = pos[:1], pos[1:]
    elif op in ("bad", "new", new_t):
        bads = [a for a in args if not a.startswith("-")][:1] or ["HEAD"]
    elif op in ("good", "old", old_t):
        goods = goods + ([a for a in args if not a.startswith("-")] or ["HEAD"])
    if not bads or not goods:
        return None  # git needs both ends before it checks anything out
    for b in bads:
        _move_to(root, cwd, b, v, f"git bisect {op}")
    names = _git_ro(cwd, "log", "--format=", "--name-only", "-m", "--no-renames",
                    "--max-count=20000", *bads, "--not", *goods, "--")
    if names is None:
        return v.add(ASK, f"`git bisect {op}` checks out commits Tess cannot list")
    top = (_git_ro(cwd, "rev-parse", "--show-toplevel") or str(root)).strip()
    globs = _protected_globs(root)
    hits = sorted({rel for n in names.split("\n") if n
                   for rel in [_rel_to_root(root, top, n)] if rel and _glob_hit(rel, globs)})
    if hits:
        v.add(ASK, f"`git bisect {op}` would check out commits that change protected Tess files "
                   f"({', '.join(hits[:5])}); those copies of the gate and rules would run")
    return None


_PATCH_PATHS = re.compile(r"^(?:diff --git a/(\S+) b/(\S+)|(?:\+\+\+|---) (\S+)|"
                          r"(?:rename|copy) (?:from|to) (.+?))\s*$", re.M)


def _git_apply(root, cwd, sub, rest, v, raw):
    if any(_abbrev(a, *_RESUME) for a in rest if a.startswith("--")):
        return None
    args, skip = [], False  # drop redirections (`<<'EOF'`, `< x.patch`, `> out`) and their targets
    for a in rest:
        if skip:
            skip = False
        elif a == "<":
            continue  # `git apply < x.patch`: the next word is the patch file
        elif re.match(r"^\d*[<>]", a):
            skip = re.fullmatch(r"\d*[<>&|-]+", a) is not None
        else:
            args.append(a)
    opts, pos, after, _ = _parse(args, "p", ("--directory", "--exclude", "--include"))
    if sub == "apply" and not any(k in opts for k in ("--apply", "--index", "--cached", "--3way",
                                                      "-3")) and any(
            k in opts for k in ("--check", "--stat", "--numstat", "--summary")):
        return  # reports only
    texts = []
    for f in pos + after:
        try:
            with open(os.path.join(cwd, f), encoding="utf-8", errors="replace") as fh:
                texts.append(fh.read(5_000_000))
        except OSError:
            v.add(ASK, f"`git {sub}` applies {f}, which Tess cannot read")
    if not pos and not after:
        texts.append(raw)  # a heredoc or pipe in this command
    prefix = opts.get("--directory") if isinstance(opts.get("--directory"), str) else ""
    names = [n for t in texts for m in _PATCH_PATHS.finditer(t) for n in m.groups() if n]
    if not names and not pos and not after:
        v.add(ASK, f"`git {sub}` reads a patch from input Tess cannot see")
    for n in names:
        if n == "/dev/null":
            continue
        for cand in {n, n.split("/", 1)[-1]}:
            hit = _pathspec_hit(root, cwd if not prefix else str(root),
                                os.path.join(prefix, cand) if prefix else cand)
            if hit:
                return v.add(DENY, f"`git {sub}` patches {cand} ({hit}), a protected Tess path",
                             "rollback")


def _check_git_tree_writes(root: Path, cwd: str | None, sub: str, rest: list, v: Verdict,
                           redirect: str | None, raw: str, depth: int):
    if sub not in _TREE_WRITE_SUBS or "-h" in rest or "--help" in rest:
        return
    if redirect:
        return v.add(DENY, f"`git {sub}` with {redirect} points git's file writes at another "
                           "directory, where it can replace Tess's git hooks or gate", "rollback")
    if cwd is None:
        return v.add(DENY, f"`git {sub}` runs in a directory known only at run time (-C), so Tess "
                           "cannot check what it writes", "rollback")
    if sub != "clone" and _has_replace_refs(cwd):
        # v1.0.0: with replace refs, HEAD and the index no longer mean what they
        # say, so even the "restore from HEAD" undo is not the same source.
        # (No answer = not a repository: the git command fails on its own.)
        return v.add(DENY, f"`git {sub}` would read commits through git replace refs "
                           "(refs/replace/ is not empty), so HEAD may not be what it looks "
                           "like. Remove them yourself (`git replace -d`) outside the agent",
                     "rollback")
    if sub == "checkout-index":
        if any(a.startswith("--prefix") for a in rest) or any(
                a in ("-a", "--all", "--stdin") or re.match(r"^-[a-z]*a", a) for a in rest):
            return v.add(DENY, "`git checkout-index` with --prefix, --all or --stdin can write "
                               "files anywhere, Tess's git hooks and gate included", "rollback")
        for p in rest:
            hit = not p.startswith("-") and _pathspec_hit(root, cwd, p)
            if hit:
                return v.add(DENY, f"`git checkout-index` overwrites {p} ({hit}) from the index",
                             "rollback")
        return None
    if sub in ("worktree", "clone"):
        if sub == "worktree":
            opts, pos, after, _ = _parse(rest[1:], "bB", ("--reason",))
            dests = (pos + after)[:1] if rest[:1] == ["add"] else []
        else:
            opts, pos, after, _ = _parse(rest, "bocuj", _CLONE_VALS)
            dests = (pos + after)[1:2] + [opts[k] for k in ("--separate-git-dir",)
                                          if isinstance(opts.get(k), str)]
        for dest in dests:
            if _pathspec_hit(root, cwd, dest):
                v.add(DENY, f"`git {sub}` writes a checkout into {dest}, a protected Tess path",
                      "rollback")
        return None
    handler = {"checkout": _git_checkout, "restore": _git_restore, "reset": _git_reset,
               "switch": _git_switch, "read-tree": _git_read_tree, "stash": _git_stash,
               "update-index": _git_update_index}.get(sub)
    if sub in ("symbolic-ref", "update-ref"):
        return _git_head_ref(root, cwd, sub, rest, v)
    if handler:
        return handler(root, cwd, rest, v)
    if sub in ("am", "apply"):
        return _git_apply(root, cwd, sub, rest, v, raw)
    if sub in ("merge", "rebase", "cherry-pick", "revert"):
        return _git_merge_like(root, cwd, sub, rest, v, raw, depth)
    if sub == "pull":
        return _git_pull(root, cwd, rest, v)
    return None


# `git pull` options that take a separate value (short: -s -X -j -o).
_PULL_VALS = ("--strategy", "--strategy-option", "--depth", "--deepen", "--shallow-since",
              "--shallow-exclude", "--jobs", "--upload-pack", "--server-option",
              "--negotiation-tip", "--refmap")
_PULL_NETWORK = ("`git pull` from {src} fetches first, and what it brings in is only known "
                 "after that fetch, so Tess cannot check whether it replaces Tess's own gate, "
                 "launcher or hook settings. Run `git fetch` and then `git merge` (or `git "
                 "rebase`) with the fetched branch: Tess checks that step against HEAD")


def _pull_rebases(cwd: str, opts: dict) -> bool:
    for k in ("--rebase", "-r"):
        if k in opts:
            return str(opts[k]).lower() not in ("false", "no", "off", "0")
    if "--no-rebase" in opts or "--ff-only" in opts:
        return False
    branch = (_git_ro(cwd, "symbolic-ref", "-q", "--short", "HEAD") or "").strip()
    for key in ([f"branch.{branch}.rebase"] if branch else []) + ["pull.rebase"]:
        val = (_git_ro(cwd, "config", "--get", key) or "").strip().lower()
        if val:
            return val not in ("false", "no", "off", "0")
    return False


def _git_pull(root, cwd, rest, v):
    """v1.0.0 final review (Cyra A-1): `git pull` merges or rebases what it
    fetches, so it can replace the in-repo launcher (.claude/hooks/run-pinned.py)
    and the hook config that starts it; the anchor check runs INSIDE that
    launcher, so the gate must judge the pull itself. The hook never fetches:
    a pull from this repository (`.`, or an upstream whose remote is `.`) is
    judged exactly, like `git merge` / `git rebase`; a pull from a remote
    cannot be computed before its fetch, so it asks (Claude) / denies (Codex)."""
    if any(_abbrev(a, *_RESUME) for a in rest if a.startswith("--")):
        return None
    opts, pos, _, _ = _parse(rest, "sXjo", _PULL_VALS)
    if any(k in opts for k in ("--all", "--multiple")):
        return v.add(ASK, _PULL_NETWORK.format(src="every remote"))
    if pos:
        repo, specs = pos[0], pos[1:]
    else:
        branch = (_git_ro(cwd, "symbolic-ref", "-q", "--short", "HEAD") or "").strip()
        repo = (_git_ro(cwd, "config", "--get", f"branch.{branch}.remote") or "").strip() \
            if branch else ""
        specs = []
    if repo != ".":
        return v.add(ASK, _PULL_NETWORK.format(src=repo or "its upstream"))
    targets = []
    for spec in specs:
        src = spec.lstrip("+").split(":", 1)[0]
        if not src or src.startswith("-"):
            return v.add(ASK, f"`git pull . {spec}` names nothing Tess can resolve")
        targets.append(src)
    if not targets:
        if pos:
            return v.add(ASK, "`git pull .` without a branch merges what git decides at run "
                              "time, which Tess cannot resolve")
        up = (_git_ro(cwd, "rev-parse", "--verify", "--quiet", "@{upstream}") or "").strip()
        if not up:
            return v.add(ASK, "`git pull` has no upstream Tess can resolve, so it cannot check "
                              "what the pull brings in")
        targets.append(up)
    rebase = _pull_rebases(cwd, opts)
    for t in targets:
        if not _tree(cwd, t):
            v.add(ASK, f"`git pull` brings in {t}, which Tess cannot resolve; it may replace "
                       "Tess's own gate, launcher or hook settings")
        elif rebase:
            _git_rebase(root, cwd, {}, [t], v)
        else:
            _move_to(root, cwd, t, v, "git pull", base="merge-base")
    return None


def _check_push(root: Path, cwd: str, rest: list, v: Verdict):
    flags = _short_flags(rest)
    opts = [a for a in rest if a.startswith("--")]
    if "--dry-run" in opts or "n" in flags:
        return
    if ("f" in flags or any(_abbrev(o, "--force", "--force-with-lease", "--force-if-includes",
                                    "--mirror", "--prune") for o in opts)
            or any(a.startswith("+") for a in rest if not a.startswith("-"))):
        v.add(ASK, "it is a force push, which can overwrite commits on the remote")
    if ("d" in flags or any(_abbrev(o, "--delete") for o in opts)
            or any(a.startswith(":") for a in rest if not a.startswith("-"))):
        v.add(ASK, "it deletes a branch or tag on the remote")
        if "d" in flags or any(_abbrev(o, "--delete") for o in opts):
            return  # every refspec names a ref to delete: no data is published
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


_HOME_ENV = ("HOME", "XDG_CONFIG_HOME")
_KEY_TOOLS = re.compile(r"(?<![\w.-])(git|tessctl|tessbrain(\.py)?)(?![\w-])")


def _check_home_env(env: dict, argv: list, raw: str, v: Verdict) -> None:
    """Round 3, N-2: HOME / XDG_CONFIG_HOME moved for a git or tessctl command
    (as TESS_BRAIN_PROVENANCE_DIR is): a verifier that trusted them would read
    a key the agent planted. tessctl uses the OS user record; this keeps the
    gate's own view consistent with it."""
    name = os.path.basename(argv[0])
    if name in ("export", "declare", "typeset", "setenv"):
        moved = [a.partition("=")[0] for a in argv[1:] if a.partition("=")[0] in _HOME_ENV
                 and "=" in a]
        tool = _KEY_TOOLS.search(raw)
    else:
        moved = [k for k in env if k in _HOME_ENV]
        tool = _KEY_TOOLS.search(" ".join(argv[:3]))
    if moved and tool:
        v.add(DENY, f"it sets {', '.join(moved)} for {tool.group(1)}; a moved home directory "
                    "could point Tess's verifiers at a key the agent made", "envhome")


EXTRACTORS = {"tar", "gtar", "bsdtar", "unzip", "ditto", "cpio", "pax"}
_TAR_VALS = ("--file", "--directory", "--exclude", "--files-from", "--transform", "--xform",
             "--strip-components", "--use-compress-program", "--to-command", "--format",
             "--owner", "--group", "--mode", "--newer", "--label", "--volno-file",
             "--info-script", "--new-volume-script", "--checkpoint-action")


def _extract_plan(argv: list, cwd: str) -> tuple | None:
    """(destination dir, archive file | None, names unknowable) for an
    extractor segment that writes files; None when it only lists or prints."""
    name = os.path.basename(argv[0])
    args = [a for a in argv[1:] if a not in REDIRECTS]
    join = lambda d: d if os.path.isabs(os.path.expanduser(d)) else os.path.join(cwd, d)  # noqa: E731
    if name in ("tar", "gtar", "bsdtar"):
        if args and not args[0].startswith("-"):
            args = ["-" + args[0]] + args[1:]  # old-style `tar xzf file`
        opts, pos, _, _ = _parse(args, "fCTXs", _TAR_VALS)
        flags = "".join(k[1:] for k in opts if re.fullmatch(r"-[A-Za-z]", k))
        if not ("x" in flags or any(str(k).startswith(("--extract", "--get")) for k in opts)):
            return None
        if "O" in flags or "--to-stdout" in opts:
            return None
        dest = opts.get("-C") or opts.get("--directory") or "."
        src = opts.get("-f") or opts.get("--file")
        odd = any(k in opts for k in ("-s", "-P", "--transform", "--xform", "--strip-components",
                                      "--absolute-names", "--to-command", "-T", "--files-from"))
        return join(str(dest)), (None if src in (None, True, "-") else join(str(src))), odd
    if name == "unzip":
        opts, pos, _, _ = _parse(args, "dx")
        if any(k in opts for k in ("-l", "-t", "-Z", "-z", "-p", "-v", "-c")):
            return None
        return join(str(opts.get("-d") or ".")), (join(pos[0]) if pos else None), False
    if name == "ditto":
        pos = [a for a in args if not a.startswith("-")]
        if "-x" in args or any(re.fullmatch(r"-[a-z]*x[a-z]*", a) for a in args):
            src = pos[0] if pos and "-k" in args else None
            return join(pos[-1] if pos else "."), (join(src) if src else None), not src
        return join(pos[-1] if pos else "."), None, True
    if name in ("cpio", "pax"):
        flags = "".join(a[1:] for a in args if re.match(r"^-[A-Za-z]+$", a))
        writes = ("i" in flags or "p" in flags or "--extract" in args or "--pass-through" in args
                  ) if name == "cpio" else "r" in flags
        if not writes:
            return None
        pos = [a for a in args if not a.startswith("-")]
        copy = ("p" in flags) if name == "cpio" else ("w" in flags)
        return join(pos[-1] if copy and pos else "."), None, True
    return None


def _archive_members(archive: str, tool: str) -> list | None:
    cmd = ["unzip", "-Z1", archive] if tool in ("unzip", "ditto") else ["tar", "-tf", archive]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    return [ln for ln in r.stdout.splitlines() if ln] if r.returncode == 0 else None


def _check_extract(root: Path, cwd: str, argv: list, v: Verdict):
    """v1.0.0 final reviews: an archive extractor writes files the command
    text does not name (`git archive <old> .claude/hooks | tar -x`)."""
    plan = _extract_plan(argv, cwd)
    if plan is None:
        return
    dest, archive, odd = plan
    rel = _rel_to_root(root, cwd, dest)
    if rel is None:
        return  # outside the project
    tool = os.path.basename(argv[0])
    members = None if odd or archive is None else _archive_members(archive, tool)
    if members is None:
        if rel == "." or _glob_hit(rel, _protected_globs(root)) or rel.split("/")[0] in {
                r.split("/")[0] for r in PROTECTED_DIR_ROOTS}:
            v.add(DENY, f"`{tool}` extracts files Tess cannot list into {dest}, which holds "
                        "protected Tess files", "protected")
        return
    for m in members:
        hit = protected_hit(root, dest, m.lstrip("/") if not m.startswith("/") else m)
        if hit:
            v.add(DENY, f"`{tool}` extracts {m} ({hit}), a protected Tess path", "protected")
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
    _check_home_env(env, argv, raw, v)
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
    if name in ("export", "declare", "typeset", "setenv") and any(
            re.split(r"[=\s]", a, 1)[0] in _REDIRECT_ENV for a in argv[1:]):
        v.add(DENY, "it points git at another work tree, git directory or index through the "
                    "environment, where later git commands can replace Tess's hooks or gate",
              "rollback")
    _check_key_text(cwd, argv, " ".join(argv), v)
    if name in EXTRACTORS:
        _check_extract(root, cwd, argv, v)
    if "GIT_REPLACE_REF_BASE" in env or (name in ("export", "declare", "typeset", "setenv") and any(
            a.split("=", 1)[0] == "GIT_REPLACE_REF_BASE" for a in argv[1:])):
        v.add(DENY, "GIT_REPLACE_REF_BASE makes git read commits through another set of replace "
                    "refs, so HEAD may not be what it looks like", "rollback")
    if name == "git":
        _check_git(root, cwd, env, argv, v, raw, depth)
    elif name == "gh":
        _check_gh(argv, v)
    for target in _write_targets(argv):
        hit = protected_hit(root, cwd, target)
        if hit:
            v.add(DENY, f"it writes to {target}, a protected Tess path ({hit})", "protected")
    if name not in READERS_OK_FOR_GIT_DIR and name != "git":
        for a in argv[1:]:
            if re.search(r"(^|/)\.git/(hooks(/|$)|config$|info(/|$)|refs/replace(/|$))", a):
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
    _check_archive_pipe(segs, v)
    cur = cwd or str(root)
    for argv in segs:
        _check_segment(root, cur, argv, v, cmd, depth)
        cur = _next_cwd(root, cur, argv)


def _check_archive_pipe(segs: list, v: Verdict) -> None:
    """`git archive <rev> <paths> | tar -x`: an old copy of any file, written
    by a tool that never names it."""
    seen_archive = False
    for seg in segs:
        _, argv = _strip_prefix(seg)
        if not argv:
            continue
        name = os.path.basename(argv[0])
        if name == "git":
            words = [a for a in argv[1:] if not a.startswith("-")]
            if "archive" in words[:3] and not any(a in ("-l", "--list") for a in argv):
                seen_archive = True
        elif seen_archive and name in EXTRACTORS:
            v.add(DENY, "it unpacks `git archive` output with an extractor, which writes older "
                        "copies of files without naming them (Tess's gate and pins included)",
                  "rollback")
            return


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
        if _KEY_TEXT.search(cmd):
            v.add(DENY, "it reads or writes Tess's key directory (~/.config/tess); the signing "
                        "keys there are for the operator's own tools, not for an agent", "keys")
        check_command(root, cwd, cmd, v)
    elif tool in READ_TOOLS:
        if isinstance(tin, dict):
            for k in ("file_path", "path", "notebook_path"):
                if key_hit(cwd, tin.get(k), ancestors=(tool == "Grep" and k == "path")):
                    v.add(DENY, f"it reads {tin.get(k)}, Tess's key directory; the signing keys "
                                "there are for the operator's own tools, not for an agent", "keys")
            if tool in ("Grep", "Glob") and _KEY_TEXT.search(
                    " ".join(str(tin.get(k) or "") for k in ("pattern", "glob"))):
                v.add(DENY, "it searches Tess's key directory (~/.config/tess)", "keys")
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
            if key_hit(cwd, p):
                v.add(DENY, f"it writes {p}, in Tess's key directory", "keys")
    elif tool.startswith("mcp__"):
        for val in _strings(tin):
            if key_hit(cwd, val, ancestors=True) or _KEY_TEXT.search(val):
                v.add(DENY, "it reaches Tess's key directory (~/.config/tess)", "keys")
                break
        if isinstance(tin, dict) and any(w in tool.lower() for w in MCP_WRITE_WORDS):
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
    mode = data.get("permission_mode")
    if v.level == ASK and (is_codex or mode not in INTERACTIVE_MODES):
        # L-c: only a known interactive mode pauses for the operator. A no-prompt
        # mode, a missing mode or one Tess does not recognise gets the deny.
        where = ("Codex" if is_codex else f"{mode} mode" if mode in NO_PROMPT_MODES
                 else f"an unrecognised permission mode ({str(mode)[:40]!r})")
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
