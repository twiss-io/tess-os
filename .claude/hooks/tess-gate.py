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

v1.0 security audit (gate shell parsing) also:
  * finds the program a segment runs the way the shell does: through `{ }`,
    `!`, `if/then/do`, glued operators, leading redirections, wrappers and
    runners with their option values (env, nice -n, timeout, xargs, sudo,
    uv run...), any letter case, `$'..'` quoting, `git-<sub>`, shell `-c`
    clusters, here-strings, here-documents and `echo ... | sh`, command
    substitutions and `find -exec/-delete`; a program named only at run time
    asks;
  * expands write targets as the shell will (globs, braces, ~, $HOME/$PWD,
    variables and `for` lists set in the same command, dd of=, --opt=DIR,
    -tDIR, curl -o, tar -cf, links made earlier in the command); a target
    known only at run time asks;
  * resolves relative paths against a tool call's own `workdir` and tracks
    `cd` through `&&`, `||`, `;`, subshells, pipes and background lists;
  * works out a push's destination and refs as git does (--repo, one-command
    config, every pushurl, insteadOf/pushInsteadOf, push refspecs, mirror,
    push.default, --all/--tags/--follow-tags, `tag <name>`);
  * parses tess.lock once per file version and stops within GATE_BUDGET
    seconds (or at MAX_COMMAND characters) with an ask, never an allow.

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
import tempfile
import time
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
OPERATORS = {";", "&&", "||", "|", "&", "(", ")", "\n", "|&", ";;", ";&", ";;&"}
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
    which may not have PyYAML); same approach as run-pinned.py. v1.0 audit:
    parsed once per file version (path, inode, mtime, size), not per path checked."""
    path = root / ".tess" / "tess.lock"
    try:
        st = os.stat(str(path))
        key = (os.path.realpath(str(path)), st.st_dev, st.st_ino, st.st_mtime_ns, st.st_ctime_ns,
               st.st_size)
        if key in _LOCK_CACHE:
            return set(_LOCK_CACHE[key])
        text = path.read_text(encoding="utf-8")
    except OSError:
        return set()
    found = _parse_security_tier(text)
    _LOCK_CACHE.clear()
    _LOCK_CACHE[key] = frozenset(found)
    return set(found)


_LOCK_CACHE: dict = {}


def _parse_security_tier(text: str) -> set:
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
# v1.0 security audit (command-word resolution, literal operands): the gate
# reads a command the way the shell does. Words keep how they were written
# (quoted, a $variable, a glob, a command substitution), operators glued to
# each other (`true&&(cp ...)`) are split, a here-document body is data (and
# a program only for a shell reading it), and the program a segment runs is
# found through reserved words, redirections, wrappers and runners.

_PUNCT = ";&|()<>\n"
# Longest first: what the shell reads as one operator or redirection.
_OPS = (";;&", ";;", ";&", "&&", "||", "|&", "&>>", "&>", ">>", "<<<", "<<-", "<<", ">|", "<>",
        ">&", "<&", ";", "&", "|", "(", ")", "<", ">", "\n")
_REDIR_OPS = {">", ">>", ">|", "&>", "&>>", "<>", ">&", "<&", "<", "<<", "<<-", "<<<"}
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_ANSI_C = {"n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b", "e": "\x1b", "E": "\x1b",
           "f": "\f", "v": "\v", "\\": "\\", "'": "'", '"': '"', "?": "?"}


class _Word(str):
    """One shell word: its text with quoting removed (what shlex gives), plus
    how it was written. `parts` holds (kind, text) pieces: "lit" quoted or
    escaped text, "raw" unquoted text (globs, braces and a leading ~ expand
    there), "var" a $NAME, "sub" a command substitution, "proc" a process
    substitution, "dyn" any other expansion. `op` marks an unquoted operator
    or redirection, `fd` a file-descriptor number glued to one (`2>`), and
    `body` a here-document's text (on the word after << / <<-)."""
    op = False
    fd = False
    parts: tuple = ()
    body = None


def _mkword(parts, op: bool = False) -> "_Word":
    show = {"var": "${}", "sub": "$()", "proc": "<()", "dyn": "${}", "fallback": ""}
    text = "".join(t if k in ("lit", "raw", "fallback", "arith") else
                   show[k][:-1] + t + show[k][-1] if k != "var" else "$" + t for k, t in parts)
    w = _Word(text)
    w.parts, w.op = tuple((k, t) for k, t in parts), op
    return w


def _plain(text: str) -> "_Word":
    """A word the gate made itself (a stand-in program name, a split value)."""
    return _mkword([("lit", text)])


def _close_quote(s: str, i: int) -> int:
    """Index of the `"` closing a double-quoted string whose text starts at i."""
    while i < len(s):
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == '"':
            return i
        if c == "`":
            i = _close_backtick(s, i)
        elif s.startswith("$(", i):
            i = _close_paren(s, i + 1)
        i += 1
    raise ValueError("No closing quotation")


def _close_backtick(s: str, i: int) -> int:
    j = i + 1
    while j < len(s):
        if s[j] == "\\":
            j += 2
            continue
        if s[j] == "`":
            return j
        j += 1
    raise ValueError("No closing backquote")


def _close_paren(s: str, i: int) -> int:
    """Index of the `)` closing the `(` at s[i] (quotes and nesting respected)."""
    depth, j = 0, i
    while j < len(s):
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == "'":
            k = s.find("'", j + 1)
            if k < 0:
                raise ValueError("No closing quotation")
            j = k
        elif c == '"':
            j = _close_quote(s, j + 1)
        elif c == "`":
            j = _close_backtick(s, j)
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return j
        j += 1
    raise ValueError("No closing parenthesis")


def _close_brace(s: str, i: int) -> int:
    depth, j = 0, i
    while j < len(s):
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == "'":
            k = s.find("'", j + 1)
            j = k if k >= 0 else len(s)
        elif c == '"':
            j = _close_quote(s, j + 1)
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return j
        j += 1
    raise ValueError("No closing brace")


def _ansi_c(s: str, i: int) -> tuple:
    """(index after the closing quote, decoded text) of a $'...' string."""
    out = []
    while i < len(s):
        c = s[i]
        if c == "'":
            return i + 1, "".join(out)
        if c == "\\" and i + 1 < len(s):
            d = s[i + 1]
            m = re.match(r"x([0-9A-Fa-f]{1,2})|u([0-9A-Fa-f]{1,4})|U([0-9A-Fa-f]{1,8})|([0-7]{1,3})|c(.)",
                         s[i + 1:])
            if d in _ANSI_C:
                out.append(_ANSI_C[d])
                i += 2
                continue
            if m:
                num = m.group(1) or m.group(2) or m.group(3)
                out.append(chr(int(num, 16)) if num else chr(int(m.group(4), 8)) if m.group(4)
                           else chr(ord(m.group(5)) & 0x1f))
                i += 1 + m.end()
                continue
            out.append("\\" + d)
            i += 2
            continue
        out.append(c)
        i += 1
    raise ValueError("No closing quotation")


def _scan_dollar(s: str, i: int, add, quoted: bool) -> int:
    nxt = s[i + 1] if i + 1 < len(s) else ""
    if nxt == "(":
        # $(cmd), and $((...)): bash runs $((cmd) ) as a command when it is
        # not arithmetic, so both are checked as a command.
        j = _close_paren(s, i + 1)
        add("sub", s[i + 2:j])
        return j + 1
    if nxt == "[":
        j = s.find("]", i)
        if j < 0:
            raise ValueError("No closing bracket")
        add("dyn", s[i + 1:j + 1])
        return j + 1
    if nxt == "{":
        j = _close_brace(s, i + 1)
        inner = s[i + 2:j]
        add("var" if _NAME.fullmatch(inner) or inner.isdigit() else "dyn", inner)
        return j + 1
    if nxt == "'" and not quoted:
        j, text = _ansi_c(s, i + 2)
        add("lit", text)
        return j
    if nxt == '"' and not quoted:
        return _scan_dquote(s, i + 2, add)
    m = _NAME.match(s, i + 1)
    if m:
        add("var", m.group(0))
        return m.end()
    if nxt.isdigit():
        add("var", nxt)
        return i + 2
    if nxt and nxt in "@*#?$!-":
        add("dyn", nxt)
        return i + 2
    add("lit" if quoted else "raw", "$")
    return i + 1


def _scan_dquote(s: str, i: int, add) -> int:
    add("lit", "")  # "" is still a word
    while i < len(s):
        c = s[i]
        if c == '"':
            return i + 1
        if c == "\\" and i + 1 < len(s) and s[i + 1] in '$`"\\\n':
            if s[i + 1] != "\n":
                add("lit", s[i + 1])
            i += 2
        elif c == "$":
            i = _scan_dollar(s, i, add, True)
        elif c == "`":
            j = _close_backtick(s, i)
            add("sub", s[i + 1:j])
            i = j + 1
        else:
            add("lit", c)
            i += 1
    raise ValueError("No closing quotation")


def _read_heredocs(s: str, i: int, toks: list, docs: list) -> int:
    """Attach each pending here-document body (the lines after the newline at
    i, up to its delimiter) to its delimiter word; returns where commands resume."""
    for idx, strip in docs:
        if idx >= len(toks) or toks[idx].op:
            continue  # `<<` with no delimiter word: a syntax error, nothing runs
        delim, lines = str(toks[idx]), []
        while i < len(s):
            j = s.find("\n", i)
            j = len(s) if j < 0 else j
            line, i = s[i:j], min(j + 1, len(s))
            if (line.lstrip("\t") if strip else line) == delim:
                break
            lines.append(line)
        toks[idx].body = "\n".join(lines)
    return i


