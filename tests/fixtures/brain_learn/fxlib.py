"""Materialise a fixture Tess instance for the ws-learn tests and smokes.

    python3 tests/fixtures/brain_learn/fxlib.py make <dir> [--no-git]

Copies instance/ (START-HERE + two fictional entities) and brain.json into
<dir>, then `git init` + one commit so status/save have a baseline.
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GIT_ID = ["-c", "user.name=probe", "-c", "user.email=probe@example.invalid", "-c", "commit.gpgsign=false"]


def make(dest, git=True, brain_json=None):
    os.makedirs(dest, exist_ok=True)
    shutil.copytree(os.path.join(HERE, "instance", "brain"), os.path.join(dest, "brain"), dirs_exist_ok=True)
    shutil.copy(brain_json or os.path.join(HERE, "brain.json"), os.path.join(dest, "brain", "brain.json"))
    os.makedirs(os.path.join(dest, "memory", "projects"), exist_ok=True)
    if git:
        run(dest, "init", "-q", "-b", "main")
        run(dest, "add", "-A")
        run(dest, *GIT_ID, "commit", "-q", "-m", "fixture seed")
    return dest


def run(dest, *args):
    return subprocess.run(["git", "-C", dest] + list(args), check=True, capture_output=True, text=True)


def planted_github_token():
    """Built at run time so no secret-shaped literal is ever committed."""
    return "ghp_" + "Q" * 36


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "make":
        print(make(sys.argv[2], git="--no-git" not in sys.argv))
    else:
        print(__doc__)
        sys.exit(2)


REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
TESSBRAIN = os.path.join(REPO, "scripts", "brain", "tessbrain.py")
CLAUDE_DIR = os.path.join(HERE, "claude")
CODEX_HOME = os.path.join(HERE, "codexhome")
CODEX_CWD = "/tmp/tess-brain-fx"


def cli(root, *args, stdin=None, env=None, timeout=120):
    """Run tessbrain.py against an instance root; returns CompletedProcess."""
    e = dict(os.environ)
    e.setdefault("TESS_BRAIN_NO_BACKFILL", "1")
    e.update(env or {})
    return subprocess.run([sys.executable, TESSBRAIN, "--root", str(root)] + [str(a) for a in args],
                          input=stdin, capture_output=True, text=True, env=e, timeout=timeout)


def sync_fixture(root, *extra):
    return cli(root, "sync", "--claude-dir", CLAUDE_DIR, "--codex-home", CODEX_HOME, "--also-cwd", CODEX_CWD, *extra)


def commit_all(root, msg="probe"):
    run(root, "add", "-A")
    return run(root, *GIT_ID, "commit", "-q", "--allow-empty", "-m", msg)
