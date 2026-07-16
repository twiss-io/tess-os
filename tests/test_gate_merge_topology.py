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

import pytest


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
    (root / "README.md").write_text("base\n", encoding="utf-8")
    base = _commit_all(root, "base")
    (root / "docs").mkdir()
    (root / "docs" / "note.md").write_text("candidate\n", encoding="utf-8")
    attestation = _commit_all(root, "candidate head")
    attestation_tree = _git(root, "rev-parse", f"{attestation}^{{tree}}")
    evaluation = _commit_tree(root, attestation_tree, base, attestation)
    return {
        "root": root,
        "base": base,
        "attestation": attestation,
        "evaluation": evaluation,
        "attestation_tree": attestation_tree,
        "base_tree": _git(root, "rev-parse", f"{base}^{{tree}}"),
    }


def _set_event(monkeypatch, graph, *, event_name: str, event: dict,
               github_sha: str, github_ref: str, workflow_ref: str | None = None):
    root = graph["root"]
    event_path = root / "event.json"
    event_path.write_text(json.dumps(event), encoding="utf-8")
    repository = "twiss-io/tess-os"
    values = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_JOB": "ship-gate",
        "GITHUB_EVENT_NAME": event_name,
        "GITHUB_EVENT_PATH": str(event_path),
        "GITHUB_REPOSITORY": repository,
        "GITHUB_REF": github_ref,
        "GITHUB_SHA": github_sha,
        "GITHUB_WORKFLOW_REF": workflow_ref or (
            f"{repository}/.github/workflows/tess-gate.yml@{github_ref}"
        ),
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return event_path


def _pr_event(graph, *, number: int = 17, base: str | None = None,
              attestation: str | None = None) -> dict:
    return {
        "number": number,
        "repository": {"full_name": "twiss-io/tess-os"},
        "pull_request": {
            "base": {"ref": "main", "sha": base or graph["base"]},
            "head": {"sha": attestation or graph["attestation"]},
        },
    }


def _push_event(graph, *, base: str | None = None,
                evaluation: str | None = None, ref: str = "refs/heads/main") -> dict:
    return {
        "ref": ref,
        "before": base or graph["base"],
        "after": evaluation or graph["evaluation"],
        "repository": {"full_name": "twiss-io/tess-os"},
    }


@pytest.mark.parametrize("event_name", ["pull_request", "push"])
def test_exact_two_parent_wrapper_is_authoritative(engine, graph, monkeypatch, event_name):
    if event_name == "pull_request":
        event = _pr_event(graph)
        github_ref = "refs/pull/17/merge"
    else:
        event = _push_event(graph)
        github_ref = "refs/heads/main"
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
        ("push", "refs/tags/v1.0.0", "CI_EVENT_REF_MISMATCH:"),
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


@pytest.mark.parametrize("source_mismatch", ["repository", "workflow"])
def test_candidate_event_source_mismatch_is_rejected(
    engine, graph, monkeypatch, source_mismatch,
):
    event = _pr_event(graph)
    workflow_ref = None
    if source_mismatch == "repository":
        event["repository"]["full_name"] = "attacker/tess-os"
    else:
        workflow_ref = "twiss-io/tess-os/.github/workflows/other.yml@refs/pull/17/merge"
    _set_event(
        monkeypatch, graph, event_name="pull_request", event=event,
        github_sha=graph["evaluation"], github_ref="refs/pull/17/merge",
        workflow_ref=workflow_ref,
    )

    authoritative, reason, _ = engine._gate_ci_event_provenance(
        graph["root"], graph["base"], graph["evaluation"],
    )

    assert authoritative is False
    assert reason.startswith("CI_EVENT_SOURCE_REQUIRED:")


def test_same_protected_job_id_from_another_workflow_is_not_authoritative(
    engine, graph, monkeypatch,
):
    """A same-named job does not become authority without the bound workflow path."""
    event = _pr_event(graph)
    _set_event(
        monkeypatch, graph, event_name="pull_request", event=event,
        github_sha=graph["evaluation"], github_ref="refs/pull/17/merge",
        workflow_ref=(
            "twiss-io/tess-os/.github/workflows/spoofed.yml@refs/pull/17/merge"
        ),
    )
    assert os.environ["GITHUB_JOB"] == "ship-gate"

    authoritative, reason, topology = engine._gate_ci_event_provenance(
        graph["root"], graph["base"], graph["evaluation"],
    )

    assert authoritative is False
    assert topology is None
    assert reason.startswith("CI_EVENT_SOURCE_REQUIRED:")


@pytest.mark.parametrize(
    ("event_name", "expected_prefix"),
    [
        ("workflow_dispatch", "CI_EVENT_SOURCE_REQUIRED:"),
        ("merge_group", "MERGE_GROUP_UNSUPPORTED:"),
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