def _scan(cmd: str) -> list:
    """The words and operators of `cmd` (see _Word). Raises ValueError on
    unbalanced quotes, as shlex does."""
    toks, docs, state = [], [], {"parts": None}

    def add(kind, text):
        parts = state["parts"]
        if parts is None:
            parts = state["parts"] = []
        if parts and parts[-1][0] == kind and kind in ("lit", "raw"):
            parts[-1][1] += text
        else:
            parts.append([kind, text])

    def end():
        if state["parts"] is not None:
            toks.append(_mkword(state["parts"]))
        state["parts"] = None

    i = 0
    while i < len(cmd):
        c = cmd[i]
        if c in " \t\r":
            end()
            i += 1
        elif c == "\\":
            if i + 1 >= len(cmd):
                raise ValueError("No escaped character")
            if cmd[i + 1] != "\n":
                add("lit", cmd[i + 1])
            i += 2
        elif c == "'":
            j = cmd.find("'", i + 1)
            if j < 0:
                raise ValueError("No closing quotation")
            add("lit", cmd[i + 1:j])
            i = j + 1
        elif c == '"':
            i = _scan_dquote(cmd, i + 1, add)
        elif c == "$":
            i = _scan_dollar(cmd, i, add, False)
        elif c == "`":
            j = _close_backtick(cmd, i)
            add("sub", cmd[i + 1:j])
            i = j + 1
        elif c in "<>" and cmd.startswith("(", i + 1):
            end()
            j = _close_paren(cmd, i + 1)
            add("proc", cmd[i + 2:j])
            end()
            i = j + 1
        elif c == "(" and cmd.startswith("((", i) and state["parts"] is None and (
                not toks or (toks[-1].op and toks[-1] not in _REDIR_OPS)):
            j = _close_paren(cmd, i)  # (( arithmetic )): one word, not a subshell
            add("arith", cmd[i:j + 1])
            end()
            i = j + 1
        elif c in _PUNCT:
            parts = state["parts"]
            fd = c in "<>" and parts is not None and len(parts) == 1 and parts[0][0] == "raw" \
                and parts[0][1].isdigit()
            end()
            if fd:
                toks[-1].fd = True
            op = next(o for o in _OPS if cmd.startswith(o, i))
            toks.append(_mkword([("raw", op)], op=True))
            i += len(op)
            if op in ("<<", "<<-"):
                docs.append((len(toks), op == "<<-"))
            elif op == "\n" and docs:
                i, docs = _read_heredocs(cmd, i, toks, docs), []
        else:
            add("raw", c)
            i += 1
    end()
    return toks


def _is_op(tok) -> bool:
    return tok.op if isinstance(tok, _Word) else (tok in OPERATORS or tok in _REDIR_OPS)


def _events(cmd: str) -> list:
    """[("seg", [word, ...]) | ("op", operator), ...] in order. Redirections
    stay inside their segment."""
    out, cur = [], []
    for tok in _scan(cmd):
        if tok.op and tok in OPERATORS:
            if cur:
                out.append(("seg", cur))
            out.append(("op", str(tok)))
            cur = []
        else:
            cur.append(tok)
    if cur:
        out.append(("seg", cur))
    return out


def _segments(cmd: str) -> list:
    """[[argv...], ...] split on shell operators. Redirection tokens stay in argv."""
    return [x for kind, x in _events(cmd) if kind == "seg"]


def _dynamic(word) -> bool:
    """The word holds a value only known when the command runs."""
    if isinstance(word, _Word) and word.parts:
        return any(k in ("var", "sub", "dyn", "proc") or (k == "fallback" and re.search(r"[$`]", t))
                   for k, t in word.parts)
    return bool(re.search(r"[$`]", str(word)))


# Words the shell reads before the program itself: `{ git ...; }`, `! git ...`,
# `if true; then git ...; fi`, `while x; do git ...; done`.
_KEYWORDS = {"{", "}", "!", "if", "then", "else", "elif", "fi", "do", "done", "while", "until",
             "esac", "coproc"}
# Wrappers and runners: the command they run follows their own options.
# name: (short options taking a value, long options taking a value, operands before the command)
_WRAP = {
    "env": ("uCSP", ("--unset", "--chdir", "--split-string", "--block-signal", "--default-signal",
                     "--ignore-signal"), 0),
    "command": ("", (), 0), "builtin": ("", (), 0), "exec": ("a", (), 0), "nohup": ("", (), 0),
    "time": ("fo", ("--format", "--output"), 0), "nice": ("n", ("--adjustment",), 0),
    "sudo": ("ugChDprtTU", ("--user", "--group", "--close-from", "--host", "--chdir", "--prompt",
                            "--role", "--type", "--command-timeout", "--other-user"), 0),
    "doas": ("uC", (), 0), "nocorrect": ("", (), 0), "noglob": ("", (), 0),
    "timeout": ("sk", ("--signal", "--kill-after"), 1), "gtimeout": ("sk", ("--signal", "--kill-after"), 1),
    "xargs": ("adEIJLnPRSs", ("--arg-file", "--delimiter", "--max-args", "--max-procs", "--max-chars",
                              "--process-slot-var"), 0),
    "stdbuf": ("ioe", ("--input", "--output", "--error"), 0),
    "gstdbuf": ("ioe", ("--input", "--output", "--error"), 0),
    "setsid": ("", (), 0), "caffeinate": ("tw", (), 0), "chronic": ("", (), 0),
    "unbuffer": ("", (), 0), "ionice": ("cnp", ("--class", "--classdata", "--pid"), 0),
    "taskset": ("", (), 1), "flock": ("wE", ("--wait", "--timeout", "--conflict-exit-code"), 1),
    "chroot": ("", ("--userspec", "--groups"), 1), "sandbox-exec": ("fpnD", (), 0),
    "arch": ("", ("-arch", "-e", "-d"), 0), "busybox": ("", (), 0), "toybox": ("", (), 0),
    "faketime": ("f", (), 1), "firejail": ("", (), 0), "proxychains": ("f", (), 0),
    "proxychains4": ("f", (), 0), "torsocks": ("", (), 0), "strace": ("eoOpPsSuEIXb", (), 0),
    "ltrace": ("eoOpPsSuEIXbn", (), 0), "dtruss": ("pnt", (), 0), "valgrind": ("", (), 0),
    "catchsegv": ("", (), 0), "pkexec": ("", ("--user",), 0), "runuser": ("ugG", ("--user",), 0),
    "nsenter": ("tSG", (), 0), "unshare": ("", (), 0), "entr": ("", (), 0), "script": ("tT", (), 0),
}
# `tool sub` pairs that run the rest of the line: `uv run git ...`, `bundle exec ...`.
_SUB_RUNNERS = {"uv": ("run", "tool"), "uvx": None, "poetry": ("run",), "pipenv": ("run",),
                "pdm": ("run",), "hatch": ("run",), "rye": ("run",), "conda": ("run",),
                "mamba": ("run",), "micromamba": ("run",), "bundle": ("exec",), "npm": ("exec",),
                "pnpm": ("exec", "dlx"), "yarn": ("exec", "dlx"), "npx": None, "bunx": None,
                "pnpx": None, "direnv": ("exec",), "mise": ("exec", "x"), "asdf": ("exec",),
                "op": ("run",), "doppler": ("run",), "aws-vault": ("exec",), "devbox": ("run",),
                "nix": ("develop", "shell"), "dotenv": None, "infisical": ("run",)}
# Programs that run a command string: `watch 'git ...'`, `su -c '...'`, `flock f -c '...'`.
_STRING_RUNNERS = {"watch": None, "hyperfine": None, "parallel": None, "su": "-c", "flock": "-c",
                   "nix-shell": "--run", "script": "-c", "sudo": None}
_READONLY_PROGRAMS = {"cd", "pushd", "popd", "echo", "printf", "true", "false", ":", "pwd", "ls",
                      "cat", "test", "[", "export", "set", "unset", "read", "for", "local",
                      "declare", "typeset", "readonly", "grep", "rg", "head", "tail", "wc",
                      "stat", "which", "type", "sleep", "date", "whoami", "hostname", "uname"}


class _Cmd:
    """The program a segment runs, found through the words in front of it."""
    __slots__ = ("env", "argv", "chdir", "inner", "via_xargs", "prefix")

    def __init__(self):
        self.env, self.argv, self.chdir, self.inner = {}, [], None, []
        self.via_xargs, self.prefix = False, []


def _interesting(word) -> bool:
    """A word that can be the program the gate has rules for."""
    low = os.path.basename(str(word)).lower()
    return (_dynamic(word) or low in _NAMED or low in WRITERS or low in INPLACE or low in SHELLS
            or low in EXTRACTORS or low in _WRAP or low in _SUB_RUNNERS or low in _STRING_RUNNERS
            or _writer_name(low) or bool(INTERPRETERS.match(low)) or low.startswith("git-"))


def _skip_options(argv: list, i: int, prog: str) -> tuple:
    """(index of the command word, chdir, split string) after the wrapper
    `prog` at argv[i-1]."""
    shorts, longs, operands = _WRAP[prog]
    cdflag = {"env": "C", "sudo": "D"}.get(prog, "")
    chdir = split = None
    while i < len(argv):
        a = str(argv[i])
        if a == "--":
            i += 1
            break
        if a.startswith("--"):
            name, eq, val = a.partition("=")
            takes = name in longs
            word = _sub_word(argv[i], len(name) + 1) if eq else None
            if takes and not eq:
                word = argv[i + 1] if i + 1 < len(argv) else _plain("")
                val, i = str(word), i + 1
            if name == "--chdir":
                chdir = word
            if name == "--split-string":
                split = val
            i += 1
            continue
        if a in longs:  # single-dash long options (`arch -arch x86_64`)
            i += 2
            continue
        if a.startswith("-") and len(a) > 1 and not a[1:].isdigit():
            for k, ch in enumerate(a[1:], 1):
                if ch in shorts:
                    val, word = a[k + 1:], _sub_word(argv[i], k + 1)
                    if not val:
                        word = argv[i + 1] if i + 1 < len(argv) else _plain("")
                        val, i = str(word), i + 1
                    if ch == cdflag:
                        chdir = word
                    if ch == "S":
                        split = val
                    break
            i += 1
            continue
        if a.startswith("-") and a[1:].isdigit():  # nice -5
            i += 1
            continue
        break
    return i + operands, chdir, split


