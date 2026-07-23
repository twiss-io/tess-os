"""Public-key path containment diagnostics never reflect rejected values.

These tests are deliberately non-cryptographic: they do not generate keys,
invoke GPG, sign verdicts, or provision trust.  A schema-invalid traversal is
rejected before signature verification, then the same denial is inspected at
every downstream serialization surface that consumes gate reasons.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACTS_SRC = REPO_ROOT / "core" / "contracts"
HAS_GIT = shutil.which("git") is not None
pytestmark = pytest.mark.skipif(not HAS_GIT, reason="git required")

SENTINEL = "TESS_PRIVATE_PUBLIC_KEY_PATH_SENTINEL_7B6D"
ESCAPING_KEY_PATH = f"../{SENTINEL}/reid.asc"


def _git(root: Path, *args: str) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@tess.test",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@tess.test",
    }
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.strip()


def _policy(*, registry: str = "verifier_keys") -> dict:
    name = "Reid" if registry == "verifier_keys" else "Xavier"
    return {
        "policy": {
            "version": 1,
            "repository_id": "test/tess-os",
            "rules": [
                {
                    "id": "prod-src",
                    "description": "test-only governed path",
                    "globs": ["src/prod/**"],
                    "classification": ["prod_touching"],
                    "require_verdict": True,
                    "allowed_verifiers": ["Reid"],
                }
            ],
            "hard_floor_rules": [],
            registry: {
                name: {
                    "fingerprint": "A" * 40,
                    "public_key_file": ESCAPING_KEY_PATH,
                }
            },
        }
    }


def test_sensitive_schema_markers_are_confined_to_both_trust_key_nodes():
    schema = json.loads((CONTRACTS_SRC / "policy.schema.json").read_text(encoding="utf-8"))
    mirror = json.loads(
        (REPO_ROOT / ".tess" / "core" / "contracts" / "policy.schema.json").read_text(
            encoding="utf-8",
        )
    )
    assert schema == mirror
    assert schema["$defs"]["VerifierKeyEntry"]["properties"]["public_key_file"][
        "x-tess-sensitive-diagnostic"
    ] == "verifier-public-key-path"
    assert schema["$defs"]["SignoffKeyEntry"]["properties"]["public_key_file"][
        "x-tess-sensitive-diagnostic"
    ] == "signoff-public-key-path"
    assert json.dumps(schema).count("x-tess-sensitive-diagnostic") == 2


def test_sensitive_marker_cannot_redact_an_unrelated_operator_diagnostic(engine, tmp_path):
    unrelated_schema = {
        "type": "string",
        "pattern": "^expected-operator-value$",
        "x-tess-sensitive-diagnostic": "verifier-public-key-path",
    }
    violations = engine.schema_validate(
        SENTINEL,
        unrelated_schema,
        unrelated_schema,
        tmp_path,
        path="$.operator_visible_field",
    )
    serialized = json.dumps(violations)

    assert SENTINEL in serialized
    assert engine.GATE_KEY_PATH_CONTAINMENT_CODE not in serialized


@pytest.fixture
def redaction_repo(project):
    root = project.root
    shutil.copytree(CONTRACTS_SRC, root / "core" / "contracts")
    (root / "core" / "policy").mkdir(parents=True)
    (root / "core" / "policy" / "policy.yaml").write_text(
        yaml.safe_dump(_policy()), encoding="utf-8",
    )

    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@tess.test")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "commit.gpgsign", "false")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "invalid key path baseline")
    base = _git(root, "rev-parse", "HEAD")

    (root / "src" / "prod").mkdir(parents=True)
    (root / "src" / "prod" / "app.py").write_text(
        "print('governed')\n", encoding="utf-8",
    )
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "governed change")
    head = _git(root, "rev-parse", "HEAD")
    return root, base, head


@pytest.mark.parametrize(
    ("registry", "expected_role"),
    (("verifier_keys", "verifier"), ("signoff_keys", "sign-off")),
)
def test_sensitive_key_path_schema_diagnostic_never_reflects_value(
    engine, tmp_path, registry, expected_role,
):
    schema = engine.load_contract_schema(REPO_ROOT, "policy")
    violations = engine.schema_validate(
        _policy(registry=registry),
        schema,
        schema,
        REPO_ROOT / "core" / "contracts",
    )
    serialized = json.dumps(violations, sort_keys=True)

    assert violations
    assert engine.GATE_KEY_PATH_CONTAINMENT_CODE in serialized
    assert expected_role in serialized
    assert SENTINEL not in serialized
    assert ESCAPING_KEY_PATH not in serialized


def test_gate_key_path_denial_redacts_all_reason_serializations(
    engine, redaction_repo, capsys,
):
    root, base, head = redaction_repo
    changed_paths = engine._gate_diff_paths(root, base, head)
    result = engine._gate_run_ship_check(
        root,
        changed_paths,
        head_shas=[head],
        base_shas=[base],
    )

    assert result["blocked"] is True
    assert any(
        engine.GATE_KEY_PATH_CONTAINMENT_CODE in reason
        for reason in result["reasons"]
    )

    engine._gate_print_result("ci", result, True)
    json_output = capsys.readouterr()
    engine._gate_print_result("ci", result, False)
    text_output = capsys.readouterr()

    engine._trace_record(
        root,
        phase="gate",
        action="gate.ci",
        outcome="block",
        exit_code=1,
        duration_s=0.001,
        changed_paths=changed_paths,
        reasons=result["reasons"],
    )
    trace_files = sorted((root / ".tess" / "trace" / "runs").glob("*.jsonl"))
    assert trace_files
    trace_text = "".join(path.read_text(encoding="utf-8") for path in trace_files)
    trace_events = [
        json.loads(line)
        for path in trace_files
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    otlp_output = json.dumps(
        engine._trace_events_to_otlp_json(trace_events), sort_keys=True,
    )

    mcp_result = engine._mcp_tool_gate_check_paths(
        root,
        {"paths": changed_paths, "base": base, "head": head},
    )
    assert mcp_result["blocked"] is True
    assert mcp_result["authoritative"] is False

    surfaces = {
        "reason_collection": result["reasons"],
        "json_stdout": json_output.out,
        "json_stderr": json_output.err,
        "text_stdout": text_output.out,
        "text_stderr": text_output.err,
        "trace_jsonl": trace_text,
        "trace_otlp": otlp_output,
        "mcp": mcp_result,
    }
    serialized_surfaces = json.dumps(surfaces, sort_keys=True)
    assert SENTINEL not in serialized_surfaces
    assert ESCAPING_KEY_PATH not in serialized_surfaces
    for name in (
        "reason_collection",
        "json_stdout",
        "text_stdout",
        "trace_jsonl",
        "trace_otlp",
        "mcp",
    ):
        assert engine.GATE_KEY_PATH_CONTAINMENT_CODE in json.dumps(surfaces[name])
