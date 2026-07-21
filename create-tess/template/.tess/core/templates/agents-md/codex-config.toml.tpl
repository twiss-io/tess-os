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