def _resolve(argv: list) -> "_Cmd":
    """Find the program a segment runs: past VAR=value assignments, reserved
    words (`{`, `!`, `then`...), redirections, wrappers and runners (env,
    nice -n 5, timeout 600, xargs -I{}, uv run...). The resolved argv starts
    at that program; `env` holds the assignments met on the way."""
    res, i, guard = _Cmd(), 0, 0
    argv = list(argv)
    while i < len(argv) and guard < 64:
        guard += 1
        tok = argv[i]
        low = os.path.basename(str(tok)).lower()
        if _is_op(tok) and str(tok) in _REDIR_OPS:
            i += 2
            continue
        if isinstance(tok, _Word) and tok.fd and i + 1 < len(argv) and _is_op(argv[i + 1]):
            i += 1
            continue
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", str(tok)) and not _is_op(tok):
            k, val = str(tok).split("=", 1)
            res.env[k] = val
            i += 1
            continue
        if (str(tok) in _KEYWORDS and not (isinstance(tok, _Word) and any(k != "raw" for k, _ in tok.parts))) \
                or (isinstance(tok, _Word) and [k for k, _ in tok.parts] == ["arith"]):
            i += 1  # a reserved word, or a (( arithmetic )) command
            continue
        if str(tok) == "function":
            i += 2
            continue
        if low in _STRING_RUNNERS and _string_runner(argv, i, low, res):
            return res
        if low in _WRAP:
            j, chdir, split = _skip_options(argv, i + 1, low)
            res.chdir = chdir if chdir is not None else res.chdir
            res.via_xargs = res.via_xargs or low == "xargs"
            if split is not None:
                argv = argv[:j] + [_plain(w) for w in split.split()] + argv[j:]
            i = _next_program(argv, j)
            continue
        if low in _SUB_RUNNERS:
            subs = _SUB_RUNNERS[low]
            if subs is None or (i + 1 < len(argv) and str(argv[i + 1]) in subs):
                i = _next_program(argv, i + (1 if subs is None else 2))
                continue
        break
    res.argv = argv[i:]
    res.prefix = argv[:i]
    return res


def _next_program(argv: list, j: int) -> int:
    """Index of the command word from j: j itself when the rule tables know it,
    else the first later word they know (a runner's unknown option values sit
    in between), else j."""
    if j >= len(argv) or _interesting(argv[j]) or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", str(argv[j])):
        return j
    for k in range(j + 1, len(argv)):
        if _interesting(argv[k]) and not _is_op(argv[k]):
            return k
    return j


def _string_runner(argv: list, i: int, low: str, res: "_Cmd") -> bool:
    """Runners whose command is one string: the string is checked as a command."""
    flag = _STRING_RUNNERS[low]
    rest = [str(a) for a in argv[i + 1:] if not _is_op(a)]
    if low == "sudo":
        if not any(a in ("-s", "-i", "--shell", "--login") for a in rest):
            return False
        cmd = [a for a in rest if not a.startswith("-")]
        res.inner.append(" ".join(cmd))
        return True
    if flag is not None:
        for k, a in enumerate(rest):
            if (a == flag or (flag == "-c" and re.fullmatch(r"-[A-Za-z]*c", a))) and k + 1 < len(rest):
                res.inner.append(rest[k + 1])
                return True
        return False
    if low == "parallel":
        cut = rest.index(":::") if ":::" in rest else len(rest)
        words = [a for a in rest[:cut] if not a.startswith("-")]
    else:
        words = [a for a in rest if not a.startswith("-") and not a.isdigit()]
    if words:
        res.inner.append(" ".join(words))
    return True


def _strip_prefix(argv: list) -> tuple:
    """(env, argv from the program on): see _resolve."""
    res = _resolve(argv)
    return res.env, res.argv


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
    "cdfail": "If a `cd` in this command fails, the shell stays where it was and runs the rest "
              "there. Write `cd <folder> && <command>` so the command runs only after the `cd` works.",
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
    cfg, i, gcwd, redirect, cenv = [], 0, cwd, None, []
    while i < len(args) and args[i].startswith("-"):
        a = args[i]
        if a.split("=", 1)[0] in ("--work-tree", "--git-dir"):
            redirect = a.split("=", 1)[0]
        if a in GIT_VALUE_OPTS and i + 1 < len(args):
            if a == "-c" or a == "--config-env":
                cfg.append(args[i + 1])
            if a == "--config-env":
                cenv.append(args[i + 1])
            if a == "-C":
                # A -C target known only at run time: later path checks cannot resolve it.
                gcwd = None if gcwd is None or any(c in args[i + 1] for c in "$`*?[") else \
                    os.path.join(gcwd or str(root), os.path.expanduser(args[i + 1]))
            i += 2
            continue
        if a.startswith("--config-env=") or a.startswith("-c") and len(a) > 2:
            cfg.append(a.split("=", 1)[1] if a.startswith("--config-env=") else a[2:])
            if a.startswith("--config-env="):
                cenv.append(cfg[-1])
        i += 1
    cfg += _env_config(env)  # GIT_CONFIG_COUNT / GIT_CONFIG_KEY_<n> / GIT_CONFIG_VALUE_<n>
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
        _check_push(root, gcwd, rest, v, cfg, cenv)


def _env_config(env: dict) -> list:
    """Config git reads from GIT_CONFIG_COUNT / GIT_CONFIG_KEY_<n> / _VALUE_<n>."""
    try:
        count = int(env.get("GIT_CONFIG_COUNT", "0"))
    except ValueError:
        count = 0
    return [f"{env[f'GIT_CONFIG_KEY_{k}']}={env.get(f'GIT_CONFIG_VALUE_{k}', '')}"
            for k in range(min(count, 64)) if f"GIT_CONFIG_KEY_{k}" in env]


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
    timeout = _budget(20)
    try:
        r = subprocess.run(["git", "-C", cwd, "-c", "core.fsmonitor=false", *args],
                           capture_output=True, text=True, timeout=timeout, env=env)
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


# v1.0 audit: the push check works out the destination and the refs the way
# git will: --repo, one-command config (-c, GIT_CONFIG_COUNT) for remotes,
# branches, url.*.insteadOf / pushInsteadOf and push.*, every pushurl,
# configured push refspecs, remote.<name>.mirror, push.default=matching,
# --all / --mirror / --tags / --follow-tags and `tag <name>`. What it cannot
# work out is refused, never guessed.
_PUSH_CFG = re.compile(r"(?i)^(remote|branch|url|push)\.")


def _push_config_key(key: str) -> bool:
    return bool(_PUSH_CFG.match(str(key).strip()))


def _check_push(root: Path, cwd: str, rest: list, v: Verdict, cfg=(), cenv=()):
    flags = _short_flags(rest)
    opts = [a for a in rest if a.startswith("--")]
    if any(_abbrev(o, "--dry-run") for o in opts) or "n" in flags:
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
    pos, repo, i = [], None, 0
    while i < len(rest):
        a = str(rest[i])
        if a == "--":
            pos += [str(x) for x in rest[i + 1:]]
            break
        if a.startswith("--"):
            name, eq, val = a.partition("=")
            full = _abbrev(name, "--repo", "--receive-pack", "--exec", "--push-option")
            if full and not eq:
                val, i = (str(rest[i + 1]) if i + 1 < len(rest) else ""), i + 1
            if full == "--repo":
                repo = val
            elif full in ("--receive-pack", "--exec"):
                v.add(ASK, f"`git push {full}` runs a program of its own choosing ({val}) to "
                           "receive the push, which Tess cannot check")
        elif re.fullmatch(r"-[A-Za-z]*o", a):
            i += 1  # -o <push option>
        elif not a.startswith("-") or a == "-":
            pos.append(a)
        i += 1
    if any(_push_config_key(str(c).split("=", 1)[0]) for c in cenv):
        v.add(DENY, "it takes push settings from an environment variable (--config-env), so Tess "
                    "cannot tell where the push goes or what it sends", "push")
        return
    pre = [x for c in cfg if _push_config_key(str(c).split("=", 1)[0]) for x in ("-c", str(c))]
    try:
        _publish_remote_check(root, cwd, pos, opts, v, pre, repo)
    except _GateTimeout:
        raise
    except Exception as exc:  # fail closed
        v.add(DENY, f"Tess could not check what this push would publish ({type(exc).__name__})", "error")


def _git(cwd: str, *args, check=False) -> str | None:
    r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=_budget(20))
    if r.returncode != 0:
        if check:
            raise RuntimeError(f"git {' '.join(args[:2])} failed")
        return None
    return r.stdout.strip()


def _url_rules(top: str, pre: list, kind: str) -> list:
    """[(prefix, replacement), ...] from url.<base>.insteadOf / pushInsteadOf."""
    out = _git(top, *pre, "config", "--get-regexp", r"^url\..*\." + kind + "$") or ""
    rules = []
    for line in out.splitlines():
        key, _, val = line.partition(" ")
        rules.append((val, key[4:-(len(kind) + 1)]))
    return rules


def _rewrite(url: str, rules: list) -> str | None:
    """`url` rewritten by the longest matching rule, as git does; None if none match."""
    best = max((r for r in rules if url.startswith(r[0])), key=lambda r: len(r[0]), default=None)
    return best[1] + url[len(best[0]):] if best else None


def _push_destination(top: str, pre: list, dest: str | None, branch: str) -> tuple:
    """(remote name or URL, is a configured remote, [push URLs]), worked out the
    way git's remote.c does: every pushurl (with insteadOf), else every url
    (with pushInsteadOf, or failing that insteadOf); a URL or path given on the
    command line is rewritten the same way."""
    if dest is None:
        dest = ((branch and _git(top, *pre, "config", "--get", f"branch.{branch}.pushRemote"))
                or _git(top, *pre, "config", "--get", "remote.pushDefault")
                or (branch and _git(top, *pre, "config", "--get", f"branch.{branch}.remote"))
                or "origin")
    pushurls = (_git(top, *pre, "config", "--get-all", f"remote.{dest}.pushurl") or "").splitlines()
    urls = (_git(top, *pre, "config", "--get-all", f"remote.{dest}.url") or "").splitlines()
    named = bool(pushurls or urls)
    if not named and re.fullmatch(r"[\w.-]+", dest):
        common = _git(top, "rev-parse", "--path-format=absolute", "--git-common-dir")
        if common and any(os.path.exists(os.path.join(common, d, dest)) for d in ("remotes", "branches")):
            raise RuntimeError("remote defined in .git/remotes or .git/branches")
    instead = _url_rules(top, pre, "insteadof")
    if pushurls:
        out = [_rewrite(u, instead) or u for u in pushurls]
    else:
        push_rules = _url_rules(top, pre, "pushinsteadof")
        out = [_rewrite(u, push_rules) or _rewrite(u, instead) or u for u in (urls or [dest])]
    return dest, named, [u for u in out if u.strip()] or [dest]


