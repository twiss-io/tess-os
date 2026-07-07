The 26 commands below are also mirrored 1:1 from `.tess/core/commands/**` as
native custom-prompt files, in two locations (both rendered from this same
project, regardless of which agent is reading this file):

- **Codex CLI**: `.codex/prompts/<name>.md` (rendered by the `codex` render
  target). Codex's custom-prompt loader currently reads only
  `$CODEX_HOME/prompts` (defaults to `~/.codex/prompts/`) — project-scoped
  prompt discovery is not yet shipped upstream (tracked: `openai/codex#9848`).
  Until it lands, symlink or copy this project's `.codex/prompts/` into
  `~/.codex/prompts/` to use them as native `/name` prompts today.
- **Any other AGENTS.md-reading agent** (Cursor, GitHub Copilot, Gemini CLI,
  Zed, Devin, or a bare-standard reader): `prompts/<name>.md` (rendered by
  the `generic` render target) — a plain, tool-agnostic mirror with no
  harness-specific frontmatter conventions assumed.

Whether or not your harness auto-loads either directory as native slash
commands, you can always run a command by reading its file directly and
following its instructions — this file (and the files it points to) is
documentation an agent reads, not a registry every harness executes natively.
