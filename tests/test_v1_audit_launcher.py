"""v1.0.0 security audit (Cloudflare method, run 1 @ 3eba77d): the hash-pinned launcher.

  F7 scripts/brain/brainlib/githooks.py:BLOCKS:unpinned-working-tree-exec
  F8 run-pinned.anchor_locate:hidden-store-reads-as-never-anchored
  F9 run-pinned.py:_lock_entries/line-scanner-vs-lock_projection-volatile-multiline-pin-override
  and the earlier finding that tests/conftest.py read and deleted under the real ~/.config/tess.

Every test here fails on 3eba77d and passes with the fix.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from fixtures.anchor import write_real_anchor
from fixtures.brain_learn import fxlib
from fixtures.os_home import use_os_home

REPO = Path(__file__).resolve().parents[1]
LAUNCHER = REPO / ".claude" / "hooks" / "run-pinned.py"
GIT_ID = ["-c", "user.name=probe", "-c", "user.email=probe@example.invalid", "-c", "commit.gpgsign=false"]


def _launcher():
    spec = importlib.util.spec_from_file_location("run_pinned_audit", str(LAUNCHER))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def pinned(tmp_path):
    """A brain instance holding the pinned tree (launcher, lock, pin list, scripts/brain)."""
    root = tmp_path / "inst"
    for rel in (".claude/hooks/run-pinned.py", ".tess/tess.lock", ".tess/core/pinned-scripts.sha256"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / rel, root / rel)
    shutil.copytree(REPO / "scripts/brain", root / "scripts/brain", ignore=shutil.ignore_patterns("__pycache__"))
    fxlib.make(str(root))
    return root


def _env(root, **extra):
    e = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
    none = str(root / ".no-such-home")
    e.update(TESS_BRAIN_NO_BACKFILL="1", CODEX_HOME=none, GEMINI_CLI_HOME=none, CLAUDE_CONFIG_DIR=none)
    e.update(extra)
    return e


def _hook(root, *args):
    return subprocess.run([sys.executable, "-I", "-B", str(root / ".claude/hooks/run-pinned.py"), "--on-fail", "warn",
                           "--closure", "scripts/brain", "--", "scripts/brain/tessbrain.py", *args],
                          cwd=str(root), capture_output=True, text=True, env=_env(root, CLAUDE_PROJECT_DIR=str(root)),
                          timeout=120)


# F9: one reader of tess.lock ---------------------------------------------------------------------------

def _hide_a_pin(root: Path, rel: str, sha: str) -> str:
    """The audit's shape: fake `live_path:` / `base_sha:` lines inside a multi-line quoted VOLATILE field."""
    lock = root / ".tess/tess.lock"
    text = lock.read_text()
    old = "    live_path: null\n    last_updated: '2026-09-28T17:49:44.108190Z'\n"
    assert old in text
    new = ("    live_path: null\n    last_updated: '2026-09-28T17:49:44.108190Z\n"
           "    live_path: %s\n    base_sha: sha256:%s'\n" % (rel, sha))
    lock.write_text(text.replace(old, new, 1))
    return text


def test_f9_a_pin_hidden_in_a_volatile_lock_value_does_not_replace_a_brain_module_pin(pinned):
    rp = _launcher()
    target = pinned / "scripts/brain/brainlib/cues.py"
    with open(target, "a") as fh:
        fh.write("\nopen(__file__ + '.PWNED', 'w').write('ran')\n")
    before = _hide_a_pin(pinned, "scripts/brain/brainlib/cues.py", hashlib.sha256(target.read_bytes()).hexdigest())
    after = (pinned / ".tess/tess.lock").read_text()
    rp.lock_strict_tree(after)  # still the strict form ...
    assert rp.lock_projection(after) == rp.lock_projection(before)  # ... and the anchored digest is unchanged
    want = next(line.split()[0] for line in (pinned / ".tess/core/pinned-scripts.sha256").read_text().splitlines()
                if line.endswith(" scripts/brain/brainlib/cues.py"))
    entries = rp._lock_entries(pinned)
    assert rp._expected("scripts/brain/brainlib/cues.py", entries, rp._pins(pinned, entries)) == want
    r = _hook(pinned, "status")
    assert "TESS HOOK NOT RUN" in r.stderr and "cues.py" in r.stderr, r.stdout + r.stderr
    assert not Path(str(target) + ".PWNED").exists()


def test_f9_the_lock_reader_matches_the_strict_reader_on_the_shipped_lock():
    rp = _launcher()
    entries = rp._lock_entries(REPO)
    tree = rp.lock_strict_tree((REPO / ".tess/tess.lock").read_text())
    assert set(entries) == set(tree["files"])
    pins = rp._pins(REPO, entries)
    assert rp._expected(".claude/hooks/run-pinned.py", entries, pins) == hashlib.sha256(LAUNCHER.read_bytes()).hexdigest()


# F8: a recorded anchor never reads as "never anchored" -------------------------------------------------