def _push_refs(top: str, pre: list, remote: str | None, specs: list, opts: list) -> list:
    """[[ref, sha], ...] the push sends, from its refspecs or git's defaults."""
    def has(*names):
        return any(_abbrev(o.split("=", 1)[0], *names) for o in opts)

    def each(pattern):
        out = _git(top, "for-each-ref", "--format=%(refname) %(objectname)", pattern, check=True)
        return [ln.split() for ln in out.splitlines() if ln.strip()]

    def conf(*args):
        return (_git(top, *pre, "config", *args) or "").strip()

    mirror = has("--mirror") or bool(remote and conf("--type=bool", "--get", f"remote.{remote}.mirror") == "true")
    all_, tags = has("--all", "--branches"), has("--tags")
    refs = each("refs/") if mirror else []
    refs += each("refs/heads/") if all_ else []
    if tags or has("--follow-tags") or conf("--type=bool", "--get", "push.followTags") == "true":
        refs += each("refs/tags/")
    specs = list(specs)
    if not specs and not (mirror or all_ or tags):
        configured = remote and conf("--get-all", f"remote.{remote}.push")
        if configured:
            specs = configured.splitlines()
        elif (conf("--get", "push.default") or "simple").lower() == "matching":
            refs += each("refs/heads/")
        else:
            sha = _git(top, "rev-parse", "--verify", "--quiet", "HEAD")
            refs += [["HEAD", sha]] if sha else []
    k = 0
    while k < len(specs):
        spec, k = specs[k], k + 1
        if spec == "tag" and k < len(specs):
            spec, k = "refs/tags/" + specs[k], k + 1
        src = spec.lstrip("+").split(":", 1)[0]
        if not src:
            continue  # a deletion carries no data
        if "*" in src:
            for pat in ({src} if src.startswith("refs/") else {src, "refs/heads/" + src, "refs/tags/" + src}):
                refs += each(pat)
            continue
        sha = _git(top, "rev-parse", "--verify", "--quiet", src)
        if not sha:
            raise RuntimeError("unresolvable ref")
        refs.append([src, sha])
    return refs


def _publish_remote_check(root: Path, cwd: str, pos: list, opts: list, v: Verdict,
                          pre: list = (), repo: str | None = None):
    top = _git(cwd or str(root), "rev-parse", "--show-toplevel")
    if not top:
        return  # not a repository: the push itself will fail
    pre = list(pre)
    branch = _git(top, "symbolic-ref", "--quiet", "--short", "HEAD") or ""
    remote, named, urls = _push_destination(top, pre, pos[0] if pos else repo, branch)
    refs = _push_refs(top, pre, remote if named else None, pos[1:], opts)
    if not refs:
        return
    stdin = "".join(f"{r} {s} {r} {ZERO}\n" for r, s in refs)
    tessctl = root / TESSCTL_REL
    if not tessctl.is_file():
        v.add(DENY, f"{TESSCTL_REL} is missing, so Tess cannot check what this push would publish", "error")
        return
    env = dict(os.environ, TESS_ROOT=top)
    for url in urls:  # git pushes to every pushurl of a remote
        # -I -B: the engine lives in the working tree, and a planted
        # .tess/bin/argparse.py (or yaml.py) beside it must never run inside this hook.
        r = subprocess.run([sys.executable, "-I", "-B", str(tessctl), "doctor", "--publish-remote",
                            remote, url],
                           input=stdin, capture_output=True, text=True, cwd=top, env=env,
                           timeout=_budget(90))
        if r.returncode != 0:
            detail = (r.stderr.strip() or r.stdout.strip() or "tess-remote-guard refused the push")
            v.add(DENY, "the public-remote guard refused it: " + _redact(root, detail), "push")
            return


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


# --------------------------------------------------------------------------- operands (v1.0 audit)
# A write target is compared with the protected list the way the shell will
# expand it: ~, $HOME / $PWD / $TMPDIR, variables set earlier in the same
# command, `for` loop lists, braces and globs (against the files on disk and
# against the protected names themselves), `$(pwd)` / `$(mktemp)`, and
# symlinks the command makes before it writes. A target that is still only
# known at run time asks, unless the text in front of it fixes a directory
# outside the project.

_NAMED = {"git", "gh", "hub", "tessctl", "tessctl.py", "eval", "find", "cd", "pushd", "popd",
          "chdir", "export", "declare", "typeset", "setenv", "local", "readonly"}
# Writers outside WRITERS: every operand, or the one noted in _write_targets.
_EXTRA_WRITERS = {"scp", "rename", "trash", "srm", "link", "mktemp", "chgrp", "mkfifo", "zip"}
# Programs that write the file an option names.
_OUTPUT_OPTS = {"curl": ("-o", "--output"), "wget": ("-O", "--output-document", "-P", "--directory-prefix"),
                "sort": ("-o", "--output"), "base64": ("-o", "--output"), "openssl": ("-out",),
                "gpg": ("-o", "--output"), "ssh-keygen": ("-f",), "uudecode": ("-o",),
                "iconv": ("-o", "--output"), "plutil": ("-o",), "pandoc": ("-o", "--output")}
_GIT_TOOLS = {"git-lfs", "git-receive-pack", "git-upload-pack", "git-upload-archive", "git-shell",
              "git-credential-osxkeychain", "git-credential-manager", "git-filter-repo"}
_STABLE_VARS = ("HOME", "TMPDIR", "USER", "LOGNAME")
_GLOB_CHARS = re.compile(r"[*?[]")
_MAX_DEPTH = 4
_FIND_LIMIT = 20000
_UNSET = object()
# Filled per evaluate(): the deadline and what this call already checked.
_STATE: dict = {"deadline": None, "interp": set()}


class _GateTimeout(Exception):
    """The gate's time budget ran out (see GATE_BUDGET)."""


def _tick() -> None:
    d = _STATE.get("deadline")
    if d is not None and time.monotonic() > d:
        raise _GateTimeout()


def _budget(seconds: float) -> float:
    """A subprocess timeout that ends inside the gate's own budget."""
    d = _STATE.get("deadline")
    if d is None:
        return seconds
    left = d - time.monotonic()
    if left <= 0.5:
        raise _GateTimeout()
    return min(seconds, left)


class _Ctx:
    """What one command has set up for the words after it: variables, the
    symlinks it creates, and whether it has changed files yet."""

    def __init__(self, raw: str, parent: "_Ctx | None" = None, env: dict | None = None):
        self.raw = raw if parent is None else parent.raw
        self.vars = dict(parent.vars) if parent is not None else {}
        self.links = parent.links if parent is not None else {}
        self.mutated = parent.mutated if parent is not None else False
        for k, val in (env or {}).items():
            self.vars[k] = None if re.search(r"[$`]", str(val)) else [str(val)]

    def assign(self, name: str, vals, cond: bool) -> None:
        if cond:
            old = self.vars.get(name, _UNSET)
            old = None if old is _UNSET else old
            vals = None if old is None or vals is None else list(dict.fromkeys(old + vals))[:64]
        self.vars[name] = vals


def _writer_name(low: str) -> str | None:
    if low in WRITERS or low in _EXTRA_WRITERS:
        return low
    if low.startswith("g") and low[1:] in WRITERS:
        return low[1:]  # GNU coreutils as installed by Homebrew: gcp, gmv, grm...
    return None


def _var_values(name: str, cwd: str | None, ctx: "_Ctx"):
    if name in ctx.vars:
        return ctx.vars[name]
    if name == "PWD":
        return [cwd] if cwd else None
    if name in _STABLE_VARS and not re.search(r"(?<![\w$])" + name + r"=", ctx.raw):
        val = os.path.expanduser("~") if name == "HOME" else os.environ.get(name)
        return [val] if val else None
    return None


def _sub_values(text: str, cwd: str | None):
    """What a command substitution prints, for the few Tess can know: $(pwd), $(mktemp ...)."""
    try:
        words = shlex.split(text)
    except ValueError:
        return None
    if words in (["pwd"], ["pwd", "-P"], ["pwd", "-L"]):
        return [cwd] if cwd else None
    if not words or words[0] != "mktemp" or any(re.search(r"[$`]", w) for w in words):
        return None
    where, k = None, 1
    while k < len(words):
        w = words[k]
        if w in ("-p", "--tmpdir") and k + 1 < len(words):
            where, k = words[k + 1], k + 2
            continue
        if w.startswith("--tmpdir="):
            where = w.split("=", 1)[1]
        elif not w.startswith("-") and "/" in w:
            where = os.path.dirname(w)
        k += 1
    base = os.path.expanduser(where) if where else (os.environ.get("TMPDIR") or tempfile.gettempdir())
    return [os.path.join(base if os.path.isabs(base) else os.path.join(cwd or ".", base),
                         "tess-mktemp.XXXXXX")]


def _braces(text: str, limit: int = 64) -> list:
    """Brace expansion of unquoted text: {a,b} and {1..3}."""
    start = 0
    while True:
        i = text.find("{", start)
        if i < 0:
            return [text]
        depth, j, commas = 0, i, []
        while j < len(text):
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            elif text[j] == "," and depth == 1:
                commas.append(j)
            j += 1
        if j >= len(text):
            return [text]
        inner = text[i + 1:j]
        if commas:
            alts, prev = [], i + 1
            for c in commas + [j]:
                alts.append(text[prev:c])
                prev = c + 1
        else:
            m = re.fullmatch(r"(-?\d+)\.\.(-?\d+)|([A-Za-z])\.\.([A-Za-z])", inner)
            if not m:
                start = i + 1
                continue
            a, b = (int(m.group(1)), int(m.group(2))) if m.group(1) else (ord(m.group(3)), ord(m.group(4)))
            step = 1 if b >= a else -1
            alts = [str(x) if m.group(1) else chr(x) for x in range(a, b + step, step)][:limit]
        out = []
        for alt in alts:
            out += _braces(text[:i] + alt + text[j + 1:], limit)
            if len(out) >= limit:
                return out[:limit]
        return out


def _tilde(text: str, cwd: str | None, ctx: "_Ctx"):
    m = re.match(r"~([^/]*)", text)
    user = m.group(1)
    if user == "":
        home = _var_values("HOME", cwd, ctx)
        return home[0] + text[1:] if home else None
    if user == "+":
        return cwd + text[2:] if cwd else None
    if user == "-":
        return None
    exp = os.path.expanduser("~" + user)
    return text if exp.startswith("~") else exp + text[m.end():]


