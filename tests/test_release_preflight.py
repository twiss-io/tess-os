from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts import release_preflight as preflight


REPO_ROOT = Path(__file__).resolve().parent.parent
PRIMARY_FINGERPRINT = "A" * 40
SIGNING_SUBKEY_FINGERPRINT = "B" * 40


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _metadata_repo(root: Path, version: str = "1.2.3") -> Path:
    _write_json(root / "package.json", {"name": "tess-os", "version": version, "private": False})
    _write_json(
        root / "create-tess" / "package.json",
        {"name": "create-tess", "version": version, "private": False},
    )
    _write_json(
        root / "create-tess" / "package-lock.json",
        {"version": version, "packages": {"": {"version": version}}},
    )
    _write_json(
        root / "gui" / "package.json",
        {"name": "tess-gui", "version": "9.8.7", "private": True},
    )
    _write_json(
        root / "gui" / "package-lock.json",
        {"version": "9.8.7", "packages": {"": {"version": "9.8.7"}}},
    )
    lock = root / ".tess" / "tess.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(
        f"schema: 1\nframework:\n  version: {version}\n  upstream_ref: v{version}\nfiles: {{}}\n",
        encoding="utf-8",
    )
    return root


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _source_repo(root: Path) -> Path:
    root.mkdir(parents=True)
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.name", "Release Test")
    _git(root, "config", "user.email", "release-test@example.invalid")
    (root / "payload.txt").write_text("one\n", encoding="utf-8")
    _git(root, "add", "payload.txt")
    _git(root, "commit", "-m", "initial")
    _git(root, "tag", "-a", "v1.2.3", "-m", "release")
    _git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    return root


def _pack_payload(name: str, version: str, paths: set[str]) -> list[dict]:
    return [
        {
            "name": name,
            "version": version,
            "files": [{"path": path} for path in sorted(paths)],
        }
    ]


def test_current_main_metadata_debt_is_explicit_not_hidden() -> None:
    target, issues = preflight.metadata_issues(REPO_ROOT)

    assert target == "0.1.1"
    assert "root package.json version is '0.1.0'; expected '0.1.1'" in issues
    assert all("GUI package must remain private:true" not in issue for issue in issues)


def test_future_unified_release_contract_accepts_aligned_public_versions(tmp_path: Path) -> None:
    repo = _metadata_repo(tmp_path)

    target, issues = preflight.metadata_issues(repo, "v1.2.3")

    assert target == "1.2.3"
    assert issues == []


def test_release_contract_rejects_any_public_version_mismatch(tmp_path: Path) -> None:
    repo = _metadata_repo(tmp_path)
    package = json.loads((repo / "create-tess" / "package.json").read_text(encoding="utf-8"))
    package["version"] = "1.2.2"
    _write_json(repo / "create-tess" / "package.json", package)

    _, issues = preflight.metadata_issues(repo, "v1.2.3")

    assert any("create-tess/package.json version" in issue for issue in issues)


def test_lock_parser_rejects_duplicate_framework_authority(tmp_path: Path) -> None:
    lock = tmp_path / "tess.lock"
    lock.write_text(
        "framework:\n  version: 1.2.3\n  upstream_ref: v1.2.3\n"
        "files: {}\nframework:\n  version: 9.9.9\n  upstream_ref: v9.9.9\n",
        encoding="utf-8",
    )

    with pytest.raises(preflight.PreflightError, match="exactly one"):
        preflight.read_lock_release_fields(lock)


@pytest.mark.parametrize("tag", ["1.2.3", "v1.2", "v1.2.3-rc1", "v01.2.3"])
def test_stable_tag_contract_rejects_noncanonical_tags(tag: str) -> None:
    with pytest.raises(preflight.PreflightError):
        preflight.version_from_tag(tag)


def test_source_accepts_annotated_tag_equal_to_origin_main(tmp_path: Path) -> None:
    repo = _source_repo(tmp_path / "repo")
    head = _git(repo, "rev-parse", "HEAD")

    assert preflight.validate_source(repo, "v1.2.3", expected_sha=head) == head


def test_source_rejects_tagged_commit_behind_origin_main(tmp_path: Path) -> None:
    repo = _source_repo(tmp_path / "repo")
    (repo / "payload.txt").write_text("two\n", encoding="utf-8")
    _git(repo, "add", "payload.txt")
    _git(repo, "commit", "-m", "main advanced")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")

    with pytest.raises(preflight.PreflightError, match="does not equal protected"):
        preflight.validate_source(repo, "v1.2.3")


def test_source_rejects_lightweight_tag(tmp_path: Path) -> None:
    repo = _source_repo(tmp_path / "repo")
    _git(repo, "tag", "v1.2.4")

    with pytest.raises(preflight.PreflightError, match="annotated tag"):
        preflight.validate_source(repo, "v1.2.4")


def test_validsig_parser_uses_primary_fingerprint_for_signing_subkey() -> None:
    status = (
        "[GNUPG:] VALIDSIG "
        f"{SIGNING_SUBKEY_FINGERPRINT} 2026-07-16 0 0 4 0 1 10 00 {PRIMARY_FINGERPRINT}"
    )

    assert preflight.parse_validsig_primary(status) == PRIMARY_FINGERPRINT


