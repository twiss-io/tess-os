"""
Phase 2 — `tessctl gate install-hooks` (git pre-commit/pre-push + CI
workflow template). Same coexistence discipline as
tests/test_hook_coexistence.py's coverage of the vault guard: a pre-existing
hook (an operator's own, or the vault guard's) is never silently neutered —
the gate guard splices ABOVE it inside a containment subshell that BLOCKS on
a gate violation and FALLS THROUGH to whatever was there on a clean result.

Also proves the hooks actually FIRE against a real git repo + a real bare
remote (not just that the installed text looks right).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from conftest import sign_verdict_for_test

HAS_GIT = shutil.which("git") is not None
pytestmark = pytest.mark.skipif(not HAS_GIT, reason="git required")

USER_SENTINEL = "TESS-TEST-USER-HOOK-RAN"
REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACTS_SRC = REPO_ROOT / "core" / "contracts"
POLICY_SRC = REPO_ROOT / "core" / "policy" / "policy.yaml"


def _git(root, *args, check=True, input_text=None):
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@tess.test",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@tess.test",
    }
    r = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True, text=True, env=env, input=input_text,
    )
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr}\n{r.stdout}")
    return r


def _init_repo(root):
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@tess.test")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "commit.gpgsign", "false")


def _write_user_hook(root, name):
    hp = root / ".git" / "hooks" / name
    hp.parent.mkdir(parents=True, exist_ok=True)
    hp.write_text(
        "#!/usr/bin/env bash\n"
        "# operator's own pre-existing hook\n"
        f'echo "{USER_SENTINEL}" >> "$(git rev-parse --show-toplevel)/.user_hook_log"\n'
        "exit 0\n"
    )
    os.chmod(str(hp), 0o755)
    return hp


# ---------------------------------------------------------------------------
# Structural: standalone install, idempotency, splice above an existing hook
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("project")
def test_no_existing_hook_installs_standalone(engine, tmp_path):
    _init_repo(tmp_path)
    engine._gate_install_git_hooks(tmp_path)

    for hook_name in ("pre-commit", "pre-push"):
        text = (tmp_path / ".git" / "hooks" / hook_name).read_text()
        assert "# tess-gate-guard v1" in text
        assert "# tess-gate-guard end" not in text, "standalone install should not carry a splice sentinel"
        assert subprocess.run(["bash", "-n", str(tmp_path / ".git" / "hooks" / hook_name)]).returncode == 0
        assert os.access(tmp_path / ".git" / "hooks" / hook_name, os.X_OK)


def test_install_is_idempotent(engine, tmp_path):
    _init_repo(tmp_path)
    engine._gate_install_git_hooks(tmp_path)
    first = (tmp_path / ".git" / "hooks" / "pre-commit").read_text()

    engine._gate_install_git_hooks(tmp_path)
    second = (tmp_path / ".git" / "hooks" / "pre-commit").read_text()

    assert first == second
    assert second.count("# tess-gate-guard v1") == 1


def test_splice_above_pre_existing_user_hook_falls_through_on_clean(engine, tmp_path):
    _init_repo(tmp_path)
    _write_user_hook(tmp_path, "pre-commit")
    engine._gate_install_git_hooks(tmp_path)

    text = (tmp_path / ".git" / "hooks" / "pre-commit").read_text()
    assert "# tess-gate-guard v1" in text
    assert "# tess-gate-guard end" in text
    assert USER_SENTINEL in text
    assert text.index("# tess-gate-guard end") < text.index(USER_SENTINEL)
    assert subprocess.run(["bash", "-n", str(tmp_path / ".git" / "hooks" / "pre-commit")]).returncode == 0


def test_splice_above_vault_guard_both_layers_present(engine, tmp_path):
    """Install order: vault first, then gate. Both guards must coexist —
    proves the two independently-shipped hook installers compose rather than
    clobber one another."""
    _init_repo(tmp_path)
    engine._vault_install_git_hooks(tmp_path)
    engine._gate_install_git_hooks(tmp_path)

    for hook_name in ("pre-commit", "pre-push"):
        text = (tmp_path / ".git" / "hooks" / hook_name).read_text()
        assert "# tess-gate-guard v1" in text
        assert "# tess-vault-guard v2" in text
        # Gate installed SECOND, so it sits above (runs first).
        assert text.index("# tess-gate-guard v1") < text.index("# tess-vault-guard v2")
        assert subprocess.run(["bash", "-n", str(tmp_path / ".git" / "hooks" / hook_name)]).returncode == 0


# ---------------------------------------------------------------------------
# CI workflow template
# ---------------------------------------------------------------------------

def test_install_ci_workflow_writes_template(engine, tmp_path):
    engine._gate_install_ci_workflow(tmp_path)
    wf = tmp_path / ".github" / "workflows" / "tess-gate.yml"
    assert wf.exists()
    text = wf.read_text()
    assert "# tess-gate-ci v2" in text
    assert "workflow_dispatch" in text
    assert "tessctl gate ci" in text
    import yaml
    parsed = yaml.safe_load(text)
    # Phase 2b (CI auto-enforce): push + pull_request triggers now ship
    # alongside workflow_dispatch. PyYAML's default (1.1) resolver reads the
    # bare `on:` key as boolean True, not the string 'on' — a well-known
    # YAML/GitHub-Actions quirk (GitHub's own parser treats `on` specially);
    # this is how every GH Actions workflow round-trips through PyYAML.
    triggers = parsed[True]
    assert set(triggers) == {"workflow_dispatch", "push", "pull_request"}
    assert triggers["push"]["branches"] == ["main"]
    assert triggers["pull_request"]["branches"] == ["main"]
    assert parsed["jobs"]["ship-gate"]["steps"][-1]["run"]


def test_install_ci_workflow_idempotent(engine, tmp_path):
    engine._gate_install_ci_workflow(tmp_path)
    first = (tmp_path / ".github" / "workflows" / "tess-gate.yml").read_text()
    engine._gate_install_ci_workflow(tmp_path)
    second = (tmp_path / ".github" / "workflows" / "tess-gate.yml").read_text()
    assert first == second


def test_install_ci_workflow_upgrades_v1_to_v2(engine, tmp_path):
    """Phase 2b: an operator who already installed the v1 (workflow_dispatch-
    only) template gets actively UPGRADED to v2 (push/pull_request added) on
    the next `install-hooks` run — not silently skipped forever, and not
    mistaken for an unrelated operator-authored workflow."""
    wf_dir = tmp_path / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    v1_text = (
        "# tess-gate-ci v1\n"
        "name: Tess OS ship-gate\n"
        "on:\n"
        "  workflow_dispatch: {}\n"
        "jobs:\n"
        "  ship-gate:\n"
        "    name: tessctl gate ci\n"
        "    runs-on: ubuntu-latest\n"
        "    steps: []\n"
    )
    (wf_dir / "tess-gate.yml").write_text(v1_text, encoding="utf-8")

    engine._gate_install_ci_workflow(tmp_path)

    upgraded = (wf_dir / "tess-gate.yml").read_text()
    assert "# tess-gate-ci v2" in upgraded
    assert "# tess-gate-ci v1" not in upgraded
    assert "push:" in upgraded
    assert "pull_request:" in upgraded


def test_install_ci_workflow_does_not_clobber_operator_authored_workflow(engine, tmp_path):
    wf_dir = tmp_path / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "tess-gate.yml").write_text("name: My Own Thing\non: push\n", encoding="utf-8")

    engine._gate_install_ci_workflow(tmp_path)

    assert (wf_dir / "tess-gate.yml").read_text() == "name: My Own Thing\non: push\n"


# ---------------------------------------------------------------------------
# Real end-to-end: hooks actually FIRE (git commit / git push against a bare
# remote), via `tessctl gate install-hooks` invoked as the real CLI command.
# ---------------------------------------------------------------------------

def _test_policy_dict(verifier_keys=None):
    return {
        "policy": {
            "version": 1,
            "rules": [{
                "id": "prod-src",
                "description": "test-only prod rule",
                "globs": ["src/prod/**"],
                "classification": ["prod_touching"],
                "require_verdict": True,
                "allowed_verifiers": ["Reid"],
            }],
            "hard_floor_rules": [],
            "verifier_keys": verifier_keys or {},
        }
    }


@pytest.fixture
def e2e_repo(project, run_cli, verifier_gpg_keys):
    """Phase 2b: also bundles + registers every generated test verifier
    identity's public key (same convention as test_gate_spine.py's
    `_policy_with_verifier_keys`), so a properly-signed e2e verdict can
    actually clear the ship-gate."""
    root = project.root
    shutil.copytree(CONTRACTS_SRC, root / "core" / "contracts")
    (root / "core" / "policy").mkdir(parents=True, exist_ok=True)

    keys_dir = root / ".tess" / "keys" / "verifiers"
    keys_dir.mkdir(parents=True, exist_ok=True)
    verifier_keys = {}
    for name, key in verifier_gpg_keys.items():
        (keys_dir / f"{name.lower()}.asc").write_text(key.pubkey_armored, encoding="utf-8")
        verifier_keys[name] = {
            "fingerprint": key.fpr,
            "public_key_file": f".tess/keys/verifiers/{name.lower()}.asc",
        }
    (root / "core" / "policy" / "policy.yaml").write_text(
        yaml.safe_dump(_test_policy_dict(verifier_keys)), encoding="utf-8",
    )
    _init_repo(root)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "initial")

    r = run_cli(root, "gate", "install-hooks")
    assert r.returncode == 0, r.stdout + r.stderr
    return root


def test_e2e_pre_commit_hook_fires_and_blocks_schema_invalid_brief(e2e_repo):
    brief = e2e_repo / "missions" / "m1" / "briefs" / "task1.brief.md"
    brief.parent.mkdir(parents=True)
    brief.write_text("---\nobjective: Do the thing.\n---\n\nBody.\n", encoding="utf-8")
    _git(e2e_repo, "add", "-A")

    r = _git(e2e_repo, "commit", "-m", "should be blocked by pre-commit", check=False)
    assert r.returncode != 0, "pre-commit hook did not fire / did not block"
    assert "tess-gate" in (r.stdout + r.stderr) or "gate pre-commit" in (r.stdout + r.stderr) or "BLOCKED" in (r.stdout + r.stderr)


def test_e2e_pre_commit_hook_fires_and_allows_valid_brief(e2e_repo):
    brief = e2e_repo / "missions" / "m1" / "briefs" / "task1.brief.md"
    brief.parent.mkdir(parents=True)
    brief.write_text(
        "---\n"
        "objective: Do the thing.\n"
        "output_contract: /tmp/out.md — sections [A]\n"
        "tools_sources_constraints: Read /tmp/in.md; every number traces to a quoted row.\n"
        "not_responsible_for: The other thing.\n"
        "milestones: []\n"
        "escalation_trigger: If blocked, stop and ask.\n"
        "---\n\nBody.\n",
        encoding="utf-8",
    )
    _git(e2e_repo, "add", "-A")
    r = _git(e2e_repo, "commit", "-m", "clean brief", check=False)
    assert r.returncode == 0, f"pre-commit hook blocked a valid brief:\n{r.stdout}\n{r.stderr}"


def test_e2e_pre_push_hook_fires_and_blocks_uncovered_prod_change(e2e_repo, tmp_path):
    bare = tmp_path / "origin.git"
    _git(e2e_repo, "init", "--bare", "-q", str(bare))
    _git(e2e_repo, "remote", "add", "origin", str(bare))
    push0 = _git(e2e_repo, "push", "-u", "origin", "HEAD", check=False)
    assert push0.returncode == 0, f"baseline push should succeed:\n{push0.stdout}\n{push0.stderr}"

    (e2e_repo / "src" / "prod").mkdir(parents=True)
    (e2e_repo / "src" / "prod" / "app.py").write_text("print('prod')\n")
    _git(e2e_repo, "add", "-A")
    _git(e2e_repo, "commit", "-q", "-m", "uncovered prod change")

    push1 = _git(e2e_repo, "push", "origin", "HEAD:main", check=False)
    assert push1.returncode != 0, "pre-push hook did not fire / did not block an uncovered prod change"
    assert "no covering APPROVE verdict" in (push1.stdout + push1.stderr) or "BLOCKED" in (push1.stdout + push1.stderr)


def test_e2e_pre_push_hook_fires_and_allows_covered_prod_change(e2e_repo, tmp_path, engine, verifier_gpg_keys):
    bare = tmp_path / "origin.git"
    _git(e2e_repo, "init", "--bare", "-q", str(bare))
    _git(e2e_repo, "remote", "add", "origin", str(bare))
    assert _git(e2e_repo, "push", "-u", "origin", "HEAD", check=False).returncode == 0

    (e2e_repo / "src" / "prod").mkdir(parents=True)
    (e2e_repo / "src" / "prod" / "app.py").write_text("print('prod')\n")
    blob = _git(e2e_repo, "hash-object", "src/prod/app.py").stdout.strip()
    verdict_path = e2e_repo / "missions" / "m1" / "verdicts" / "prod-src.verdict.md"
    verdict_path.parent.mkdir(parents=True)
    verdict = {
        "verifier": "Reid",
        "output_domain": "Code diff / PR",
        "primary_artifacts_read": ["src/prod/**"],
        "findings": [],
        "severity_counts": {"critical": 0, "high": 0, "medium": 0, "low": 0},
        "summary_line": "Reviewed. Found 0 CRITICAL, 0 HIGH, 0 MEDIUM, 0 LOW. Top priority: none.",
        "disposition": "APPROVE",
        "covers_paths": ["src/prod/**"],
        "artifact_hashes": {"src/prod/app.py": blob},
    }
    # Phase 2b: a covering verdict must be signed to clear the ship-gate.
    verdict["signature"] = sign_verdict_for_test(engine, verdict, verifier_gpg_keys["Reid"])
    verdict_path.write_text("---\n" + yaml.safe_dump(verdict) + "---\n\nBody.\n", encoding="utf-8")
    _git(e2e_repo, "add", "-A")
    _git(e2e_repo, "commit", "-q", "-m", "covered prod change")

    push = _git(e2e_repo, "push", "origin", "HEAD:main", check=False)
    assert push.returncode == 0, f"pre-push hook blocked a covered change:\n{push.stdout}\n{push.stderr}"


def test_e2e_git_push_no_verify_bypasses_local_hook_but_ci_would_still_catch_it(e2e_repo, tmp_path):
    """Documents the known, expected local-hook limitation the CI mounting
    point exists to close (README.md / core comment: 'the harness-independent
    backstop that still catches git push --no-verify'). Proves --no-verify
    DOES bypass the local hook, and that `tessctl gate ci` over the SAME ref
    range independently still blocks — i.e. the backstop is real, not just
    asserted in a comment."""
    bare = tmp_path / "origin.git"
    _git(e2e_repo, "init", "--bare", "-q", str(bare))
    _git(e2e_repo, "remote", "add", "origin", str(bare))
    base = _git(e2e_repo, "rev-parse", "HEAD").stdout.strip()
    assert _git(e2e_repo, "push", "-u", "origin", "HEAD", check=False).returncode == 0

    (e2e_repo / "src" / "prod").mkdir(parents=True)
    (e2e_repo / "src" / "prod" / "app.py").write_text("print('prod')\n")
    _git(e2e_repo, "add", "-A")
    _git(e2e_repo, "commit", "-q", "-m", "uncovered prod change")
    head = _git(e2e_repo, "rev-parse", "HEAD").stdout.strip()

    push = _git(e2e_repo, "push", "--no-verify", "origin", "HEAD:main", check=False)
    assert push.returncode == 0, "git --no-verify should bypass the local hook (expected git behavior)"

    ci = subprocess.run(
        [
            "python3", str(e2e_repo / ".tess" / "bin" / "tessctl"), "gate", "ci",
            "--base", base, "--head", head, "--json",
        ],
        cwd=str(e2e_repo), capture_output=True, text=True,
        env={**os.environ, "TESS_ROOT": str(e2e_repo)},
    )
    assert ci.returncode == 1, "CI backstop must still block the same uncovered change"
    payload = json.loads(ci.stdout)
    assert payload["blocked"] is True