def _gescape(text: str) -> str:
    return re.sub(r"([*?[])", r"[\1]", text)


def _word_values(word, cwd: str | None, ctx: "_Ctx | None", limit: int = 64) -> tuple:
    """([(text, glob pattern or None), ...], None) for the strings `word` can
    become; (None, prefix) when part of it is only known at run time, with the
    text in front of that part."""
    ctx = ctx if ctx is not None else _Ctx("")
    parts = word.parts if isinstance(word, _Word) and word.parts else (("fallback", str(word)),)
    cands = [("", "", False)]
    for n, (kind, t) in enumerate(parts):
        alts = None
        if kind == "lit":
            alts = [(t, _gescape(t), False)]
        elif kind in ("raw", "fallback") and not (kind == "fallback" and re.search(r"[$`]", t)):
            if n == 0 and t.startswith("~"):
                t = _tilde(t, cwd, ctx)
            if t is not None:
                alts = [(b, b, bool(_GLOB_CHARS.search(b))) for b in _braces(t)]
        elif kind == "var":
            vals = _var_values(t, cwd, ctx)
            alts = None if vals is None else [(x, x, bool(_GLOB_CHARS.search(x))) for x in vals]
        elif kind == "sub":
            vals = _sub_values(t, cwd)
            alts = None if vals is None else [(x, _gescape(x), False) for x in vals]
        if alts is None:
            return None, cands[0][0]
        cands = [(a + x, p + y, g or h) for a, p, g in cands for x, y, h in alts][:limit]
    return [(text, pat if glob else None) for text, pat, glob in cands], None


def _may_reach(root: Path, cwd: str | None, prefix: str) -> bool:
    """False only when the text in front of a run-time part fixes a directory
    outside the project and not above it (`/tmp/build-$ID`)."""
    base = os.path.realpath(str(root))
    if "/" in prefix:
        head = prefix.rsplit("/", 1)[0] or "/"
        real = os.path.realpath(os.path.join(cwd or base, os.path.expanduser(head)))
    else:
        real = os.path.realpath(cwd or base)
    return real == base or base.startswith(real.rstrip(os.sep) + os.sep) or real.startswith(base + os.sep)


def _through_links(path: str, cwd: str, ctx: "_Ctx") -> str | None:
    """`path` with the symlinks this command creates earlier followed; None
    when one points somewhere only known at run time."""
    full = os.path.normpath(os.path.join(cwd, path))
    for _ in range(8):
        for link, target in ctx.links.items():
            if full == link or full.startswith(link + os.sep):
                if target is None:
                    return None
                full = os.path.normpath(target + full[len(link):])
                break
        else:
            return full
    return full


def _seg_match(name: str, pat: str) -> bool:
    if name.startswith(".") and not pat.startswith("."):
        return False  # a glob does not match a dot file unless it starts with a dot
    return fnmatch.fnmatchcase(name.lower(), pat.lower())


def _pattern_hit(root: Path, cwd: str, pat: str) -> str | None:
    """The protected path a glob pattern can name, whether or not that file
    exists when the gate runs (`CLAUDE.m?`, `.claude/hook[s]/*`, `*`)."""
    full = pat if os.path.isabs(pat) else os.path.join(cwd, pat)
    parts = full.split(os.sep)
    k = next((i for i, p in enumerate(parts) if _GLOB_CHARS.search(p)), len(parts))
    head = os.path.realpath(os.sep.join(parts[:k]) or os.sep)
    base = os.path.realpath(str(root))
    if head != base and not head.startswith(base + os.sep):
        return None
    rel = os.path.relpath(head, base)
    pparts = ([] if rel == "." else rel.split(os.sep)) + [p for p in parts[k:] if p]
    for g in _protected_globs(root):
        entry = g[:-3] if g.endswith("/**") else g
        if _GLOB_CHARS.search(entry):
            continue
        eparts = entry.split("/")
        if len(pparts) <= len(eparts) and all(_seg_match(e, p) for e, p in zip(eparts, pparts)):
            return g  # the entry, or a directory holding it
        if g.endswith("/**") and len(pparts) > len(eparts) and all(
                _seg_match(e, p) for e, p in zip(eparts, pparts)):
            return g  # a file inside a protected directory
    return None


def _check_target(root: Path, cwd: str, word, v: "Verdict", ctx: "_Ctx") -> None:
    if isinstance(word, _Word) and word.parts and all(k == "proc" for k, _ in word.parts):
        return  # >(cmd): a pipe to a command checked on its own
    cands, prefix = _word_values(word, cwd, ctx)
    if cands is None:
        if _may_reach(root, cwd, prefix):
            v.add(ASK, f"it writes to {word}, a path that is only known when the command runs, "
                       "so Tess cannot check it against its protected files")
        return
    for text, pat in cands:
        for p in (_glob(cwd, pat) if pat else []) or [text]:
            full = _through_links(p, cwd, ctx)
            if full is None:
                v.add(ASK, f"it writes to {word} through a link this command makes to a place "
                           "Tess cannot work out")
                return
            hit = protected_hit(root, cwd, full)
            if hit:
                v.add(DENY, f"it writes to {word}, a protected Tess path ({hit})", "protected")
                return
        hit = pat and _pattern_hit(root, cwd, pat)
        if hit:
            v.add(DENY, f"it writes to {word}, which matches a protected Tess path ({hit})", "protected")
            return


def _sub_word(word, k: int):
    """`word` without its first k characters, keeping how the rest was written."""
    if not isinstance(word, _Word) or not word.parts:
        return str(word)[k:]
    out, left = [], k
    for kind, t in word.parts:
        if left and kind in ("lit", "raw", "fallback"):
            take = min(left, len(t))
            t, left = t[take:], left - take
            if not t:
                continue
        elif left:
            return _mkword([("dyn", "")])
        out.append((kind, t))
    return _mkword(out or [("lit", "")])


def _redirect_targets(argv: list) -> list:
    out = []
    for i, tok in enumerate(argv):
        s = str(tok)
        red = (tok.op and s in _REDIR_OPS) if isinstance(tok, _Word) else (
            s in REDIRECTS or s == ">&" or re.match(r"^\d*>{1,2}\|?$", s))
        if not red or s in ("<", "<<", "<<-", "<<<", "<&") or i + 1 >= len(argv) or _is_op(argv[i + 1]):
            continue
        if s == ">&" and re.fullmatch(r"\d+-?|-", str(argv[i + 1])):
            continue  # 2>&1: a descriptor, not a file
        out.append(argv[i + 1])
    return out


def _output_targets(name: str, args: list) -> list:
    out = []
    for i, a in enumerate(args):
        s = str(a)
        for o in _OUTPUT_OPTS.get(name, ()):
            if s == o and i + 1 < len(args):
                out.append(args[i + 1])
            elif o.startswith("--") and s.startswith(o + "="):
                out.append(_sub_word(a, len(o) + 1))
            elif len(o) == 2 and s.startswith(o) and len(s) > 2:
                out.append(_sub_word(a, 2))
    if name == "curl" and any(str(a) in ("--remote-name", "--remote-name-all") or
                              re.fullmatch(r"-[A-Za-z]*O[A-Za-z]*", str(a)) for a in args):
        for a in args:
            m = re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://[^/]+/(?:[^?#]*/)?([^/?#]+)", str(a))
            if m:
                out.append(_plain(m.group(1)))
    if name in ("tar", "gtar", "bsdtar"):
        words = [str(a) for a in args]
        if words and not words[0].startswith("-"):
            words[0] = "-" + words[0]  # old-style `tar czf out.tgz ...`
        clusters = [w for w in words if re.fullmatch(r"-[A-Za-z]+", w)]
        if any(set("cruA") & set(c[1:]) for c in clusters) or any(
                w in ("--create", "--append", "--update") for w in words):
            for i, w in enumerate(words):
                if w.startswith("--file="):
                    out.append(_sub_word(args[i], 7))
                elif w == "--file" and i + 1 < len(args):
                    out.append(args[i + 1])
                elif re.fullmatch(r"-[A-Za-z]+", w) and "f" in w:
                    rest = w[w.index("f") + 1:]
                    out.append(_plain(rest) if rest else (args[i + 1] if i + 1 < len(args) else _plain("")))
    return out


def _write_targets(argv: list, orig: list | None = None) -> list:
    """Words naming what a segment writes: redirect targets (in `orig`, the
    whole segment when given) and the operands the program writes (`argv`,
    from the program on)."""
    out = _redirect_targets(orig if orig is not None else argv)
    if not argv:
        return out
    name = os.path.basename(str(argv[0])).lower()
    args = [a for a in argv[1:] if not (_is_op(a) and str(a) in _REDIR_OPS)]
    w = _writer_name(name)
    ops = [a for a in args if not str(a).startswith("-")]
    if w == "dd":
        out += [_sub_word(a, 3) for a in args if str(a).startswith("of=")]
    elif w == "scp":
        out += ops[-1:]
    elif w == "zip":
        out += ops[:1]
    elif w:
        out += ops
        for a in args:
            s = str(a)
            if s.startswith("--") and "=" in s:
                out.append(_sub_word(a, s.index("=") + 1))  # --target-directory=DIR
            elif w in ("cp", "mv", "install", "ln") and re.match(r"^-[A-Za-z]*t.", s):
                out.append(_sub_word(a, s.index("t") + 1))  # -tDIR
    elif name in INPLACE and any(re.match(r"^-[A-Za-z]*i", str(a)) or str(a).startswith("--in-place")
                                 for a in args):
        out += ops
    return out + _output_targets(name, args)


def _check_targets(root: Path, cwd: str, targets: list, v: "Verdict", ctx: "_Ctx") -> None:
    for t in targets:
        _tick()
        _check_target(root, cwd, t, v, ctx)


def _operands(words: list) -> list:
    """Words that are not redirections (nor their targets)."""
    out, skip = [], False
    for w in words:
        if skip:
            skip = False
        elif _is_op(w) and str(w) in _REDIR_OPS:
            skip = True
        elif not (isinstance(w, _Word) and w.fd):
            out.append(w)
    return out


