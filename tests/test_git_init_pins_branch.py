"""Every test fixture that runs `git init` names its initial branch.

CI regression (v1.0 code review, CRITICAL): tests/test_codex_gate.py ran a bare
`git init` and then relied on the branch being `main`. On a machine or runner
whose git has `init.defaultBranch` set to anything else (`master` is git's own
built-in default when the key is unset), the fixture's `main` does not exist
and every test that pushes, diffs or checks out `main` fails -- all four CI
pytest jobs went red. The fix is `git init -b main` at every call site. This
test keeps it that way: a new fixture that calls `git init` without `-b` /
`--initial-branch` fails here, before it fails on somebody else's git config.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCAN = [(REPO / "tests", ("*.py", "*.sh")), (REPO / "create-tess" / "test", ("*.js", "*.mjs"))]

# A `git init` invocation, in the call shapes this suite uses:
#   _git(x, "init", ...), git("init"), g("init", ...), ["git", "init", ...],
#   g + ["init", ...], (("init", "-q"), ...) arg tuples, spawnSync('git', ['init', ...]),
#   and shell `git init`.
INIT_CALL = re.compile(
    r"""\b(?:_git|git|g)\((?:[^()"]*?,\s*)?"init"\s*[,)]"""
    r"""|\[\s*"git",\s*"init\""""
    r"""|\[\s*"init"\s*,\s*"-q\""""
    r"""|\(\s*"init"\s*,\s*"-q"\s*\)"""
    r"""|'git',\s*\[\s*'init'"""
)
SH_INIT = re.compile(r"""(?:^|[;&|(]\s*)git init\b""")  # shell scripts only
PINNED = re.compile(r"""["']-b["']|\s-b\s|--initial-branch""")


def _offenders():
    bad = []
    for base, globs in SCAN:
        for g in globs:
            for p in sorted(base.rglob(g)):
                if p.name == Path(__file__).name or "node_modules" in p.parts:
                    continue
                for n, line in enumerate(p.read_text(errors="replace").splitlines(), 1):
                    s = line.strip()
                    if s.startswith(("#", "//", "*")) or "`git init`" in line:
                        continue
                    rx = SH_INIT if p.suffix == ".sh" else INIT_CALL
                    if rx.search(s) and not PINNED.search(s):
                        bad.append("%s:%d: %s" % (p.relative_to(REPO), n, s))
    return bad


def test_every_git_init_in_the_suite_names_its_branch():
    bad = _offenders()
    assert not bad, (
        "git init without -b <branch> depends on the host's init.defaultBranch; "
        "use `git init -b main`:\n  " + "\n  ".join(bad))


def test_the_scanner_catches_the_original_bug(tmp_path):
    # The exact line that turned CI red must be flagged; its fix must not be.
    assert INIT_CALL.search('        _git(tmp_path, "init", "-q", str(root))')
    assert not PINNED.search('        _git(tmp_path, "init", "-q", str(root))')
    assert PINNED.search('        _git(tmp_path, "init", "-b", "main", "-q", str(root))')
    assert INIT_CALL.search('    subprocess.run(["git", "init", "-q", "--bare", str(bare)])')
    assert SH_INIT.search('rm -rf "$S/p.git"; git init -q --bare "$S/p.git"')
    assert INIT_CALL.search("spawnSync('git', ['init', '-q', snap])")
    # Not git: tessctl/onboard subcommands named "init" and commit messages.
    assert not INIT_CALL.search('    r = run_cli(project.root, "init", "--from", "x")')
    assert not INIT_CALL.search('    h.onboard(root, "init", "--non-interactive")')
    assert not INIT_CALL.search('    _git(root, "commit", "-q", "-m", "init")')