def test_validsig_parser_rejects_multiple_valid_signatures() -> None:
    status = (
        f"[GNUPG:] VALIDSIG {PRIMARY_FINGERPRINT} 1 2 3 4 5 6 7 8 {PRIMARY_FINGERPRINT}\n"
        f"[GNUPG:] VALIDSIG {PRIMARY_FINGERPRINT} 1 2 3 4 5 6 7 8 {PRIMARY_FINGERPRINT}"
    )

    with pytest.raises(preflight.PreflightError, match="exactly one"):
        preflight.parse_validsig_primary(status)


@pytest.mark.parametrize("bad_status", ["EXPKEYSIG", "REVKEYSIG", "BADSIG", "NO_PUBKEY"])
def test_signature_status_rejects_invalid_or_untrusted_states(bad_status: str) -> None:
    status = (
        f"[GNUPG:] {bad_status} unsafe\n"
        f"[GNUPG:] VALIDSIG {PRIMARY_FINGERPRINT} 1 2 3 4 5 6 7 8 {PRIMARY_FINGERPRINT}"
    )

    with pytest.raises(preflight.PreflightError, match="expired, revoked, missing, or invalid"):
        preflight.validate_signature_status(status, PRIMARY_FINGERPRINT)


def test_signature_status_rejects_valid_signature_from_other_primary_key() -> None:
    status = (
        f"[GNUPG:] VALIDSIG {SIGNING_SUBKEY_FINGERPRINT} 1 2 3 4 5 6 7 8 "
        f"{SIGNING_SUBKEY_FINGERPRINT}"
    )

    with pytest.raises(preflight.PreflightError, match="does not match"):
        preflight.validate_signature_status(status, PRIMARY_FINGERPRINT)


def test_fingerprint_rejects_short_or_decorated_values() -> None:
    for value in ("ABC123", "AA:BB", f"fingerprint={PRIMARY_FINGERPRINT}"):
        with pytest.raises(preflight.PreflightError):
            preflight.normalize_fingerprint(value)


def test_root_pack_manifest_is_exact() -> None:
    package = {"name": "tess-os", "version": "1.2.3"}
    preflight.validate_pack_record(
        "root",
        _pack_payload("tess-os", "1.2.3", preflight.ROOT_PACK_FILES),
        package,
    )


def test_root_pack_rejects_unexpected_runtime_payload() -> None:
    package = {"name": "tess-os", "version": "1.2.3"}
    payload = _pack_payload(
        "tess-os",
        "1.2.3",
        preflight.ROOT_PACK_FILES | {".tess/bin/tessctl"},
    )

    with pytest.raises(preflight.PreflightError, match="root metadata pack changed"):
        preflight.validate_pack_record("root", payload, package)


def test_create_tess_pack_rejects_secret_path() -> None:
    paths = set(preflight.PACK_RULES["create-tess"]["required"]) | {"src/.env.production"}
    payload = _pack_payload("create-tess", "1.2.3", paths)

    with pytest.raises(preflight.PreflightError, match="forbidden"):
        preflight.validate_pack_record(
            "create-tess",
            payload,
            {"name": "create-tess", "version": "1.2.3"},
        )


def test_pack_manifest_rejects_parent_traversal_shape() -> None:
    paths = set(preflight.PACK_RULES["create-tess"]["required"]) | {"src/../unexpected.js"}

    with pytest.raises(preflight.PreflightError, match="forbidden"):
        preflight.validate_pack_record(
            "create-tess",
            _pack_payload("create-tess", "1.2.3", paths),
            {"name": "create-tess", "version": "1.2.3"},
        )


def test_gui_publication_toggle_is_a_release_blocker(tmp_path: Path) -> None:
    repo = _metadata_repo(tmp_path)
    gui = json.loads((repo / "gui" / "package.json").read_text(encoding="utf-8"))
    gui["private"] = False
    _write_json(repo / "gui" / "package.json", gui)

    _, issues = preflight.metadata_issues(repo, "v1.2.3")

    assert "GUI package must remain private:true" in issues


def test_required_check_accepts_only_success_for_exact_sha() -> None:
    sha = "c" * 40
    payload = {
        "check_runs": [
            {
                "id": 7,
                "name": "secret scan (gitleaks)",
                "head_sha": sha,
                "status": "completed",
                "conclusion": "success",
                "app": {"slug": "github-actions"},
            }
        ]
    }

    preflight.validate_required_checks(payload, sha, ["secret scan (gitleaks)"])


@pytest.mark.parametrize(
    ("head_sha", "conclusion", "app_slug"),
    [("d" * 40, "success", "github-actions"), ("c" * 40, "failure", "github-actions"), ("c" * 40, "success", "other-app")],
)
def test_required_check_rejects_wrong_source_failure_or_wrong_provider(
    head_sha: str, conclusion: str, app_slug: str
) -> None:
    sha = "c" * 40
    payload = {
        "check_runs": [
            {
                "id": 7,
                "name": "secret scan (gitleaks)",
                "head_sha": head_sha,
                "status": "completed",
                "conclusion": conclusion,
                "app": {"slug": app_slug},
            }
        ]
    }

    with pytest.raises(preflight.PreflightError):
        preflight.validate_required_checks(payload, sha, ["secret scan (gitleaks)"])


