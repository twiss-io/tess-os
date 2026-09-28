# .codex/config.toml — Tess OS project-scoped Codex CLI defaults.
# Rendered by `tessctl render --target codex`. Regenerate, do not hand-edit
# (hand-edits are flagged as uncaptured drift by `tessctl doctor`/`verify`).
#
# Codex only loads a project-scoped .codex/config.toml for a project you have
# marked TRUSTED (openai/codex docs: "Codex loads project-scoped config files
# only when you trust the project"). An untrusted project ignores this file
# entirely, so these defaults can only ever NARROW behavior below whatever
# your own ~/.codex/config.toml already allows — never broaden it.
#
# Defaults below mirror Rule Zero / the Doctrine Gates hard floor rendered
# into AGENTS.md at this project's root: dispatch discipline, never solo
# destructive action, and a human-approval floor for anything ambiguous.
# Precedence (highest first): CLI flags > this file > --profile > ~/.codex/config.toml.

# on-request: Codex asks before anything it isn't confident is safe.
# ("on-failure" is deprecated upstream — use "on-request" for interactive
# runs or "never" for fully non-interactive runs; neither this project's
# doctrine nor its render target ever choose "never" as a shipped default.)
approval_policy = "on-request"

# workspace-write: filesystem writes are contained to the project workspace;
# no full-disk access. Network access and additional writable roots are
# sandbox_workspace_write.* keys — Codex requires those to live in your
# USER-level ~/.codex/config.toml, not a project-scoped file, so they are
# deliberately absent here (project config cannot broaden the sandbox).
sandbox_mode = "workspace-write"

# Second-brain hooks: onboarding and the learning loop (docs/brain/LEARNING.md).
# The same pinned scripts Claude Code runs from .claude/settings.json, each
# through .claude/hooks/run-pinned.py, which runs a script only when its sha256
# matches the release pinned by .tess/tess.lock (a changed or unpinned file is
# skipped with a warning, never run). Inline here, not in .codex/hooks.json, so
# a hooks.json you write stays yours (Codex merges both and warns).
#   SessionStart      onboarding question + the brain snapshot (what was learned)
#   UserPromptSubmit  notes the redacted prompt; a one-line nudge on a cue
#   Stop, SessionEnd  hand the transcript to a detached, locked sync (journal,
#                     cue pass, verifier, promote, index); they print {} (Codex
#                     expects JSON from Stop)
# No hook ever blocks a turn: every one exits 0, and a failure is a warning.
# Codex runs project hooks only in a TRUSTED project and only after you trust
# each hook in `/hooks` (trust is pinned to the hook's hash). Until then the
# "Second brain" block in AGENTS.md starts onboarding on its own and
# `tessbrain.py sync` (skill brain-save) sweeps ~/.codex/sessions for this
# project. Each command exits 0 silently when the launcher or python3 is missing.
[[hooks.SessionStart]]
matcher = "startup|resume|clear|compact"

[[hooks.SessionStart.hooks]]
type = "command"
command = "sh -c 'r=$(git rev-parse --show-toplevel 2>/dev/null || pwd); l=\"$r/.claude/hooks/run-pinned.py\"; [ -f \"$l\" ] && command -v python3 >/dev/null 2>&1 && exec python3 \"$l\" --on-fail warn --closure scripts/brain -- scripts/brain/onboard.py hook session-start --runtime codex || exit 0'"
timeout = 5
statusMessage = "Tess: checking onboarding"

[[hooks.SessionStart.hooks]]
type = "command"
command = "sh -c 'r=$(git rev-parse --show-toplevel 2>/dev/null || pwd); l=\"$r/.claude/hooks/run-pinned.py\"; [ -f \"$l\" ] && command -v python3 >/dev/null 2>&1 && exec python3 \"$l\" --on-fail warn --closure scripts/brain -- scripts/brain/tessbrain.py hook session-start --runtime codex || exit 0'"
timeout = 5
statusMessage = "Tess: loading the brain"

