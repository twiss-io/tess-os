"""Fresh install -> onboard -> apply, per mode, through the REAL create-tess package (acceptance O2/O3).

Opt-in (slow; needs node >= 18 and the committed create-tess/template/):
    TESS_BRAIN_E2E=1 python3 -m pytest -q tests/test_brain_fresh_install_e2e.py

CI runs it from the real `npm pack` tarball (ci.yml, release.yml):
    TESS_E2E_TARBALL=/path/create-tess-X.tgz  install with `npx --yes --package <tarball> create-tess`
    TESS_E2E_PYTHON=/usr/bin/python3          the only python3 the install and
                                              onboarding see (stock macOS: no PyYAML)

For each fixture mode: `create-tess --yes` into a temp dir with a temp HOME,
onboarding status is `pending`, the non-interactive fixture answers apply
cleanly, the brain tree equals tests/fixtures/brain_oobe/expected-tree-<m>.txt,
`tessctl doctor` / `verify` are OK, the brain is committed through the
installed gate, every entity starts with START HERE, the shims are exact,
a second apply is a no-op, and the SessionStart hook is silent afterwards.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import _brain_oobe_helpers as h

pytestmark = pytest.mark.skipif(
    os.environ.get("TESS_BRAIN_E2E") != "1" or shutil.which("node") is None,
    reason="opt-in: set TESS_BRAIN_E2E=1 (needs node)")

CREATE_TESS = h.REPO_ROOT / "create-tess" / "bin" / "create-tess.mjs"
MODES = ["personal", "agency-solo", "organisation-startup"]
TARBALL = os.environ.get("TESS_E2E_TARBALL")
PYTHON = os.environ.get("TESS_E2E_PYTHON") or sys.executable
WIZARD = ["npx", "--yes", "--package", TARBALL, "create-tess"] if TARBALL else ["node", str(CREATE_TESS)]
FLAGS = ["--yes", "--operator", "Probe", "--conductor", "Tess", "--vibe", "command", "--path", "founders",
         "--pathway", "chief-of-staff"]


@pytest.fixture(scope="module")
def python_dir(tmp_path_factory) -> str:
    """A PATH entry whose `python3` is PYTHON, so nothing else can be picked up."""
    shim = tmp_path_factory.mktemp("python-shim")
    os.symlink(PYTHON, str(shim / "python3"))
    return str(shim)


def run(cmd, cwd: Path, extra=None, python_path: str = "") -> subprocess.CompletedProcess:
    env = h.env(extra)
    env["PATH"] = (python_path or os.path.dirname(PYTHON)) + os.pathsep + env.get("PATH", "")
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, env=env, timeout=900)


@pytest.fixture(scope="module", params=MODES)
def installed(request, tmp_path_factory, python_dir):
    base = tmp_path_factory.mktemp("e2e-%s" % request.param)
    dest = base / ("i-%s" % request.param)
    # --no-onboarding: these fixtures answer all 7 steps themselves, below.
    made = run(WIZARD + [str(dest), "--no-onboarding"] + FLAGS, base, {"HOME": str(base / "home")}, python_dir)
    assert made.returncode == 0, made.stdout[-3000:] + made.stderr[-3000:]
    return request.param, dest


def onboard(root: Path, *args: str) -> subprocess.CompletedProcess:
    return run([PYTHON, "scripts/brain/onboard.py"] + list(args), root)


@pytest.mark.parametrize("mode,preset", [("agency", "solo-consultant"), ("personal", "none")])
def test_wizard_runs_onboarding_itself(mode, preset, tmp_path, python_dir):
    """v0.2.1: `--mode` alone gives a committed brain; nobody runs onboard.py by hand."""
    dest = tmp_path / "inst"
    made = run(WIZARD + [str(dest), "--mode", mode, "--preset", preset] + FLAGS, tmp_path,
               {"HOME": str(tmp_path / "home")}, python_dir)
    assert made.returncode == 0, made.stdout[-3000:] + made.stderr[-3000:]
    assert "What to do next:" in made.stdout and "in Claude Code or Codex and say hi" in made.stdout  # B4 wording
    assert "In Codex: trust this folder and approve Tess's hooks when asked (/hooks)." in made.stdout
    assert '"status": "complete"' in onboard(dest, "status", "--json").stdout
    assert (dest / ".gitignore").is_file()
    assert h.git(dest, "log", "--format=%s").stdout.strip() == "tess: seed instance + second brain (onboarding)"
    tracked = set(h.git(dest, "ls-files").stdout.splitlines())
    assert "brain/brain.json" in tracked and "operator/profile.json" not in tracked
    for private in (".env", "operator/profile.json", "clients/acme/notes.md"):
        assert h.git(dest, "check-ignore", "-q", private, check=False).returncode == 0, private
    for verb in ("doctor", "verify"):
        done = run([str(dest / "tessctl"), verb], dest, python_path=python_dir)
        assert done.stdout.strip().splitlines()[-1].startswith("%s: OK" % verb), done.stdout[-2000:]


def test_install_onboard_apply_commit(installed):
    mode, root = installed
    assert '"status": "pending"' in onboard(root, "status", "--json").stdout
    answers = h.FIXTURES / ("answers-%s.json" % mode)
    init = onboard(root, "init", "--non-interactive", "--answers", str(answers))
    assert init.returncode == 0, init.stderr
    applied = onboard(root, "apply")
    assert applied.returncode == 0, applied.stdout + applied.stderr
    h.assert_expected_tree(root, mode)
    doctor = run([str(root / "tessctl"), "doctor"], root)
    assert doctor.stdout.strip().splitlines()[-1].startswith("doctor: OK"), doctor.stdout[-2000:]
    verify = run([str(root / "tessctl"), "verify"], root)
    assert verify.stdout.strip().splitlines()[-1].startswith("verify: OK"), verify.stdout[-2000:]
    assert "brain" in h.git(root, "log", "--format=%s").stdout.lower()
    assert h.git(root, "status", "--porcelain").stdout == ""


def ensure_applied(mode: str, root: Path) -> None:
    """Lets each test run on its own (-k); a no-op after test_install_onboard_apply_commit."""
    if not (root / "brain" / "brain.json").exists():
        onboard(root, "init", "--non-interactive", "--answers", str(h.FIXTURES / ("answers-%s.json" % mode)))
        assert onboard(root, "apply").returncode == 0


def test_entities_start_here_and_shims_are_exact(installed):
    mode, root = installed
    ensure_applied(mode, root)
    agents = sorted((root / "brain").rglob("AGENTS.md"))
    assert agents
    for path in agents:
        head = path.read_text().splitlines()[:80]
        assert any(ln.startswith("# START HERE") for ln in head), path
        assert (path.parent / "CLAUDE.md").read_text() == "@AGENTS.md\n"
        assert (path.parent / "GEMINI.md").read_text() == "@./AGENTS.md\n"


def test_second_apply_is_a_noop_and_hook_is_silent(installed):
    mode, root = installed
    ensure_applied(mode, root)
    again = onboard(root, "apply")
    assert again.returncode == 0, again.stderr
    assert h.git(root, "status", "--porcelain").stdout == ""
    hook = run([PYTHON, "scripts/brain/onboard.py", "hook", "session-start", "--runtime", "claude"],
               root)
    assert hook.returncode == 0 and hook.stdout == ""