def test_latest_required_check_rerun_must_be_successful() -> None:
    sha = "c" * 40
    payload = {
        "check_runs": [
            {"id": 7, "name": "secret scan (gitleaks)", "head_sha": sha, "status": "completed", "conclusion": "success", "app": {"slug": "github-actions"}},
            {"id": 8, "name": "secret scan (gitleaks)", "head_sha": sha, "status": "completed", "conclusion": "failure", "app": {"slug": "github-actions"}},
        ]
    }

    with pytest.raises(preflight.PreflightError, match="latest upstream check"):
        preflight.validate_required_checks(payload, sha, ["secret scan (gitleaks)"])


def test_live_workflows_pass_static_release_boundary_audit() -> None:
    preflight.validate_workflows(REPO_ROOT)


def test_workflow_audit_rejects_mutable_action_reference(tmp_path: Path) -> None:
    workflow_dir = tmp_path / ".github" / "workflows"
    shutil.copytree(REPO_ROOT / ".github" / "workflows", workflow_dir)
    release = workflow_dir / "release.yml"
    release.write_text(
        release.read_text(encoding="utf-8").replace(
            "actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5",
            "actions/checkout@v4",
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(preflight.PreflightError, match="not pinned"):
        preflight.validate_workflows(tmp_path)


def test_workflow_audit_rejects_second_or_gui_publish_command(tmp_path: Path) -> None:
    workflow_dir = tmp_path / ".github" / "workflows"
    shutil.copytree(REPO_ROOT / ".github" / "workflows", workflow_dir)
    release = workflow_dir / "release.yml"
    release.write_text(
        release.read_text(encoding="utf-8")
        + "\n# forbidden\n# run: npm publish\n  run: |\n    npm --prefix gui publish\n",
        encoding="utf-8",
    )

    with pytest.raises(preflight.PreflightError, match="exactly one npm publish"):
        preflight.validate_workflows(tmp_path)


def test_workflow_audit_rejects_automatic_npm_publish_trigger(tmp_path: Path) -> None:
    workflow_dir = tmp_path / ".github" / "workflows"
    shutil.copytree(REPO_ROOT / ".github" / "workflows", workflow_dir)
    publish = workflow_dir / "publish-npm.yml"
    publish.write_text(
        publish.read_text(encoding="utf-8").replace(
            "on:\n  workflow_dispatch:",
            "on:\n  push:\n    tags: ['create-tess-v*']\n  workflow_dispatch:",
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(preflight.PreflightError, match="explicit manual"):
        preflight.validate_workflows(tmp_path)


def test_workflow_audit_rejects_tag_push_release_authority(tmp_path: Path) -> None:
    workflow_dir = tmp_path / ".github" / "workflows"
    shutil.copytree(REPO_ROOT / ".github" / "workflows", workflow_dir)
    release = workflow_dir / "release.yml"
    release.write_text(
        release.read_text(encoding="utf-8").replace(
            "on:\n  pull_request:",
            "on:\n  push:\n    tags: ['v*']\n  pull_request:",
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(preflight.PreflightError, match="tag pushes must be inert"):
        preflight.validate_workflows(tmp_path)


def test_workflow_audit_rejects_candidate_controlled_signer_gate(tmp_path: Path) -> None:
    workflow_dir = tmp_path / ".github" / "workflows"
    shutil.copytree(REPO_ROOT / ".github" / "workflows", workflow_dir)
    release = workflow_dir / "release.yml"
    release.write_text(
        release.read_text(encoding="utf-8").replace(
            "control/scripts/release_preflight.py signer",
            "candidate/scripts/release_preflight.py signer",
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(preflight.PreflightError, match="trusted main control"):
        preflight.validate_workflows(tmp_path)


def test_rehearsal_has_no_release_environment_or_release_secrets() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    rehearsal, production = workflow.split("  release_preflight:\n", 1)
    preflight_job, publish_job = production.split("  publish_release:\n", 1)

    assert "pull_request_target" not in workflow
    assert "secrets." not in rehearsal
    assert "environment: release" not in rehearsal
    assert "contents: write" not in rehearsal
    assert "environment: release" in preflight_job
    assert "contents: write" not in preflight_job
    assert "path: control" in preflight_job and "path: candidate" in preflight_job
    assert preflight_job.index("TESS_RELEASE_SIGNER_FINGERPRINT") < preflight_job.index("GH_TOKEN")
    assert "candidate/scripts/release_preflight.py" not in preflight_job
    assert "contents: write" in publish_job
    assert "EXPECTED_TAG_OBJECT" in publish_job
    assert "release tag moved after signed preflight" in publish_job
    assert "candidate/scripts" not in publish_job
    assert not re.search(r"^\s*run:\s*npm\b.*\bpublish\b", production, re.MULTILINE)
