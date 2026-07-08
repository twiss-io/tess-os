This project's commands (`.tess/core/commands/**`) are mirrored 1:1 as
native custom-prompt files: `.codex/prompts/<name>.md` for Codex CLI
(rendered by the `codex` target — project-scoped prompt discovery isn't
shipped upstream yet, tracked `openai/codex#9848`; symlink `.codex/prompts/`
into `~/.codex/prompts/` to use them natively today) and `prompts/<name>.md`
for any other AGENTS.md-reading agent (Cursor, Copilot, Gemini CLI, Zed,
Devin — rendered by the `generic` target, no harness-specific frontmatter
assumed).

These are optional — read one only if invoked by name; this digest does not
reproduce their contents (see the banner above for why it stays lean).
