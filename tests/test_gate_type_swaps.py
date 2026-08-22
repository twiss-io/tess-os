"""A13b — protected regular-file to symlink swaps must not evade the gate.

These fixtures intentionally use the shipped policy unchanged. Current main
registers Cyra's public verifier key, but the fixtures contain no verdict
artifact or private key, so protected paths remain fail-closed. No key is
generated, registered, or used to make a test pass.
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
HAS_GPG = shutil.which("gpg") is not None
pytestmark = pytest.mark.skipif(not (HAS_GIT and HAS_GPG), reason="git + gpg required")


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
    (root / ".tess" / "tess.lock").write_text("framework: {}\nfiles: {}\n", encoding="utf-8")
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
            str(ENGINE_SRC),
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


@pytest.mark.parametrize("phase", ("ci", "pre-push"))
def test_protected_guardrails_type_swap_is_classified_and_blocked_without_verdict(tmp_path, phase):
    root, base = _type_swap_repo(tmp_path)
    _replace_with_symlink(root / "conductor" / "guardrails.md", "../docs/guardrails-baseline.md")
    head = _commit_all(root, "A13b: replace protected guardrails with a symlink")

    git_changed = _git(root, "diff", "--name-only", "--diff-filter=ACDMRT", base, head).stdout.splitlines()
    assert "conductor/guardrails.md" in git_changed

    result, payload = _run_gate(root, phase, base, head)

    assert result.returncode == 1, result.stdout + result.stderr
    assert payload["blocked"] is True
    assert payload["changed_paths_count"] == 1
    assert any(
        "no covering APPROVE verdict" in reason
        for reason in payload["reasons"]
    )


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
    assert payload["reasons"]


@pytest.mark.parametrize("phase", ("ci", "pre-push"))
def test_ordinary_protected_edit_remains_blocked_without_verdict(tmp_path, phase):
    root, base = _type_swap_repo(tmp_path)
    (root / "conductor" / "guardrails.md").write_text("# Ordinary protected edit\n", encoding="utf-8")
    head = _commit_all(root, "control: ordinary guardrails edit")

    result, payload = _run_gate(root, phase, base, head)

    assert result.returncode == 1, result.stdout + result.stderr
    assert payload["blocked"] is True
    assert payload["changed_paths_count"] == 1
    assert any("no covering APPROVE verdict" in reason for reason in payload["reasons"])


@pytest.mark.parametrize("phase", ("ci", "pre-push"))
def test_ungoverned_type_swap_is_reported_but_does_not_require_a_verdict(tmp_path, phase):
    root, base = _type_swap_repo(tmp_path)
    _replace_with_symlink(root / "docs" / "ungoverned.md", "ungoverned-target.md")
    head = _commit_all(root, "control: ungoverned document type swap")

    result, payload = _run_gate(root, phase, base, head)

    assert result.returncode == 0, result.stdout + result.stderr
    assert payload["blocked"] is False
    assert payload["changed_paths_count"] == 1
    assert payload["reasons"] == []


def test_staged_protected_type_swap_is_discovered_by_the_staged_diff_ingress(engine, tmp_path):
    root, _base = _type_swap_repo(tmp_path)
    _replace_with_symlink(root / "conductor" / "guardrails.md", "../docs/guardrails-baseline.md")
    _git(root, "add", "-A")

    assert engine._gate_changed_paths_staged(root) == ["conductor/guardrails.md"]


@pytest.mark.parametrize(
    ("rel_path", "expected_code"),
    [
        ("conductor/guardrails.md", "COVERING_APPROVAL_MISSING"),
        ("core/policy/policy.yaml", "SECURITY_CONTROL_DELETION"),
        (".tess/bin/tessctl", "SECURITY_CONTROL_DELETION"),
        (".tess/tess.lock", "SECURITY_CONTROL_DELETION"),
    ],
)
@pytest.mark.parametrize("phase", ("ci", "pre-push"))
def test_protected_policy_gate_and_lock_deletions_fail_closed(
    tmp_path, phase, rel_path, expected_code,
):
    root, base = _type_swap_repo(tmp_path)
    (root / rel_path).unlink()
    head = _commit_all(root, f"delete {rel_path}")

    result, payload = _run_gate(root, phase, base, head)

    assert result.returncode == 1, result.stdout + result.stderr
    assert payload["blocked"] is True
    assert payload["changed_paths_count"] == 1
    assert any(reason.startswith(f"{expected_code}:") for reason in payload["reasons"])


def test_staged_deletion_is_discovered_by_gate_ingress(engine, tmp_path):
    root, _base = _type_swap_repo(tmp_path)
    (root / "conductor" / "guardrails.md").unlink()
    _git(root, "add", "-A")

    assert engine._gate_changed_paths_staged(root) == ["conductor/guardrails.md"]


@pytest.mark.parametrize("phase", ("ci", "pre-push"))
def test_ordinary_protected_rename_exposes_source_and_remains_blocked(tmp_path, phase):
    root, base = _type_swap_repo(tmp_path)
    destination = "docs/renamed-guardrails.md"
    _git(root, "mv", "conductor/guardrails.md", destination)
    head = _commit_all(root, "rename protected guardrails to ungoverned docs")

    # This is the bypass shape: Git's normal rename detection collapses the
    # pair to R100 and `--name-only` emits only the ungoverned destination.
    collapsed = _git(root, "diff", "--name-status", base, head).stdout.splitlines()
    assert collapsed == [f"R100\tconductor/guardrails.md\t{destination}"]

    result, payload = _run_gate(root, phase, base, head)

    assert result.returncode == 1, result.stdout + result.stderr
    assert payload["blocked"] is True
    assert payload["changed_paths_count"] == 2
    assert any(
        reason.startswith("COVERING_APPROVAL_MISSING:") for reason in payload["reasons"]
    )


@pytest.mark.parametrize(
    ("source", "destination"),
    [
        (".tess/bin/tessctl", "docs/moved-tessctl"),
        (".tess/tess.lock", "docs/moved-tess.lock"),
        ("core/policy/policy.yaml", "docs/moved-policy.yaml"),
    ],
)
@pytest.mark.parametrize("phase", ("ci", "pre-push"))
def test_security_control_rename_is_denied_as_protected_source_deletion(
    tmp_path, phase, source, destination,
):
    root, base = _type_swap_repo(tmp_path)
    _git(root, "mv", source, destination)
    head = _commit_all(root, f"rename security control {source}")

    collapsed = _git(root, "diff", "--name-status", base, head).stdout.splitlines()
    assert collapsed == [f"R100\t{source}\t{destination}"]

    result, payload = _run_gate(root, phase, base, head)

    assert result.returncode == 1, result.stdout + result.stderr
    assert payload["blocked"] is True
    assert payload["changed_paths_count"] == 2
    assert any(
        reason.startswith("SECURITY_CONTROL_DELETION:") for reason in payload["reasons"]
    )


@pytest.mark.parametrize(
    ("source", "destination"),
    [
        ("conductor/guardrails.md", "docs/renamed-guardrails.md"),
        (".tess/bin/tessctl", "docs/moved-tessctl"),
        (".tess/tess.lock", "docs/moved-tess.lock"),
    ],
)
def test_staged_rename_ingress_reports_both_source_and_destination(
    engine, tmp_path, source, destination,
):
    root, _base = _type_swap_repo(tmp_path)
    _git(root, "mv", source, destination)

    assert set(engine._gate_changed_paths_staged(root)) == {source, destination}
