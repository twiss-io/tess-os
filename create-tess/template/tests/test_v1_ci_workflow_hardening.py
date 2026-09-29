"""v1.0.0 final security review (Cyra, 2026-09-29): CI workflow hardening.

M4  The installed ship-gate workflow (`tess-gate.yml`, template in tessctl
    `_GATE_CI_WORKFLOW`) interpolated `${{ inputs.base/head }}` into its shell
    script (script injection from a dispatch form), accepted ANY dispatch base
    (diff from a commit that already contains the change → nothing to check),
    used tag-pinned actions and an unpinned pyyaml.
M5  release.yml ran every gate (the full test suite, npm ci, scripts) in the
    job that holds `contents: write`, with the checkout token persisted.
L1  publish-npm.yml published create-tess without checking that the framework
    GitHub Release it ships the proof of exists and that its run succeeded.
L3  The gitleaks tarball was piped straight into tar with no checksum.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
WF = REPO / ".github" / "workflows"
GITLEAKS_SHA256 = "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb"


# release.yml / ci.yml / publish-npm.yml are Tess OS's own pipelines; create-tess
# leaves them out of every scaffolded project (create-tess/src/ignore.js).
_OWN = pytest.mark.skipif(not (WF / "release.yml").exists(),
                          reason="Tess OS source repo only (no release pipeline here)")


def _steps(wf: dict) -> list:
    return [s for job in wf["jobs"].values() for s in job.get("steps", [])]


def _template(engine) -> str:
    return engine._GATE_CI_WORKFLOW


# ---------------------------------------------------------------------------
# M4 — tess-gate.yml
# ---------------------------------------------------------------------------

def test_repo_workflow_is_the_engine_template(engine):
    assert (WF / "tess-gate.yml").read_text(encoding="utf-8") == _template(engine)
    assert engine._GATE_CI_WORKFLOW_MARKER == "# tess-gate-ci v4"
    assert "# tess-gate-ci v3" in engine._GATE_CI_WORKFLOW_KNOWN_MARKERS  # v3 installs upgrade


def test_gate_workflow_never_interpolates_dispatch_inputs_into_a_script(engine):
    wf = yaml.safe_load(_template(engine))
    for step in _steps(wf):
        assert "inputs." not in str(step.get("run", "")), step.get("name")
    refs = next(s for s in _steps(wf) if s.get("id") == "refs")
    assert refs["env"]["DISPATCH_BASE"] == "${{ inputs.base }}"
    assert refs["env"]["DISPATCH_HEAD"] == "${{ inputs.head }}"


def test_gate_workflow_pins_actions_and_pyyaml(engine):
    text = _template(engine)
    uses = [ln for ln in text.splitlines() if "uses:" in ln]
    assert uses and all(re.search(r"uses: [\w.-]+/[\w.-]+@[0-9a-f]{40} # v\d+\.\d+\.\d+$", ln)
                        for ln in uses), uses
    install = next(s for s in _steps(yaml.safe_load(text)) if s.get("name") == "Install dependencies")
    assert re.search(r'pyyaml==\d+\.\d+\.\d+', install["run"]) and "--upgrade" not in install["run"]


def test_upgrading_a_v3_workflow_installs_v4(engine, tmp_path):
    wf_dir = tmp_path / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "tess-gate.yml").write_text("# tess-gate-ci v3\nname: old\n", encoding="utf-8")
    engine._gate_install_ci_workflow(tmp_path)
    assert (wf_dir / "tess-gate.yml").read_text(encoding="utf-8") == _template(engine)


def _git(cwd: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True,
                          text=True, env=env).stdout.strip()


@pytest.fixture
def dispatch_checkout(tmp_path):
    """A clone laid out as actions/checkout (fetch-depth 0) leaves it: main
    at origin/main, plus an off-main commit that already holds a change."""
    if shutil.which("git") is None or shutil.which("bash") is None:
        pytest.skip("needs git and bash")
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(origin, "init", "-q", "-b", "main")
    (origin / "a.txt").write_text("1\n")
    _git(origin, "add", "-A")
    _git(origin, "commit", "-q", "-m", "one")
    (origin / "a.txt").write_text("2\n")
    _git(origin, "commit", "-qam", "two")
    _git(origin, "checkout", "-q", "-b", "evil")
    (origin / "evil.txt").write_text("x\n")
    _git(origin, "add", "-A")
    _git(origin, "commit", "-q", "-m", "evil")
    _git(origin, "checkout", "-q", "main")
    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", str(origin), str(clone))
    _git(clone, "fetch", "-q", "origin", "evil:refs/remotes/origin/evil")
    return clone


def _run_refs(engine, cwd: Path, base: str, head: str, tmp_path: Path):
    step = next(s for s in _steps(yaml.safe_load(_template(engine))) if s.get("id") == "refs")
    script = step["run"].replace("${{ github.event_name }}", "workflow_dispatch")
    assert "${{" not in script.split("elif", 1)[0], "dispatch branch still holds an expression"
    out = tmp_path / "gh_output"
    out.write_text("")
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
           "DISPATCH_BASE": base, "DISPATCH_HEAD": head, "DEFAULT_BRANCH": "main",
           "GITHUB_OUTPUT": str(out)}
    r = subprocess.run(["bash", "-e", "-c", script], cwd=str(cwd), env=env,
                       capture_output=True, text=True)
    return r, out.read_text()


def test_dispatch_with_an_ancestor_base_resolves_to_commits(engine, dispatch_checkout, tmp_path):
    r, out = _run_refs(engine, dispatch_checkout, "HEAD~1", "HEAD", tmp_path)
    assert r.returncode == 0, r.stderr
    base = _git(dispatch_checkout, "rev-parse", "HEAD~1")
    assert f"base={base}" in out and re.search(r"head=[0-9a-f]{40}", out)


def test_dispatch_base_off_the_default_branch_is_refused(engine, dispatch_checkout, tmp_path):
    r, out = _run_refs(engine, dispatch_checkout, "origin/evil", "origin/evil", tmp_path)
    assert r.returncode != 0 and "not an ancestor" in r.stdout + r.stderr
    assert "base=" not in out


@pytest.mark.parametrize("payload", ['$(touch PWNED)', '"; touch PWNED; echo "', "`touch PWNED`",
                                     "--output=PWNED"])
def test_dispatch_inputs_cannot_inject_shell(engine, dispatch_checkout, tmp_path, payload):
    r, out = _run_refs(engine, dispatch_checkout, payload, "HEAD", tmp_path)
    assert r.returncode != 0, r.stdout
    assert not (dispatch_checkout / "PWNED").exists()
    assert not list(dispatch_checkout.glob("*PWNED*"))


# ---------------------------------------------------------------------------
# M5 — release.yml: read-only gates, minimal write job
# ---------------------------------------------------------------------------

@_OWN
def test_release_gates_run_read_only_and_the_write_job_runs_no_project_code():
    wf = yaml.safe_load((WF / "release.yml").read_text(encoding="utf-8"))
    assert wf["permissions"] == {"contents": "read"}
    gates, release = wf["jobs"]["gates"], wf["jobs"]["release"]
    assert gates["permissions"] == {"contents": "read"}
    assert release["permissions"] == {"contents": "write"} and release["needs"] == "gates"
    for job in (gates, release):
        checkout = next(s for s in job["steps"] if "actions/checkout@" in str(s.get("uses")))
        assert checkout["with"]["persist-credentials"] is False
    runs = "\n".join(str(s.get("run", "")) for s in release["steps"])
    for forbidden in ("pytest", "npm ", "pip install", "tessctl", ".github/scripts", "gitleaks"):
        assert forbidden not in runs, forbidden
    uses = [str(s.get("uses")) for s in release["steps"] if s.get("uses")]
    assert all(u.startswith(("actions/checkout@", "softprops/action-gh-release@")) for u in uses)
    gate_runs = "\n".join(str(s.get("run", "")) for s in gates["steps"])
    assert "python -m pytest" in gate_runs and "npm test" in gate_runs


# ---------------------------------------------------------------------------
# L3 — gitleaks checksum; L1 — publish needs the framework release
# ---------------------------------------------------------------------------

@_OWN
@pytest.mark.parametrize("name", ["release.yml", "ci.yml"])
def test_gitleaks_download_is_checksum_verified(name):
    step = next(s for s in _steps(yaml.safe_load((WF / name).read_text(encoding="utf-8")))
                if s.get("name") == "Install gitleaks")
    run = step["run"]
    assert f"GITLEAKS_SHA256={GITLEAKS_SHA256}" in run
    assert run.index("sha256sum -c") < run.index("tar -xzf")
    assert "| sudo tar" not in run and "set -euo pipefail" in run


@_OWN
def test_npm_publish_requires_the_framework_release_and_its_successful_run():
    job = yaml.safe_load((WF / "publish-npm.yml").read_text(encoding="utf-8"))["jobs"]["publish"]
    names = [s.get("name", "") for s in job["steps"]]
    gate = names.index("Gate 0c — the framework GitHub Release exists and its release run succeeded")
    assert gate < names.index("npm publish (Trusted Publishing / OIDC)")
    run = job["steps"][gate]["run"]
    assert 'gh release view "$FW"' in run and "isDraft == false" in run
    assert "gh run list --workflow release.yml" in run and '.conclusion == \\"success\\"' in run
    assert run.index("=~ ^create-tess-v") < run.index("gh run list")
    assert job["permissions"]["actions"] == "read"