def _stdin_source(orig: list):
    """('herestring', word) | ('heredoc', body) | ('file', word) | None: the
    last input redirection of a segment."""
    src = None
    for i, tok in enumerate(orig):
        if _is_op(tok) and i + 1 < len(orig):
            s = str(tok)
            if s == "<<<":
                src = ("herestring", orig[i + 1])
            elif s in ("<<", "<<-"):
                src = ("heredoc", getattr(orig[i + 1], "body", None) or "")
            elif s == "<":
                src = ("file", orig[i + 1])
    return src


def _upstream_words(upstream) -> list | None:
    """The text a pipeline's previous command prints, when Tess can read it
    from the command line (echo, printf, cat of a here-document); None if not."""
    if upstream is None:
        return None
    argv = _resolve(upstream).argv
    name = os.path.basename(str(argv[0])).lower() if argv else ""
    if name in ("echo", "printf"):
        return [str(a) for a in _operands(argv[1:]) if not re.fullmatch(r"-[neE]+", str(a))]
    if name == "cat" and not [a for a in _operands(argv[1:]) if not str(a).startswith("-")]:
        src = _stdin_source(upstream)
        if src and src[0] in ("heredoc", "herestring"):
            return [str(src[1])]
    return None


def _recurse(root: Path, cwd: str, text: str, v: "Verdict", depth: int, ctx: "_Ctx",
             env: dict | None = None) -> None:
    if depth >= _MAX_DEPTH:
        v.add(ASK, "it nests commands (`bash -c`, `eval`, `$(...)`) more deeply than Tess checks")
        return
    check_command(root, cwd, text, v, depth + 1, ctx=_Ctx(ctx.raw, ctx, env))


def _body_subs(body: str) -> list:
    """Command substitutions a here-document with an unquoted delimiter runs."""
    out, i = [], 0
    while i < len(body):
        c = body[i]
        if c == "\\":
            i += 2
            continue
        try:
            if body.startswith("$(", i):
                j = _close_paren(body, i + 1)
                out.append(body[i + 2:j])
                i = j
            elif c == "`":
                j = _close_backtick(body, i)
                out.append(body[i + 1:j])
                i = j
        except ValueError:
            out.append(body[i:])
            break
        i += 1
    return out


def _check_subs(root: Path, cwd: str, word, v: "Verdict", depth: int, ctx: "_Ctx") -> None:
    """Command and process substitutions in a word run first, in this directory."""
    if not isinstance(word, _Word):
        return
    for kind, t in word.parts:
        if kind in ("sub", "proc") and t.strip():
            _recurse(root, cwd, t, v, depth, ctx)
        if kind == "arith":
            for inner in _body_subs(t):
                _recurse(root, cwd, inner, v, depth, ctx)
    if word.body and all(k == "raw" for k, _ in word.parts):
        for t in _body_subs(word.body):
            _recurse(root, cwd, t, v, depth, ctx)


def _check_shell(root: Path, cwd: str, argv: list, orig: list, v: "Verdict", depth: int,
                 ctx: "_Ctx", upstream) -> bool:
    """A shell's program: `-c` string (any option cluster holding c: -c, -Ec,
    -xc; `--` allowed), a here-string or here-document, or the text a pipe
    feeds it. A script file is not read (documented limit). True when the
    segment was a shell running a program Tess checked or refused."""
    words, i, has_c, has_s = [str(a) for a in argv[1:]], 0, False, False
    while i < len(words):
        a = words[i]
        if a == "--":
            i += 1
            break
        if a in ("-o", "+o", "-O", "+O", "--rcfile", "--init-file"):
            i += 2
            continue
        if re.fullmatch(r"[-+][A-Za-z]+", a):
            has_c = has_c or (a[0] == "-" and "c" in a[1:])
            has_s = has_s or (a[0] == "-" and "s" in a[1:])
            i += 1
            continue
        if a.startswith("--"):
            i += 1
            continue
        break
    operands = _operands(argv[1 + i:])
    if has_c:
        if operands:  # `sh -c 'rm "$1"' _ file`: $0, $1... are the words after the string
            _recurse(root, cwd, str(operands[0]), v, depth, ctx,
                     {str(k): str(w) for k, w in enumerate(operands[1:10])})
        return True
    if operands and not has_s and str(operands[0]) not in ("-", "/dev/stdin", "/dev/fd/0"):
        if _program_from(root, cwd, operands[0], v, depth, ctx):
            return True
        return False  # a script file: see SECURITY.md "Hooks read command text"
    src = _stdin_source(orig)
    if src and src[0] in ("herestring", "heredoc"):
        _recurse(root, cwd, str(src[1]), v, depth, ctx)
    elif src is None and upstream is not None:
        texts = _upstream_words(upstream)
        if texts is None:
            prog = _resolve(upstream).argv
            v.add(ASK, f"it runs shell commands that another program "
                       f"({os.path.basename(str(prog[0])) if prog else 'a pipe'}) prints, which "
                       "Tess cannot read before they run")
        for t in texts or []:
            _recurse(root, cwd, t, v, depth, ctx)
        if texts:
            _recurse(root, cwd, " ".join(texts), v, depth, ctx)
    return True


def _program_from(root: Path, cwd: str, word, v: "Verdict", depth: int, ctx: "_Ctx") -> bool:
    """`bash <(cmd)`, `source <(cmd)`: the program is what another command
    prints. Checked when that is echo/printf/cat of a here-document, asked
    otherwise. False when `word` is a plain file (a script: documented limit)."""
    if not (isinstance(word, _Word) and word.parts and all(k == "proc" for k, _ in word.parts)):
        return False
    try:
        segs = _segments(word.parts[0][1])
    except ValueError:
        segs = []
    texts = _upstream_words(segs[-1]) if segs else None
    if texts is None:
        v.add(ASK, "it runs shell commands that another program prints, which Tess cannot read "
                   "before they run")
    for t in texts or []:
        _recurse(root, cwd, t, v, depth, ctx)
    return True


def _check_stdin_operands(root: Path, cwd: str, name: str, orig: list, v: "Verdict",
                          ctx: "_Ctx", upstream) -> None:
    """`xargs <writer>`: the file names come from its input."""
    src = _stdin_source(orig)
    words = None
    if src and src[0] in ("heredoc", "herestring"):
        words = str(src[1]).split()
    elif src is None and upstream is not None:
        up = _upstream_words(upstream)
        words = None if up is None else " ".join(up).split()
    if words is None:
        v.add(ASK, f"it hands {name} file names that it reads from its input, which Tess cannot "
                   "check against its protected files")
        return
    for w in words:
        _check_target(root, cwd, _plain(w), v, ctx)


def _check_patch_input(root: Path, cwd: str, argv: list, orig: list, v: "Verdict") -> None:
    """`patch` writes the files its diff names (from -i FILE, `<`, or a here-document)."""
    texts, args = [], [str(a) for a in argv[1:]]
    src = _stdin_source(orig)
    files = [args[k + 1] for k, a in enumerate(args[:-1]) if a == "-i"] + [
        a.split("=", 1)[1] for a in args if a.startswith("--input=")]
    if src and src[0] == "file":
        files.append(str(src[1]))
    elif src:
        texts.append(str(src[1]))
    for f in files:
        try:
            with open(os.path.join(cwd, os.path.expanduser(f)), encoding="utf-8", errors="replace") as fh:
                texts.append(fh.read(5_000_000))
        except OSError:
            v.add(ASK, f"`patch` applies {f}, which Tess cannot read")
    for n in {n for t in texts for m in _PATCH_PATHS.finditer(t) for n in m.groups() if n}:
        for cand in {n, n.split("/", 1)[-1]}:
            hit = cand != "/dev/null" and protected_hit(root, cwd, cand)
            if hit:
                v.add(DENY, f"`patch` changes {cand} ({hit}), a protected Tess path", "protected")
                return


def _record_links(cwd: str, argv: list, ctx: "_Ctx") -> None:
    """Remember the links `ln` makes, so a later write through one in the same
    command (`ln -s . x && cp y x/CLAUDE.md`) is checked where it lands."""
    args, tdir, ops, i = _operands(argv[1:]), None, [], 0
    sym = any(re.match(r"^-[A-Za-z]*s", str(a)) or str(a) == "--symbolic" for a in args)
    while i < len(args):
        s = str(args[i])
        if s in ("-t", "-S", "--suffix") and i + 1 < len(args):
            tdir = args[i + 1] if s == "-t" else tdir
            i += 2
            continue
        if s.startswith("--target-directory="):
            tdir = _sub_word(args[i], 19)
        elif not s.startswith("-") or s == "-":
            ops.append(args[i])
        i += 1

    def val(w):
        cands, _ = _word_values(w, cwd, ctx)
        return cands[0][0] if cands and len(cands) == 1 else None

    if tdir is not None:
        pairs = [(t, os.path.join(val(tdir) or "\0", os.path.basename(val(t) or "\0"))) for t in ops]
    elif len(ops) == 1:
        pairs = [(ops[0], os.path.basename(val(ops[0]) or "\0"))]
    elif len(ops) >= 2:
        dest = val(ops[-1])
        dest_abs = os.path.join(cwd, dest) if dest else None
        many = len(ops) > 2 or (dest_abs and os.path.isdir(dest_abs) and not os.path.islink(dest_abs))
        pairs = [(t, os.path.join(dest_abs, os.path.basename(val(t) or "\0")) if many else dest_abs)
                 for t in ops[:-1]] if dest_abs else []
    else:
        pairs = []
    for t, link in pairs:
        if not link or "\0" in link:
            continue
        link = os.path.normpath(os.path.join(cwd, link))
        tv = val(t)
        target = None if tv is None else os.path.normpath(
            os.path.join(os.path.dirname(link) if sym else cwd, os.path.expanduser(tv)))
        ctx.links[link] = target


def _find_match(path: str, shown: str, preds: list, ftype: str | None) -> bool:
    name = os.path.basename(path.rstrip(os.sep)) or path
    for op, pat in preds:
        low = op in ("-iname", "-ipath", "-iwholename", "-iregex")
        subject = name if op in ("-name", "-iname") else shown
        if op.endswith("regex"):
            try:
                if not re.fullmatch(pat, subject, re.I if low else 0):
                    return False
            except re.error:
                continue
        elif not fnmatch.fnmatchcase(subject.lower() if low else subject, pat.lower() if low else pat):
            return False
    if ftype == "f" and not os.path.isfile(path):
        return False
    if ftype == "d" and not os.path.isdir(path):
        return False
    return True