[[hooks.UserPromptSubmit]]

[[hooks.UserPromptSubmit.hooks]]
type = "command"
command = "sh -c 'r=$(git rev-parse --show-toplevel 2>/dev/null || pwd); l=\"$r/.claude/hooks/run-pinned.py\"; [ -f \"$l\" ] && command -v python3 >/dev/null 2>&1 && exec python3 \"$l\" --on-fail warn --closure scripts/brain -- scripts/brain/tessbrain.py hook prompt --runtime codex || exit 0'"
timeout = 5

[[hooks.Stop]]

[[hooks.Stop.hooks]]
type = "command"
command = "sh -c 'r=$(git rev-parse --show-toplevel 2>/dev/null || pwd); l=\"$r/.claude/hooks/run-pinned.py\"; [ -f \"$l\" ] && command -v python3 >/dev/null 2>&1 && exec python3 \"$l\" --on-fail warn --closure scripts/brain -- scripts/brain/tessbrain.py hook stop --runtime codex || { echo {}; exit 0; }'"
timeout = 30

[[hooks.SessionEnd]]

[[hooks.SessionEnd.hooks]]
type = "command"
command = "sh -c 'r=$(git rev-parse --show-toplevel 2>/dev/null || pwd); l=\"$r/.claude/hooks/run-pinned.py\"; [ -f \"$l\" ] && command -v python3 >/dev/null 2>&1 && exec python3 \"$l\" --on-fail warn --closure scripts/brain -- scripts/brain/tessbrain.py hook stop --runtime codex || { echo {}; exit 0; }'"
timeout = 30

# Tess safety gate (v1.0) — the Codex twin of the Claude Code PreToolUse hooks.
# One hook on every shell command (`Bash` covers shell and exec_command), file
# edit (`apply_patch`, also matched as Edit/Write), subagent spawn
# (`spawn_agent`, matched as Agent) and MCP tool call. It runs
# .claude/hooks/tess-gate.py through the sha-pinned launcher
# .claude/hooks/run-pinned.py with `--on-fail block`: a missing, edited or
# unpinned script BLOCKS the call instead of silently skipping the check.
# It blocks: secret-shaped values in commands and dispatches, edits to Tess's
# security-tier and enforcement files, `--no-verify` and core.hooksPath
# bypasses, `gh auth token`, and a push of brain/ or clients/ data to a public
# or unverifiable remote (the pre-push guard's own check). Codex cannot ASK
# from a hook (an "ask" fails the hook and runs the command), so force pushes,
# remote changes and visibility changes are DENIED with a message telling you
# to run them yourself.
# Codex runs it only in a TRUSTED project, after you trust it in `/hooks`;
# trust is pinned to this hook's hash, so re-approve after a Tess update.
# Backstop when the hook is not trusted yet: .codex/rules/tess.rules.
[[hooks.PreToolUse]]
matcher = "^(Bash|apply_patch|Edit|Write|Agent|spawn_agent|mcp__.*)$"

[[hooks.PreToolUse.hooks]]
type = "command"
command = "sh -c 'd=$(pwd -P); while [ \"$d\" != / ] && [ ! -f \"$d/.tess/tess.lock\" ]; do d=$(dirname \"$d\"); done; command -v python3 >/dev/null 2>&1 || { echo \"TESS GATE NOT RUN: python3 was not found, so the Tess safety check cannot run; this tool call is blocked.\" >&2; exit 2; }; [ -f \"$d/.claude/hooks/run-pinned.py\" ] || { echo \"TESS GATE NOT RUN: no Tess project (.tess/tess.lock with .claude/hooks/run-pinned.py) was found above $(pwd); this tool call is blocked. Start Codex inside your Tess project.\" >&2; exit 2; }; CLAUDE_PROJECT_DIR=\"$d\" exec python3 \"$d/.claude/hooks/run-pinned.py\" --on-fail block -- .claude/hooks/tess-gate.py --runtime codex'"
timeout = 120
statusMessage = "Tess: safety check"
