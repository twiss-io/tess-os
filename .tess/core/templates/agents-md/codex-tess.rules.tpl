# .codex/rules/tess.rules — Tess OS command rules for Codex (v1.0).
# Rendered by `tessctl render --target codex`. Regenerate, do not hand-edit.
#
# A BACKSTOP, not the main guard. The main guard is the PreToolUse hook in
# .codex/config.toml (.claude/hooks/tess-gate.py), which reads the whole
# command. These rules match only a command PREFIX (the first words), so
# `git commit -m x --no-verify` slips past a rule that `git commit --no-verify`
# hits. They still help while the hook is untrusted or not yet approved in
# `/hooks`. Codex loads project rules only in a TRUSTED project and applies
# the most restrictive match (forbidden > prompt > allow).
# Check a command: codex execpolicy check --pretty --rules .codex/rules/tess.rules -- git push --no-verify

prefix_rule(
    pattern = ["git", ["commit", "push", "merge", "rebase", "am", "cherry-pick", "revert", "pull"], "--no-verify"],
    decision = "forbidden",
    justification = "--no-verify skips Tess's git hooks (secret scan, ship gate, public-remote guard). Commit without it and fix what the hook reports.",
    match = ["git commit --no-verify -m wip", "git push --no-verify origin main"],
    not_match = ["git commit -m wip"],
)

prefix_rule(
    pattern = ["git", "commit", "-n"],
    decision = "forbidden",
    justification = "git commit -n is --no-verify: it skips Tess's git hooks.",
    match = ["git commit -n -m wip"],
)

prefix_rule(
    pattern = ["git", "config", ["core.hooksPath", "core.hookspath", "--global", "--system", "--local", "--worktree", "--unset", "--replace-all", "--add"]],
    decision = "prompt",
    justification = "Changing git config (core.hooksPath in particular) can switch off Tess's git hooks.",
    match = ["git config core.hooksPath /dev/null", "git config --local core.hooksPath x"],
    not_match = ["git config --get user.email"],
)

prefix_rule(
    pattern = ["git", "-c"],
    decision = "prompt",
    justification = "A one-off git -c setting can point core.hooksPath elsewhere and skip Tess's git hooks.",
    match = ["git -c core.hooksPath=/dev/null commit -m x"],
)

prefix_rule(
    pattern = ["gh", "auth", "token"],
    decision = "forbidden",
    justification = "gh auth token prints your live GitHub token into the session. Use gh itself, or tessctl vault exec, instead.",
    match = ["gh auth token"],
)

prefix_rule(
    pattern = ["git", "remote", ["add", "set-url", "rename", "remove", "rm"]],
    decision = "prompt",
    justification = "Changing a remote changes where your brain and client data can be pushed.",
    match = ["git remote add public https://github.com/x/y.git", "git remote set-url origin x"],
    not_match = ["git remote -v"],
)

prefix_rule(
    pattern = ["gh", "repo", ["edit", "create", "rename", "delete", "archive"]],
    decision = "prompt",
    justification = "Repository create, visibility and rename changes decide who can see your data.",
    match = ["gh repo edit --visibility public", "gh repo create x --public"],
)

prefix_rule(
    pattern = ["git", "push", ["--force", "-f", "--force-with-lease", "--mirror"]],
    decision = "prompt",
    justification = "A force push can overwrite commits on the remote.",
    match = ["git push --force origin main", "git push -f"],
)