def _find_plan(argv: list) -> tuple:
    """(start paths, expression) of a find command."""
    args, i, starts = argv[1:], 0, []
    while i < len(args):
        a = str(args[i])
        if a in ("-H", "-L", "-P", "-E", "-X", "-d", "-s", "-x") or re.fullmatch(r"-O\d*", a):
            i += 1
        elif a == "-D":
            i += 2
        elif a == "-f" and i + 1 < len(args):
            starts.append(args[i + 1])
            i += 2
        else:
            break
    while i < len(args) and not str(args[i]).startswith("-") and str(args[i]) not in ("(", "!", ","):
        starts.append(args[i])
        i += 1
    return starts or [_plain(".")], args[i:]


def _check_find(root: Path, cwd: str, argv: list, v: "Verdict", raw: str, depth: int,
                ctx: "_Ctx") -> None:
    """`find -delete`, `find -exec <cmd> {} ;` and `-fprint FILE` change files
    the command line does not name: the files find would match are listed
    (up to _FIND_LIMIT) and checked."""
    starts, expr = _find_plan(argv)
    changes, j = False, 0
    while j < len(expr):
        a = str(expr[j])
        if a in ("-exec", "-execdir", "-ok", "-okdir"):
            k = j + 1
            while k < len(expr) and str(expr[k]) not in (";", "+"):
                k += 1
            inner = list(expr[j + 1:k])  # {} stays: a plain name, the matches are walked below
            if inner:
                _check_segment(root, cwd, inner, v, raw, depth + 1, _Ctx(raw, ctx))
                prog = _resolve(inner).argv
                low = os.path.basename(str(prog[0])).lower() if prog else ""
                changes = changes or bool(prog) and low not in _READONLY_PROGRAMS and low not in (
                    "git", "gh", "file", "shasum", "sha256sum", "md5", "md5sum", "basename", "dirname")
            j = k + 1
            continue
        if a == "-delete":
            changes = True
        if a in ("-fprint", "-fprint0", "-fls", "-fprintf") and j + 1 < len(expr):
            _check_target(root, cwd, expr[j + 1], v, ctx)
        j += 1
    if changes:
        _find_protected(root, cwd, starts, expr, v, ctx)


def _find_protected(root: Path, cwd: str, starts: list, expr: list, v: "Verdict", ctx: "_Ctx") -> None:
    words = [str(w) for w in expr]
    simple = not any(w in ("-o", "-or", "!", "-not", ",", "(", ")") for w in words)
    preds, maxdepth, mindepth, ftype = [], None, 0, None
    for k, w in enumerate(words[:-1]):
        nxt = words[k + 1]
        if w in ("-name", "-iname", "-path", "-ipath", "-wholename", "-iwholename", "-regex", "-iregex"):
            preds.append((w, nxt))
        elif w in ("-maxdepth", "-mindepth") and nxt.isdigit():
            maxdepth, mindepth = (int(nxt), mindepth) if w == "-maxdepth" else (maxdepth, int(nxt))
        elif w == "-type":
            ftype = nxt
    if not simple:
        preds, ftype = [], None  # an expression with -o / ! / ( ): every file counts
    seen = 0
    for s in starts:
        cands, prefix = _word_values(s, cwd, ctx)
        if cands is None:
            if _may_reach(root, cwd, prefix):
                v.add(ASK, f"`find` changes files under {s}, a directory only known when the command "
                           "runs, so Tess cannot check them")
            continue
        for text, pat in cands:
            for start in (_glob(cwd, pat) if pat else []) or [text]:
                top = os.path.normpath(os.path.join(cwd, start))
                base = os.path.realpath(str(root))
                real = os.path.realpath(top)
                if real != base and not real.startswith(base + os.sep) and not base.startswith(real + os.sep):
                    continue  # nowhere near the project
                entries = [(top, start, 0)]
                for dirpath, dirnames, filenames in os.walk(top):
                    rel = os.path.relpath(dirpath, top)
                    d = 0 if rel == "." else rel.count(os.sep) + 1
                    if maxdepth is not None and d + 1 > maxdepth:
                        dirnames[:] = []
                        continue
                    shown_dir = start if rel == "." else os.path.join(start, rel)
                    entries += [(os.path.join(dirpath, n), os.path.join(shown_dir, n), d + 1)
                                for n in dirnames + filenames]
                    seen += len(dirnames) + len(filenames)
                    if seen > _FIND_LIMIT:
                        v.add(ASK, "`find` would change more files than Tess can list, so it cannot "
                                   "check them against its protected files")
                        return
                    _tick()
                for path, shown, d in entries:
                    if d < mindepth or not _find_match(path, shown, preds, ftype):
                        continue
                    hit = protected_hit(root, cwd, path)
                    if hit:
                        v.add(DENY, f"`find` would change {shown}, a protected Tess path ({hit})", "protected")
                        return


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
    code = str(_interp_code(argv, raw))
    if not _INTERP_WRITE.search(code):
        return
    # v1.0 audit: each distinct token is checked once, and one evaluation
    # checks a program text once (a heredoc program is the whole command, which
    # every interpreter segment of that command would otherwise rescan).
    memo = _STATE["interp"] if _STATE.get("deadline") is not None else {}
    key = (str(root), cwd, code)
    if key not in memo:
        memo[key] = None
        for n, tok in enumerate(dict.fromkeys(_INTERP_TOKEN.findall(code))):
            if n % 256 == 0:
                _tick()
            t = tok[2:] if tok.startswith("./") else tok
            hit = (t.rstrip("/") in PROTECTED_DIR_ROOTS and t.rstrip("/"))
            if not hit and ("/" in t or "." in t):
                hit = protected_hit(root, cwd, t)
            if hit:
                memo[key] = (tok, hit)
                break
    if memo[key]:
        tok, hit = memo[key]
        v.add(DENY, f"an inline {os.path.basename(str(argv[0]))} program writes near {tok}, a "
                    f"protected Tess path ({hit})", "protected")


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
    timeout = _budget(20)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
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


def _check_segment(root: Path, cwd: str | None, argv: list, v: Verdict, raw: str, depth: int,
                   ctx: "_Ctx | None" = None, upstream=None):
    ctx = ctx if ctx is not None else _Ctx(raw)
    _tick()
    orig = list(argv)
    res = _resolve(orig)
    env, argv = res.env, res.argv
    for k, val in env.items():
        if k in GIT_CONFIG_FILE_ENV and val not in _EMPTY_CONFIG:
            v.add(DENY, f"it sets {k}, which makes git read another config file (that file can "
                        "switch off Tess's git hooks)", "hookspath")
    if res.chdir is not None and cwd is not None:
        cands, _ = _word_values(res.chdir, cwd, ctx)
        cwd = os.path.normpath(os.path.join(cwd, cands[0][0])) if cands and len(cands) == 1 else None
    targets = _write_targets(argv, orig)
    if cwd is None:
        # a `cd` earlier in this command (or the tool's working directory) went
        # somewhere Tess cannot resolve
        if any(not os.path.isabs(os.path.expanduser(str(t))) for t in targets):
            v.add(DENY, "it writes to a relative path after a `cd` whose target is only known "
                        "at run time, so Tess cannot check it against the protected list", "protected")
        cwd = str(root)
    for w in orig:  # command and process substitutions run first, in this directory
        _check_subs(root, cwd, w, v, depth, ctx)
    for text in res.inner:
        _recurse(root, cwd, text, v, depth, ctx, env)
    _check_targets(root, cwd, targets, v, ctx)
    if not argv:
        return
    if _dynamic(argv[0]):
        return _check_dynamic_program(root, cwd, argv, v, raw, depth, ctx)
    name = os.path.basename(str(argv[0])).lower()  # macOS finds `GIT` as git
    if name == "hub" or (name.startswith("git-") and name not in _GIT_TOOLS):
        argv = [_plain("git")] + ([_plain(name[4:])] if name.startswith("git-") else []) + list(argv[1:])
        name = "git"
    _check_home_env(env, argv, raw, v)
    if INTERPRETERS.match(name):
        _check_interpreter(root, cwd, argv, v, raw)
    if name in SHELLS and _check_shell(root, cwd, argv, orig, v, depth, ctx, upstream):
        return
    if name == "eval":
        _recurse(root, cwd, " ".join(str(a) for a in _operands(argv[1:])), v, depth, ctx)
        return
    if name in ("source", ".") and len(argv) > 1:
        _program_from(root, cwd, argv[1], v, depth, ctx)
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
    if name in ("export", "declare", "typeset", "setenv") and any(
            re.match(r"GIT_CONFIG_KEY_\d+=", a) and _push_config_key(a.partition("=")[2])
            for a in argv[1:]):
        v.add(ASK, "it sets git configuration through the environment that changes where a push "
                   "goes or what it sends")
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
    elif name == "find":
        _check_find(root, cwd, argv, v, raw, depth, ctx)
    elif name == "patch":
        _check_patch_input(root, cwd, argv, orig, v)
    if res.via_xargs and (_writer_name(name) or name in INPLACE):
        _check_stdin_operands(root, cwd, name, orig, v, ctx, upstream)
    if name == "ln":
        _record_links(cwd, argv, ctx)
    if name not in READERS_OK_FOR_GIT_DIR and name != "git":
        for a in argv[1:]:
            if re.search(r"(^|/)\.git/(hooks(/|$)|config$|info(/|$)|refs/replace(/|$))", a):
                v.add(DENY, f"it touches {a}; Tess's git hooks and git config are off limits", "hookspath")


def _check_dynamic_program(root: Path, cwd: str, argv: list, v: Verdict, raw: str, depth: int,
                           ctx: "_Ctx") -> None:
    """The program is a variable or command substitution. A value set earlier
    in the command is checked as that program; otherwise the command is
    checked as if it were git, gh, a shell, python and a file writer, and
    asks if any of those would be stopped (or if it has no arguments at all)."""
    cands, _ = _word_values(argv[0], cwd, ctx)
    if cands and depth < _MAX_DEPTH:
        for text, _pat in cands:
            words = [_plain(w) for w in text.split()]
            if words:
                _check_segment(root, cwd, words + list(argv[1:]), v, raw, depth + 1, ctx)
        return
    probe = Verdict()
    if depth < _MAX_DEPTH:
        for stand_in in ("git", "gh", "sh", "python3", "cp"):
            _check_segment(root, cwd, [_plain(stand_in)] + list(argv[1:]), probe, raw, depth + 1,
                           _Ctx(raw, ctx))
    why = f"it runs a program whose name is only known when the command runs ({argv[0]})"
    if probe.level > ALLOW:
        v.add(ASK, why + "; if that is git, gh, a shell, python or a file writer, Tess would stop "
                         "it: " + "; ".join(probe.reasons))
    elif len(argv) == 1 or depth >= _MAX_DEPTH:
        v.add(ASK, why + ", so Tess cannot check what it does")


