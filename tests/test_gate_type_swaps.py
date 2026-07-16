"""A13b — protected regular-file to symlink swaps must not evade the gate.

These fixtures intentionally use the shipped policy unchanged, including its
empty ``verifier_keys`` registry.  Every denial below is therefore caused by
the absence of a covering verdict; no key is generated, registered, or used
to make a test pass.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import ENGINE_SRC, REPO_ROOT


HAS_GIT = shutil.which("git") is not None
pytestmark = pytest.mark.skipif(not HAS_GIT, reason="git required")


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "A13b Test",
        "GIT_AUTHOR_EMAIL": "a13b@tess.test",
        "GIT_COMMITTER_NAME": "A13b Test",
        "GIT_COMMITTER_EMAIL": "a13b@tess.test",
    }
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, env=env,
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{result.stderr}\n{result.stdout}")
    return result


def _commit_all(root: Path, message: str) -> str:
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)
    return _git(root, "rev-parse", "HEAD").stdout.strip()


def _commit_index(root: Path, message: str) -> str:
    _git(root, "commit", "-q", "-m", message)
    return _git(root, "rev-parse", "HEAD").stdout.strip()


def _type_swap_repo(tmp_path: Path) -> tuple[Path, str]:
    """Build a disposable repo with an unmodified copy of shipped policy.

    The extra docs files are baseline-only symlink targets.  They are outside
    the shipped policy's protected globs, allowing the tests to prove that it
    is the protected path's *type change*, not target content, that the gate
    must classify.
    """
    root = tmp_path / "repo"
    engine_path = root / ".tess" / "bin" / "tessctl"
    engine_path.parent.mkdir(parents=True)
    shutil.copy2(ENGINE_SRC, engine_path)
    os.chmod(engine_path, 0o755)
    shutil.copytree(REPO_ROOT / "core" / "contracts", root / "core" / "contracts")
    (root / "core" / "policy").mkdir(parents=True)
    shutil.copy2(REPO_ROOT / "core" / "policy" / "policy.yaml", root / "core" / "policy" / "policy.yaml")

    (root / "conductor").mkdir()
    (root / "conductor" / "guardrails.md").write_text("# Baseline guardrails\n", encoding="utf-8")
    docs = root / "docs"
    docs.mkdir()
    (docs / "guardrails-baseline.md").write_text("# Ungoverned replacement\n", encoding="utf-8")
    shutil.copy2(root / "core" / "policy" / "policy.yaml", docs / "policy-baseline.yaml")
    (docs / "ungoverned.md").write_text("baseline ungoverned document\n", encoding="utf-8")
    (docs / "ungoverned-target.md").write_text("ungoverned symlink target\n", encoding="utf-8")

    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "a13b@tess.test")
    _git(root, "config", "user.name", "A13b Test")
    _git(root, "config", "commit.gpgsign", "false")
    return root, _commit_all(root, "A13b protected-path baseline")


def _replace_with_symlink(path: Path, target: str) -> None:
    path.unlink()
    path.symlink_to(target)


def _run_gate(root: Path, phase: str, base: str, head: str) -> tuple[subprocess.CompletedProcess, dict]:
    result = subprocess.run(
        [
            sys.executable,
            str(root / ".tess" / "bin" / "tessctl"),
            "gate",
            phase,
            "--base",
            base,
            "--head",
            head,
            "--json",
        ],
        cwd=str(root),
        env={**os.environ, "TESS_ROOT": str(root)},
        capture_output=True,
        text=True,
    )
    return result, json.loads(result.stdout)


def _run_pre_commit(root: Path) -> tuple[subprocess.CompletedProcess, dict]:
    result = subprocess.run(
        [
            sys.executable,
            str(root / ".tess" / "bin" / "tessctl"),
            "gate",
            "pre-commit",
            "--json",
        ],
        cwd=str(root),
        env={**os.environ, "TESS_ROOT": str(root)},
        capture_output=True,
        text=True,
    )
    return result, json.loads(result.stdout)


@pytest.mark.parametrize("phase", ("ci", "pre-push"))
def test_protected_guardrails_type_swap_is_categorically_blocked_before_verdict(tmp_path, phase):
    root, base = _type_swap_repo(tmp_path)
    _replace_with_symlink(root / "conductor" / "guardrails.md", "../docs/guardrails-baseline.md")
    head = _commit_all(root, "A13b: replace protected guardrails with a symlink")

    git_changed = _git(root, "diff", "--name-only", "--diff-filter=ACMRT", base, head).stdout.splitlines()
    assert "conductor/guardrails.md" in git_changed

    result, payload = _run_gate(root, phase, base, head)

    assert result.returncode == 1, result.stdout + result.stderr
    assert payload["blocked"] is True
    assert payload["changed_paths_count"] == 1
    assert payload["reasons"] == [
        "GOVERNED_TRANSITION_UNSUPPORTED: a governed Git path transition is unsupported"
    ]
    assert "conductor/guardrails.md" not in json.dumps(payload)
    assert not any("no covering APPROVE verdict" in reason for reason in payload["reasons"])


@pytest.mark.parametrize("phase", ("ci", "pre-push"))
def test_combined_policy_and_guardrails_type_swaps_are_both_blocked_without_verdict(tmp_path, phase):
    root, base = _type_swap_repo(tmp_path)
    _replace_with_symlink(root / "conductor" / "guardrails.md", "../docs/guardrails-baseline.md")
    _replace_with_symlink(root / "core" / "policy" / "policy.yaml", "../../docs/policy-baseline.yaml")
    head = _commit_all(root, "A13b: replace policy and guardrails with symlinks")

    result, payload = _run_gate(root, phase, base, head)

    assert result.returncode == 1, result.stdout + result.stderr
    assert payload["blocked"] is True
    assert payload["changed_paths_count"] == 2
    assert payload["reasons"] == [
        "GOVERNED_TRANSITION_UNSUPPORTED: a governed Git path transition is unsupported",
        "GOVERNED_TRANSITION_UNSUPPORTED: a governed Git path transition is unsupported",
    ]
    assert "conductor/guardrails.md" not in json.dumps(payload)
    assert "core/policy/policy.yaml" not in json.dumps(payload)


@pytest.mark.parametrize("phase", ("ci", "pre-push"))
def test_ordinary_protected_edit_remains_blocked_without_verdict(tmp_path, phase):
    root, base = _type_swap_repo(tmp_path)
    (root / "conductor" / "guardrails.md").write_text("# Ordinary protected edit\n", encoding="utf-8")
    head = _commit_all(root, "control: ordinary guardrails edit")

    result, payload = _run_gate(root, phase, base, head)

    assert result.returncode == 1, result.stdout + result.stderr
    assert payload["blocked"] is True
    assert payload["changed_paths_count"] == 1
    assert payload["reasons"] == [
        "COVERING_APPROVAL_MISSING: no covering APPROVE verdict found"
    ]
    assert "conductor/guardrails.md" not in json.dumps(payload)


@pytest.mark.parametrize("phase", ("ci", "pre-push"))
def test_ungoverned_type_swap_is_reported_but_does_not_require_a_verdict(tmp_path, phase):
    root, base = _type_swap_repo(tmp_path)
    _replace_with_symlink(root / "docs" / "ungoverned.md", "ungoverned-target.md")
    _git(root, "add", "-A")
    staged_result, staged_payload = _run_pre_commit(root)
    assert staged_result.returncode == 0, staged_result.stdout + staged_result.stderr
    assert staged_payload["blocked"] is False
    assert staged_payload["reasons"] == []
    head = _commit_index(root, "control: ungoverned document type swap")

    result, payload = _run_gate(root, phase, base, head)

    assert result.returncode == 0, result.stdout + result.stderr
    assert payload["blocked"] is False
    assert payload["changed_paths"] == ["docs/ungoverned.md"]
    assert payload["reasons"] == []

    # A new non-regular entry is different: pre-commit denies every new
    # symlink/gitlink even when no policy glob covers it.
    (root / "docs" / "new-ungoverned-link").symlink_to("ungoverned-target.md")
    _git(root, "add", "-A")
    addition_result, addition_payload = _run_pre_commit(root)
    assert addition_result.returncode == 1
    assert addition_payload["blocked"] is True
    assert any(
        reason.startswith("NONREGULAR_ADDITION_UNSUPPORTED:")
        and "docs/new-ungoverned-link" in reason
        for reason in addition_payload["reasons"]
    )


def test_staged_protected_type_swap_is_discovered_by_the_staged_diff_ingress(engine, tmp_path):
    root, _base = _type_swap_repo(tmp_path)
    _replace_with_symlink(root / "conductor" / "guardrails.md", "../docs/guardrails-baseline.md")
    _git(root, "add", "-A")

    assert engine._gate_changed_paths_staged(root) == ["conductor/guardrails.md"]
    result, payload = _run_pre_commit(root)
    assert result.returncode == 1, result.stdout + result.stderr
    assert payload["blocked"] is True
    assert any(
        reason.startswith("GOVERNED_TRANSITION_UNSUPPORTED:")
        and "conductor/guardrails.md" in reason
        for reason in payload["reasons"]
    )