@pytest.fixture
def anchored(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    use_os_home(monkeypatch, home)
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "README.md").write_text("x\n")
    for args in (["init", "-q", "-b", "main"], ["add", "-A"], GIT_ID + ["commit", "-q", "-m", "seed"]):
        subprocess.run(["git", "-C", str(proj)] + args, check=True, capture_output=True)
    write_real_anchor(proj)
    return proj, home


def test_f8_the_first_hook_records_that_the_checkout_is_anchored(anchored):
    proj, _ = anchored
    rp = _launcher()
    assert rp.anchor_check(proj) is not None
    assert rp.anchor_path_key(proj) in (proj / ".git/info/tess-anchored").read_text().split()


def test_f8_hiding_the_anchor_store_is_a_stop_not_a_pass(anchored):
    proj, home = anchored
    rp = _launcher()
    rp.anchor_check(proj)  # a hook ran after the install
    (home / ".config").rename(home / ".config.off")  # `mv ~/.config ~/.config.off`
    with pytest.raises(rp.AnchorError) as exc:
        rp.anchor_check(proj)
    assert "put it back" in str(exc.value) and "anchor accept" in str(exc.value)
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(proj))
    r = subprocess.run([sys.executable, "-I", "-B", str(LAUNCHER), "--on-fail", "block", "--", "x.py"],
                       capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 2 and "TESS STOPPED" in r.stderr, r.stderr


def test_f8_an_unreadable_anchor_store_is_a_stop(anchored):
    proj, home = anchored
    rp = _launcher()
    os.chmod(str(home / ".config"), 0)  # `chmod 000 ~/.config`
    try:
        with pytest.raises(rp.AnchorError):
            rp.anchor_check(proj)
    finally:
        os.chmod(str(home / ".config"), 0o700)


def test_f8_a_checkout_that_was_never_anchored_still_runs(tmp_path, monkeypatch):
    use_os_home(monkeypatch, tmp_path / "home")
    proj = tmp_path / "proj"
    proj.mkdir()
    subprocess.run(["git", "-C", str(proj), "init", "-q"], check=True)
    rp = _launcher()
    assert rp.anchor_check(proj) is None and not (proj / ".git/info/tess-anchored").exists()


# F7: brain git hooks run only verified code -----------------------------------------------------------

def test_f7_git_hooks_never_run_a_changed_brain_module(pinned):
    assert fxlib.cli(pinned, "githooks", "install").returncode == 0
    hook = pinned / ".git/hooks/post-merge"
    assert "run-pinned.py" in hook.read_text()
    ok = subprocess.run(["sh", str(hook)], cwd=str(pinned), capture_output=True, text=True, env=_env(pinned),
                        timeout=120)
    assert ok.returncode == 0 and "TESS HOOK NOT RUN" not in ok.stdout + ok.stderr, ok.stderr
    with open(pinned / "scripts/brain/brainlib/index.py", "a") as fh:  # a merged change to one module
        fh.write("\nopen(__file__ + '.PWNED', 'w').write('ran')\n")
    for name in ("post-merge", "pre-commit"):
        r = subprocess.run(["sh", str(pinned / ".git/hooks" / name)], cwd=str(pinned), capture_output=True,
                           text=True, env=_env(pinned), timeout=120)
        assert r.returncode == 0 and "TESS HOOK NOT RUN" in r.stderr, (name, r.stdout + r.stderr)
    assert not (pinned / "scripts/brain/brainlib/index.py.PWNED").exists()


def test_f7_an_older_unpinned_brain_block_is_replaced(pinned):
    hook = pinned / ".git/hooks/post-merge"
    hook.write_text('#!/bin/sh\n# tess-brain-guard v1\nf="$(git rev-parse --show-toplevel)/scripts/brain/'
                    'tessbrain.py"; [ -f "$f" ] && python3 "$f" index --quiet || true\n# /tess-brain-guard v1\n'
                    '# user hook\nexit 0\n')
    r = fxlib.cli(pinned, "--json", "githooks", "install")
    assert r.returncode == 0 and '"post-merge": "upgraded"' in r.stdout, r.stdout
    text = hook.read_text()
    assert "tess-brain-guard v1" not in text and 'python3 "$f"' not in text
    assert text.count("# tess-brain-guard v2") == 1 and "# user hook" in text and "run-pinned.py" in text


# the test suite itself never touches the real ~/.config/tess ------------------------------------------

def test_isolated_interpreters_in_this_suite_see_a_fake_os_home():
    probe = "import os, pwd; print(pwd.getpwuid(os.getuid()).pw_dir)"
    seen = subprocess.run([sys.executable, "-I", "-B", "-c", probe], capture_output=True, text=True,
                          check=True).stdout.strip()
    real = subprocess.run([sys.executable, "-I", "-S", "-c", probe], capture_output=True, text=True,
                          check=True).stdout.strip()  # -S: no site-packages, so no test patch
    assert seen == os.environ["TESS_TEST_OS_HOME"] and seen != real
    via_path = subprocess.run("python3 -I -c '%s'" % probe, shell=True, capture_output=True, text=True,
                              check=True).stdout.strip()  # what a hook command line starts
    assert via_path == seen
