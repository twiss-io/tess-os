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

# Onboarding at session start — the same scripts/brain/onboard.py hook Claude
# Code runs from .claude/settings.json, printing Codex's SessionStart
# shape ({"hookSpecificOutput": {"additionalContext": ...}}). Inline here, not
# in .codex/hooks.json, so a hooks.json you write stays yours (Codex merges
# both and warns). Codex runs project hooks only in a TRUSTED project and only
# after you trust each hook in `/hooks` (trust is pinned to the hook's hash).
# Until then the "Second brain" block in AGENTS.md starts onboarding on its
# own. The command exits 0 silently when the script or python3 is missing.
[[hooks.SessionStart]]
matcher = "startup|resume|clear|compact"

[[hooks.SessionStart.hooks]]
type = "command"
command = "sh -c 'r=$(git rev-parse --show-toplevel 2>/dev/null || pwd); f=\"$r/scripts/brain/onboard.py\"; [ -f \"$f\" ] && command -v python3 >/dev/null 2>&1 && exec python3 \"$f\" hook session-start --runtime codex || exit 0'"
timeout = 5
statusMessage = "Tess: checking onboarding"
