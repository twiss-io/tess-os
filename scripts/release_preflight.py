#!/usr/bin/env python3
"""Fail-closed release preflight for Tess OS.

This module intentionally has no non-stdlib imports.  Release identity comes
from the signed tag plus protected GitHub environment configuration; candidate
repository files are never accepted as signer allowlists.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable, Sequence


SEMVER_TAG = re.compile(r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
FINGERPRINT = re.compile(r"^[A-F0-9]{40}(?:[A-F0-9]{24})?$")
ACTION_SHA = re.compile(r"^\s*uses:\s*([^\s#]+)@([0-9a-f]{40})(?:\s*#.*)?$")
ANY_ACTION = re.compile(r"^\s*uses:\s*([^\s#]+)@([^\s#]+)")
NPM_PUBLISH = re.compile(r"\bnpm\b[^;&|\n]*\bpublish\b")

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


def validate_workflows(repo: Path) -> None:
    workflow_dir = repo / ".github" / "workflows"
    release_path = workflow_dir / "release.yml"
    release_text = release_path.read_text(encoding="utf-8")
    issues: list[str] = []
    publish_path = workflow_dir / "publish-npm.yml"
    publish_text = publish_path.read_text(encoding="utf-8")
    if "pull_request_target" in release_text or "pull_request_target" in publish_text:
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
    if "control/scripts/release_preflight.py signer" not in publish_text:
        issues.append("trusted main control must perform npm candidate signature verification")
    if "candidate/scripts/release_preflight.py" in publish_text:
        issues.append("npm candidate code must never implement its own release identity gate")
    token_binding = re.compile(
        r"(?:secrets\.(?:NPM_TOKEN|NODE_AUTH_TOKEN)|^\s*(?:NPM_TOKEN|NODE_AUTH_TOKEN):)",
        re.MULTILINE,
    )
    if token_binding.search(publish_text):
        issues.append("npm publication must use Trusted Publishing without registry tokens")

    audited_workflows = [release_path, publish_path]
    for path in audited_workflows:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            candidate = ANY_ACTION.match(line)
            if not candidate or candidate.group(1).startswith("./"):
                continue
            if not ACTION_SHA.match(line):
                issues.append(f"{path.name}:{lineno}: third-party action is not pinned to a full SHA")

    publish_lines: list[tuple[Path, int, str]] = []
    for path in sorted(workflow_dir.glob("*.y*ml")):
        for lineno, command in workflow_run_commands(path):
            if NPM_PUBLISH.search(command):
                publish_lines.append((path, lineno, command))
    allowed = [
        (workflow_dir / "publish-npm.yml", "npm publish --ignore-scripts --access public")
    ]
    if len(publish_lines) != 1:
        issues.append("exactly one npm publish command is allowed across workflows")
    elif (publish_lines[0][0], publish_lines[0][2]) != allowed[0]:
        issues.append("the sole npm publish command must be the create-tess OIDC publish command")
    if not re.search(
        r"^\s*working-directory:\s*candidate/create-tess\s*$", publish_text, re.MULTILINE
    ):
        issues.append("npm publish workflow must remain scoped to create-tess")
    if re.search(r"(?:working-directory:\s*gui|\bcd\s+gui\b|npm\s+--prefix\s+gui)", publish_text):
        issues.append("GUI must never be a publish target")
    final_publish = re.compile(
        r"- name: Publish create-tess through npm Trusted Publishing\s+"
        r"working-directory: candidate/create-tess\s+"
        r"run: npm publish --ignore-scripts --access public",
        re.MULTILINE,
    )
    if not final_publish.search(publish_text):
        issues.append("the only npm publication step must run from create-tess")

    if issues:
        raise PreflightError("workflow boundary violations:\n- " + "\n- ".join(issues))


def validate_required_checks(payload: object, sha: str, required: Iterable[str]) -> None:
    if not isinstance(payload, dict) or not isinstance(payload.get("check_runs"), list):
        raise PreflightError("GitHub check-runs response is malformed")
    runs = payload["check_runs"]
    for name in required:
        matches = [
            run
            for run in runs
            if isinstance(run, dict)
            and run.get("name") == name
            and run.get("head_sha") == sha
            and isinstance(run.get("app"), dict)
            and run["app"].get("slug") == "github-actions"
        ]
        if not matches:
            raise PreflightError(f"required upstream check {name!r} is missing for {sha}")
        try:
            latest = max(matches, key=lambda run: int(run.get("id", 0)))
        except (TypeError, ValueError) as exc:
            raise PreflightError(f"required upstream check {name!r} has a malformed id") from exc
        if latest.get("status") != "completed" or latest.get("conclusion") != "success":
            raise PreflightError(f"latest upstream check {name!r} is not successful for {sha}")


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

    checks = sub.add_parser("checks", help="validate required check runs for exact source")
    checks.add_argument("--input", type=Path, required=True)
    checks.add_argument("--sha", required=True)
    checks.add_argument("--required", action="append", required=True)
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
        if args.command == "checks":
            payload = json.loads(args.input.read_text(encoding="utf-8"))
            validate_required_checks(payload, args.sha, args.required)
            print("OK: required upstream checks succeeded for the exact release source")
            return 0
    except (OSError, json.JSONDecodeError, PreflightError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