def check_command(root: Path, cwd: str, cmd: str, v: Verdict, depth: int = 0, ctx: "_Ctx | None" = None):
    ctx = ctx if ctx is not None else _Ctx(cmd)
    _tick()
    _check_operator_only(cmd, v)
    try:
        events = _events(cmd)
    except ValueError:
        # Unparseable (unbalanced quotes). The shell may still run it: a quote
        # inside a `# comment` (`rm .claude/hooks/tess-gate.py # it's`) breaks
        # shlex but not bash. Never fail open here (v1.0 code review, HIGH):
        # check the raw text, then re-parse with shell comments, and if the
        # command is still undecidable ask (Claude) -- decide() turns that ask
        # into a deny for Codex and the no-prompt modes.
        cwd = str(root) if cwd is _NOWHERE else cwd
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
                cur.append(_mkword([("fallback", tok)]))
        for argv in segs:
            _check_segment(root, cwd, argv, v, cmd, depth, ctx)
        return
    _check_archive_pipe([x for k, x in events if k == "seg"], v)
    start = None if cwd is _NOWHERE else (cwd or str(root))
    _walk(root, events, 0, frozenset([start]), v, cmd, depth, ctx)


def _run_in(state, S, F, pending, last_run):
    if S is None:
        return state
    return {"&&": S, "||": F, "|": last_run}.get(pending, S | F)


def _and_or(S, F, pending, s, f):
    if S is None:
        return s, f
    if pending == "&&":
        return s, F | f
    if pending == "||":
        return S | s, f
    return S | s, F | f


def _walk(root: Path, events: list, i: int, start: frozenset, v: Verdict, cmd: str, depth: int,
          ctx: "_Ctx", nested: bool = False) -> tuple:
    """Check events[i:] up to the matching `)` (or the end), starting in the
    set of possible working directories `start` (None: only known at run
    time). A `cd` moves the commands that can only run after it (`&&`); a
    command that runs whether or not the `cd` worked (`;`, `||`) is checked in
    both places, a subshell's `cd` and variables stay inside it, and a
    background list's `cd` never reaches the next command. A `)` with no
    open subshell (a `case` pattern) only separates commands.
    Returns (index after, directories after)."""
    state = list_start = start
    S = F = None
    pending, last_run, prev = None, start, None
    while i < len(events):
        kind, x = events[i]
        if kind == "op":
            if x == ")" and nested:
                return i + 1, (state if S is None else S | F)
            if x in ("&&", "||"):
                pending = x
            elif x in ("|", "|&"):
                pending = "|"
            elif x == "(":
                run = _run_in(state, S, F, pending, last_run)
                saved = dict(ctx.vars)
                i, _ = _walk(root, events, i + 1, run, v, cmd, depth, ctx, True)
                ctx.vars = saved
                S, F = _and_or(S, F, pending, run, run)
                last_run, pending, prev = run, None, None
                continue
            else:  # ; newline & ;; ;& ;;&
                end = state if S is None else S | F
                state = list_start if x == "&" else end
                list_start, S, F, pending, prev = state, None, None, None, None
            i += 1
            continue
        run = _run_in(state, S, F, pending, last_run)
        nxt = events[i + 1][1] if i + 1 < len(events) and events[i + 1][0] == "op" else None
        piped = pending == "|" or nxt in ("|", "|&")
        cond = pending in ("&&", "||") or piped or nxt == "&"
        s, f = _run_segment(root, x, run, v, cmd, depth, ctx, prev if pending == "|" else None,
                            piped, cond)
        S, F = _and_or(S, F, pending, s, f)
        last_run, pending, prev = run, None, x
        i += 1
    return i, (state if S is None else S | F)


def _run_segment(root: Path, argv: list, run: frozenset, v: Verdict, cmd: str, depth: int,
                 ctx: "_Ctx", upstream, piped: bool, cond: bool) -> tuple:
    """Check one simple command in every directory it can run in; returns the
    directories after it succeeds and after it fails."""
    if len(run) == 1:
        _check_segment(root, next(iter(run)), argv, v, cmd, depth, ctx, upstream)
    else:
        verdicts = []
        for c in sorted(run, key=lambda d: (d is None, d or "")):
            sub = Verdict()
            _check_segment(root, c, argv, sub, cmd, depth, ctx, upstream)
            verdicts.append(sub)
        for sub in verdicts:
            for r in sub.reasons:
                v.add(sub.level, r)
            for a in sub.advice:
                if a not in v.advice:
                    v.advice.append(a)
        if len({sub.level for sub in verdicts}) > 1 and ADVICE["cdfail"] not in v.advice:
            v.advice.append(ADVICE["cdfail"])
    res = _resolve(argv)
    one = next(iter(run)) if len(run) == 1 else None
    _track_vars(argv, res, one, ctx, cond)
    name = os.path.basename(str(res.argv[0])).lower() if res.argv else ""
    if res.argv and name not in _READONLY_PROGRAMS:
        ctx.mutated = True
    if name in ("cd", "pushd", "chdir", "popd"):
        after = frozenset(None if name == "popd" else _next_cwd(root, c, argv, ctx) for c in run)
        return (after | run if piped else after), run
    return run, run


def _track_vars(orig: list, res: "_Cmd", cwd: str | None, ctx: "_Ctx", cond: bool) -> None:
    """Variables the command sets for the words after it."""
    argv = res.argv
    name = os.path.basename(str(argv[0])).lower() if argv else ""
    if not argv:
        assigns = [w for w in orig if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", str(w)) and not _is_op(w)]
    elif name in ("export", "declare", "typeset", "local", "readonly"):
        assigns = [w for w in argv[1:] if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", str(w))]
    else:
        assigns = []
    for w in assigns:
        n = str(w).split("=", 1)[0]
        cands, _ = _word_values(_sub_word(w, len(n) + 1), cwd, ctx)
        ctx.assign(n, None if cands is None else [t for t, _p in cands], cond)
    if name == "for" and len(argv) >= 2 and _NAME.fullmatch(str(argv[1])):
        vals = [] if len(argv) > 2 and str(argv[2]) == "in" else None
        for w in (argv[3:] if vals is not None else []):
            cands, _ = _word_values(w, cwd, ctx)
            if cands is None:
                vals = None
                break
            for t, pat in cands:
                vals += (_glob(cwd or ".", pat) if pat else []) or [t]
        ctx.assign(str(argv[1]), vals, False)
    if name in ("read", "mapfile", "readarray", "getopts", "select"):
        for w in argv[1:]:
            if _NAME.fullmatch(str(w)):
                ctx.assign(str(w), None, False)
    if name == "unset":
        for w in argv[1:]:
            if _NAME.fullmatch(str(w)):
                ctx.assign(str(w), [""], cond)


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


def _next_cwd(root: Path, cur: str | None, argv: list, ctx: "_Ctx | None" = None) -> str | None:
    """Track `cd` / `pushd` across the segments of one command (M1), so
    `cd .git/hooks && echo x > pre-commit` is checked as a write to
    .git/hooks/pre-commit. None = moved somewhere only known at run time."""
    _, argv = _strip_prefix(argv)
    if not argv or os.path.basename(str(argv[0])).lower() not in ("cd", "pushd", "chdir"):
        return cur
    args = [a for a in _operands(argv[1:]) if str(a) not in ("-L", "-P", "-e", "-@", "--")]
    if not args:
        return os.path.expanduser("~")
    target = args[0]
    if cur is None or str(target) == "-" or re.fullmatch(r"[+-]\d+", str(target)):
        return None
    cands, _ = _word_values(target, cur, ctx)
    if not cands or len(cands) != 1:
        return None
    text, pat = cands[0]
    if pat is not None:
        found = _glob(cur, pat)
        if len(found) != 1:
            return None
        text = found[0]
    full = os.path.normpath(os.path.join(cur, text))
    return _through_links(full, cur, ctx) if ctx is not None else full


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

# v1.0 audit: the whole evaluation, git and tessctl subprocesses included,
# ends well inside the host hook timeout (120 s, of which run-pinned's anchor
# lookup may take up to 60 s before the gate starts). Out of time is an ask
# (a deny for Codex and the no-prompt modes), never an unchecked allow.
GATE_BUDGET = 40.0
MAX_COMMAND = 256 * 1024
_NOWHERE = "\0a working directory Tess cannot resolve"


def _tool_cwd(tin, cwd: str) -> str:
    """The directory a shell call runs in: the tool input's own working
    directory (Codex shell/exec `workdir`) when it names one, else the
    payload's cwd; _NOWHERE when it names one Tess cannot resolve."""
    if not isinstance(tin, dict):
        return cwd
    for k in ("workdir", "cwd", "directory", "working_directory"):
        val = tin.get(k)
        if val in (None, ""):
            continue
        if not isinstance(val, str) or re.search(r"[$`]", val):
            return _NOWHERE
        return os.path.normpath(os.path.join(cwd, os.path.expanduser(val)))
    return cwd


def evaluate(data: dict, root: Path) -> Verdict:
    v = Verdict()
    _STATE.update(deadline=time.monotonic() + GATE_BUDGET, interp={})
    try:
        _evaluate(data, root, v)
    except _GateTimeout:
        v.add(ASK, f"Tess could not finish checking this call within {int(GATE_BUDGET)} seconds "
                   "(a very long command, or git answering slowly), so it cannot say it is safe")
    finally:
        _STATE.update(deadline=None, interp={})
    return v


def _evaluate(data: dict, root: Path, v: Verdict) -> None:
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
        if len(cmd) > MAX_COMMAND:
            v.add(ASK, f"the command is {len(cmd)} characters long, more than Tess checks; split it "
                       "into smaller commands, or run it yourself")
        else:
            check_command(root, _tool_cwd(tin, cwd), cmd, v)
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
