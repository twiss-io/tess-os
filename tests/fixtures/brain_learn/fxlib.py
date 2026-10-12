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
        run(dest, "config", "user.email", "probe@example.invalid")  # the typing speaker is 'probe' (git_emails)
        run(dest, "config", "user.name", "probe")
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
    none = os.path.join(str(root), ".no-such-home")  # hermetic: never sweep the real ~/.codex or ~/.gemini
    e.setdefault("CODEX_HOME", none)
    e.setdefault("GEMINI_CLI_HOME", none)
    e.setdefault("CLAUDE_CONFIG_DIR", none)
    e.update(env or {})
    return subprocess.run([sys.executable, TESSBRAIN, "--root", str(root)] + [str(a) for a in args],
                          input=stdin, capture_output=True, text=True, env=e, timeout=timeout)


def sync_fixture(root, *extra):
    return cli(root, "sync", "--claude-dir", CLAUDE_DIR, "--codex-home", CODEX_HOME, "--also-cwd", CODEX_CWD, *extra)


def commit_all(root, msg="probe"):
    run(root, "add", "-A")
    return run(root, *GIT_ID, "commit", "-q", "--allow-empty", "-m", msg)


def claude_session(path, sid, turns, start_minute=0, cwd="/work/fx"):
    """Write a synthetic Claude transcript. turns: [(role, text)] with role in
    user | assistant | chan:<user_id> (a plugin-injected channel turn, never journaled). One minute apart,
    starting 2026-09-24T06:<start_minute>Z (14:<start_minute> SGT)."""
    import json as _json
    recs = []
    for i, (role, text) in enumerate(turns):
        ts = "2026-09-24T06:%02d:00.000Z" % (start_minute + i)
        base = {"sessionId": sid, "timestamp": ts, "cwd": cwd, "version": "2.1.281", "gitBranch": "main",
                "uuid": "u-%s-%d" % (sid[:4], i), "isSidechain": False}
        if role == "assistant":
            base.update(type="assistant", message={"role": "assistant", "content": [{"type": "text", "text": text}]})
        elif role.startswith("chan:"):
            uid = role[5:]
            body = ('<channel source="plugin:chat:chat" chat_id="-1" message_id="%d" user="u%s" '
                    'user_id="%s" ts="%s">%s</channel>' % (i, uid, uid, ts, text))
            base.update(type="user", isMeta=True, promptSource="system", message={"role": "user", "content": body})
        else:
            base.update(type="user", promptSource="typed", message={"role": "user", "content": text})
        recs.append(base)
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with open(str(path), "a", encoding="utf-8") as fh:
        for r in recs:
            fh.write(_json.dumps(r) + "\n")
    return path


def sync_dir(root, claude_dir, *extra, env=None):
    """sync against one Claude transcript dir, with no Codex/Gemini sweep."""
    none = os.path.join(str(root), ".no-such-home")
    return cli(root, "sync", "--claude-dir", str(claude_dir), "--codex-home", none, "--gemini-home", none,
               *extra, env=env)


def journal_of(root, sid):
    import glob
    hits = glob.glob(os.path.join(str(root), "brain", "journal", "*", "*", "*", "*-%s.md" % sid[:8]))
    return hits[0] if hits else None


def note(root, speaker, text, env=None):
    """`journal note --speaker`: how another principal's words enter in these tests (held for review)."""
    return cli(root, "--json", "journal", "note", "--speaker", speaker, "--text", text, env=env)
