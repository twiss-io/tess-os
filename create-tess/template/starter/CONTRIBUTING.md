# Contributing

Thanks for your interest in improving the Claude Code Starter Kit.

## Reporting Issues

Use [GitHub Issues](../../issues). Include:
- Claude Code version (`claude --version`)
- OS and environment (macOS, Linux, WSL2)
- Steps to reproduce
- Expected vs actual behavior

## Submitting Changes

1. Fork the repo
2. Create a branch from `main` (`git checkout -b feat/your-change`)
3. Make your changes
4. Run `pnpm test` to verify all tests pass
5. Run the `/review` slash command in Claude Code on every file you changed
6. Open a PR against `main`

## What's Welcome

- New slash commands (`.claude/commands/`)
- New skills (`.claude/skills/`)
- New hooks (`.claude/hooks/`)
- Documentation improvements
- Bug fixes
- Test coverage improvements

## What's NOT Welcome

- Framework-specific opinions — keep it stack-agnostic where possible
- Removing existing rules without discussion — open an issue first
- Large refactors without a prior issue/discussion

## Code Style

- TypeScript strict mode for all new files
- Follow the existing patterns in the project
- No file > 300 lines, no function > 50 lines
- Run `/review` before submitting your PR
- See `CLAUDE.md` for the full coding standards

## License

By contributing, you agree that your contributions will be licensed under the same license as this project (see [LICENSE](LICENSE)).

## Credit

Contributors are acknowledged in README.md and the [GitHub Pages site](https://thedecipherist.github.io/claude-code-mastery-project-starter-kit/).

## Context

This project implements patterns from the [Claude Code Mastery Guide](https://github.com/TheDecipherist/claude-code-mastery). Understanding V1-V5 helps explain why rules exist the way they do.
