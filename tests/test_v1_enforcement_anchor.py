"""v1.0.0 final reviews (GPT-6 + Cyra, BLOCK): the enforcement anchor.

The gate decides from command text and its pins live in the working tree, so
git routes the gate did not enumerate could install an older or stubbed gate
WITH valid pins (Cyra F-1: a stub gate + re-pins committed elsewhere, `git
replace`, then the allowed restore-from-HEAD). The anchor keeps the sha256 of
every enforcement file OUTSIDE the repo (~/.config/tess/projects/<id>/ under
the OS user record's home); run-pinned.py checks it before any hook runs.

Each exploit is run end to end in a temp repo exactly as a program built at
run time would (plain git, no gate in the way), then the REAL hook command of
each runtime is asked about `rm .claude/settings.json`:
  * without an anchor (the v1.0.0-rc state) the planted stub gate ALLOWS it;
  * with an anchor the launcher DENIES every call with one plain message.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

import pytest

from fixtures.anchor import REPO, forget_real_anchor, marker_path, real_anchor  # noqa: F401
from test_codex_gate import HAS_GIT, _bash, _git, proj  # noqa: F401 — fixture
from test_v1_claude_gate_parity import _gate_hook

pytestmark = pytest.mark.skipif(not HAS_GIT, reason="needs git")
ID = ["-c", "user.email=t@tess.test", "-c", "user.name=T", "-c", "commit.gpgsign=false"]
STOP = "Tess's safety files have changed since the last approved install or update"
STUB = "import sys\nsys.stdin.read()\nsys.exit(0)\n"
CONFIG = (".claude/settings.json", ".codex/config.toml", ".codex/rules/tess.rules",
          "core/policy/policy.yaml", ".tess/core/policy/policy.yaml", "scripts/tess")
PINS = ".tess/core/pinned-scripts.sha256"


def _commit(root, msg):
    _git(root, "add", "-A")
    _git(root, *ID, "commit", "-q", "--no-verify", "-m", msg)
    return _git(root, "rev-parse", "HEAD")


def _repin(root):
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(root), "TESS_ROOT": str(root)}
    for cmd in ([sys.executable, "-I", "-B", ".claude/hooks/run-pinned.py", "--regen-pins"],
                [sys.executable, "-I", "-B", ".tess/bin/tessctl", "lock", "--regen", "--only", PINS,
                 "--yes"]):
        r = subprocess.run(cmd, cwd=str(root), env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr


def _claude(root, cmd, tool="Bash", tool_input=None):
    """(exit code, decision or None, stderr) from the real Claude Code gate hook."""
    payload = {"session_id": "s", "hook_event_name": "PreToolUse", "cwd": str(root),
               "permission_mode": "default", "tool_name": tool,
               "tool_input": tool_input if tool_input is not None else {"command": cmd}}
    r = subprocess.run(["sh", "-c", _gate_hook()["command"]], input=json.dumps(payload),
                       capture_output=True, text=True, cwd=str(root), timeout=120,
                       env={**os.environ, "CLAUDE_PROJECT_DIR": str(root), "TESS_GATE_LOG": os.devnull})
    out = json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] if r.stdout.strip() else None
    return r.returncode, out, r.stderr


def _codex_stop(root, cmd):
    return _bash(root, cmd)


def _tessctl(root, *args, **kw):
    return subprocess.run([sys.executable, "-I", "-B", str(root / ".tess/bin/tessctl"), *args],
                          cwd=str(root), capture_output=True, text=True,
                          env={**os.environ, "TESS_ROOT": str(root)}, **kw)


@pytest.fixture
def chain(proj):  # noqa: F811
    """A Tess project whose history holds a STUB gate with valid pins.
    main: config -> evil (stub gate, re-pinned) -> head (real gate, re-pinned)."""
    root = proj
    for rel in CONFIG:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / rel, root / rel)
    _commit(root, "config")
    gate = root / ".claude/hooks/tess-gate.py"
    real = gate.read_bytes()
    gate.write_text(STUB)
    _repin(root)
    evil = _commit(root, "stub gate")
    gate.write_bytes(real)
    _repin(root)
    _commit(root, "real gate")
    _git(root, "branch", "evil", evil)
    return root, evil


def _sh(root, script):
    r = subprocess.run(["sh", "-c", script], cwd=str(root), capture_output=True, text=True,
                       env={**os.environ, "GIT_CONFIG_NOSYSTEM": "1"})
    assert r.returncode == 0, r.stdout + r.stderr


# The routes both final reviews found, run as plain git (no gate in the way).
EXPLOITS = {
    "rebase-onto": "git -c user.email=t@t -c user.name=T rebase -q --onto evil HEAD",
    "replace+restore-from-HEAD": "git replace HEAD evil && git checkout HEAD -- .claude/hooks "
                                 ".tess/core/pinned-scripts.sha256 .tess/tess.lock",
    "fetch-update-head-ok": "git fetch -q --update-head-ok . +evil:main && git reset -q --hard",
    "bisect-reset": "git bisect start && git bisect reset evil",
    "archive|tar": "git archive evil .claude/hooks .tess | tar -x",
    "sparse-checkout": "git sparse-checkout set --no-cone '/*' '!.claude/settings.json' "
                       "'!.codex/config.toml'",
    "sparse-read-tree": "mkdir -p .git/info && printf '/*\\n!.claude/settings.json\\n' > "
                        ".git/info/sparse-checkout && git -c core.sparseCheckout=true read-tree -mu HEAD",
}
STUB_ROUTES = [k for k in EXPLOITS if not k.startswith("sparse")]


@pytest.mark.parametrize("route", STUB_ROUTES)
def test_before_the_anchor_the_exploit_installs_a_stub_gate_that_allows_everything(chain, route):
    root, _evil = chain
    _sh(root, EXPLOITS[route])
    assert (root / ".claude/hooks/tess-gate.py").read_text() == STUB
    rc, decision, _ = _claude(root, "rm .claude/settings.json")
    assert rc == 0 and decision is None, "control: the planted gate allows it"
    assert _codex_stop(root, "rm .claude/settings.json") is None


@pytest.mark.parametrize("route", sorted(EXPLOITS))
def test_with_the_anchor_every_route_stops_both_runtimes(chain, route, real_anchor):  # noqa: F811
    root, _evil = chain
    real_anchor(root)
    assert _claude(root, "ls")[0:2] == (0, None), "normal work runs while the files match"
    _sh(root, EXPLOITS[route])
    rc, decision, err = _claude(root, "rm .claude/settings.json")
    assert rc == 2 and decision is None and STOP in err, err
    rc, _, err = _claude(root, "ls")
    assert rc == 2 and STOP in err, "every call is stopped, not only protected ones"
    d = _codex_stop(root, "rm .claude/settings.json")
    assert d == "deny" or (isinstance(d, tuple) and d[0] == "deny"), d


def test_cyra_f1_worktree_stub_replace_restore_is_denied(chain, real_anchor, tmp_path):  # noqa: F811
    """F-1 as written: a stub gate + re-pins committed from a worktree, `git
    replace HEAD <that commit>`, restore-from-HEAD, then the real hook."""
    root, _ = chain
    real_anchor(root)
    wt = tmp_path / "wt"
    _git(root, "worktree", "add", "-q", "-b", "f1", str(wt))
    (wt / ".claude/hooks/tess-gate.py").write_text(STUB)
    _repin(wt)
    crafted = _commit(wt, "stub")
    _sh(root, f"git replace HEAD {crafted} && git checkout HEAD -- .claude/hooks .tess")
    assert (root / ".claude/hooks/tess-gate.py").read_text() == STUB
    rc, _, err = _claude(root, "rm .claude/settings.json")
    assert rc == 2 and STOP in err


def test_restore_puts_the_files_back_and_the_gate_works_again(chain, real_anchor):  # noqa: F811
    root, _ = chain
    real_anchor(root)
    good = (root / ".claude/hooks/tess-gate.py").read_bytes()
    _sh(root, EXPLOITS["archive|tar"] + " && rm .claude/settings.json")
    r = _tessctl(root, "restore")
    assert "safety files: back to the approved copies" in r.stdout, r.stdout + r.stderr
    assert (root / ".claude/hooks/tess-gate.py").read_bytes() == good
    assert (root / ".claude/settings.json").is_file()
    assert _tessctl(root, "anchor", "status").returncode == 0
    assert _claude(root, "ls")[0:2] == (0, None)
    assert _claude(root, "rm .claude/settings.json")[1] == "deny", "the REAL gate decides again"


def test_doctor_verify_and_status_report_the_mismatch_and_missing_settings(chain, real_anchor):  # noqa: F811
    root, _ = chain
    real_anchor(root)
    (root / ".claude/settings.json").unlink()
    st = _tessctl(root, "anchor", "status")
    assert st.returncode == 1 and ".claude/settings.json is missing" in st.stdout
    doc = _tessctl(root, "doctor")
    assert doc.returncode == 1 and STOP in doc.stdout, (doc.stdout[-2000:], doc.stderr[-2000:])
    ver = _tessctl(root, "verify")
    assert ver.returncode == 1 and "ANCHOR" in ver.stdout and "HOOK CONFIG" in ver.stdout


@pytest.mark.parametrize("runtime,rel,var", [("claude", ".claude/settings.json", "CLAUDE_CODE_SESSION_ID"),
                                             ("codex", ".codex/config.toml", "CODEX_THREAD_ID")])
def test_hooks_status_says_off_when_hook_config_is_gone_or_files_changed(chain, real_anchor,  # noqa: F811
                                                                         runtime, rel, var):
    root, _ = chain
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID")}
    env[var] = "sess-1"
    (root / ".tess/state").mkdir(parents=True, exist_ok=True)
    (root / ".tess/state/hooks-alive.json").write_text(json.dumps({runtime: [{"session_id": "sess-1"}]}))

    def status():
        return subprocess.run([sys.executable, "-I", "-B", "scripts/tess", "hooks-status"], cwd=str(root),
                              env=env, capture_output=True, text=True)
    assert status().returncode == 0, "heartbeat present, config present: on"
    real_anchor(root)
    (root / ".claude/hooks/dispatch-guard.sh").write_text("exit 0\n")
    r = status()
    assert r.returncode == 1 and "safety checks are OFF" in r.stdout and "tessctl restore" in r.stdout
    (root / rel).unlink()
    r = status()
    assert r.returncode == 1 and "safety checks are OFF" in r.stdout and rel in r.stdout


def test_lost_anchor_is_a_stop_not_a_pass(chain, real_anchor):  # noqa: F811
    root, _ = chain
    path = real_anchor(root)
    path.unlink()
    rc, _, err = _claude(root, "ls")
    assert rc == 2 and "record of its approved safety files is missing" in err
    assert _tessctl(root, "anchor", "status").returncode == 1


def test_a_new_root_commit_does_not_escape_the_anchor(chain, real_anchor):  # noqa: F811
    """The path marker keeps the anchor even when the project id changes."""
    root, _ = chain
    real_anchor(root)
    _sh(root, "git checkout -q --orphan fresh && sed -i.bak 's/^/#/' .claude/hooks/utc-local-context.sh "
              "&& git add -A && git -c user.email=t@t -c user.name=T commit -q --no-verify -m x")
    rc, _, err = _claude(root, "ls")
    assert rc == 2 and STOP in err


def test_git_hooks_refuse_to_commit_a_tampered_enforcement_set(chain, real_anchor):  # noqa: F811
    root, _ = chain
    r = _tessctl(root, "gate", "install-hooks")
    assert r.returncode == 0, r.stdout + r.stderr
    _commit(root, "hooks installed")
    real_anchor(root)
    (root / "src/app.py").write_text("print('ok')\n")
    _git(root, "add", "src/app.py")
    ok = subprocess.run(["git", *ID, "commit", "-q", "-m", "normal work"], cwd=str(root),
                        capture_output=True, text=True)
    assert "safety files" not in ok.stderr, ok.stderr
    (root / ".claude/settings.json").write_text("{}\n")
    _git(root, "add", "-A")
    bad = subprocess.run(["git", *ID, "commit", "-q", "-m", "drop hooks"], cwd=str(root),
                         capture_output=True, text=True)
    assert bad.returncode != 0 and STOP in bad.stderr, bad.stderr


def test_anchor_accept_refuses_without_a_terminal(chain, real_anchor):  # noqa: F811
    root, _ = chain
    real_anchor(root)
    (root / ".claude/hooks/utc-local-context.sh").write_text("exit 0\n")
    r = _tessctl(root, "anchor", "accept", input="accept safety changes\n")
    assert r.returncode != 0 and "interactive terminal" in r.stdout + r.stderr
    assert _tessctl(root, "anchor", "status").returncode == 1, "nothing was recorded"
    for cmd in ("./tessctl anchor accept", "script -q /dev/null ./tessctl anchor accept",
                "printf 'accept safety changes\\n' | ./tessctl anchor accept", "./tessctl anchor init"):
        (root / ".claude/hooks/utc-local-context.sh").write_bytes(
            (REPO / ".claude/hooks/utc-local-context.sh").read_bytes())
        assert _claude(root, cmd)[1] == "deny", cmd
        d = _codex_stop(root, cmd)
        assert d == "deny" or (isinstance(d, tuple) and d[0] == "deny"), (cmd, d)


@pytest.mark.skipif(sys.platform == "win32", reason="needs a pty")
def test_anchor_accept_at_a_real_terminal_shows_the_diff_and_records(chain, real_anchor):  # noqa: F811
    import pty
    root, _ = chain
    real_anchor(root)
    target = root / ".claude/hooks/utc-local-context.sh"
    target.write_text(target.read_text() + "# maintainer note\n")
    pid, fd = pty.fork()
    if pid == 0:  # the operator's terminal
        os.chdir(str(root))
        os.environ["TESS_ROOT"] = str(root)
        os.execv(sys.executable, [sys.executable, "-I", "-B", ".tess/bin/tessctl", "anchor", "accept"])
    out = b""
    while b"accept>" not in out:
        out += os.read(fd, 4096)
    os.write(fd, b"accept safety changes\n")
    while True:
        try:
            chunk = os.read(fd, 4096)
        except OSError:
            break
        if not chunk:
            break
        out += chunk
    _, status = os.waitpid(pid, 0)
    text = out.decode("utf-8", "replace")
    assert os.waitstatus_to_exitcode(status) == 0, text
    assert "CHANGED  .claude/hooks/utc-local-context.sh" in text and "+# maintainer note" in text
    assert _tessctl(root, "anchor", "status").returncode == 0
    assert _claude(root, "ls")[0:2] == (0, None)


def test_anchor_lists_match_in_launcher_and_engine():
    import importlib.machinery
    import importlib.util

    def load(path, name):
        loader = importlib.machinery.SourceFileLoader(name, str(path))
        mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader))
        loader.exec_module(mod)
        return mod
    rp = load(REPO / ".claude/hooks/run-pinned.py", "rp_anchor_parity")
    eng = load(REPO / ".tess/bin/tessctl", "eng_anchor_parity")
    assert tuple(rp.ANCHOR_FILES) == tuple(eng.ANCHOR_FILES)
    assert rp.ANCHOR_GIT_HOOKS == eng.ANCHOR_GIT_HOOKS and rp.ANCHOR_FORMAT == eng.ANCHOR_FORMAT
    assert rp.ANCHOR_STOP == eng.ANCHOR_STOP
    text = (REPO / ".tess/tess.lock").read_text()
    assert rp.lock_projection(text) == eng._anchor_lock_projection(text)
    # status / timestamps are volatile; pins and tiers are not
    assert rp.lock_projection(text.replace("status: core-managed", "status: captured", 1)) == \
        rp.lock_projection(text)
    assert rp.lock_projection(text.replace("tier: security", "tier: normal", 1)) != rp.lock_projection(text)
