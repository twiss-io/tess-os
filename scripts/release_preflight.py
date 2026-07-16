#!/usr/bin/env python3
"""Fail-closed release preflight for Tess OS.

This module intentionally has no non-stdlib imports.  Release identity comes
from the signed tag plus protected GitHub environment configuration; candidate
repository files are never accepted as signer allowlists.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Sequence


SEMVER_TAG = re.compile(r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
FINGERPRINT = re.compile(r"^[A-F0-9]{40}(?:[A-F0-9]{24})?$")
ACTION_SHA = re.compile(r"^\s*uses:\s*([^\s#]+)@([0-9a-f]{40})(?:\s*#.*)?$")
ANY_ACTION = re.compile(r"^\s*uses:\s*([^\s#]+)@([^\s#]+)")
NPM_PUBLISH = re.compile(r"(?:^|[;&|]\s*)npm\b[^;&|\n]*\bpublish\b")
REPOSITORY_NAME = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")

GITHUB_ACTIONS_APP_ID = 15368
GITHUB_ACTIONS_APP_SLUG = "github-actions"
GITHUB_ACTIONS_APP_OWNER = "github"
GITLEAKS_VERSION = "8.30.1"
GITLEAKS_LINUX_X64_SHA256 = "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb"

# These immutable commits were resolved from the named tags in the official
# action repositories. A full SHA alone is not sufficient if it points to an
# unreviewed fork or an unexpected upstream commit.
REQUIRED_ACTION_PINS = {
    "actions/checkout": "34e114876b0b11c390a56381ad16ebd13914f8d5",  # v4.3.1
    "actions/setup-python": "a26af69be951a213d495a4c3e4e4022e16d87065",  # v5.6.0
    "actions/setup-node": "49933ea5288caeca8642d1e84afbd3f7d6820020",  # v4.4.0
    "actions/upload-artifact": "ea165f8d65b6e75b540449e92b4886f43607fa02",  # v4.6.2
    "actions/download-artifact": "d3f86a106a0bac45b974a628896c90dbdf5c8093",  # v4.3.0
    "softprops/action-gh-release": "3bb12739c298aeb8a4eeaf626c5b8d85266b0e65",  # v2.6.2
}

ROOT_PACK_FILES = {
    "CHANGELOG.md",
    "CLA.md",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "NOTICE",
    "README.md",
    "SECURITY.md",
    "TRADEMARK.md",
    "package.json",
}

PACK_RULES = {
    "root": {
        "directory": ".",
        "required": ROOT_PACK_FILES,
        "exact": ROOT_PACK_FILES,
        "prefixes": (),
    },
    "create-tess": {
        "directory": "create-tess",
        "required": {
            "LICENSE",
            "NOTICE",
            "README.md",
            "package.json",
            "bin/create-tess.mjs",
            "src/index.js",
        },
        "exact": None,
        "prefixes": ("bin/", "src/"),
    },
    "gui": {
        "directory": "gui",
        "required": {
            "LICENSE",
            "NOTICE",
            "README.md",
            "package.json",
            "bin/tess-gui.mjs",
            "server/index.js",
            "client/index.html",
        },
        "exact": None,
        "prefixes": ("bin/", "server/", "client/"),
    },
}


class PreflightError(RuntimeError):
    """A release invariant is not satisfied."""


def _read_json(path: Path) -> dict:
    def no_duplicates(pairs: list[tuple[str, object]]) -> dict:
        result: dict = {}
        for key, value in pairs:
            if key in result:
                raise PreflightError(f"duplicate JSON key {key!r} in {path}")
            result[key] = value
        return result

    try:
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=no_duplicates)
    except (OSError, json.JSONDecodeError) as exc:
        raise PreflightError(f"cannot read valid JSON from {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise PreflightError(f"expected a JSON object in {path}")
    return data


def _yaml_scalar(raw: str) -> str:
    value = raw.strip()
    if not value:
        return ""
    if value[:1] == value[-1:] and value[:1] in {"'", '"'}:
        return value[1:-1]
    return value


def read_lock_release_fields(path: Path) -> dict[str, str]:
    """Read only the two release fields from the top-level framework mapping.

    A deliberately narrow parser avoids installing a YAML dependency before
    release identity is checked.  Duplicate or structurally surprising fields
    fail closed instead of being interpreted permissively.
    """

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise PreflightError(f"cannot read {path}: {exc}") from exc

    framework_headers = [lineno for lineno, line in enumerate(lines, start=1) if line == "framework:"]
    if len(framework_headers) != 1:
        raise PreflightError(
            f"expected exactly one top-level framework mapping in {path}; found {len(framework_headers)}"
        )

    in_framework = False
    values: dict[str, str] = {}
    wanted = {"version", "upstream_ref"}
    for lineno, line in enumerate(lines, start=1):
        if not in_framework:
            if line == "framework:":
                in_framework = True
            continue
        if line and not line.startswith(" "):
            break
        match = re.match(r"^  ([A-Za-z_][A-Za-z0-9_]*):\s*(.*?)\s*$", line)
        if not match:
            continue
        key, raw = match.groups()
        if key not in wanted:
            continue
        if key in values:
            raise PreflightError(f"duplicate framework.{key} in {path}:{lineno}")
        values[key] = _yaml_scalar(raw)

    missing = sorted(wanted - values.keys())
    if missing:
        raise PreflightError(f"missing lock release field(s): {', '.join(missing)}")
    return values


def version_from_tag(tag: str) -> str:
    match = SEMVER_TAG.fullmatch(tag)
    if not match:
        raise PreflightError(
            f"release tag {tag!r} is invalid; expected stable tag vX.Y.Z"
        )
    return tag[1:]


def _lock_root(lock: dict, path: Path) -> dict:
    root = lock.get("packages", {}).get("")
    if not isinstance(root, dict):
        raise PreflightError(f"{path} is missing packages[''] metadata")
    return root


def metadata_issues(repo: Path, tag: str | None = None) -> tuple[str, list[str]]:
    root_package = _read_json(repo / "package.json")
    create_package = _read_json(repo / "create-tess" / "package.json")
    create_lock_path = repo / "create-tess" / "package-lock.json"
    create_lock = _read_json(create_lock_path)
    gui_package = _read_json(repo / "gui" / "package.json")
    gui_lock_path = repo / "gui" / "package-lock.json"
    gui_lock = _read_json(gui_lock_path)
    lock = read_lock_release_fields(repo / ".tess" / "tess.lock")

    target = version_from_tag(tag) if tag else version_from_tag(f"v{lock['version']}")
    issues: list[str] = []

    release_values = {
        "root package.json version": root_package.get("version"),
        "create-tess/package.json version": create_package.get("version"),
        "create-tess/package-lock.json version": create_lock.get("version"),
        "create-tess lock root version": _lock_root(create_lock, create_lock_path).get("version"),
        ".tess/tess.lock framework.version": lock["version"],
    }
    for label, actual in release_values.items():
        if actual != target:
            issues.append(f"{label} is {actual!r}; expected {target!r}")

    expected_ref = f"v{target}"
    if lock["upstream_ref"] != expected_ref:
        issues.append(
            ".tess/tess.lock framework.upstream_ref is "
            f"{lock['upstream_ref']!r}; expected {expected_ref!r}"
        )

    if root_package.get("name") != "tess-os":
        issues.append("root package name must remain 'tess-os'")
    if root_package.get("private") is True:
        issues.append("root tess-os metadata package must not be private")
    if create_package.get("name") != "create-tess":
        issues.append("create-tess package name must remain 'create-tess'")
    if create_package.get("private") is True:
        issues.append("create-tess must not be private")

    gui_lock_root = _lock_root(gui_lock, gui_lock_path)
    if gui_package.get("name") != "tess-gui":
        issues.append("GUI package name must remain 'tess-gui'")
    if gui_package.get("private") is not True:
        issues.append("GUI package must remain private:true")
    gui_version = gui_package.get("version")
    if gui_lock.get("version") != gui_version or gui_lock_root.get("version") != gui_version:
        issues.append("GUI package and package-lock versions must match")

    return target, issues


def _run(
    args: Sequence[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=str(cwd),
        env=env,
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
    )


def _git(repo: Path, *args: str) -> str:
    result = _run(["git", *args], cwd=repo)
    if result.returncode:
        raise PreflightError(f"git {' '.join(args)} failed")
    return result.stdout.strip()


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise PreflightError(f"{label} must be a positive integer")
    return value


def _full_name(payload: object, label: str) -> str:
    if not isinstance(payload, dict) or not isinstance(payload.get("full_name"), str):
        raise PreflightError(f"{label} is malformed")
    return payload["full_name"]


def _validate_repository(repository: str) -> str:
    if not REPOSITORY_NAME.fullmatch(repository):
        raise PreflightError("GitHub repository must be an exact owner/name value")
    return repository


def _validate_sha(sha: str, label: str) -> str:
    if not FULL_SHA.fullmatch(sha):
        raise PreflightError(f"{label} must be a full lowercase Git SHA")
    return sha


def validate_source(
    repo: Path,
    tag: str,
    *,
    main_ref: str = "origin/main",
    expected_sha: str | None = None,
) -> str:
    version_from_tag(tag)
    if _git(repo, "cat-file", "-t", tag) != "tag":
        raise PreflightError(f"{tag!r} must be an annotated tag object")
    source_sha = _git(repo, "rev-parse", f"{tag}^{{commit}}")
    main_sha = _git(repo, "rev-parse", f"{main_ref}^{{commit}}")
    if source_sha != main_sha:
        raise PreflightError(
            f"tag source {source_sha} does not equal protected {main_ref} HEAD {main_sha}"
        )
    if expected_sha and source_sha != expected_sha:
        raise PreflightError(
            f"tag source {source_sha} does not equal workflow source {expected_sha}"
        )
    return source_sha


def normalize_fingerprint(value: str) -> str:
    normalized = value.strip().upper()
    if not FINGERPRINT.fullmatch(normalized):
        raise PreflightError("release signer fingerprint must be exactly 40 or 64 hex characters")
    return normalized


def parse_primary_fingerprints(colon_output: str) -> list[str]:
    fingerprints: list[str] = []
    want_primary = False
    for line in colon_output.splitlines():
        fields = line.split(":")
        record = fields[0] if fields else ""
        if record == "pub":
            want_primary = True
        elif record == "sub":
            want_primary = False
        elif record == "fpr" and want_primary:
            if len(fields) <= 9 or not fields[9]:
                raise PreflightError("GPG primary fingerprint record is malformed")
            fingerprints.append(fields[9].upper())
            want_primary = False
    return fingerprints


def parse_validsig_primary(status_output: str) -> str:
    signatures: list[str] = []
    for line in status_output.splitlines():
        marker = "[GNUPG:] VALIDSIG "
        if marker not in line:
            continue
        fields = line.split(marker, 1)[1].split()
        if not fields:
            raise PreflightError("GPG VALIDSIG status is malformed")
        # OpenPGP GPG emits the signing fingerprint first and the primary-key
        # fingerprint last.  The latter is the stable allowlist identity when a
        # signing subkey is used.
        signatures.append((fields[-1] if len(fields) >= 10 else fields[0]).upper())
    if len(signatures) != 1:
        raise PreflightError(f"expected exactly one valid tag signature, found {len(signatures)}")
    return normalize_fingerprint(signatures[0])


def validate_signature_status(status: str, expected_fingerprint: str) -> str:
    rejected_statuses = (
        "BADSIG",
        "ERRSIG",
        "EXPSIG",
        "EXPKEYSIG",
        "REVKEYSIG",
        "KEYREVOKED",
        "NO_PUBKEY",
    )
    if any(f"[GNUPG:] {status_name}" in status for status_name in rejected_statuses):
        raise PreflightError("tag signature reports an expired, revoked, missing, or invalid key")
    expected = normalize_fingerprint(expected_fingerprint)
    signing_primary = parse_validsig_primary(status)
    if signing_primary != expected:
        raise PreflightError("valid tag signature does not match the protected fingerprint")
    return signing_primary


def validate_signer(repo: Path, tag: str, public_key: str, expected_fingerprint: str) -> str:
    version_from_tag(tag)
    if not public_key.strip():
        raise PreflightError("TESS_SIGNING_PUBKEY is missing from the protected release environment")
    expected = normalize_fingerprint(expected_fingerprint)

    with tempfile.TemporaryDirectory(prefix="tess-release-gpg-") as temp:
        home = Path(temp)
        home.chmod(0o700)
        env = {**os.environ, "GNUPGHOME": str(home)}
        imported = _run(
            ["gpg", "--batch", "--no-tty", "--import-options", "import-minimal", "--import"],
            cwd=repo,
            env=env,
            input_text=public_key,
        )
        if imported.returncode:
            raise PreflightError("protected release signer public key could not be imported")

        secret_keys = _run(
            ["gpg", "--batch", "--no-tty", "--with-colons", "--list-secret-keys"],
            cwd=repo,
            env=env,
        )
        if secret_keys.returncode not in {0, 2}:
            raise PreflightError("could not inspect imported signer key material")
        if any(line.startswith(("sec:", "ssb:")) for line in secret_keys.stdout.splitlines()):
            raise PreflightError("release environment must contain public key material only")

        public_keys = _run(
            ["gpg", "--batch", "--no-tty", "--with-colons", "--fingerprint", "--list-keys"],
            cwd=repo,
            env=env,
        )
        if public_keys.returncode:
            raise PreflightError("could not inspect imported release signer public key")
        primary = parse_primary_fingerprints(public_keys.stdout)
        if primary != [expected]:
            raise PreflightError("imported public key does not exactly match the protected fingerprint")

        verified = _run(
            [
                "git",
                "-c",
                "gpg.format=openpgp",
                "-c",
                "gpg.program=gpg",
                "verify-tag",
                "--raw",
                tag,
            ],
            cwd=repo,
            env=env,
        )
        status = f"{verified.stdout}\n{verified.stderr}"
        if verified.returncode:
            raise PreflightError("tag signature is not valid under the protected public key")
        validate_signature_status(status, expected)
    return expected


def _forbidden_pack_path(path: str) -> bool:
    lowered = path.lower()
    parts = [part.lower() for part in Path(path).parts]
    if Path(path).is_absolute() or any(part in {".", ".."} for part in parts):
        return True
    if any(part in {"node_modules", ".git", "vault", "secrets", "tess-secrets"} for part in parts):
        return True
    if any(part.startswith(".env") for part in parts):
        return True
    return lowered.endswith((".key", ".pem", ".age", ".env.json"))


def validate_pack_record(component: str, payload: object, package: dict) -> None:
    if component not in PACK_RULES:
        raise PreflightError(f"unknown pack component {component!r}")
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
        raise PreflightError(f"{component}: npm pack must return exactly one package record")
    record = payload[0]
    if record.get("name") != package.get("name") or record.get("version") != package.get("version"):
        raise PreflightError(f"{component}: npm pack identity does not match package.json")
    file_records = record.get("files")
    if not isinstance(file_records, list):
        raise PreflightError(f"{component}: npm pack did not return a file manifest")
    paths = {
        item.get("path")
        for item in file_records
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    }
    if len(paths) != len(file_records):
        raise PreflightError(f"{component}: pack manifest contains malformed or duplicate paths")
    if any(_forbidden_pack_path(path) for path in paths):
        raise PreflightError(f"{component}: pack manifest contains a forbidden secret-bearing path")

    rules = PACK_RULES[component]
    missing = set(rules["required"]) - paths
    if missing:
        raise PreflightError(f"{component}: required pack files missing: {', '.join(sorted(missing))}")
    exact = rules["exact"]
    if exact is not None and paths != set(exact):
        extra = paths - set(exact)
        absent = set(exact) - paths
        detail = []
        if extra:
            detail.append(f"extra={','.join(sorted(extra))}")
        if absent:
            detail.append(f"missing={','.join(sorted(absent))}")
        raise PreflightError(f"{component}: root metadata pack changed ({'; '.join(detail)})")
    if exact is None:
        allowed_exact = {"LICENSE", "NOTICE", "README.md", "package.json"}
        prefixes = tuple(rules["prefixes"])
        unexpected = sorted(path for path in paths if path not in allowed_exact and not path.startswith(prefixes))
        if unexpected:
            raise PreflightError(f"{component}: unexpected pack files: {', '.join(unexpected)}")


def validate_packs(repo: Path) -> None:
    for component, rules in PACK_RULES.items():
        directory = repo / str(rules["directory"])
        package = _read_json(directory / "package.json")
        if component == "gui" and package.get("private") is not True:
            raise PreflightError("GUI package must remain private:true before it can be packed")
        with tempfile.TemporaryDirectory(prefix=f"tess-pack-{component}-") as cache:
            env = {
                **os.environ,
                "npm_config_cache": cache,
                "npm_config_ignore_scripts": "true",
                "npm_config_audit": "false",
                "npm_config_fund": "false",
            }
            result = _run(
                ["npm", "pack", "--dry-run", "--json", "--ignore-scripts"],
                cwd=directory,
                env=env,
            )
        if result.returncode:
            raise PreflightError(f"{component}: npm pack --dry-run failed")
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise PreflightError(f"{component}: npm pack returned invalid JSON") from exc
        validate_pack_record(component, payload, package)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_npm_package_artifact(
    repo: Path,
    tag: str,
    output_dir: Path,
    *,
    repository: str,
    workflow_ref: str,
    run_id: int,
    run_attempt: int,
) -> dict:
    """Pack create-tess without lifecycle scripts and write trusted evidence."""

    repository = _validate_repository(repository)
    run_id = _positive_int(run_id, "workflow run id")
    run_attempt = _positive_int(run_attempt, "workflow run attempt")
    expected_workflow_ref = (
        f"{repository}/.github/workflows/publish-npm.yml@refs/heads/main"
    )
    if workflow_ref != expected_workflow_ref:
        raise PreflightError(
            "npm package evidence must originate from publish-npm.yml on protected main"
        )

    version = version_from_tag(tag)
    package_dir = repo / "create-tess"
    package = _read_json(package_dir / "package.json")
    if package.get("name") != "create-tess" or package.get("version") != version:
        raise PreflightError("create-tess package identity does not match the release tag")
    if package.get("private") is True:
        raise PreflightError("create-tess must remain publishable")

    if output_dir.is_symlink():
        raise PreflightError("npm artifact output directory must not be a symlink")
    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.iterdir()):
        raise PreflightError("npm artifact output directory must start empty")

    with tempfile.TemporaryDirectory(prefix="tess-release-pack-cache-") as cache:
        env = {
            **os.environ,
            "npm_config_cache": cache,
            "npm_config_ignore_scripts": "true",
            "npm_config_audit": "false",
            "npm_config_fund": "false",
        }
        result = _run(
            [
                "npm",
                "pack",
                "--json",
                "--ignore-scripts",
                "--pack-destination",
                str(output_dir),
            ],
            cwd=package_dir,
            env=env,
        )
    if result.returncode:
        raise PreflightError("create-tess: npm pack --ignore-scripts failed")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise PreflightError("create-tess: npm pack returned invalid JSON") from exc
    validate_pack_record("create-tess", payload, package)

    record = payload[0]
    filename = record.get("filename")
    expected_filename = f"create-tess-{version}.tgz"
    if filename != expected_filename:
        raise PreflightError(
            f"create-tess tarball name is {filename!r}; expected {expected_filename!r}"
        )
    tarball = output_dir / expected_filename
    if tarball.is_symlink() or not tarball.is_file() or tarball.resolve().parent != output_dir.resolve():
        raise PreflightError("create-tess tarball is missing or escaped the artifact directory")
    unexpected = sorted(path.name for path in output_dir.iterdir() if path != tarball)
    if unexpected:
        raise PreflightError(
            "npm pack produced unexpected artifact files: " + ", ".join(unexpected)
        )

    source_sha = _validate_sha(_git(repo, "rev-parse", f"{tag}^{{commit}}"), "tag source")
    if _git(repo, "cat-file", "-t", tag) != "tag":
        raise PreflightError("npm artifact source must be an annotated tag")
    tag_object_sha = _validate_sha(
        _git(repo, "rev-parse", f"{tag}^{{tag}}"), "annotated tag object"
    )
    file_records = record.get("files")
    assert isinstance(file_records, list)  # established by validate_pack_record
    manifest = sorted(item["path"] for item in file_records)
    evidence = {
        "schema": 1,
        "repository": repository,
        "workflow_ref": workflow_ref,
        "run_id": run_id,
        "run_attempt": run_attempt,
        "release_tag": tag,
        "source_sha": source_sha,
        "tag_object_sha": tag_object_sha,
        "package": {
            "name": "create-tess",
            "version": version,
            "filename": expected_filename,
            "sha256": _sha256_file(tarball),
            "files": manifest,
        },
    }
    (output_dir / "release-evidence.json").write_text(
        json.dumps(evidence, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return evidence


def workflow_run_commands(path: Path) -> list[tuple[int, str]]:
    """Return executable lines from YAML ``run`` scalars, excluding labels/comments."""

    lines = path.read_text(encoding="utf-8").splitlines()
    commands: list[tuple[int, str]] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        match = re.match(r"^(\s*)run:\s*(.*?)\s*$", line)
        if not match:
            index += 1
            continue
        indent, value = match.groups()
        if value and value not in {"|", "|-", "|+", ">", ">-", ">+"}:
            commands.append((index + 1, value))
            index += 1
            continue
        block_indent = len(indent)
        index += 1
        while index < len(lines):
            child = lines[index]
            if not child.strip():
                index += 1
                continue
            child_indent = len(child) - len(child.lstrip())
            if child_indent <= block_indent:
                break
            stripped = child.strip()
            if not stripped.startswith("#"):
                commands.append((index + 1, stripped))
            index += 1
    return commands


def workflow_job_blocks(text: str) -> dict[str, str]:
    """Split a conventionally formatted Actions workflow into job blocks."""

    lines = text.splitlines()
    try:
        jobs_index = lines.index("jobs:")
    except ValueError as exc:
        raise PreflightError("workflow is missing a top-level jobs mapping") from exc
    blocks: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines[jobs_index + 1 :]:
        if line and not line.startswith(" "):
            break
        match = re.match(r"^  ([A-Za-z_][A-Za-z0-9_-]*):\s*$", line)
        if match:
            current = match.group(1)
            if current in blocks:
                raise PreflightError(f"duplicate workflow job id {current!r}")
            blocks[current] = [line]
        elif current is not None:
            blocks[current].append(line)
    if not blocks:
        raise PreflightError("workflow jobs mapping is empty")
    return {name: "\n".join(block) for name, block in blocks.items()}


def workflow_step_names(job_block: str) -> list[str]:
    return re.findall(r"^\s{6}- name:\s*(.+?)\s*$", job_block, re.MULTILINE)


def validate_workflows(repo: Path) -> None:
    workflow_dir = repo / ".github" / "workflows"
    release_path = workflow_dir / "release.yml"
    release_text = release_path.read_text(encoding="utf-8")
    issues: list[str] = []
    publish_path = workflow_dir / "publish-npm.yml"
    publish_text = publish_path.read_text(encoding="utf-8")
    ci_path = workflow_dir / "ci.yml"
    ci_text = ci_path.read_text(encoding="utf-8")
    if any("pull_request_target" in text for text in (release_text, publish_text, ci_text)):
        issues.append("release-bearing workflows must never use pull_request_target")
    if not re.search(r"^\s*environment:\s*release\s*$", release_text, re.MULTILINE):
        issues.append("release job must use the protected release environment")
    if "secrets.TESS_SIGNING_PUBKEY" not in release_text:
        issues.append("release signer public key must come from protected environment secrets")
    if "vars.TESS_RELEASE_SIGNER_FINGERPRINT" not in release_text:
        issues.append("release signer fingerprint must come from protected environment variables")
    release_trigger = release_text.split("jobs:", 1)[0]
    if "workflow_dispatch:" not in release_trigger or re.search(
        r"^\s{2}push:\s*$", release_trigger, re.MULTILINE
    ):
        issues.append("production release must be manually dispatched; tag pushes must be inert")
    release_production = release_text.split("  release_preflight:", 1)[-1]
    if "github.ref == 'refs/heads/main'" not in release_production:
        issues.append("production release must refuse dispatches outside protected main")
    if "path: control" not in release_production or "path: candidate" not in release_production:
        issues.append("production release must separate trusted control from candidate contents")
    if "control/scripts/release_preflight.py signer" not in release_production:
        issues.append("trusted main control must perform candidate signature verification")
    if "candidate/scripts/release_preflight.py" in release_production:
        issues.append("candidate code must never implement its own release identity gate")
    if "tag_object_sha" not in release_production or "EXPECTED_TAG_OBJECT" not in release_production:
        issues.append("GitHub Release publication must re-check the exact annotated tag object")
    if release_text.count("contents: write") != 1:
        issues.append("exactly one downstream GitHub Release job may hold contents:write")
    if "--workflow-path .github/workflows/ci.yml" not in release_production:
        issues.append("release must bind secret-scan evidence to the exact CI workflow run")

    if not re.search(r"^\s*environment:\s*release\s*$", publish_text, re.MULTILINE):
        issues.append("npm publication must use the protected release environment")
    if "secrets.TESS_SIGNING_PUBKEY" not in publish_text or "vars.TESS_RELEASE_SIGNER_FINGERPRINT" not in publish_text:
        issues.append("npm publication must repeat the protected signer identity check")
    publish_trigger = publish_text.split("jobs:", 1)[0]
    if "workflow_dispatch:" not in publish_trigger or re.search(r"^\s{2}push:\s*$", publish_trigger, re.MULTILINE):
        issues.append("npm publication must remain an explicit manual post-release action")
    if "create-tess-v" in publish_trigger:
        issues.append("independent create-tess tags must not authorize npm publication")
    if "github.ref == 'refs/heads/main'" not in publish_text:
        issues.append("npm publication must refuse dispatches outside protected main")
    if "path: control" not in publish_text or "path: candidate" not in publish_text:
        issues.append("npm publication must separate trusted control from candidate contents")
    if publish_text.count("control/scripts/release_preflight.py signer") < 2:
        issues.append("test and pack jobs must independently verify the npm candidate signer")
    if "candidate/scripts/release_preflight.py" in publish_text:
        issues.append("npm candidate code must never implement its own release identity gate")
    token_binding = re.compile(
        r"(?:secrets\.(?:NPM_TOKEN|NODE_AUTH_TOKEN)|^\s*(?:NPM_TOKEN|NODE_AUTH_TOKEN):)",
        re.MULTILINE,
    )
    if token_binding.search(publish_text):
        issues.append("npm publication must use Trusted Publishing without registry tokens")

    try:
        publish_jobs = workflow_job_blocks(publish_text)
    except PreflightError as exc:
        issues.append(str(exc))
        publish_jobs = {}
    expected_jobs = {"candidate_test", "pack_artifact", "publish_oidc"}
    if set(publish_jobs) != expected_jobs:
        issues.append("npm workflow must contain only candidate_test, pack_artifact, and publish_oidc jobs")
    oidc_jobs = [
        name
        for name, block in publish_jobs.items()
        if re.search(r"^\s*id-token:\s*write\s*$", block, re.MULTILINE)
    ]
    if oidc_jobs != ["publish_oidc"]:
        issues.append("only the minimal publish_oidc job may request id-token:write")
    oidc_block = publish_jobs.get("publish_oidc", "")
    expected_oidc_steps = [
        "Download exact package artifact by immutable artifact id",
        "Set up trusted npm OIDC client",
        "Gate — Trusted Publishing runtime floor",
        "Gate — live tag object and artifact digest immediately before publish",
        "Publish create-tess through npm Trusted Publishing",
    ]
    if workflow_step_names(oidc_block) != expected_oidc_steps:
        issues.append("OIDC publication job must contain only the five reviewed publication steps")
    oidc_step_entries = re.findall(r"^\s{6}-\s+", oidc_block, re.MULTILINE)
    if len(oidc_step_entries) != len(expected_oidc_steps):
        issues.append("OIDC publication job must contain exactly five YAML step entries")
    candidate_execution = (
        r"actions/checkout@",
        r"uses:\s*\./",
        r"\bcandidate(?:/|\b)",
        r"working-directory:",
        r"\bnpm\s+(?:ci|install|test|pack|run|exec)\b",
        r"\bnpx\b",
        r"\bnode\s+[^-]",
        r"\btar\s+.*(?:-x|--extract)",
        r"\bunzip\b",
        r"\b(?:bash|zsh)\b",
        r"\bsh\s+-",
        r"\b(?:curl|wget)\b",
        r"\bpython(?:3)?\s+(?!-)",
        r"(?m)^\s*(?:source|eval)\s+",
        r"(?:^|\s)\./",
    )
    if any(re.search(pattern, oidc_block, re.IGNORECASE) for pattern in candidate_execution):
        issues.append("OIDC publication job must never checkout or execute candidate content")
    for unprivileged in ("candidate_test", "pack_artifact"):
        if "id-token: write" in publish_jobs.get(unprivileged, ""):
            issues.append(f"{unprivileged} must remain OIDC-ineligible")
    if "actions/download-artifact@" not in oidc_block:
        issues.append("OIDC publication must consume only the pinned package artifact")
    if "actions/upload-artifact@" not in publish_jobs.get("pack_artifact", ""):
        issues.append("npm pack job must upload immutable package evidence")
    if "artifact-digest" not in publish_text or "release-evidence.json" not in publish_text:
        issues.append("npm publication must bind artifact-service and tarball digests")
    if "--workflow-path .github/workflows/ci.yml" not in publish_text:
        issues.append("npm publication must bind secret-scan evidence to the exact CI workflow")
    if "--workflow-path .github/workflows/release.yml" not in publish_text:
        issues.append("npm publication must bind GitHub Release evidence to the exact release workflow")
    if "Gate — live tag object and artifact digest immediately before publish" not in oidc_block:
        issues.append("npm publication must immediately re-check the live annotated tag object")
    required_oidc_guards = (
        "artifact-ids: ${{ needs.pack_artifact.outputs.artifact_id }}",
        "merge-multiple: true",
        'artifact.get("digest") == expected_digest',
        'evidence.get("run_attempt") == expected_run_attempt',
        'hmac.compare_digest(actual_sha256, package.get("sha256", ""))',
        'tag_object.get("sha") == expected_tag_object',
        'npm_version="$(npm --version)"',
        "< (11, 5, 1)",
    )
    if any(marker not in oidc_block for marker in required_oidc_guards):
        issues.append("OIDC publication job is missing a reviewed digest, envelope, tag, or runtime guard")

    audited_workflows = [release_path, publish_path, ci_path]
    for path in audited_workflows:
        lines = path.read_text(encoding="utf-8").splitlines()
        if sum(line == "jobs:" for line in lines) != 1:
            issues.append(f"{path.name}: workflow must contain exactly one top-level jobs mapping")
        for lineno, line in enumerate(lines, start=1):
            control_key = re.match(
                r"^\s*(?P<quote>['\"]?)(?P<key>run|uses)(?P=quote)\s*:",
                line,
            )
            if control_key and not line.lstrip().startswith(f"{control_key.group('key')}:"):
                issues.append(
                    f"{path.name}:{lineno}: run/uses keys must use canonical unquoted YAML syntax"
                )
            candidate = ANY_ACTION.match(line)
            if not candidate:
                continue
            action, reference = candidate.groups()
            if action.startswith("./"):
                issues.append(f"{path.name}:{lineno}: local actions are not allowed in trusted workflows")
                continue
            if not ACTION_SHA.match(line):
                issues.append(f"{path.name}:{lineno}: third-party action is not pinned to a full SHA")
                continue
            expected = REQUIRED_ACTION_PINS.get(action)
            if expected is None:
                issues.append(f"{path.name}:{lineno}: action {action!r} is not on the reviewed allowlist")
            elif reference != expected:
                issues.append(f"{path.name}:{lineno}: action {action!r} is not at its reviewed commit")

    if f"GITLEAKS_VERSION: '{GITLEAKS_VERSION}'" not in ci_text:
        issues.append("CI must pin the reviewed Gitleaks version")
    if f"GITLEAKS_SHA256: '{GITLEAKS_LINUX_X64_SHA256}'" not in ci_text:
        issues.append("CI must pin the official Gitleaks linux_x64 SHA-256")
    if "sha256sum --check" not in ci_text:
        issues.append("CI must verify the Gitleaks archive before extraction")
    if re.search(r"curl[^\n]*\|\s*(?:sudo\s+)?tar", ci_text):
        issues.append("CI must never stream an unverified Gitleaks archive into tar")

    publish_lines: list[tuple[Path, int, str]] = []
    for path in sorted(workflow_dir.glob("*.y*ml")):
        for lineno, command in workflow_run_commands(path):
            if NPM_PUBLISH.search(command):
                publish_lines.append((path, lineno, command))
    allowed = [(workflow_dir / "publish-npm.yml", 'npm publish "$PACKAGE_TARBALL" --ignore-scripts --provenance --access public')]
    if len(publish_lines) != 1:
        issues.append("exactly one npm publish command is allowed across workflows")
    elif (publish_lines[0][0], publish_lines[0][2]) != allowed[0]:
        issues.append("the sole npm publish command must be the create-tess OIDC publish command")
    if re.search(r"(?:working-directory:\s*gui|\bcd\s+gui\b|npm\s+--prefix\s+gui)", publish_text):
        issues.append("GUI must never be a publish target")
    final_publish = re.compile(
        r"- name: Publish create-tess through npm Trusted Publishing\s+"
        r"env:\s+PACKAGE_TARBALL:.*?\s+"
        r"run: npm publish \"\$PACKAGE_TARBALL\" --ignore-scripts --provenance --access public",
        re.MULTILINE,
    )
    if not final_publish.search(publish_text):
        issues.append("the only npm publication step must publish the verified exact tarball")

    if issues:
        raise PreflightError("workflow boundary violations:\n- " + "\n- ".join(issues))


def select_workflow_run(
    workflow_payload: object,
    runs_payload: object,
    *,
    repository: str,
    workflow_path: str,
    workflow_name: str,
    event: str,
    branch: str,
    sha: str,
) -> dict:
    repository = _validate_repository(repository)
    _validate_sha(sha, "workflow evidence source")
    if not isinstance(workflow_payload, dict):
        raise PreflightError("GitHub workflow metadata response is malformed")
    workflow_id = _positive_int(workflow_payload.get("id"), "workflow id")
    expected_workflow = {
        "name": workflow_name,
        "path": workflow_path,
        "state": "active",
    }
    for key, expected in expected_workflow.items():
        if workflow_payload.get(key) != expected:
            raise PreflightError(f"workflow metadata {key} is not the expected {expected!r}")

    if not isinstance(runs_payload, dict) or not isinstance(runs_payload.get("workflow_runs"), list):
        raise PreflightError("GitHub workflow-runs response is malformed")
    runs = runs_payload["workflow_runs"]
    total_count = _positive_int(runs_payload.get("total_count"), "workflow run count")
    if total_count != len(runs):
        raise PreflightError("workflow-runs response is incomplete; refusing partial evidence")
    sort_keys: list[tuple[tuple[int, int, int], dict]] = []
    for run in runs:
        if not isinstance(run, dict):
            raise PreflightError("workflow-runs response contains a malformed run")
        sort_keys.append(
            (
                (
                    _positive_int(run.get("run_number"), "workflow run number"),
                    _positive_int(run.get("run_attempt"), "workflow run attempt"),
                    _positive_int(run.get("id"), "workflow run id"),
                ),
                run,
            )
        )
    latest = max(sort_keys, key=lambda item: item[0])[1]
    expected_fields = {
        "name": workflow_name,
        "path": workflow_path,
        "workflow_id": workflow_id,
        "event": event,
        "head_branch": branch,
        "head_sha": sha,
        "status": "completed",
        "conclusion": "success",
    }
    for key, expected in expected_fields.items():
        if latest.get(key) != expected:
            raise PreflightError(f"latest workflow run {key} is not the expected {expected!r}")
    if _full_name(latest.get("repository"), "workflow run repository") != repository:
        raise PreflightError("workflow run belongs to the wrong repository")
    if _full_name(latest.get("head_repository"), "workflow run head repository") != repository:
        raise PreflightError("workflow run head belongs to the wrong repository")
    return {
        "workflow_id": workflow_id,
        "workflow_name": workflow_name,
        "workflow_path": workflow_path,
        "run_id": _positive_int(latest.get("id"), "workflow run id"),
        "run_number": _positive_int(latest.get("run_number"), "workflow run number"),
        "run_attempt": _positive_int(latest.get("run_attempt"), "workflow run attempt"),
        "check_suite_id": _positive_int(latest.get("check_suite_id"), "workflow check suite id"),
        "repository": repository,
        "event": event,
        "branch": branch,
        "sha": sha,
    }


def select_workflow_job(jobs_payload: object, run: dict, job_name: str) -> dict:
    if not isinstance(jobs_payload, dict) or not isinstance(jobs_payload.get("jobs"), list):
        raise PreflightError("GitHub workflow-jobs response is malformed")
    jobs = jobs_payload["jobs"]
    total_count = _positive_int(jobs_payload.get("total_count"), "workflow job count")
    if total_count != len(jobs):
        raise PreflightError("workflow-jobs response is incomplete; refusing partial evidence")
    matches = [job for job in jobs if isinstance(job, dict) and job.get("name") == job_name]
    if len(matches) != 1:
        raise PreflightError(f"expected exactly one workflow job named {job_name!r}")
    job = matches[0]
    expected_fields = {
        "run_id": run["run_id"],
        "run_attempt": run["run_attempt"],
        "workflow_name": run["workflow_name"],
        "head_branch": run["branch"],
        "head_sha": run["sha"],
        "status": "completed",
        "conclusion": "success",
    }
    for key, expected in expected_fields.items():
        if job.get(key) != expected:
            raise PreflightError(f"workflow job {key} is not the expected {expected!r}")
    job_id = _positive_int(job.get("id"), "workflow job id")
    expected_check_url = (
        f"https://api.github.com/repos/{run['repository']}/check-runs/{job_id}"
    )
    if job.get("check_run_url") != expected_check_url:
        raise PreflightError("workflow job check-run URL is not bound to its exact job id")
    return {"job_id": job_id, "job_name": job_name}


def validate_workflow_check_run(check_payload: object, run: dict, job: dict) -> None:
    if not isinstance(check_payload, dict):
        raise PreflightError("GitHub check-run response is malformed")
    expected_fields = {
        "id": job["job_id"],
        "name": job["job_name"],
        "head_sha": run["sha"],
        "status": "completed",
        "conclusion": "success",
    }
    for key, expected in expected_fields.items():
        if check_payload.get(key) != expected:
            raise PreflightError(f"workflow check-run {key} is not the expected {expected!r}")
    suite = check_payload.get("check_suite")
    if not isinstance(suite, dict) or suite.get("id") != run["check_suite_id"]:
        raise PreflightError("workflow check-run belongs to the wrong check suite")
    app = check_payload.get("app")
    if not isinstance(app, dict):
        raise PreflightError("workflow check-run app identity is missing")
    owner = app.get("owner")
    if (
        app.get("id") != GITHUB_ACTIONS_APP_ID
        or app.get("slug") != GITHUB_ACTIONS_APP_SLUG
        or not isinstance(owner, dict)
        or owner.get("login") != GITHUB_ACTIONS_APP_OWNER
    ):
        raise PreflightError("workflow check-run is not owned by the exact GitHub Actions app")
    expected_details = (
        f"https://github.com/{run['repository']}/actions/runs/{run['run_id']}"
        f"/job/{job['job_id']}"
    )
    if check_payload.get("details_url") != expected_details:
        raise PreflightError("workflow check-run details URL is not bound to its exact run and job")
    if not isinstance(check_payload.get("external_id"), str) or not check_payload["external_id"]:
        raise PreflightError("workflow check-run external id is missing")


def validate_actions_evidence(
    workflow_payload: object,
    runs_payload: object,
    jobs_payload: object,
    check_payload: object,
    *,
    repository: str,
    workflow_path: str,
    workflow_name: str,
    event: str,
    branch: str,
    sha: str,
    job_name: str,
) -> dict:
    run = select_workflow_run(
        workflow_payload,
        runs_payload,
        repository=repository,
        workflow_path=workflow_path,
        workflow_name=workflow_name,
        event=event,
        branch=branch,
        sha=sha,
    )
    job = select_workflow_job(jobs_payload, run, job_name)
    validate_workflow_check_run(check_payload, run, job)
    return {**run, **job}


def _github_json(url: str, token: str) -> object:
    if not token:
        raise PreflightError("GitHub token is required for Actions provenance evidence")
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "tess-os-release-preflight",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status != 200:
                raise PreflightError("GitHub Actions API returned a non-success status")
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PreflightError("could not obtain valid GitHub Actions provenance evidence") from exc


def fetch_actions_evidence(
    *,
    repository: str,
    workflow_path: str,
    workflow_name: str,
    event: str,
    branch: str,
    sha: str,
    job_name: str,
    token: str,
) -> dict:
    repository = _validate_repository(repository)
    _validate_sha(sha, "workflow evidence source")
    if Path(workflow_path).parent.as_posix() != ".github/workflows":
        raise PreflightError("workflow evidence path must be inside .github/workflows")
    api = f"https://api.github.com/repos/{repository}"
    workflow_file = urllib.parse.quote(Path(workflow_path).name, safe="")
    workflow_payload = _github_json(f"{api}/actions/workflows/{workflow_file}", token)
    if not isinstance(workflow_payload, dict):
        raise PreflightError("GitHub workflow metadata response is malformed")
    workflow_id = _positive_int(workflow_payload.get("id"), "workflow id")
    query = urllib.parse.urlencode(
        {"branch": branch, "event": event, "head_sha": sha, "per_page": 100}
    )
    runs_payload = _github_json(
        f"{api}/actions/workflows/{workflow_id}/runs?{query}", token
    )
    run = select_workflow_run(
        workflow_payload,
        runs_payload,
        repository=repository,
        workflow_path=workflow_path,
        workflow_name=workflow_name,
        event=event,
        branch=branch,
        sha=sha,
    )
    jobs_payload = _github_json(
        f"{api}/actions/runs/{run['run_id']}/attempts/{run['run_attempt']}/jobs?per_page=100",
        token,
    )
    job = select_workflow_job(jobs_payload, run, job_name)
    check_payload = _github_json(f"{api}/check-runs/{job['job_id']}", token)
    validate_workflow_check_run(check_payload, run, job)
    return {**run, **job}


def validate_live_tag_ref(payload: object, tag: str, expected_tag_object: str) -> None:
    version_from_tag(tag)
    _validate_sha(expected_tag_object, "expected annotated tag object")
    if not isinstance(payload, dict) or payload.get("ref") != f"refs/tags/{tag}":
        raise PreflightError("live tag ref response is malformed or refers to the wrong tag")
    target = payload.get("object")
    if not isinstance(target, dict) or target.get("type") != "tag":
        raise PreflightError("live release ref no longer targets an annotated tag object")
    if target.get("sha") != expected_tag_object:
        raise PreflightError("live release tag moved after validation")


def _emit_issues(target: str, issues: Sequence[str], *, advisory: bool) -> int:
    if not issues:
        print(f"READY: release metadata is aligned at {target}")
        return 0
    label = "NOT READY (advisory)" if advisory else "BLOCKED"
    print(f"{label}: release metadata target is {target}", file=sys.stderr)
    for issue in issues:
        print(f"- {issue}", file=sys.stderr)
    return 0 if advisory else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    metadata = sub.add_parser("metadata", help="validate release version contract")
    metadata.add_argument("--repo", type=Path, default=Path("."))
    metadata.add_argument("--tag")
    metadata.add_argument("--advisory", action="store_true")

    source = sub.add_parser("source", help="prove tag source equals protected main HEAD")
    source.add_argument("--repo", type=Path, default=Path("."))
    source.add_argument("--tag", required=True)
    source.add_argument("--main-ref", default="origin/main")
    source.add_argument("--expected-sha")

    signer = sub.add_parser("signer", help="verify tag under protected signer identity")
    signer.add_argument("--repo", type=Path, default=Path("."))
    signer.add_argument("--tag", required=True)

    packs = sub.add_parser("packs", help="validate credential-free npm pack manifests")
    packs.add_argument("--repo", type=Path, default=Path("."))

    workflows = sub.add_parser("workflows", help="validate workflow trust boundaries")
    workflows.add_argument("--repo", type=Path, default=Path("."))

    actions = sub.add_parser("actions", help="validate an exact GitHub Actions job provenance chain")
    actions.add_argument("--repository", required=True)
    actions.add_argument("--workflow-path", required=True)
    actions.add_argument("--workflow-name", required=True)
    actions.add_argument("--event", required=True)
    actions.add_argument("--branch", required=True)
    actions.add_argument("--sha", required=True)
    actions.add_argument("--job", required=True)

    package = sub.add_parser("package", help="build a no-lifecycle create-tess artifact and evidence")
    package.add_argument("--repo", type=Path, default=Path("."))
    package.add_argument("--tag", required=True)
    package.add_argument("--output", type=Path, required=True)
    package.add_argument("--repository", required=True)
    package.add_argument("--workflow-ref", required=True)
    package.add_argument("--run-id", type=int, required=True)
    package.add_argument("--run-attempt", type=int, required=True)

    tag_ref = sub.add_parser("tag-ref", help="verify a live GitHub tag-ref response")
    tag_ref.add_argument("--input", type=Path, required=True)
    tag_ref.add_argument("--tag", required=True)
    tag_ref.add_argument("--expected-tag-object", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "metadata":
            target, issues = metadata_issues(args.repo.resolve(), args.tag)
            return _emit_issues(target, issues, advisory=args.advisory)
        if args.command == "source":
            sha = validate_source(
                args.repo.resolve(),
                args.tag,
                main_ref=args.main_ref,
                expected_sha=args.expected_sha,
            )
            print(f"OK: tag source exactly matches protected main at {sha}")
            return 0
        if args.command == "signer":
            fingerprint = validate_signer(
                args.repo.resolve(),
                args.tag,
                os.environ.get("TESS_SIGNING_PUBKEY", ""),
                os.environ.get("TESS_RELEASE_SIGNER_FINGERPRINT", ""),
            )
            print(f"OK: tag verified under protected signer {fingerprint}")
            return 0
        if args.command == "packs":
            validate_packs(args.repo.resolve())
            print("OK: root, create-tess, and private GUI pack manifests are safe")
            return 0
        if args.command == "workflows":
            validate_workflows(args.repo.resolve())
            print("OK: release workflow and npm publish boundaries are constrained")
            return 0
        if args.command == "actions":
            evidence = fetch_actions_evidence(
                repository=args.repository,
                workflow_path=args.workflow_path,
                workflow_name=args.workflow_name,
                event=args.event,
                branch=args.branch,
                sha=args.sha,
                job_name=args.job,
                token=os.environ.get("GH_TOKEN", os.environ.get("GITHUB_TOKEN", "")),
            )
            print(
                "OK: exact GitHub Actions provenance established for "
                f"run {evidence['run_id']} attempt {evidence['run_attempt']} "
                f"job {evidence['job_id']}"
            )
            return 0
        if args.command == "package":
            evidence = build_npm_package_artifact(
                args.repo.resolve(),
                args.tag,
                args.output.resolve(),
                repository=args.repository,
                workflow_ref=args.workflow_ref,
                run_id=args.run_id,
                run_attempt=args.run_attempt,
            )
            print(
                "OK: no-lifecycle npm artifact built as "
                f"{evidence['package']['filename']} sha256={evidence['package']['sha256']}"
            )
            return 0
        if args.command == "tag-ref":
            payload = json.loads(args.input.read_text(encoding="utf-8"))
            validate_live_tag_ref(payload, args.tag, args.expected_tag_object)
            print("OK: live annotated tag object is unchanged")
            return 0
    except (OSError, json.JSONDecodeError, PreflightError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
