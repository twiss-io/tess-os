"""Authoritative GitHub admission is merge-wrapper-only and source-bound.

These tests use real commit objects and ordered parent lists. They never create
keys, signatures, verdicts, or repository settings. Local/MCP callers remain
diagnostic; only the protected GitHub event context exercises this topology.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest


EVENT_REPOSITORY = "twiss-io/tess-os"
WORKFLOW_SOURCE_REPOSITORY = "twiss-io/tess-gate-workflows"
WORKFLOW_SOURCE_PATH = ".github/workflows/tess-gate.yml"
WORKFLOW_SOURCE_REF = "refs/tags/gate-v1"
WORKFLOW_SOURCE_SHA = "a" * 40


GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "Tess topology test",
    "GIT_AUTHOR_EMAIL": "topology@tess.test",
    "GIT_COMMITTER_NAME": "Tess topology test",
    "GIT_COMMITTER_EMAIL": "topology@tess.test",
}


def _git(root: Path, *args: str, input_text: str | None = None) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args], input=input_text,
        capture_output=True, text=True, env=GIT_ENV,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _commit_all(root: Path, message: str) -> str:
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)
    return _git(root, "rev-parse", "HEAD")


def _commit_tree(root: Path, tree: str, *parents: str, message: str = "wrapper") -> str:
    command = ["commit-tree", tree]
    for parent in parents:
        command.extend(["-p", parent])
    return _git(root, *command, input_text=f"{message}\n")


@pytest.fixture
def graph(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "Tess topology test")
    _git(root, "config", "user.email", "topology@tess.test")
    policy_path = root / "core" / "policy" / "policy.yaml"
    policy_path.parent.mkdir(parents=True)
    unconfigured_policy = {
        "policy": {
            "version": 1,
            "repository_id": EVENT_REPOSITORY,
            "rules": [],
            "hard_floor_rules": [],
        },
    }
    policy_path.write_text(json.dumps(unconfigured_policy), encoding="utf-8")
    (root / "README.md").write_text("bootstrap\n", encoding="utf-8")
    unconfigured_base = _commit_all(root, "unconfigured BASE")
    configured_policy = json.loads(json.dumps(unconfigured_policy))
    configured_policy["policy"]["ci_admission"] = {
        "version": 1,
        "event": "pull_request",
        "workflow_source_repository": WORKFLOW_SOURCE_REPOSITORY,
        "workflow_source_path": WORKFLOW_SOURCE_PATH,
        "workflow_source_ref": WORKFLOW_SOURCE_REF,
        "workflow_source_sha": WORKFLOW_SOURCE_SHA,
    }
    policy_path.write_text(json.dumps(configured_policy), encoding="utf-8")
    (root / "README.md").write_text("base\n", encoding="utf-8")
    base = _commit_all(root, "base")
    (root / "docs").mkdir()
    (root / "docs" / "note.md").write_text("candidate\n", encoding="utf-8")
    attestation = _commit_all(root, "candidate head")
    attestation_tree = _git(root, "rev-parse", f"{attestation}^{{tree}}")
    evaluation = _commit_tree(root, attestation_tree, base, attestation)
    return {
        "root": root,
        "unconfigured_base": unconfigured_base,
        "base": base,
        "attestation": attestation,
        "evaluation": evaluation,
        "attestation_tree": attestation_tree,
        "base_tree": _git(root, "rev-parse", f"{base}^{{tree}}"),
    }


def _set_event(
    monkeypatch, graph, *, event_name: str, event: dict,
    github_sha: str, github_ref: str, workflow_ref: str | None = None,
    workflow_sha: str = WORKFLOW_SOURCE_SHA,
    github_repository: str = EVENT_REPOSITORY,
):
    root = graph["root"]
    event_path = root / "event.json"
    event_path.write_text(json.dumps(event), encoding="utf-8")
    values = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_JOB": "ship-gate",
        "GITHUB_EVENT_NAME": event_name,
        "GITHUB_EVENT_PATH": str(event_path),
        "GITHUB_REPOSITORY": github_repository,
        "GITHUB_REF": github_ref,
        "GITHUB_SHA": github_sha,
        "GITHUB_WORKFLOW_REF": workflow_ref or (
            f"{WORKFLOW_SOURCE_REPOSITORY}/{WORKFLOW_SOURCE_PATH}@"
            f"{WORKFLOW_SOURCE_REF}"
        ),
        "GITHUB_WORKFLOW_SHA": workflow_sha,
        "TESS_JOB_CONTEXT_JSON": json.dumps({
            "workflow_ref": workflow_ref or (
                f"{WORKFLOW_SOURCE_REPOSITORY}/{WORKFLOW_SOURCE_PATH}@"
                f"{WORKFLOW_SOURCE_REF}"
            ),
            "workflow_sha": workflow_sha,
            "workflow_repository": WORKFLOW_SOURCE_REPOSITORY,
            "workflow_file_path": WORKFLOW_SOURCE_PATH,
        }),
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return event_path


def _pr_event(graph, *, number: int = 17, base: str | None = None,
              attestation: str | None = None) -> dict:
    return {
        "number": number,
        "repository": {"full_name": EVENT_REPOSITORY},
        "pull_request": {
            "base": {
                "ref": "main",
                "sha": base or graph["base"],
                "repo": {"full_name": EVENT_REPOSITORY},
            },
            "head": {"sha": attestation or graph["attestation"]},
        },
    }


def _push_event(graph, *, base: str | None = None,
                evaluation: str | None = None, ref: str = "refs/heads/main") -> dict:
    return {
        "ref": ref,
        "before": base or graph["base"],
        "after": evaluation or graph["evaluation"],
        "repository": {"full_name": EVENT_REPOSITORY},
    }


def test_exact_two_parent_pr_wrapper_is_authoritative(engine, graph, monkeypatch):
    assert WORKFLOW_SOURCE_REPOSITORY != EVENT_REPOSITORY
    event_name = "pull_request"
    event = _pr_event(graph)
    github_ref = "refs/pull/17/merge"
    _set_event(
        monkeypatch, graph, event_name=event_name, event=event,
        github_sha=graph["evaluation"], github_ref=github_ref,
    )

    authoritative, reason, topology = engine._gate_ci_event_provenance(
        graph["root"], graph["base"], graph["evaluation"],
    )

    assert authoritative is True
    assert reason is None
    assert topology == {
        "base_sha": graph["base"],
        "attestation_head_sha": graph["attestation"],
        "evaluation_head_sha": graph["evaluation"],
    }


@pytest.mark.parametrize(
    "shape",
    ["fast_forward", "squash", "rebase", "octopus", "reordered", "tree_mismatch"],
)
def test_noncanonical_merge_shapes_fail_closed(engine, graph, monkeypatch, shape):
    root = graph["root"]
    if shape == "fast_forward":
        evaluation = graph["attestation"]
    elif shape in ("squash", "rebase"):
        (root / "docs" / "note.md").write_text(f"{shape}\n", encoding="utf-8")
        evaluation = _commit_all(root, f"one-parent {shape}-like commit")
    elif shape == "octopus":
        other = _commit_tree(root, graph["base_tree"], graph["base"], message="other")
        evaluation = _commit_tree(
            root, graph["attestation_tree"], graph["base"], graph["attestation"], other,
        )
    elif shape == "reordered":
        evaluation = _commit_tree(
            root, graph["attestation_tree"], graph["attestation"], graph["base"],
        )
    else:
        evaluation = _commit_tree(
            root, graph["base_tree"], graph["base"], graph["attestation"],
        )
    event = _pr_event(graph)
    _set_event(
        monkeypatch, graph, event_name="pull_request", event=event,
        github_sha=evaluation, github_ref="refs/pull/17/merge",
    )

    authoritative, reason, topology = engine._gate_ci_event_provenance(
        root, graph["base"], evaluation,
    )

    assert authoritative is False
    assert topology is None
    assert reason.startswith("CI_MERGE_TOPOLOGY_INVALID:")


def test_divergent_attestation_head_fails_closed(engine, graph, monkeypatch):
    divergent = _commit_tree(
        graph["root"], graph["attestation_tree"], message="unrelated root",
    )
    evaluation = _commit_tree(
        graph["root"], graph["attestation_tree"], graph["base"], divergent,
    )
    event = _pr_event(graph, attestation=divergent)
    _set_event(
        monkeypatch, graph, event_name="pull_request", event=event,
        github_sha=evaluation, github_ref="refs/pull/17/merge",
    )

    authoritative, reason, _ = engine._gate_ci_event_provenance(
        graph["root"], graph["base"], evaluation,
    )

    assert authoritative is False
    assert "strictly up to date" in reason


@pytest.mark.parametrize(
    ("event_name", "github_ref", "expected_prefix"),
    [
        ("pull_request", "refs/heads/main", "CI_EVENT_REF_MISMATCH:"),
        ("pull_request", "refs/pull/18/merge", "CI_EVENT_REF_MISMATCH:"),
        ("push", "refs/tags/v1.0.0", "CI_PR_EVENT_REQUIRED:"),
    ],
)
def test_arbitrary_ref_or_pr_number_is_rejected(
    engine, graph, monkeypatch, event_name, github_ref, expected_prefix,
):
    event = _pr_event(graph) if event_name == "pull_request" else _push_event(
        graph, ref="refs/tags/v1.0.0",
    )
    _set_event(
        monkeypatch, graph, event_name=event_name, event=event,
        github_sha=graph["evaluation"], github_ref=github_ref,
    )

    authoritative, reason, _ = engine._gate_ci_event_provenance(
        graph["root"], graph["base"], graph["evaluation"],
    )

    assert authoritative is False
    assert reason.startswith(expected_prefix)


@pytest.mark.parametrize("mismatch", ["cli_base", "cli_head", "event_head", "github_sha"])
def test_base_head_event_and_context_races_are_rejected(engine, graph, monkeypatch, mismatch):
    cli_base = graph["base"]
    cli_head = graph["evaluation"]
    github_sha = graph["evaluation"]
    event = _pr_event(graph)
    if mismatch == "cli_base":
        cli_base = graph["attestation"]
    elif mismatch == "cli_head":
        cli_head = graph["attestation"]
    elif mismatch == "event_head":
        event = _pr_event(graph, attestation=graph["base"])
    else:
        github_sha = graph["attestation"]
    _set_event(
        monkeypatch, graph, event_name="pull_request", event=event,
        github_sha=github_sha, github_ref="refs/pull/17/merge",
    )

    authoritative, reason, _ = engine._gate_ci_event_provenance(
        graph["root"], cli_base, cli_head,
    )

    assert authoritative is False
    assert reason.startswith(("CI_EVENT_RANGE_MISMATCH:", "CI_MERGE_TOPOLOGY_INVALID:"))


@pytest.mark.parametrize("target_mismatch", ["event_repository", "github_repository", "base_repository"])
def test_event_target_mismatch_is_rejected(engine, graph, monkeypatch, target_mismatch):
    event = _pr_event(graph)
    github_repository = EVENT_REPOSITORY
    if target_mismatch == "event_repository":
        event["repository"]["full_name"] = "attacker/tess-os"
    elif target_mismatch == "github_repository":
        github_repository = "attacker/tess-os"
    else:
        event["pull_request"]["base"]["repo"]["full_name"] = "attacker/tess-os"
    _set_event(
        monkeypatch, graph, event_name="pull_request", event=event,
        github_sha=graph["evaluation"], github_ref="refs/pull/17/merge",
        github_repository=github_repository,
    )

    authoritative, reason, _ = engine._gate_ci_event_provenance(
        graph["root"], graph["base"], graph["evaluation"],
    )

    assert authoritative is False
    assert reason.startswith(("CI_EVENT_TARGET_MISMATCH:", "CI_EVENT_REF_MISMATCH:"))


@pytest.mark.parametrize("source_mismatch", ["repository", "path", "ref", "sha"])
def test_ruleset_workflow_source_mismatch_is_rejected(
    engine, graph, monkeypatch, source_mismatch,
):
    source_repository = WORKFLOW_SOURCE_REPOSITORY
    source_path = WORKFLOW_SOURCE_PATH
    source_ref = WORKFLOW_SOURCE_REF
    source_sha = WORKFLOW_SOURCE_SHA
    if source_mismatch == "repository":
        source_repository = "attacker/workflows"
    elif source_mismatch == "path":
        source_path = ".github/workflows/spoofed.yml"
    elif source_mismatch == "ref":
        source_ref = "refs/heads/candidate"
    else:
        source_sha = "b" * 40
    workflow_ref = f"{source_repository}/{source_path}@{source_ref}"
    event = _pr_event(graph)
    _set_event(
        monkeypatch, graph, event_name="pull_request", event=event,
        github_sha=graph["evaluation"], github_ref="refs/pull/17/merge",
        workflow_ref=workflow_ref, workflow_sha=source_sha,
    )

    authoritative, reason, topology = engine._gate_ci_event_provenance(
        graph["root"], graph["base"], graph["evaluation"],
    )

    assert authoritative is False
    assert topology is None
    assert reason.startswith("CI_WORKFLOW_SOURCE_MISMATCH:")


def test_same_protected_job_id_from_another_workflow_is_not_authoritative(
    engine, graph, monkeypatch,
):
    """A same-named job does not become authority without the bound workflow path."""
    event = _pr_event(graph)
    _set_event(
        monkeypatch, graph, event_name="pull_request", event=event,
        github_sha=graph["evaluation"], github_ref="refs/pull/17/merge",
        workflow_ref=(
            f"{WORKFLOW_SOURCE_REPOSITORY}/.github/workflows/spoofed.yml@"
            f"{WORKFLOW_SOURCE_REF}"
        ),
    )
    assert os.environ["GITHUB_JOB"] == "ship-gate"

    authoritative, reason, topology = engine._gate_ci_event_provenance(
        graph["root"], graph["base"], graph["evaluation"],
    )

    assert authoritative is False
    assert topology is None
    assert reason.startswith("CI_WORKFLOW_SOURCE_MISMATCH:")


def test_unconfigured_immutable_base_never_authorizes(engine, graph, monkeypatch):
    event = _pr_event(graph, base=graph["unconfigured_base"])
    _set_event(
        monkeypatch, graph, event_name="pull_request", event=event,
        github_sha=graph["evaluation"], github_ref="refs/pull/17/merge",
    )

    authoritative, reason, topology = engine._gate_ci_event_provenance(
        graph["root"], graph["unconfigured_base"], graph["evaluation"],
    )

    assert authoritative is False
    assert topology is None
    assert reason.startswith("CI_TRUST_BOOTSTRAP_REQUIRED:")


@pytest.mark.parametrize("event_value", [None, "push", "pull_request_target"])
def test_ci_admission_event_must_be_explicit_pull_request(
    engine, graph, event_value,
):
    policy_path = graph["root"] / "core" / "policy" / "policy.yaml"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    if event_value is None:
        policy["policy"]["ci_admission"].pop("event")
    else:
        policy["policy"]["ci_admission"]["event"] = event_value
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    invalid_base = _commit_all(graph["root"], "invalid CI admission event")

    config, reason = engine._gate_ci_admission_config_at_base(
        graph["root"], invalid_base,
    )

    assert config is None
    assert reason.startswith("CI_TRUST_BOOTSTRAP_REQUIRED:")
    assert "ci_admission.event" in reason


@pytest.mark.parametrize(
    ("event_name", "expected_prefix"),
    [
        ("push", "CI_PR_EVENT_REQUIRED:"),
        ("pull_request_target", "CI_PR_EVENT_REQUIRED:"),
        ("workflow_dispatch", "CI_PR_EVENT_REQUIRED:"),
        ("merge_group", "CI_PR_EVENT_REQUIRED:"),
    ],
)
def test_manual_and_merge_queue_events_never_authorize(
    engine, graph, monkeypatch, event_name, expected_prefix,
):
    event = {
        "repository": {"full_name": "twiss-io/tess-os"},
        "inputs": {"base": graph["base"], "head": graph["evaluation"]},
    }
    _set_event(
        monkeypatch, graph, event_name=event_name, event=event,
        github_sha=graph["evaluation"], github_ref="refs/heads/main",
    )

    authoritative, reason, _ = engine._gate_ci_event_provenance(
        graph["root"], graph["base"], graph["evaluation"],
    )

    assert authoritative is False
    assert reason.startswith(expected_prefix)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("workflow_ref", "attacker/workflows/.github/workflows/tess-gate.yml@refs/heads/main"),
        ("workflow_sha", "b" * 40),
        ("workflow_repository", "attacker/workflows"),
        ("workflow_file_path", ".github/workflows/spoofed.yml"),
    ],
)
def test_job_workflow_identity_mismatch_is_rejected(
    engine, graph, monkeypatch, field, value,
):
    _set_event(
        monkeypatch, graph, event_name="pull_request", event=_pr_event(graph),
        github_sha=graph["evaluation"], github_ref="refs/pull/17/merge",
    )
    job_context = json.loads(os.environ["TESS_JOB_CONTEXT_JSON"])
    job_context[field] = value
    monkeypatch.setenv("TESS_JOB_CONTEXT_JSON", json.dumps(job_context))

    authoritative, reason, topology = engine._gate_ci_event_provenance(
        graph["root"], graph["base"], graph["evaluation"],
    )

    assert authoritative is False
    assert topology is None
    assert reason.startswith("CI_WORKFLOW_SOURCE_MISMATCH:")


def _set_post_merge_event(monkeypatch, graph, *, event: dict | None = None):
    root = graph["root"]
    event = event or _push_event(graph)
    event_path = root / "post-merge-event.json"
    event_path.write_text(json.dumps(event), encoding="utf-8")
    workflow_ref = (
        f"{EVENT_REPOSITORY}/.github/workflows/tess-post-merge-audit.yml@"
        "refs/heads/main"
    )
    values = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_JOB": "post-merge-audit",
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_EVENT_PATH": str(event_path),
        "GITHUB_REPOSITORY": EVENT_REPOSITORY,
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_SHA": graph["evaluation"],
        "GITHUB_WORKFLOW_REF": workflow_ref,
        "GITHUB_WORKFLOW_SHA": graph["evaluation"],
        "TESS_JOB_CONTEXT_JSON": json.dumps({
            "workflow_ref": workflow_ref,
            "workflow_sha": graph["evaluation"],
            "workflow_repository": EVENT_REPOSITORY,
            "workflow_file_path": ".github/workflows/tess-post-merge-audit.yml",
        }),
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_post_merge_audit_validates_landed_two_parent_topology(
    engine, graph, monkeypatch,
):
    _set_post_merge_event(monkeypatch, graph)

    valid, reason, topology = engine._gate_post_merge_event_provenance(
        graph["root"], graph["base"], graph["evaluation"],
    )

    assert valid is True
    assert reason is None
    assert topology == {
        "base_sha": graph["base"],
        "attestation_head_sha": graph["attestation"],
        "evaluation_head_sha": graph["evaluation"],
    }


def test_post_merge_audit_rejects_non_merge_landed_head(engine, graph, monkeypatch):
    event = _push_event(graph, evaluation=graph["attestation"])
    _set_post_merge_event(monkeypatch, graph, event=event)
    monkeypatch.setenv("GITHUB_SHA", graph["attestation"])
    monkeypatch.setenv("GITHUB_WORKFLOW_SHA", graph["attestation"])
    job_context = json.loads(os.environ["TESS_JOB_CONTEXT_JSON"])
    job_context["workflow_sha"] = graph["attestation"]
    monkeypatch.setenv("TESS_JOB_CONTEXT_JSON", json.dumps(job_context))

    valid, reason, topology = engine._gate_post_merge_event_provenance(
        graph["root"], graph["base"], graph["attestation"],
    )

    assert valid is False
    assert topology is None
    assert reason.startswith("POST_MERGE_TOPOLOGY_INVALID:")


def test_post_merge_audit_output_never_claims_merge_prevention(
    engine, graph, monkeypatch, capsys,
):
    _set_post_merge_event(monkeypatch, graph)
    monkeypatch.setattr(engine, "_gate_diff_paths", lambda *_: ["docs/note.md"])
    monkeypatch.setattr(
        engine, "_gate_run_ship_check",
        lambda *_: {"blocked": False, "reasons": [], "changed_paths": ["docs/note.md"]},
    )
    monkeypatch.setattr(engine, "_trace_record", lambda *args, **kwargs: None)

    with pytest.raises(SystemExit) as stopped:
        engine._cmd_gate_post_merge_audit(
            SimpleNamespace(
                base=graph["base"], head=graph["evaluation"],
                verdict_dirs=None, json_out=True,
            ),
            graph["root"],
        )

    assert stopped.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "phase": "post-merge-audit",
        "audit_passed": True,
        "authoritative": False,
        "prevented_merge": False,
        "reasons": [],
        "changed_paths_count": 1,
    }


def test_post_merge_audit_projects_reasons_and_trace_without_raw_detail(
    engine, graph, capsys,
):
    secret = "POST_MERGE_AUDIT_SECRET_7c5c5b9f"
    raw_path = f"private/{secret}/key.asc"
    result = {
        "audit_passed": False,
        "authoritative": False,
        "prevented_merge": False,
        "reasons": [
            f"no covering APPROVE verdict found for {raw_path}",
            f"UNRECOGNIZED_INTERNAL_DETAIL: {secret}",
        ],
        "changed_paths": [raw_path],
    }

    engine._gate_print_post_merge_audit(result, True)
    json_output = capsys.readouterr().out
    payload = json.loads(json_output)
    assert payload == {
        "phase": "post-merge-audit",
        "audit_passed": False,
        "authoritative": False,
        "prevented_merge": False,
        "reasons": [
            "COVERING_APPROVAL_MISSING: no covering APPROVE verdict found",
            "INTERNAL_ERROR_REDACTED: an internal failure was redacted",
        ],
        "changed_paths_count": 1,
    }

    engine._gate_print_post_merge_audit(result, False)
    text_output = capsys.readouterr().out
    engine._trace_record(
        graph["root"],
        phase="gate-audit",
        action="gate.post-merge-audit",
        outcome="fail",
        exit_code=1,
        duration_s=0.001,
        changed_paths=result["changed_paths"],
        reasons=result["reasons"],
    )
    trace_files = sorted((graph["root"] / ".tess" / "trace" / "runs").glob("*.jsonl"))
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

    for surface in (json_output, text_output, trace_text, otlp_output):
        assert secret not in surface
        assert raw_path not in surface
        assert "COVERING_APPROVAL_MISSING: no covering APPROVE verdict found" in surface
        assert "INTERNAL_ERROR_REDACTED: an internal failure was redacted" in surface


def test_hard_floor_receives_attestation_head_not_evaluation_merge(
    engine, graph, monkeypatch,
):
    captured = {}
    policy = {
        "policy": {
            "version": 1,
            "repository_id": "twiss-io/tess-os",
            "rules": [],
            "hard_floor_rules": [{
                "id": "money",
                "category": "money_movement",
                "description": "test",
                "globs": ["docs/**"],
            }],
            "signoff_keys": {},
            "verifier_keys": {},
        }
    }
    monkeypatch.setattr(engine, "_gate_renderer_admission_prepare", lambda *args: (args[1], []))
    monkeypatch.setattr(engine, "_gate_validate_contracts", lambda *_: [])
    monkeypatch.setattr(engine, "_gate_load_policy", lambda *_: (policy, []))
    monkeypatch.setattr(
        engine, "_gate_load_policy_at_base_with_ref",
        lambda *_: (policy, graph["base"]),
    )
    monkeypatch.setattr(engine, "_gate_load_baseline_signoff_key_blobs", lambda *_: ({}, {}))

    def capture_gap(*args):
        captured["base_shas"] = args[5]
        captured["head_shas"] = args[6]
        return ["sentinel hard-floor block"]

    monkeypatch.setattr(engine, "_gate_hard_floor_gap_report", capture_gap)

    result = engine._gate_run_ship_check(
        graph["root"], ["docs/note.md"], None,
        [graph["evaluation"]], [graph["base"]],
        engine._GATE_ADMISSION_SOURCE_CI_EVENT, [graph["attestation"]],
    )

    assert result["blocked"] is True
    assert captured == {
        "base_shas": [graph["base"]],
        "head_shas": [graph["attestation"]],
    }
