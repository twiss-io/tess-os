# Harness hardening (v0.2.1)

Three changes from the 2026-09-29 security review of the Claude Code harness,
what each one protects, and what it does not.

## 1. Hooks only run pinned scripts

Claude Code hooks run on their own: at session start, on every prompt and
around tool calls. Before v0.2.1 they executed whatever bytes were in
`.claude/hooks/*` and `scripts/brain/onboard.py`, and three hook lines pointed
at `scripts/brain/tessbrain.py`, a file that does not ship. Anything able to
write the working tree, an agent included, could change what runs, or create
`tessbrain.py` and have it run on every prompt.

Now every hook command in `.claude/settings.json` goes through
`.claude/hooks/run-pinned.py`. It runs a script only when the file exists, is
not a symlink, and its sha256 matches `.tess/tess.lock`:

| Script | Pinned by |
|---|---|
| `.claude/hooks/dispatch-guard.sh`, `task-lock-set.sh`, `task-lock-clear.sh`, `utc-local-context.sh` | their own tess.lock entries (`.tess/core/hooks/*`, tier security) |
| `.claude/hooks/run-pinned.py`, `.claude/hooks/vault-dispatch-scan.py`, `.claude/hooks/tess-gate.py` (the PreToolUse safety gate for Claude Code and Codex, v1.0), every `scripts/brain/**/*.py` | `.tess/core/pinned-scripts.sha256`, which tess.lock pins (tier security) |

For the onboarding hook the whole `scripts/brain` Python tree is checked, not
only `onboard.py`: it imports its siblings, and an extra file such as
`scripts/brain/json.py` would replace a standard-library module. Python hooks
run with `-I -B` and an empty bytecode cache, so a planted `.pyc` is never
loaded.

The launcher itself is started the same way (v1.0.1, 2026-09-29 Codex review).
Every hook command in `.claude/settings.json` and `.codex/config.toml` runs
`python3 -I -B .../run-pinned.py`, so `.claude/hooks/` is not on `sys.path`
and a planted `.claude/hooks/hashlib.py` or `json.py` cannot run while the
launcher loads. A caller that omits the flags is re-executed with them before
anything but `os` and `sys` is imported, and the launcher refuses to run while
any importable file other than `run-pinned.py`, `vault-dispatch-scan.py` and
`tess-gate.py` sits in `.claude/hooks/`. The root `./tessctl` wrapper and the
git hooks start the engine with `-I -B` for the same reason.

The engine's own fallback YAML reader, `.tess/vendor/yaml` (used when PyYAML
is not installed), loads only after every file matches a sha256 table written
into `.tess/bin/tessctl`. It is compiled in memory from the verified bytes,
`.tess/vendor` is never put on `sys.path`, and no `.pyc` is read or written.
`.tess/vendor/**` is in the security tier and every file there is pinned in
`tess.lock`.

If a check fails, the script does not run. Most hooks then show a warning and
let the session continue. The dispatch secret scan blocks the dispatch instead,
because its job is to block.

The hook lines for `tessbrain.py` are removed until that tool ships with its
own pinned entry.

`.claude/hooks/**`, `.tess/core/hooks/**`, `.claude/settings.json`,
`.tess/core/settings-core.json`, `.tess/core/pinned-scripts.sha256` and
`scripts/brain/**` are now in the `tess-os-security-tier-doctrine` policy
rule, so a change to any of them needs a covering signed verdict at the gate.

After a deliberate, reviewed change to a pinned script:

```bash
python3 .claude/hooks/run-pinned.py --regen-pins
./tessctl lock --regen --only .tess/core/pinned-scripts.sha256
```

What this does not do:

- `run-pinned.py` is the trust root. A tampered copy of it can skip its own
  checks; the gate rule above and `tessctl doctor` are what catch that.
- `tess.lock` is a committed file. Someone who can edit a script and
  `tess.lock` and get the change through the gate can re-pin it.
- A file swapped between the hash check and the interpreter reading it is
  not detected.
- `scripts/brain/**` has no `.tess/core` master, so `tessctl update` does not
  refresh it. After an update that changes `pinned-scripts.sha256`, the
  onboarding hook warns until `scripts/brain/` matches the release. Making
  `scripts/brain/` core-managed is a follow-up.

## 2. Agents are not pre-approved for arbitrary git commands

The shipped settings used to allow `Bash(git*)`. That lets an agent run,
without asking, `git commit --no-verify` or `git push --no-verify` (skipping
the publish-clean, public-remote and gate hooks), `git -c core.hooksPath=/dev/null
...` (the same thing another way), and `git push <any-url>` (sending the
repository somewhere no remote names).

The shipped allow list now covers read-only inspection only:

```
Bash(git status:*)  Bash(git branch --list:*)
```

Every other git command (commit, push, fetch, config, checkout, reset, ...)
goes through Claude Code's normal permission prompt, so the operator sees it
first. If you want broader rules on your own machine, put them in
`.claude/settings.local.json`, which is yours and never shipped.

`git diff`, `git log` and `git show` were removed from the allow list in the
v1.0 security review, round 2 (H-A). They accept `--output=<file>`, which
writes the command's output to ANY file: `git log -1
--format='#!/bin/sh%nexit 0' --output=.git/hooks/pre-push` wrote a working
hook that switched off the pre-push checks. Claude Code's `*` does match
mid-argument (`Bash(git log *)` matches `git log --output=x main`, per the
permissions docs), so the `deny` rules for `--output`, `--no-index`,
`--ext-diff` and `--textconv` are kept, but they cannot match git's
abbreviations (`--outp=x`), a `-C dir` or `--no-pager` before the
subcommand, or `format-patch -o`. The in-session gate (`tess-gate.py`)
parses the options and denies all of those; without the allow rules these
commands also go through the normal permission flow.

## 3. Dispatch locks live in a per-user directory

`dispatch-guard.sh` stays quiet while a dispatched subagent is working,
detected through lock files that `task-lock-set.sh` and `task-lock-clear.sh`
maintain. Those lived in `/tmp/tess-dispatch-locks`, which any local user or
process could create or write, and so silence the guard.

They now live in `${XDG_CACHE_HOME:-$HOME/.cache}/tess/dispatch-locks`,
created with mode 700. `dispatch-guard.sh` ignores the directory unless it is
owned by the current user and not writable by group or others, and ignores
lock files owned by anyone else. `TESS_LOCK_DIR` still overrides the location.

The dispatch secret scan (`vault-dispatch-scan.py`) now fails closed: if it
cannot read the tool call or errors while scanning, the dispatch is blocked
with a plain message instead of going through unscanned.
