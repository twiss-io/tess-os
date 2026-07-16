"""Raw-diff path ingress and governed-transition reverse-direction tests.

These tests never generate, register, or use verifier/sign-off keys.  The
shipped empty registries are intentional: reviewable regular-file changes
reach the normal fail-closed "no covering APPROVE verdict" result, while
unreviewable path/type/mode transitions stop categorically before verdicts.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest

from conftest import ENGINE_SRC, REPO_ROOT


HAS_GIT = shutil.which("git") is not None
pytestmark = pytest.mark.skipif(not HAS_GIT, reason="git required")


def _git(
    root: Path, *args: str, check: bool = True, input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Path Ingress Test",
        "GIT_AUTHOR_EMAIL": "path-ingress@tess.test",
        "GIT_COMMITTER_NAME": "Path Ingress Test",
        "GIT_COMMITTER_EMAIL": "path-ingress@tess.test",
    }
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        input=input_bytes,
        capture_output=True,
        env=env,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"git {args!r} failed:\n"
            f"{result.stderr.decode('utf-8', errors='replace')}\n"
            f"{result.stdout.decode('utf-8', errors='replace')}"
        )
    return result


def _git_text(root: Path, *args: str) -> str:
    return _git(root, *args).stdout.decode("ascii").strip()


def _commit_all(root: Path, message: str) -> str:
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)
    return _git_text(root, "rev-parse", "HEAD")


def _commit_index(root: Path, message: str) -> str:
    _git(root, "commit", "-q", "-m", message)
    return _git_text(root, "rev-parse", "HEAD")


def _repo(tmp_path: Path, *, object_format: str = "sha1") -> tuple[Path, str]:
    root = tmp_path / f"repo-{object_format}"
    root.mkdir()
    init_args = ["init", "-q", "-b", "main"]
    if object_format != "sha1":
        init_args.insert(1, f"--object-format={object_format}")
    init = _git(root, *init_args, check=False)
    if init.returncode != 0:
        pytest.skip(f"Git does not support {object_format} repositories")
    _git(root, "config", "user.email", "path-ingress@tess.test")
    _git(root, "config", "user.name", "Path Ingress Test")
    _git(root, "config", "commit.gpgsign", "false")

    engine_path = root / ".tess" / "bin" / "tessctl"
    engine_path.parent.mkdir(parents=True)
    shutil.copy2(ENGINE_SRC, engine_path)
    os.chmod(engine_path, 0o755)
    shutil.copytree(REPO_ROOT / "core" / "contracts", root / "core" / "contracts")
    (root / "core" / "policy").mkdir(parents=True)
    shutil.copy2(
        REPO_ROOT / "core" / "policy" / "policy.yaml",
        root / "core" / "policy" / "policy.yaml",
    )
    fixtures = root / "core" / "policy" / "fixtures"
    fixtures.mkdir()
    (fixtures / "existing.txt").write_text("baseline\n", encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "target.txt").write_text("target\n", encoding="utf-8")
    return root, _commit_all(root, "path-ingress baseline")


def _run_gate(
    root: Path, base: str, head: str, *, phase: str = "ci", as_json: bool = True,
) -> subprocess.CompletedProcess:
    args = [
        sys.executable,
        str(root / ".tess" / "bin" / "tessctl"),
        "gate",
        phase,
        "--base",
        base,
        "--head",
        head,
    ]
    if as_json:
        args.append("--json")
    return subprocess.run(
        args,
        cwd=str(root),
        env={**os.environ, "TESS_ROOT": str(root)},
        capture_output=True,
        text=True,
    )


def _run_pre_push_stdin(
    root: Path, local_sha: str, remote_sha: str, *, record: str | None = None,
) -> subprocess.CompletedProcess:
    stdin_record = record or (
        f"refs/heads/main {local_sha} refs/heads/main {remote_sha}\n"
    )
    return subprocess.run(
        [
            sys.executable,
            str(root / ".tess" / "bin" / "tessctl"),
            "gate",
            "pre-push",
            "--json",
        ],
        cwd=str(root),
        env={**os.environ, "TESS_ROOT": str(root)},
        input=stdin_record,
        capture_output=True,
        text=True,
    )


def _run_pre_commit(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
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


def _payload(result: subprocess.CompletedProcess) -> dict:
    return json.loads(result.stdout)


def _assert_categorical(result: subprocess.CompletedProcess, path: str) -> dict:
    payload = _payload(result)
    assert result.returncode == 1, result.stdout + result.stderr
    assert payload["blocked"] is True
    assert payload["changed_paths_count"] == 1
    assert "changed_paths" not in payload
    assert payload["reasons"] == [
        "GOVERNED_TRANSITION_UNSUPPORTED: a governed Git path transition is unsupported"
    ]
    assert path not in json.dumps(payload)
    assert not any("no covering APPROVE verdict" in r for r in payload["reasons"])
    return payload


def _assert_reviewable_but_unapproved(
    result: subprocess.CompletedProcess, path: str,
) -> dict:
    payload = _payload(result)
    assert result.returncode == 1, result.stdout + result.stderr
    assert payload["blocked"] is True
    assert payload["changed_paths_count"] == 1
    assert "changed_paths" not in payload
    assert payload["reasons"] == [
        "COVERING_APPROVAL_MISSING: no covering APPROVE verdict found"
    ]
    assert path not in json.dumps(payload)
    assert not any(r.startswith("GOVERNED_TRANSITION_UNSUPPORTED:") for r in payload["reasons"])
    return payload


def _index_blob(root: Path, path: str, content: bytes = b"indexed\n", mode: str = "100644") -> None:
    blob = _git(root, "hash-object", "-w", "--stdin", input_bytes=content).stdout.decode("ascii").strip()
    _git(root, "update-index", "--add", "--cacheinfo", mode, blob, path)


def _raw_record(
    width: int,
    *,
    status: str = "A",
    old_mode: str = "000000",
    new_mode: str = "100644",
    old_oid: str | None = None,
    new_oid: str | None = None,
    path: bytes = b"core/policy/fixtures/file.txt",
) -> bytes:
    old_oid = old_oid if old_oid is not None else "0" * width
    new_oid = new_oid if new_oid is not None else "a" * width
    header = f":{old_mode} {new_mode} {old_oid} {new_oid} {status}".encode("ascii")
    return header + b"\0" + path + b"\0"


@pytest.mark.parametrize("width", (40, 64))
def test_raw_parser_accepts_full_sha1_and_sha256_object_ids(engine, width):
    delta = engine._gate_parse_raw_diff(_raw_record(width), width)[0]
    assert delta.status == "A"
    assert len(delta.old_oid) == width
    assert len(delta.new_oid) == width
    assert delta.new_mode == "100644"


@pytest.mark.parametrize(
    "raw,width,needle",
    [
        (_raw_record(40)[:-1], 40, "not NUL-terminated"),
        (b":malformed\0path\0", 40, "malformed raw Git diff header"),
        (_raw_record(40, status="R100"), 40, "unexpected raw Git diff status"),
        (_raw_record(40, old_oid="b" * 40), 40, "absence markers disagree"),
        (_raw_record(40, new_oid="0" * 40), 40, "absence markers disagree"),
        (_raw_record(40, new_mode="040000"), 40, "unsupported mode transition"),
        (_raw_record(40).replace(b"a" * 40, b"a" * 39), 40, "malformed raw Git diff header"),
    ],
)
def test_raw_parser_rejects_malformed_status_mode_and_oid_tuples(engine, raw, width, needle):
    with pytest.raises(engine.GateSpineError, match=needle):
        engine._gate_parse_raw_diff(raw, width)


def test_raw_parser_rejects_duplicate_and_uxb_records_and_filter_captures_them(
    engine, monkeypatch, tmp_path,
):
    record = _raw_record(40)
    with pytest.raises(engine.GateSpineError, match="duplicate path"):
        engine._gate_parse_raw_diff(record + record, 40)
    for status in ("U", "X", "B"):
        with pytest.raises(engine.GateSpineError, match="unexpected raw Git diff status"):
            engine._gate_parse_raw_diff(_raw_record(40, status=status), 40)

    captured = {}

    def fake_git(_root, *args, **_kwargs):
        captured["args"] = args
        return b""

    monkeypatch.setattr(engine, "_gate_run_git_bytes", fake_git)
    monkeypatch.setattr(engine, "_gate_object_id_length", lambda _root: 40)
    assert engine._gate_raw_diff(tmp_path, cached=True) == []
    assert "--diff-filter=ACMRTDUXB" in captured["args"]


@pytest.mark.parametrize("path", (b"/absolute", b"a/../b", b"a//b", b"./a"))
def test_raw_parser_rejects_noncanonical_paths(engine, path):
    with pytest.raises(engine.GateSpineError, match="non-canonical"):
        engine._gate_parse_raw_diff(_raw_record(40, path=path), 40)


def test_raw_parser_accepts_control_characters_and_nfc_unicode(engine):
    paths = [
        b"core/policy/fixtures/line\nbreak.txt",
        b"core/policy/fixtures/tab\tname.txt",
        "core/policy/fixtures/caf\u00e9.txt".encode("utf-8"),
    ]
    for path in paths:
        delta = engine._gate_parse_raw_diff(_raw_record(40, path=path), 40)[0]
        assert delta.path.encode("utf-8") == path


def test_raw_parser_rejects_nfd_and_non_utf8_paths(engine):
    nfd = "core/policy/fixtures/cafe\u0301.txt".encode("utf-8")
    assert unicodedata.normalize("NFC", nfd.decode()) != nfd.decode()
    with pytest.raises(engine.GateSpineError, match="not Unicode NFC-normalized"):
        engine._gate_parse_raw_diff(_raw_record(40, path=nfd), 40)
    with pytest.raises(engine.GateSpineError, match="not valid UTF-8"):
        engine._gate_parse_raw_diff(_raw_record(40, path=b"core/policy/fixtures/\xff"), 40)


def test_governed_nonexecutable_addition_reaches_normal_review(tmp_path):
    root, base = _repo(tmp_path)
    path = "core/policy/fixtures/new-regular.txt"
    file_path = root / path
    file_path.write_text("new\n", encoding="utf-8")
    os.chmod(file_path, 0o644)
    _git(root, "add", "-A")
    pre_commit = _run_pre_commit(root)
    assert pre_commit.returncode == 0, pre_commit.stdout + pre_commit.stderr
    assert _payload(pre_commit)["reasons"] == []
    head = _commit_index(root, "regular addition")
    _assert_reviewable_but_unapproved(_run_gate(root, base, head), path)


def test_governed_executable_addition_is_unavailable_without_mode_bound_evidence(tmp_path):
    root, base = _repo(tmp_path)
    path = "core/policy/fixtures/new-executable"
    file_path = root / path
    file_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    os.chmod(file_path, 0o755)
    _git(root, "add", "-A")

    staged = _assert_categorical(_run_pre_commit(root), path)
    assert any(
        "executable-file additions are unavailable" in reason
        and "binds blob content but not Git status/mode" in reason
        for reason in staged["reasons"]
    )

    head = _commit_index(root, "executable addition")
    shipped = _assert_categorical(_run_gate(root, base, head), path)
    assert any("executable-file additions are unavailable" in reason for reason in shipped["reasons"])


def test_governed_same_mode_regular_modification_reaches_normal_review(tmp_path):
    root, base = _repo(tmp_path)
    path = "core/policy/fixtures/existing.txt"
    (root / path).write_text("modified\n", encoding="utf-8")
    _git(root, "add", "-A")
    pre_commit = _run_pre_commit(root)
    assert pre_commit.returncode == 0, pre_commit.stdout + pre_commit.stderr
    assert _payload(pre_commit)["reasons"] == []
    head = _commit_index(root, "same-mode regular edit")
    _assert_reviewable_but_unapproved(_run_gate(root, base, head), path)


def test_governed_deletion_is_categorical(tmp_path):
    root, base = _repo(tmp_path)
    path = "core/policy/fixtures/existing.txt"
    (root / path).unlink()
    _git(root, "add", "-A")
    staged = _assert_categorical(_run_pre_commit(root), path)
    assert any("status=D" in r for r in staged["reasons"])
    head = _commit_index(root, "delete governed path")
    payload = _assert_categorical(_run_gate(root, base, head), path)
    assert any("status=D" in r for r in payload["reasons"])


def test_governed_rename_away_is_deletion_plus_addition_and_categorical(tmp_path):
    root, base = _repo(tmp_path)
    old = "core/policy/fixtures/existing.txt"
    new = "docs/renamed.txt"
    _git(root, "mv", old, new)
    head = _commit_all(root, "rename governed path away")
    payload = _assert_categorical(_run_gate(root, base, head), old)
    assert {old, new} <= set(payload["changed_paths"])
    assert any("status=D" in r and old in r for r in payload["reasons"])


def test_governed_0644_to_0755_after_review_is_categorical(tmp_path):
    root, base = _repo(tmp_path)
    path = "core/policy/fixtures/existing.txt"
    # The committed 0644 baseline stands for the already-admitted/reviewed
    # state. A later chmod cannot reuse that blob review as mode authority.
    os.chmod(root / path, 0o755)
    # Stage a valid but fully weakened candidate policy beside the chmod.
    # Pre-commit must classify from immutable HEAD, never this candidate.
    (root / "core" / "policy" / "policy.yaml").write_text(
        "policy:\n"
        "  version: 1\n"
        "  rules: []\n"
        "  hard_floor_rules: []\n"
        "  verifier_keys: {}\n"
        "  signoff_keys: {}\n",
        encoding="utf-8",
    )
    _git(root, "add", "-A")
    staged = _assert_categorical(_run_pre_commit(root), path)
    assert any(
        "100644->100755" in r
        and "signed evidence binds blob content" in r
        for r in staged["reasons"]
    )
    head = _commit_index(root, "chmod governed path beside candidate policy weakening")
    payload = _assert_categorical(_run_gate(root, base, head), path)
    assert any(
        "100644->100755" in r
        and "signed evidence binds blob content" in r
        for r in payload["reasons"]
    )


def test_governed_regular_to_symlink_type_change_is_categorical(tmp_path):
    root, base = _repo(tmp_path)
    path = "core/policy/fixtures/existing.txt"
    (root / path).unlink()
    (root / path).symlink_to("../../../docs/target.txt")
    _git(root, "add", "-A")
    _assert_categorical(_run_pre_commit(root), path)
    head = _commit_index(root, "replace governed regular file with symlink")
    payload = _assert_categorical(_run_gate(root, base, head), path)
    assert any("status=T" in r and "100644->120000" in r for r in payload["reasons"])


def test_governed_new_symlink_is_categorical(tmp_path):
    root, base = _repo(tmp_path)
    path = "core/policy/fixtures/new-link"
    (root / path).symlink_to("../../../docs/target.txt")
    _git(root, "add", "-A")
    staged = _assert_categorical(_run_pre_commit(root), path)
    assert any(r.startswith("NONREGULAR_ADDITION_UNSUPPORTED:") for r in staged["reasons"])
    head = _commit_index(root, "add governed symlink")
    payload = _assert_categorical(_run_gate(root, base, head), path)
    assert any("status=A" in r and "000000->120000" in r for r in payload["reasons"])


def test_governed_new_gitlink_is_categorical(tmp_path):
    root, base = _repo(tmp_path)
    path = "core/policy/fixtures/vendor"
    _git(root, "update-index", "--add", "--cacheinfo", "160000", base, path)
    staged = _assert_categorical(_run_pre_commit(root), path)
    assert any(r.startswith("NONREGULAR_ADDITION_UNSUPPORTED:") for r in staged["reasons"])
    head = _commit_index(root, "add governed gitlink")
    payload = _assert_categorical(_run_gate(root, base, head), path)
    assert any("status=A" in r and "000000->160000" in r for r in payload["reasons"])


def test_governed_regular_to_gitlink_type_change_is_categorical(tmp_path):
    root, base = _repo(tmp_path)
    path = "core/policy/fixtures/existing.txt"
    _git(root, "update-index", "--add", "--cacheinfo", "160000", base, path)
    _assert_categorical(_run_pre_commit(root), path)
    head = _commit_index(root, "replace governed regular file with gitlink")
    payload = _assert_categorical(_run_gate(root, base, head), path)
    assert any("status=T" in r and "100644->160000" in r for r in payload["reasons"])


@pytest.mark.parametrize(
    "path",
    (
        "core/policy/fixtures/line\nbreak.txt",
        "core/policy/fixtures/tab\tname.txt",
        "core/policy/fixtures/caf\u00e9.txt",
    ),
)
def test_real_git_hostile_but_valid_paths_are_unambiguous_and_json_safe(tmp_path, path):
    root, base = _repo(tmp_path)
    _index_blob(root, path)
    head = _commit_index(root, "add hostile but valid path")
    result = _run_gate(root, base, head)
    payload = _assert_reviewable_but_unapproved(result, path)
    assert payload["changed_paths"] == [path]
    # json.loads above proves machine output remains a valid single JSON value.

    plain = _run_gate(root, base, head, as_json=False)
    assert plain.returncode == 1
    assert "\\n" in plain.stdout if "\n" in path else True
    assert "\\t" in plain.stdout if "\t" in path else True
    if "\n" in path or "\t" in path:
        assert path not in plain.stdout  # attacker path never becomes raw log framing


def test_real_git_nfd_path_fails_closed_before_policy_matching(tmp_path):
    root, base = _repo(tmp_path)
    path = "core/policy/fixtures/cafe\u0301.txt"
    blob = _git(root, "hash-object", "-w", "--stdin", input_bytes=b"nfd\n").stdout.strip()
    raw_path = path.encode("utf-8")
    record = b"100644 " + blob + b"\t" + raw_path + b"\0"
    _git(
        root, "-c", "core.precomposeunicode=false",
        "update-index", "-z", "--index-info", input_bytes=record,
    )
    indexed = _git(
        root, "-c", "core.precomposeunicode=false", "ls-files", "-z",
    ).stdout.split(b"\0")
    assert raw_path in indexed
    head = _commit_index(root, "add NFD path")
    result = _run_gate(root, base, head)
    payload = _payload(result)
    assert result.returncode == 1
    assert payload["blocked"] is True
    assert payload["changed_paths"] == []
    assert any("not Unicode NFC-normalized" in r for r in payload["reasons"])


def test_real_git_non_utf8_path_fails_closed_before_policy_matching(tmp_path):
    root, base = _repo(tmp_path)
    blob = _git(root, "hash-object", "-w", "--stdin", input_bytes=b"non-utf8\n").stdout.strip()
    path = b"core/policy/fixtures/non-utf8-\xff.txt"
    record = b"100644 " + blob + b"\t" + path + b"\0"
    _git(root, "update-index", "-z", "--index-info", input_bytes=record)
    head = _commit_index(root, "add non-UTF8 path")
    result = _run_gate(root, base, head)
    payload = _payload(result)
    assert result.returncode == 1
    assert payload["blocked"] is True
    assert payload["changed_paths"] == []
    assert any("not valid UTF-8" in r for r in payload["reasons"])


def test_real_sha256_repo_ingress_is_full_width_but_approval_schema_fails_closed(tmp_path):
    root, base = _repo(tmp_path, object_format="sha256")
    assert len(base) == 64
    path = "core/policy/fixtures/sha256.txt"
    (root / path).write_text("sha256\n", encoding="utf-8")
    head = _commit_all(root, "sha256 governed regular add")
    assert len(head) == 64
    _assert_reviewable_but_unapproved(_run_gate(root, base, head), path)

    blob = _git_text(root, "rev-parse", f"{head}:{path}")
    assert len(blob) == 64
    verdict = {
        "verifier": "Reid",
        "output_domain": "Code diff / PR",
        "primary_artifacts_read": [path],
        "findings": [],
        "severity_counts": {"critical": 0, "high": 0, "medium": 0, "low": 0},
        "summary_line": (
            "Reviewed. Found 0 CRITICAL, 0 HIGH, 0 MEDIUM, 0 LOW. "
            "Top priority: none."
        ),
        "disposition": "APPROVE",
        "covers_paths": [path],
        "artifact_hashes": {path: blob},
    }
    verdict_path = root / "missions" / "m1" / "verdicts" / "sha256.verdict.json"
    verdict_path.parent.mkdir(parents=True)
    verdict_path.write_text(json.dumps(verdict, indent=2) + "\n", encoding="utf-8")
    approval_head = _commit_all(root, "add SHA-256 approval-shaped verdict")
    result = _run_gate(root, base, approval_head)
    payload = _payload(result)
    assert result.returncode == 1, result.stdout + result.stderr
    assert payload["blocked"] is True
    assert any(
        "[contract]" in reason
        and "artifact_hashes" in reason
        and "^[0-9a-f]{40}$" in reason
        for reason in payload["reasons"]
    )
    assert any(path in reason and "no covering APPROVE verdict" in reason for reason in payload["reasons"])


def test_pre_push_stdin_uses_raw_delta_and_blocks_deletion(tmp_path):
    root, base = _repo(tmp_path)
    path = "core/policy/fixtures/existing.txt"
    (root / path).unlink()
    head = _commit_all(root, "delete through pre-push stdin")
    _assert_categorical(_run_pre_push_stdin(root, head, base), path)


def test_pre_push_stdin_rejects_malformed_ref_update_record(tmp_path):
    root, base = _repo(tmp_path)
    result = _run_pre_push_stdin(root, base, base, record="only three fields\n")
    payload = _payload(result)
    assert result.returncode == 1
    assert payload["changed_paths"] == []
    assert any("malformed stdin ref-update record" in r for r in payload["reasons"])

    deletion = _run_pre_push_stdin(
        root,
        base,
        base,
        record=f"refs/heads/main {'0' * 40} refs/heads/main {base}\n",
    )
    deletion_payload = _payload(deletion)
    assert deletion.returncode == 1
    assert deletion_payload["changed_paths"] == []
    assert any(
        reason.startswith("REF_DELETION_UNSUPPORTED:")
        and "ref-topology deletion" in reason
        for reason in deletion_payload["reasons"]
    )


def test_pre_push_stdin_validates_sha256_repository_width(tmp_path):
    root, base = _repo(tmp_path, object_format="sha256")
    path = "core/policy/fixtures/stdin-sha256.txt"
    (root / path).write_text("sha256 stdin\n", encoding="utf-8")
    head = _commit_all(root, "sha256 pre-push change")
    assert len(base) == len(head) == 64
    _assert_reviewable_but_unapproved(_run_pre_push_stdin(root, head, base), path)

    # A first push supplies an all-zero remote object ID. The gate must
    # derive this repository format's empty-tree ID (never use the SHA-1
    # constant) and still produce a real review decision over the full tree.
    first_push = _run_pre_push_stdin(root, head, "0" * 64)
    first_payload = _payload(first_push)
    assert first_push.returncode == 1, first_push.stdout + first_push.stderr
    assert ".tess/bin/tessctl" in first_payload["changed_paths"]
    assert any(
        ".tess/bin/tessctl" in r
        and "executable-file additions are unavailable" in r
        for r in first_payload["reasons"]
    )
    assert not any("wrong repository format/length" in r for r in first_payload["reasons"])


def test_staged_ingress_retains_deletion_metadata_and_rejects_real_conflict(engine, tmp_path):
    root, _base = _repo(tmp_path)
    path = "core/policy/fixtures/existing.txt"
    (root / path).unlink()
    _git(root, "add", "-A")
    changed = engine._gate_changed_paths_staged(root)
    assert changed == [path]
    assert len(changed.deltas) == 1
    delta = changed.deltas[0]
    assert delta.status == "D"
    assert delta.old_mode == "100644"
    assert delta.new_mode == "000000"
    assert len(delta.old_oid) == 40
    assert delta.new_oid == "0" * 40

    conflict_parent = tmp_path / "conflict"
    conflict_parent.mkdir()
    conflict_root, _conflict_base = _repo(conflict_parent)
    conflict_path = conflict_root / "core" / "policy" / "fixtures" / "existing.txt"
    _git(conflict_root, "checkout", "-q", "-b", "side")
    conflict_path.write_text("side\n", encoding="utf-8")
    _commit_all(conflict_root, "side conflict")
    _git(conflict_root, "checkout", "-q", "main")
    conflict_path.write_text("main\n", encoding="utf-8")
    _commit_all(conflict_root, "main conflict")
    merge = _git(conflict_root, "merge", "--no-edit", "side", check=False)
    assert merge.returncode != 0, "fixture must retain an unresolved index conflict"

    conflict_result = _run_pre_commit(conflict_root)
    conflict_payload = _payload(conflict_result)
    assert conflict_result.returncode == 1, conflict_result.stdout + conflict_result.stderr
    assert conflict_payload["changed_paths"] == []
    assert any(
        "unexpected raw Git diff status 'U'" in reason
        for reason in conflict_payload["reasons"]
    )


def test_installed_pre_push_hook_uses_same_raw_transition_denial(tmp_path):
    root, base = _repo(tmp_path)
    path = "core/policy/fixtures/existing.txt"
    (root / path).unlink()
    head = _commit_all(root, "hook deletion attack")
    install = subprocess.run(
        [sys.executable, str(root / ".tess" / "bin" / "tessctl"), "gate", "install-hooks"],
        cwd=str(root),
        env={**os.environ, "TESS_ROOT": str(root)},
        capture_output=True,
        text=True,
    )
    assert install.returncode == 0, install.stdout + install.stderr
    hook = root / ".git" / "hooks" / "pre-push"
    result = subprocess.run(
        [str(hook)],
        cwd=str(root),
        env={**os.environ, "TESS_ROOT": str(root)},
        input=f"refs/heads/main {head} refs/heads/main {base}\n",
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "GOVERNED_TRANSITION_UNSUPPORTED:" in result.stdout
    assert path not in result.stdout


def test_mcp_gate_derives_raw_diff_and_rejects_claimed_subset(engine, tmp_path):
    root, base = _repo(tmp_path)
    path = "core/policy/fixtures/existing.txt"
    (root / path).unlink()
    head = _commit_all(root, "MCP deletion attack")

    categorical = engine._mcp_tool_gate_check_paths(
        root, {"paths": [path], "base": base, "head": head},
    )
    assert categorical["blocked"] is True
    assert categorical["changed_paths_count"] == 1
    assert categorical["reasons"] == [
        "GOVERNED_TRANSITION_UNSUPPORTED: a governed Git path transition is unsupported"
    ]
    assert path not in json.dumps(categorical)

    mismatch = engine._mcp_tool_gate_check_paths(
        root, {"paths": ["docs/invented.md"], "base": base, "head": head},
    )
    assert mismatch["blocked"] is True
    assert mismatch["changed_paths_count"] == 1
    assert mismatch["reasons"] == [
        "PATH_SET_MISMATCH: the supplied path set does not match the immutable Git diff"
    ]
    assert path not in json.dumps(mismatch)


def test_ship_check_rejects_governed_path_only_evidence(engine, tmp_path, monkeypatch):
    policy = {
        "policy": {
            "rules": [{
                "id": "governed",
                "description": "test",
                "globs": ["core/policy/**"],
                "classification": ["prod_touching"],
                "require_verdict": True,
                "allowed_verifiers": ["Reid"],
            }],
            "hard_floor_rules": [],
        }
    }
    monkeypatch.setattr(engine, "_gate_validate_contracts", lambda *_: [])
    monkeypatch.setattr(engine, "_gate_load_policy", lambda *_: (policy, []))
    monkeypatch.setattr(engine, "_gate_load_policy_at_base_with_ref", lambda *_: (None, None))
    result = engine._gate_run_ship_check(
        tmp_path, ["core/policy/fixtures/file.txt"], head_shas=[], base_shas=[],
    )
    assert result["blocked"] is True
    assert result["reasons"] == [
        "GOVERNED_TRANSITION_UNSUPPORTED: governed paths have no trusted raw "
        "PathDelta evidence (status, modes, and full object IDs are required)"
    ]
