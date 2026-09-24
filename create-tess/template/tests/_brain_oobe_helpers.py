"""Shared helpers for the tests/test_brain_*.py onboarding suites (ws-oobe).

Two kinds of throwaway instance:
  * mini_instance(): scripts/brain + memory/projects + operator/profile.json in
    a fresh `git init` (no framework, no gate hooks). Fast; used by the unit
    and scaffold-tree suites.
  * full_instance(): the framework's own working tree (tracked + untracked,
    non-ignored files, minus create-tess/) copied into a fresh repo with the
    real gate hooks installed by `tessctl gate install-hooks`: what
    `npm create tess` produces. Used by the gate-matrix and upgrade suites.
Nothing here touches the real repo or any global config.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
BRAIN_TOOLS = REPO_ROOT / "scripts" / "brain"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "brain_oobe"
GIT_ENV = {
    "GIT_AUTHOR_NAME": "Probe", "GIT_AUTHOR_EMAIL": "probe@example.invalid",
    "GIT_COMMITTER_NAME": "Probe", "GIT_COMMITTER_EMAIL": "probe@example.invalid",
    "GIT_CONFIG_NOSYSTEM": "1",
}


def env(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    out = dict(os.environ)
    out.update(GIT_ENV)
    out["TESS_BRAIN_NO_LEARN"] = "1"
    for key in ("TESS_BRAIN_QUIET", "TESS_HEADLESS", "TESS_BRAIN_TEST_NONCE", "TESS_BRAIN_ROOT"):
        out.pop(key, None)
    out.update(extra or {})
    return out


def git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root)] + list(args), capture_output=True, text=True,
                          env=env(), check=check)


def onboard(root: Path, *args: str, stdin: Optional[str] = None,
            extra_env: Optional[Dict[str, str]] = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(root / "scripts" / "brain" / "onboard.py")] + list(args),
                          cwd=str(root), capture_output=True, text=True, input=stdin,
                          env=env(extra_env), timeout=300)


def mini_instance(tmp: Path, profile: Optional[dict] = None, source_repo: bool = False) -> Path:
    root = tmp / "inst"
    (root / "scripts").mkdir(parents=True)
    shutil.copytree(str(BRAIN_TOOLS), str(root / "scripts" / "brain"),
                    ignore=shutil.ignore_patterns("__pycache__"))
    (root / "memory" / "projects").mkdir(parents=True)
    shutil.copy2(str(REPO_ROOT / "memory" / "projects" / "EXAMPLE.md"), str(root / "memory" / "projects"))
    (root / "operator").mkdir()
    prof = profile if profile is not None else {"operator_name": "Probe", "assistant_name": "Tess",
                                                 "pathway": "chief-of-staff"}
    (root / "operator" / "profile.json").write_text(json.dumps(prof))
    (root / ".gitignore").write_text("operator/profile.json\n")
    if source_repo:
        (root / "create-tess").mkdir()
        (root / "create-tess" / "package.json").write_text("{}\n")
    git(root, "init", "-q", "-b", "main")
    return root


def framework_files() -> List[str]:
    """Tracked + untracked-but-not-ignored files of the framework tree."""
    out = subprocess.run(["git", "-C", str(REPO_ROOT), "ls-files", "-z", "--cached", "--others",
                          "--exclude-standard"], capture_output=True, check=True).stdout
    files = [f for f in out.decode("utf-8").split("\0") if f]
    return [f for f in files if not f.startswith("create-tess/") and (REPO_ROOT / f).is_file()]


def full_instance(tmp: Path, operator: str = "Probe") -> Path:
    """A create-tess-shaped instance: framework copy, git init, gate hooks, profile."""
    root = tmp / "full"
    for rel in framework_files():
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(REPO_ROOT / rel), str(dest))
    (root / "operator" / "profile.json").write_text(json.dumps(
        {"operator_name": operator, "assistant_name": "Tess", "pathway": "chief-of-staff"}))
    git(root, "init", "-q", "-b", "main")
    done = subprocess.run([sys.executable, str(root / ".tess" / "bin" / "tessctl"), "gate", "install-hooks"],
                          cwd=str(root), capture_output=True, text=True, env=env({"TESS_ROOT": str(root)}))
    assert done.returncode == 0, done.stdout + done.stderr
    return root


def tree(root: Path) -> List[str]:
    """`find brain memory/projects -type f ! -path '*/.private/*' | LC_ALL=C sort`."""
    out = []
    for top in ("brain", "memory/projects"):
        base = root / top
        if base.exists():
            out.extend(p.relative_to(root).as_posix() for p in base.rglob("*")
                       if p.is_file() and "/.private/" not in "/" + p.relative_to(root).as_posix())
    return sorted(out, key=lambda s: s.encode("utf-8"))


def onboard_fixture(root: Path, name: str) -> subprocess.CompletedProcess:
    done = onboard(root, "init", "--non-interactive", "--answers", str(FIXTURES / ("answers-%s.json" % name)))
    assert done.returncode == 0, done.stdout + done.stderr
    return onboard(root, "apply")
