"""v1.0.0 final security review (Cyra, 2026-09-29), M1: Codex gate bypasses.

`.claude/hooks/tess-gate.py` allowed, before this fix: pointing git at another
config file through the environment (GIT_CONFIG_GLOBAL / GIT_CONFIG_SYSTEM),
writing a git include or alias, a shell write after `cd` into a protected
directory, and an inline interpreter program writing a protected file. Each
case below ran the REAL rendered Codex hook command and was allowed at
release/v1.0 @ 6f16a7f; each is denied now, and the allow cases stay allowed.
"""

from __future__ import annotations

import pytest

from test_codex_gate import _bash, _gate, proj  # noqa: F401 — `proj` is a fixture


@pytest.mark.parametrize("cmd", [
    "GIT_CONFIG_GLOBAL=/tmp/evil.gitconfig git commit -m x",
    "GIT_CONFIG_SYSTEM=/tmp/evil git push origin main",
    "env GIT_CONFIG_GLOBAL=/tmp/evil git commit -m x",
    "export GIT_CONFIG_GLOBAL=/tmp/evil",
    "GIT_CONFIG_PARAMETERS=\"'core.hookspath'='/dev/null'\" git commit -m x",
    "git config include.path /tmp/evil.gitconfig",
    "git config --global include.path /tmp/evil",
    "git config includeIf.gitdir:~/.path /tmp/evil",
    "git config alias.ci 'commit --no-verify'",
    "git config --local alias.st '!sh -c x'",
    "git -c include.path=/tmp/evil commit -m x",
    "git -c alias.ci='commit -n' ci -m x",
    "cd .git && echo x > config",
    "cd .git/hooks && echo 'exit 0' > pre-commit",
    "cd .git; rm -rf hooks",
    "cd .tess && rm tess.lock",
    "cd .tess/core && cp /tmp/x pinned-scripts.sha256",
    "cd .claude && echo '{}' > settings.json",
    "cd .claude/hooks; tee tess-gate.py < /dev/null",
    "cd \"$(git rev-parse --git-dir)\" && echo x > config",
    "python3 -c \"open('.tess/tess.lock','w').write('x')\"",
    "python3 -c \"from pathlib import Path; Path('.claude/settings.json').write_text('{}')\"",
    "python3 -c \"import os; os.remove('.git/hooks/pre-commit')\"",
    "python3 -c \"import pathlib; (pathlib.Path('.tess') / 'tess.lock').write_text('')\"",
    "node -e \"require('fs').writeFileSync('core/policy/policy.yaml', '')\"",
    "perl -e 'unlink \".git/hooks/pre-push\"'",
    "python3 - <<'EOF'\nfrom pathlib import Path\nPath('conductor/guardrails.md').write_text('')\nEOF",
])
def test_m1_bypasses_are_denied(proj, cmd):
    dec, why = _bash(proj, cmd)
    assert dec == "deny", cmd
    assert "What to do:" in why


@pytest.mark.parametrize("cmd", [
    "git config --get alias.ci",
    "git config --get-regexp '^include\\.'",
    "git config user.name 'A Person'",
    "GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 python3 -m pytest -q",
    "cd src && echo hi > out.txt",
    "cd src; cd ..; echo hi > src/out2.txt",
    "cd /tmp && echo hi > scratch.txt",
    "python3 -c \"print(open('.tess/tess.lock').read()[:10])\"",
    "python3 -c \"open('src/out.txt','w').write('x')\"",
    "node -e \"console.log(require('fs').readFileSync('AGENTS.md', 'utf8').length)\"",
    "python3 -m pytest -q",
    "cat .git/config",
])
def test_m1_normal_commands_stay_allowed(proj, cmd):
    assert _bash(proj, cmd) is None, cmd


def test_tess_core_policy_is_explicitly_protected():
    g = _gate()
    assert ".tess/core/policy/policy.yaml" in g.PROTECTED_GLOBS


# ---------------------------------------------------------------------------
# M2 — the read-only git allow rules must not pre-approve file reads/writes
# ---------------------------------------------------------------------------

import json  # noqa: E402
import re  # noqa: E402
from pathlib import Path  # noqa: E402

_REPO = Path(__file__).resolve().parent.parent
_SETTINGS = [_REPO / ".tess" / "core" / "settings-core.json", _REPO / ".claude" / "settings.json"]


def _rule_matches(rule: str, command: str) -> bool:
    """Claude Code's documented Bash rule match (code.claude.com/docs/en/permissions,
    "Wildcard patterns"): the whole command text, `*` = any text, a trailing
    `:*` = a trailing ` *`."""
    m = re.fullmatch(r"Bash\((.*)\)", rule)
    if not m:
        return False
    pat = m.group(1)
    if pat.endswith(":*"):
        pat = pat[:-2] + " *"
    rx = ".*".join(re.escape(part) for part in pat.split("*"))
    if pat.endswith(" *") and pat.count("*") == 1:
        rx = re.escape(pat[:-2]) + r"(?: .*)?"
    return re.fullmatch(rx, command, re.S) is not None


def _decision(perms: dict, command: str) -> str:
    for kind in ("deny", "ask", "allow"):
        if any(_rule_matches(r, command) for r in perms.get(kind, [])):
            return kind
    return "prompt"


@pytest.mark.parametrize("path", _SETTINGS, ids=["core", "live"])
@pytest.mark.parametrize("cmd", [
    "git diff --no-index /etc/passwd /dev/null",
    "git diff HEAD --no-index a b",
    "git diff --output=/tmp/x HEAD",
    "git diff HEAD --output /tmp/x",
    "git log -p --output=.git/hooks/pre-commit",
    "git show HEAD --output=CLAUDE.md",
    "git diff --ext-diff",
    "git log -p --ext-diff",
    "git show --textconv HEAD:secret.bin",
    "git diff --textconv",
])
def test_template_settings_deny_git_read_rule_escapes(path, cmd):
    perms = json.loads(path.read_text(encoding="utf-8"))["permissions"]
    assert _decision(perms, cmd) == "deny", cmd


@pytest.mark.parametrize("path", _SETTINGS, ids=["core", "live"])
@pytest.mark.parametrize("cmd,want", [
    # v1.0 security review round 2 (H-A): diff/log/show take --output=<file>
    # (and abbreviations the deny rules cannot list), so they are no longer
    # pre-approved; tess-gate.py parses their options.
    ("git diff", "prompt"), ("git diff --stat HEAD~1", "prompt"),
    ("git log --oneline -5", "prompt"), ("git show HEAD", "prompt"),
    ("git status", "allow"), ("git branch --list", "allow"),
])
def test_template_settings_pre_approve_only_git_reads_that_cannot_write(path, cmd, want):
    perms = json.loads(path.read_text(encoding="utf-8"))["permissions"]
    assert _decision(perms, cmd) == want, cmd
