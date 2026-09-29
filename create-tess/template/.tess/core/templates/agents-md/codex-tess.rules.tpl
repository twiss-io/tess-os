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

# Security review round 2 (M-2, H-A, H-B). git accepts any unique prefix of a
# long option, so the common abbreviations are listed too. A prefix rule
# matches whole words only: `--output=x` is not the word `--output`, which is
# why the PreToolUse hook (which parses every option) stays the main guard.
prefix_rule(
    pattern = ["git", ["commit", "push", "merge", "rebase", "am", "cherry-pick", "revert", "pull"], ["--no-verif", "--no-veri", "--no-ver"]],
    decision = "forbidden",
    justification = "An abbreviation of --no-verify still skips Tess's git hooks.",
    match = ["git commit --no-veri -m wip", "git push --no-ver origin main"],
    not_match = ["git commit -m wip"],
)

prefix_rule(
    pattern = ["git", "push", ["--forc", "--for", "--mirro", "--mirr", "--mir", "--delete", "--delet", "--dele", "--del", "-d", "--prune"]],
    decision = "prompt",
    justification = "A force push, mirror or remote delete can overwrite or remove commits on the remote.",
    match = ["git push --forc origin main", "git push --delete origin old"],
    not_match = ["git push origin main"],
)

prefix_rule(
    pattern = ["git", ["diff", "log", "show", "format-patch", "whatchanged", "archive"], ["--output", "--outp", "--out", "--output-directory", "-o", "--no-index", "--ext-diff", "--textconv"]],
    decision = "forbidden",
    justification = "These git options write the output to a file (any file, Tess's hooks included) or run an external program. Let git print to the terminal instead.",
    match = ["git log --output .git/hooks/pre-push", "git diff --no-index a b", "git format-patch -o out"],
    not_match = ["git log --oneline", "git diff --stat"],
)

prefix_rule(
    pattern = ["git", "update-ref"],
    decision = "prompt",
    justification = "update-ref can forge a remote-tracking ref (refs/remotes/...), which records what a remote already holds.",
    match = ["git update-ref refs/remotes/origin/x HEAD"],
)

prefix_rule(
    pattern = ["git", "config", ["tess.privateRemote", "tess.privateremote", "set"]],
    decision = "prompt",
    justification = "tess.privateRemote tells the public-remote guard a remote is private; only the operator should set it.",
    match = ["git config tess.privateRemote https://github.com/x/y.git"],
    not_match = ["git config --get user.email"],
)

# v1.0.0 final reviews (#224). Git routes that can put an older or different
# copy of Tess's safety files in place. The PreToolUse hook judges most of
# these by what they would change and is the main guard; these rules catch
# the plain spellings before the hook runs. Env-var forms
# (GIT_REPLACE_REF_BASE=...) and `--onto=x` are not separate words, so only
# the hook and the enforcement anchor cover them.
prefix_rule(
    pattern = ["git", "replace"],
    decision = "forbidden",
    justification = "git replace makes git show a different commit in place of the real one, so a check or undo can read old safety files. Tess never needs it.",
    match = ["git replace HEAD evil", "git replace --graft HEAD", "git replace -d 0123456"],
    not_match = ["git rebase main"],
)

prefix_rule(
    pattern = ["git", "sparse-checkout", ["set", "add", "init", "reapply", "disable"]],
    decision = "forbidden",
    justification = "A sparse checkout can hide Tess's safety files from the working tree. `git sparse-checkout list` is fine.",
    match = ["git sparse-checkout set --no-cone /*", "git sparse-checkout init --no-cone", "git sparse-checkout add x", "git sparse-checkout disable"],
    not_match = ["git sparse-checkout list"],
)

prefix_rule(
    pattern = ["git", "fetch", ["--update-head-ok", "--update-head-o", "--update-head-", "--update-head", "--update-hea", "--update-he", "--update-h", "-u"]],
    decision = "forbidden",
    justification = "fetch --update-head-ok lets a fetch overwrite the checked-out branch, replacing the files under you without a checkout.",
    match = ["git fetch --update-head-ok . +evil:main", "git fetch -u . +evil:main", "git fetch --update-he . evil:main"],
    not_match = ["git fetch origin", "git fetch --all --prune"],
)

prefix_rule(
    pattern = ["git", "bisect", ["start", "good", "bad", "new", "old", "skip", "reset", "run", "replay"]],
    decision = "prompt",
    justification = "git bisect checks out other commits, which can put older safety files in place. `git bisect log` and `view` are fine.",
    match = ["git bisect start evil main", "git bisect reset evil", "git bisect run make test"],
    not_match = ["git bisect log"],
)

prefix_rule(
    pattern = ["git", "rebase", ["--onto", "--ont"]],
    decision = "prompt",
    justification = "rebase --onto can rebuild your branch on an old commit and drop the changes that set up Tess's safety files.",
    match = ["git rebase --onto evil main", "git rebase --onto 0123456 HEAD"],
    not_match = ["git rebase main", "git rebase --continue"],
)
