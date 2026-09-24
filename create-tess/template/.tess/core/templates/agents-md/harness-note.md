This project's commands (`.tess/core/commands/**`) are rendered as Agent Skills at `.agents/skills/tess-<name>/SKILL.md` by the `codex` target — Codex, Gemini CLI, Cursor, Copilot CLI, OpenCode and Amp all read `.agents/skills/`. In Codex, run one with `$tess-<name>` or `/skills`; they are explicit-only (never picked implicitly). The `generic` target mirrors the same bodies as plain `prompts/<name>.md` for any other AGENTS.md-reading agent.

These are optional — read one only if invoked by name; this digest does not reproduce their contents (see the banner above for why it stays lean).
