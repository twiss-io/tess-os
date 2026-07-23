"""Immutable-BASE renderer admission, without keys, signatures, or GPG.

The fixture is deliberately a tiny real Git history.  Every authorization
input is therefore read from committed BASE/HEAD objects, while the imported
engine under test remains the repository's actual tessctl implementation.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml


SOURCE = ".tess/core/templates/agents-md/AGENTS.md.tpl"
OUTPUT = "AGENTS.md"
OUTPUT_SECONDARY = "prompts/AGENTS.md"
LOCK = ".tess/tess.lock"
REGISTRY = ".tess/bin/tessctl"
TARGET_CONFIG = "tess.manifest.json"
POLICY = "core/policy/policy.yaml"
SCHEMA = "core/contracts/policy.schema.json"
VERDICT_SCHEMA = "core/contracts/verdict.schema.json"
FAMILY_GLOB = ".tess/core/templates/agents-md/**"
RULE_ID = "renderer-admission-test"
EVENT_REPOSITORY = "twiss-io/tess-os"
WORKFLOW_SOURCE_REPOSITORY = "twiss-io/tess-gate-workflows"
WORKFLOW_SOURCE_REF = "refs/tags/gate-v1"
WORKFLOW_SOURCE_SHA = "a" * 40


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _write(root: Path, rel: str, content: str | bytes) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


def _policy_document(*, admission: bool) -> dict:
    policy: dict = {
        "version": 1,
        "repository_id": EVENT_REPOSITORY,
        "ci_admission": {
            "version": 1,
            "event": "pull_request",
            "workflow_source_repository": WORKFLOW_SOURCE_REPOSITORY,
            "workflow_source_path": ".github/workflows/tess-gate.yml",
            "workflow_source_ref": WORKFLOW_SOURCE_REF,
            "workflow_source_sha": WORKFLOW_SOURCE_SHA,
        },
        "rules": [],
        "hard_floor_rules": [],
        "verifier_keys": {},
    }
    if not admission:
        return {"policy": policy}

    inventory = {
        "version": 1,
        "rule_id": RULE_ID,
        "lock_file": LOCK,
        "registry_file": REGISTRY,
        "target_config_files": [TARGET_CONFIG],
        "family_globs": [FAMILY_GLOB],
        "mappings": [
            {
                "input_glob": ".tess/core/templates/agents-md/*.tpl",
                "lock_live_glob": OUTPUT,
                "canonical_status": "core-managed",
                "canonical_tier": "normal",
                "canonical_render": None,
                "projections": [
                    {"output_glob": OUTPUT, "mode": "source-copy"},
                    {"output_glob": OUTPUT_SECONDARY, "mode": "source-copy"},
                ],
                "min_matches": 1,
            }
        ],
    }
    inventory_globs = [
        LOCK, REGISTRY, TARGET_CONFIG, FAMILY_GLOB, OUTPUT, OUTPUT_SECONDARY,
    ]
    policy["renderer_admission"] = inventory
    policy["rules"] = [
        {
            "id": RULE_ID,
            "description": "Test-only immutable renderer admission surface.",
            "globs": inventory_globs,
            "classification": ["prod_touching"],
            "require_verdict": True,
            "allowed_verifiers": ["Reid", "Cyra"],
        }
    ]
    return {"policy": policy}


def _write_policy(root: Path, *, admission: bool) -> None:
    _write(
        root,
        POLICY,
        yaml.safe_dump(_policy_document(admission=admission), sort_keys=False),
    )


def _write_lock(root: Path, engine, source: bytes, **row_overrides) -> None:
    row = {
        "status": "core-managed",
        "tier": "normal",
        "base_sha": engine.sha256_bytes(source),
        "live_path": OUTPUT,
    }
    row.update(row_overrides)
    _write(
        root,
        LOCK,
        yaml.safe_dump({"schema": 1, "files": {SOURCE: row}}, sort_keys=False),
    )


def _load_lock(root: Path) -> dict:
    return yaml.safe_load((root / LOCK).read_text(encoding="utf-8"))


def _save_lock(root: Path, lock: dict) -> None:
    _write(root, LOCK, yaml.safe_dump(lock, sort_keys=False))


def _commit(root: Path, message: str, *, stage: bool = True) -> str:
    if stage:
        _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)
    oid = _git(root, "rev-parse", "HEAD")
    assert len(oid) in (40, 64)
    return oid


def _new_history(tmp_path: Path, engine, *, admission: bool = True):
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "Renderer Admission Test")
    _git(root, "config", "user.email", "renderer-admission@example.invalid")

    repo_root = Path(__file__).resolve().parent.parent
    for schema_rel in (SCHEMA, VERDICT_SCHEMA):
        schema_path = root / schema_rel
        schema_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo_root / schema_rel, schema_path)

    source = b"BASE renderer source\n"
    _write(root, SOURCE, source)
    _write(root, OUTPUT, source)
    _write(root, OUTPUT_SECONDARY, source)
    registry_path = root / REGISTRY
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(repo_root / REGISTRY, registry_path)
    registry_path.chmod(0o755)
    shutil.copy2(repo_root / TARGET_CONFIG, root / TARGET_CONFIG)
    # issue #118 / see tests/conftest.py Project.write(): TARGET_CONFIG's own
    # render_targets.enabled is this repo's LIVE, evolving default (grew to
    # include "codex" post-#76) — copying it verbatim makes this synthetic
    # history's enabled-target list silently track whatever this repo
    # currently enables, and this fixture never seeds codex/generic's own
    # core inputs, so it fails loud with "template not found" the moment
    # anything renders. Pin back to the historically-stable ["claude-code"]
    # baseline right after the copy, exactly like conftest.py already does.
    target_config_path = root / TARGET_CONFIG
    target_config = json.loads(target_config_path.read_text(encoding="utf-8"))
    target_config.setdefault("render_targets", {})["enabled"] = ["claude-code"]
    target_config_path.write_text(json.dumps(target_config), encoding="utf-8")
    _write_policy(root, admission=admission)
    _write_lock(root, engine, source)
    base = _commit(root, "BASE")
    return SimpleNamespace(root=root, base=base)


def _admission(engine, history, head: str, base: str | None = None):
    baseline = base or history.base
    changed = engine._gate_diff_paths(history.root, baseline, head)
    return engine._gate_renderer_admission_prepare(
        history.root, changed, [head], [baseline],
        engine._GATE_ADMISSION_SOURCE_CI_EVENT,
    )


def _ship(engine, history, head: str, base: str | None = None):
    baseline = base or history.base
    changed = engine._gate_diff_paths(history.root, baseline, head)
    return engine._gate_run_ship_check(
        history.root, changed, [], [head], [baseline],
        engine._GATE_ADMISSION_SOURCE_CI_EVENT,
    )


def _new_dynamic_claude_history(tmp_path: Path, engine):
    """Seed a BASE whose CLAUDE.md projection has user-space inputs.

    These inputs are deliberately outside the policy's immutable renderer
    family.  The regression below proves that a candidate must not use one of
    them to manufacture a byte-coherent, but unattested, protected output.
    """
    history = _new_history(tmp_path, engine, admission=False)
    source = ".tess/core/templates/CLAUDE.md.tpl"
    output = "CLAUDE.md"
    template = (
        "# {{ASSISTANT_NAME}}\n\n"
        "{{OPERATOR_IDENTITY}}\n"
        "{{OPERATOR_PROFILE}}\n"
        "{{OPERATOR_CHANNELS}}\n"
    )
    _write(history.root, source, template)
    _write(history.root, output, engine.render_claude_md(history.root))

    inventory = {
        "version": 1,
        "rule_id": RULE_ID,
        "lock_file": LOCK,
        "registry_file": REGISTRY,
        "target_config_files": [TARGET_CONFIG],
        "family_globs": [source],
        "mappings": [
            {
                "input_glob": source,
                "lock_live_glob": output,
                "canonical_status": "core-managed",
                "canonical_tier": "normal",
                "canonical_render": "template",
                "projections": [{"output_glob": output, "mode": "engine-render"}],
                "min_matches": 1,
            }
        ],
    }
    policy = _policy_document(admission=False)
    policy["policy"]["renderer_admission"] = inventory
    policy["policy"]["rules"] = [{
        "id": RULE_ID,
        "description": "Test-only immutable renderer admission surface.",
        "globs": [LOCK, REGISTRY, TARGET_CONFIG, source, output],
        "classification": ["prod_touching"],
        "require_verdict": True,
        "allowed_verifiers": ["Reid", "Cyra"],
    }]
    _write(history.root, POLICY, yaml.safe_dump(policy, sort_keys=False))
    _write(history.root, LOCK, yaml.safe_dump({"schema": 1, "files": {
        source: {
            "status": "core-managed",
            "tier": "normal",
            "base_sha": engine.sha256_bytes(template.encode("utf-8")),
            "live_path": output,
            "render": "template",
        }
    }}, sort_keys=False))
    history.base = _commit(history.root, "BASE renderer with dynamic inputs")
    return history


def _new_profile_projection_history(tmp_path: Path, engine):
    """Seed three renderer families that read the shared operator profile."""
    history = _new_history(tmp_path, engine, admission=False)
    sources = {
        ".tess/core/templates/agents-md/AGENTS.md.tpl": "AGENTS {{ASSISTANT_NAME}}\n",
        ".tess/core/commands/status.md": "COMMAND {{ASSISTANT_NAME}}\n",
        ".tess/core/conductor/personality.md": "PERSONA {{PATHWAY}} {{OPERATOR_NAME}}\n",
        ".tess/core/personas/chief-of-staff.md": "BASE PERSONA\n",
    }
    for rel, content in sources.items():
        _write(history.root, rel, content)
    _write(
        history.root,
        "operator/profile.json",
        json.dumps({"assistant_name": "Base", "operator_name": "Operator", "pathway": "chief-of-staff"}) + "\n",
    )
    _write(history.root, "AGENTS.md", engine.render_agents_md(history.root))
    _write(
        history.root, ".codex/prompts/status.md",
        engine._render_command_prompt_bytes(history.root, "status"),
    )
    personality_source = history.root / ".tess/core/conductor/personality.md"
    _write(
        history.root, "conductor/personality.md",
        engine.render_core_to_live(personality_source, history.root / "conductor/personality.md", history.root),
    )

    agents_source = ".tess/core/templates/agents-md/AGENTS.md.tpl"
    command_source = ".tess/core/commands/status.md"
    personality_source_rel = ".tess/core/conductor/personality.md"
    inventory = {
        "version": 1,
        "rule_id": RULE_ID,
        "lock_file": LOCK,
        "registry_file": REGISTRY,
        "target_config_files": [TARGET_CONFIG],
        "family_globs": [agents_source, ".tess/core/commands/*.md", personality_source_rel],
        "mappings": [
            {
                "input_glob": agents_source,
                "lock_live_glob": None,
                "canonical_status": "core-managed",
                "canonical_tier": "normal",
                "canonical_render": None,
                "projections": [{"output_glob": "AGENTS.md", "mode": "engine-render"}],
                "min_matches": 1,
            },
            {
                "input_glob": ".tess/core/commands/*.md",
                "lock_live_glob": ".claude/commands/*.md",
                "lock_name_binding": True,
                "canonical_status": "core-managed",
                "canonical_tier": "normal",
                "canonical_render": None,
                "projections": [{"output_glob": ".codex/prompts/*.md", "mode": "engine-render"}],
                "min_matches": 1,
            },
            {
                "input_glob": personality_source_rel,
                "lock_live_glob": "conductor/personality.md",
                "canonical_status": "core-managed",
                "canonical_tier": "normal",
                "canonical_render": None,
                "projections": [{"output_glob": "conductor/personality.md", "mode": "core-render"}],
                "min_matches": 1,
            },
        ],
    }
    policy = _policy_document(admission=False)
    policy["policy"]["renderer_admission"] = inventory
    policy["policy"]["rules"] = [{
        "id": RULE_ID,
        "description": "Test-only immutable renderer admission surface.",
        "globs": [
            LOCK, REGISTRY, TARGET_CONFIG, agents_source, ".tess/core/commands/*.md",
            personality_source_rel, "AGENTS.md", ".codex/prompts/*.md", "conductor/personality.md",
        ],
        "classification": ["prod_touching"],
        "require_verdict": True,
        "allowed_verifiers": ["Reid", "Cyra"],
    }]
    _write(history.root, POLICY, yaml.safe_dump(policy, sort_keys=False))
    _write(history.root, LOCK, yaml.safe_dump({"schema": 1, "files": {
        agents_source: {
            "status": "core-managed", "tier": "normal",
            "base_sha": engine.sha256_bytes(sources[agents_source].encode("utf-8")),
            "live_path": None, "render": None,
        },
        command_source: {
            "status": "core-managed", "tier": "normal",
            "base_sha": engine.sha256_bytes(sources[command_source].encode("utf-8")),
            "live_path": ".claude/commands/status.md", "render": None,
        },
        personality_source_rel: {
            "status": "core-managed", "tier": "normal",
            "base_sha": engine.sha256_bytes(sources[personality_source_rel].encode("utf-8")),
            "live_path": "conductor/personality.md", "render": None,
        },
    }}, sort_keys=False))
    history.base = _commit(history.root, "BASE profile-driven renderer projections")
    return history


def _assert_requires_verdict(result: dict) -> None:
    assert result["blocked"] is True
    assert any("no covering APPROVE verdict" in reason for reason in result["reasons"])


def test_bootstrap_inventory_cannot_claim_to_self_protect(engine, tmp_path):
    history = _new_history(tmp_path, engine, admission=False)
    _write(history.root, REGISTRY, "candidate adds admission implementation\n")
    _write_policy(history.root, admission=True)
    head = _commit(history.root, "candidate bootstrap")

    changed, reasons = _admission(engine, history, head)

    assert REGISTRY in changed
    assert any("TRUST_BOOTSTRAP_REQUIRED" in reason for reason in reasons)
    assert any("cannot self-protect" in reason for reason in reasons)


@pytest.mark.parametrize("bad_base", ["deadbeef", "f" * 40])
def test_missing_or_nonimmutable_base_fails_closed(engine, tmp_path, bad_base):
    history = _new_history(tmp_path, engine)
    _write(history.root, SOURCE, "candidate\n")
    head = _commit(history.root, "candidate")

    _changed, reasons = engine._gate_renderer_admission_prepare(
        history.root, [SOURCE], [head], [bad_base],
    )

    assert reasons
    assert any(
        token in " ".join(reasons)
        for token in ("BASE_REQUIRED", "failed", "fail-closed")
    )


def test_malformed_base_policy_is_not_candidate_authority(engine, tmp_path):
    history = _new_history(tmp_path, engine, admission=False)
    _write(history.root, POLICY, "policy: [malformed baseline shape\n")
    malformed_base = _commit(history.root, "malformed historical policy")
    _write_policy(history.root, admission=True)
    _write(history.root, REGISTRY, "candidate registry\n")
    head = _commit(history.root, "candidate attempts recovery")

    _changed, reasons = _admission(engine, history, head, malformed_base)

    assert any("TRUST_BOOTSTRAP_REQUIRED" in reason for reason in reasons)


def test_source_hash_and_output_laundering_still_need_base_policy_verdict(engine, tmp_path):
    history = _new_history(tmp_path, engine)
    source = b"candidate source whose hash is honestly refreshed\n"
    _write(history.root, SOURCE, source)
    _write_lock(history.root, engine, source)
    _write(history.root, OUTPUT, "LAUNDERED generated doctrine\n")
    _write(history.root, OUTPUT_SECONDARY, source)
    head = _commit(history.root, "coherent hashes with laundered output")

    _changed, consistency_reasons = _admission(engine, history, head)
    result = _ship(engine, history, head)

    assert any("stale or incoherent" in reason for reason in consistency_reasons)
    _assert_requires_verdict(result)
    assert {SOURCE, LOCK, OUTPUT}.issubset(set(result["changed_paths"]))


@pytest.mark.parametrize(
    ("dynamic_path", "content"),
    [
        ("operator/user-profile.md", "---\ninject: true\n---\n\nINJECTED PROFILE\n"),
        ("operator/profile.json", json.dumps({"assistant_name": "Injected", "operator_name": "Operator", "pathway": "chief-of-staff"}) + "\n"),
        ("CLAUDE.md.local.md", "INJECTED LOCAL SHADOW\n"),
    ],
)
def test_dynamic_claude_inputs_cannot_launder_a_protected_projection(
    engine, tmp_path, dynamic_path, content,
):
    """Only declared renderer-family HEAD blobs may influence a projection.

    Operator state and append-first local shadows are intentionally outside
    the immutable renderer inventory.  A candidate that makes a generated
    CLAUDE.md agree with such a HEAD-side input must therefore be rejected,
    rather than treating the candidate's ambient filesystem as authority.
    """
    history = _new_dynamic_claude_history(tmp_path, engine)
    _write(history.root, dynamic_path, content)
    _write(history.root, "CLAUDE.md", engine.render_claude_md(history.root))
    head = _commit(history.root, f"candidate dynamic input {dynamic_path}")

    _changed, reasons = _admission(engine, history, head)

    assert any(
        "stale or incoherent" in reason and "CLAUDE.md" in reason
        for reason in reasons
    )


def test_candidate_profile_cannot_launder_agents_command_or_conductor_outputs(engine, tmp_path):
    """The profile is ambient for every renderer family, not just CLAUDE.md."""
    history = _new_profile_projection_history(tmp_path, engine)
    _write(
        history.root,
        "operator/profile.json",
        json.dumps({"assistant_name": "Candidate", "operator_name": "Candidate", "pathway": "chief-of-staff"}) + "\n",
    )
    _write(history.root, "AGENTS.md", engine.render_agents_md(history.root))
    _write(
        history.root, ".codex/prompts/status.md",
        engine._render_command_prompt_bytes(history.root, "status"),
    )
    personality_source = history.root / ".tess/core/conductor/personality.md"
    _write(
        history.root, "conductor/personality.md",
        engine.render_core_to_live(personality_source, history.root / "conductor/personality.md", history.root),
    )
    head = _commit(history.root, "candidate profile-driven outputs")

    _changed, reasons = _admission(engine, history, head)

    for output in ("AGENTS.md", ".codex/prompts/status.md", "conductor/personality.md"):
        assert any("stale or incoherent" in reason and output in reason for reason in reasons)


def test_candidate_persona_cannot_launder_conductor_projection(engine, tmp_path):
    """A persona remains BASE-pinned unless a future immutable inventory admits it."""
    history = _new_profile_projection_history(tmp_path, engine)
    _write(history.root, ".tess/core/personas/chief-of-staff.md", "CANDIDATE PERSONA\n")
    personality_source = history.root / ".tess/core/conductor/personality.md"
    _write(
        history.root, "conductor/personality.md",
        engine.render_core_to_live(personality_source, history.root / "conductor/personality.md", history.root),
    )
    head = _commit(history.root, "candidate persona-driven output")

    _changed, reasons = _admission(engine, history, head)

    assert any(
        "stale or incoherent" in reason and "conductor/personality.md" in reason
        for reason in reasons
    )


def test_validated_canonical_source_still_updates_its_projection(engine, tmp_path):
    """The BASE overlay deliberately includes a coherent admitted source upgrade."""
    history = _new_profile_projection_history(tmp_path, engine)
    source = ".tess/core/templates/agents-md/AGENTS.md.tpl"
    upgraded = "UPGRADED AGENTS {{ASSISTANT_NAME}}\n"
    _write(history.root, source, upgraded)
    lock = _load_lock(history.root)
    lock["files"][source]["base_sha"] = engine.sha256_bytes(upgraded.encode("utf-8"))
    _save_lock(history.root, lock)
    _write(history.root, "AGENTS.md", engine.render_agents_md(history.root))
    head = _commit(history.root, "coherent canonical source upgrade")

    _changed, reasons = _admission(engine, history, head)

    assert reasons == []


def test_candidate_cannot_delete_base_lock_row(engine, tmp_path):
    history = _new_history(tmp_path, engine)
    lock = _load_lock(history.root)
    del lock["files"][SOURCE]
    _save_lock(history.root, lock)
    head = _commit(history.root, "delete renderer row")

    _changed, reasons = _admission(engine, history, head)

    assert any("has no mapping row in candidate lock" in reason for reason in reasons)


def test_candidate_cannot_remap_base_live_path(engine, tmp_path):
    history = _new_history(tmp_path, engine)
    lock = _load_lock(history.root)
    lock["files"][SOURCE]["live_path"] = "attacker/AGENTS.md"
    _save_lock(history.root, lock)
    head = _commit(history.root, "remap renderer row")

    _changed, reasons = _admission(engine, history, head)

    assert any("outside canonical BASE mapping" in reason for reason in reasons)
    assert any("ownership field 'live_path'" in reason for reason in reasons)


@pytest.mark.parametrize(
    ("field", "value"),
    [("status", "project-owned"), ("tier", "informational")],
)
def test_candidate_cannot_downgrade_base_ownership(engine, tmp_path, field, value):
    history = _new_history(tmp_path, engine)
    lock = _load_lock(history.root)
    lock["files"][SOURCE][field] = value
    _save_lock(history.root, lock)
    head = _commit(history.root, f"downgrade {field}")

    _changed, reasons = _admission(engine, history, head)

    assert any(f"ownership field '{field}'" in reason for reason in reasons)


@pytest.mark.parametrize(
        ("control_path", "content"),
    [
        (REGISTRY, None),
        (
            TARGET_CONFIG,
            json.dumps({"render_targets": {"enabled": ["claude-code"], "_doc": "candidate"}}) + "\n",
        ),
    ],
)
def test_regular_registry_or_target_config_change_needs_verdict(
    engine, tmp_path, control_path, content,
):
    history = _new_history(tmp_path, engine)
    if content is None:
        content = (history.root / control_path).read_text(encoding="utf-8") + "\n# candidate comment\n"
    _write(history.root, control_path, content)
    head = _commit(history.root, f"change {control_path}")

    _changed, consistency_reasons = _admission(engine, history, head)
    result = _ship(engine, history, head)

    assert consistency_reasons == []
    _assert_requires_verdict(result)
    assert control_path in result["changed_paths"]


def test_invalid_candidate_target_config_fails_consistency(engine, tmp_path):
    history = _new_history(tmp_path, engine)
    _write(history.root, TARGET_CONFIG, "not-json\n")
    head = _commit(history.root, "invalid target config")

    _changed, reasons = _admission(engine, history, head)

    assert any("target config" in reason and "invalid strict JSON" in reason for reason in reasons)


@pytest.mark.parametrize(
    "authoring_path",
    ["lock --regen", "capture", "doctor --fix", "update", "render"],
)
def test_candidate_commit_is_gated_independent_of_authoring_command(
    engine, tmp_path, authoring_path,
):
    """Equivalent candidate commits cannot inherit trust from a local command.

    These are intentionally outcome tests, not command-provenance tests: Git
    does not preserve which command authored bytes, so the ship gate must make
    the same BASE-derived decision for regen/capture/fix/update/render output.
    """
    history = _new_history(tmp_path, engine)
    source = f"candidate bytes from simulated {authoring_path}\n".encode()
    _write(history.root, SOURCE, source)
    _write_lock(history.root, engine, source)
    _write(history.root, OUTPUT, source)
    _write(history.root, OUTPUT_SECONDARY, source)
    head = _commit(history.root, f"simulated {authoring_path}")

    _changed, consistency_reasons = _admission(engine, history, head)
    result = _ship(engine, history, head)

    assert consistency_reasons == []
    _assert_requires_verdict(result)


@pytest.mark.parametrize("path", [SOURCE, OUTPUT, REGISTRY, TARGET_CONFIG])
def test_candidate_symlink_swap_is_rejected(engine, tmp_path, path):
    history = _new_history(tmp_path, engine)
    target = history.root / path
    target.unlink()
    target.symlink_to("/tmp/tess-renderer-admission-decoy")
    head = _commit(history.root, f"symlink {path}")

    _changed, reasons = _admission(engine, history, head)

    assert any("not a regular blob" in reason or "symlinks" in reason for reason in reasons)


@pytest.mark.parametrize("path", [SOURCE, OUTPUT, REGISTRY, TARGET_CONFIG])
def test_candidate_submodule_swap_is_rejected(engine, tmp_path, path):
    history = _new_history(tmp_path, engine)
    target = history.root / path
    target.unlink()
    _git(history.root, "rm", "-q", "--cached", path)
    _git(
        history.root,
        "update-index",
        "--add",
        "--cacheinfo",
        f"160000,{history.base},{path}",
    )
    head = _commit(history.root, f"gitlink {path}", stage=False)

    _changed, reasons = _admission(engine, history, head)

    assert any("not a regular blob" in reason or "submodules" in reason for reason in reasons)


def test_deleted_source_and_output_are_recovered_from_acmrtd_diff(engine, tmp_path):
    history = _new_history(tmp_path, engine)
    (history.root / SOURCE).unlink()
    (history.root / OUTPUT).unlink()
    head = _commit(history.root, "delete renderer source and output")

    changed, reasons = _admission(engine, history, head)

    assert SOURCE in changed
    assert OUTPUT in changed
    assert any("deleted required BASE renderer input" in reason for reason in reasons)
    assert any("deleted BASE renderer output" in reason for reason in reasons)


def test_candidate_added_family_input_cannot_escape_base_mapping(engine, tmp_path):
    history = _new_history(tmp_path, engine)
    added = ".tess/core/templates/agents-md/attacker-fragment.md"
    _write(history.root, added, "candidate-only input\n")
    head = _commit(history.root, "add unmapped renderer input")

    _changed, reasons = _admission(engine, history, head)

    assert any(added in reason and "matches 0 canonical BASE mappings" in reason for reason in reasons)


@pytest.mark.parametrize(
    "orphan",
    [
        ".tess/core/templates/agents-md/orphan.tpl",
        ".tess/core/templates/agents-md/orphan.md",
    ],
)
def test_candidate_orphan_renderer_lock_row_is_rejected(engine, tmp_path, orphan):
    """A candidate lock row cannot invent a source that is absent from HEAD."""
    history = _new_history(tmp_path, engine)
    lock = _load_lock(history.root)
    lock["files"][orphan] = {
        "status": "core-managed",
        "tier": "normal",
        "render": None,
        "base_sha": engine.sha256_bytes(b"invented source bytes\n"),
        "live_path": OUTPUT,
    }
    _save_lock(history.root, lock)
    head = _commit(history.root, "add orphan renderer lock row")

    _changed, reasons = _admission(engine, history, head)

    assert any(
        orphan in reason and "orphaned" in reason and "source" in reason
        for reason in reasons
    )


def test_positive_coherent_upgrade_passes_consistency_but_not_authorization(engine, tmp_path):
    history = _new_history(tmp_path, engine)
    source = b"reviewable coherent renderer upgrade\n"
    _write(history.root, SOURCE, source)
    _write_lock(history.root, engine, source)
    _write(history.root, OUTPUT, source)
    _write(history.root, OUTPUT_SECONDARY, source)
    head = _commit(history.root, "coherent renderer upgrade")

    changed, consistency_reasons = _admission(engine, history, head)
    result = _ship(engine, history, head)

    assert consistency_reasons == []
    assert {SOURCE, LOCK, OUTPUT}.issubset(set(changed))
    _assert_requires_verdict(result)
    assert not any("renderer-base" in reason for reason in result["reasons"])


def test_commit_range_rejects_same_base_and_head(engine, tmp_path):
    history = _new_history(tmp_path, engine)

    reasons = engine._gate_validate_commit_range(history.root, history.base, history.base)

    assert any("must be distinct" in reason for reason in reasons)


@pytest.mark.parametrize("object_kind", ["tree", "blob"])
def test_commit_range_rejects_tree_and_blob_object_ids(engine, tmp_path, object_kind):
    history = _new_history(tmp_path, engine)
    _write(history.root, "docs/range.md", "candidate\n")
    head = _commit(history.root, "candidate")
    object_id = _git(
        history.root,
        "rev-parse",
        f"{history.base}^{{tree}}" if object_kind == "tree" else f"{history.base}:{SOURCE}",
    )

    reasons = engine._gate_validate_commit_range(history.root, object_id, head)

    assert any(f"is {object_kind}, not a commit" in reason for reason in reasons)


def test_commit_range_rejects_reversed_unrelated_and_nonexistent(engine, tmp_path):
    history = _new_history(tmp_path, engine)
    _write(history.root, "docs/range.md", "candidate\n")
    head = _commit(history.root, "candidate")
    tree = _git(history.root, "rev-parse", f"{head}^{{tree}}")
    unrelated = _git(history.root, "commit-tree", tree, "-m", "unrelated root")

    reversed_reasons = engine._gate_validate_commit_range(history.root, head, history.base)
    unrelated_reasons = engine._gate_validate_commit_range(history.root, unrelated, head)
    missing_reasons = engine._gate_validate_commit_range(history.root, "f" * 40, head)

    assert any("must be an ancestor" in reason for reason in reversed_reasons)
    assert any("must be an ancestor" in reason for reason in unrelated_reasons)
    assert any("does not exist" in reason for reason in missing_reasons)


def test_mcp_gate_preview_is_never_authoritative_even_when_diagnostic_would_allow(
    engine, tmp_path,
):
    history = _new_history(tmp_path, engine)
    _write(history.root, "docs/diagnostic.md", "ordinary docs\n")
    head = _commit(history.root, "ordinary docs")

    result = engine._mcp_tool_gate_check_paths(
        history.root,
        {"paths": ["docs/diagnostic.md"], "base": history.base, "head": head},
    )

    assert result["authoritative"] is False
    assert result["blocked"] is True
    assert result["diagnostic_would_block"] is False
    assert result["reasons"][0].startswith("MCP_DIAGNOSTIC_ONLY:")


@pytest.mark.parametrize(
    ("field", "value", "omit", "expected"),
    [
        ("status", "project-owned", False, "BASE mapping requires 'core-managed'"),
        ("tier", "security", False, "BASE mapping requires 'normal'"),
        ("render", "fragment", False, "BASE mapping requires None"),
        ("render", None, True, "must explicitly declare canonical lock metadata field 'render'"),
    ],
)
def test_candidate_added_mapped_input_must_use_canonical_metadata(
    engine, tmp_path, field, value, omit, expected,
):
    history = _new_history(tmp_path, engine)
    added = ".tess/core/templates/agents-md/new-fragment.tpl"
    content = b"candidate-added mapped input\n"
    _write(history.root, added, content)
    lock = _load_lock(history.root)
    row = {
        "status": "core-managed",
        "tier": "normal",
        "render": None,
        "base_sha": engine.sha256_bytes(content),
        "live_path": OUTPUT,
    }
    if omit:
        row.pop(field)
    else:
        row[field] = value
    lock["files"][added] = row
    _save_lock(history.root, lock)
    _write(history.root, OUTPUT, content)
    _write(history.root, OUTPUT_SECONDARY, content)
    head = _commit(history.root, f"candidate-added bad {field}")

    _changed, reasons = _admission(engine, history, head)

    assert any(expected in reason for reason in reasons)


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ('{"render_targets":{"enabled":["claude-code"],"enabled":["codex"]}}\n', "duplicate JSON key"),
        (json.dumps({"render_targets": {"enabled": ["claude-code"], "unknown": True}}), "unknown keys"),
        (json.dumps({"render_targets": {"enabled": []}}), "non-empty array"),
        (json.dumps({"render_targets": {"enabled": "claude-code"}}), "non-empty array"),
        (json.dumps({"render_targets": {"enabled": ["codex", "codex"]}}), "duplicate target names"),
        (json.dumps({"render_targets": {"enabled": ["candidate-target"]}}), "absent from immutable BASE registry"),
    ],
)
def test_target_config_is_strict(engine, tmp_path, content, expected):
    history = _new_history(tmp_path, engine)
    _write(history.root, TARGET_CONFIG, content + ("" if content.endswith("\n") else "\n"))
    head = _commit(history.root, "malformed target config")

    _changed, reasons = _admission(engine, history, head)

    assert any(expected in reason for reason in reasons)


@pytest.mark.parametrize("projection_case", ["missing", "partial", "stale"])
def test_changed_input_requires_complete_exact_output_projections(
    engine, tmp_path, projection_case,
):
    history = _new_history(tmp_path, engine)
    source = b"candidate source requiring every projection\n"
    _write(history.root, SOURCE, source)
    _write_lock(history.root, engine, source)
    if projection_case in ("partial", "stale"):
        _write(history.root, OUTPUT, source if projection_case == "partial" else b"stale\n")
    if projection_case == "stale":
        _write(history.root, OUTPUT_SECONDARY, source)
    head = _commit(history.root, f"{projection_case} projection")

    _changed, reasons = _admission(engine, history, head)

    if projection_case == "missing":
        assert sum("missing required projection change" in reason for reason in reasons) == 2
    elif projection_case == "partial":
        assert any(OUTPUT_SECONDARY in reason and "missing required projection change" in reason for reason in reasons)
    else:
        assert any(OUTPUT in reason and "stale or incoherent" in reason for reason in reasons)


def _duplicate_lock_text(engine, source: bytes) -> str:
    row = (
        "    status: core-managed\n"
        "    tier: normal\n"
        f"    base_sha: {engine.sha256_bytes(source)}\n"
        f"    live_path: {OUTPUT}\n"
    )
    return f"schema: 1\nfiles:\n  {SOURCE}:\n{row}  {SOURCE}:\n{row}"


def test_candidate_duplicate_lock_row_is_rejected(engine, tmp_path):
    history = _new_history(tmp_path, engine)
    source = (history.root / SOURCE).read_bytes()
    _write(history.root, LOCK, _duplicate_lock_text(engine, source))
    head = _commit(history.root, "duplicate candidate lock row")

    _changed, reasons = _admission(engine, history, head)

    assert any("duplicate key" in reason for reason in reasons)


def test_base_duplicate_lock_row_is_rejected(engine, tmp_path):
    history = _new_history(tmp_path, engine)
    source = (history.root / SOURCE).read_bytes()
    _write(history.root, LOCK, _duplicate_lock_text(engine, source))
    duplicate_base = _commit(history.root, "duplicate BASE lock row")
    _write_lock(history.root, engine, source)
    registry = (history.root / REGISTRY).read_text(encoding="utf-8")
    _write(history.root, REGISTRY, registry + "\n# descendant\n")
    head = _commit(history.root, "candidate after duplicate BASE")

    _changed, reasons = _admission(engine, history, head, duplicate_base)

    assert any("duplicate key" in reason for reason in reasons)


def _run_history_cli(history, *args, input_text=None, extra_env=None):
    env = {**os.environ, "TESS_ROOT": str(history.root)}
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(history.root / REGISTRY), *args],
        cwd=str(history.root),
        env=env,
        input=input_text,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("operation", ["lock-regen", "capture", "doctor-fix", "render"])
def test_real_mutator_command_outcome_cannot_bypass_admission(
    engine, tmp_path, operation,
):
    """Invoke real command entrypoints; never infer safety from command provenance."""
    history = _new_history(tmp_path, engine)
    source = f"real {operation} candidate bytes\n".encode()

    if operation == "lock-regen":
        _write(history.root, SOURCE, source)
        result = _run_history_cli(
            history, "lock", "--regen", "--only", SOURCE, "--yes",
        )
        assert result.returncode == 0, result.stdout + result.stderr
    elif operation == "capture":
        _write(history.root, OUTPUT, b"hand-edited live output\n")
        result = _run_history_cli(history, "capture", OUTPUT)
        assert result.returncode == 0, result.stdout + result.stderr
    elif operation == "doctor-fix":
        _write(history.root, OUTPUT, b"doctor-fix live drift\n")
        result = _run_history_cli(history, "doctor", "--fix", OUTPUT)
        assert "doctor --fix" in result.stdout
    else:
        _write(history.root, SOURCE, source)
        repin = _run_history_cli(
            history, "lock", "--regen", "--only", SOURCE, "--yes",
        )
        assert repin.returncode == 0, repin.stdout + repin.stderr
        result = _run_history_cli(history, "render", "--target", "generic")
        assert result.returncode == 0, result.stdout + result.stderr

    head = _commit(history.root, f"real {operation} outcome")
    _changed, reasons = _admission(engine, history, head)

    assert reasons
    if operation in ("capture", "doctor-fix"):
        assert any("BASE mapping requires 'core-managed'" in reason for reason in reasons)
    else:
        assert any("missing required projection change" in reason for reason in reasons)


def test_real_update_command_outcome_is_coherent_but_still_requires_verdict(
    engine, tmp_path, monkeypatch,
):
    """Run cmd_update with only its network/signature fetch seam replaced.

    No GPG executable is called: the fake fetch provides already-fetched staging
    bytes, while the real snapshot, resolution, core advance, lock re-pin, and
    update orchestration paths execute.
    """
    history = _new_history(tmp_path, engine)
    lock = _load_lock(history.root)
    lock["framework"] = {
        "track": "v2",
        "version": "1.0.0",
        "upstream": "test-upstream",
        "upstream_ref": "v2.0.0",
    }
    _save_lock(history.root, lock)
    # Make the framework-bearing lock part of the trusted BASE.
    history.base = _commit(history.root, "BASE with update framework metadata")
    source = b"real update candidate bytes\n"

    def fake_fetch(root, target_ref, allow_tofu=False):
        assert target_ref == "v2.0.0"
        _write(root, f".tess/staging/{SOURCE}", source)

    def fake_render(root, verbose=False):
        _write(root, OUTPUT, source)
        _write(root, OUTPUT_SECONDARY, source)

    monkeypatch.setattr(engine, "fetch_to_staging", fake_fetch)
    monkeypatch.setattr(engine, "_render_enabled_targets", fake_render)
    args = SimpleNamespace(
        dry_run=False,
        check=False,
        to=None,
        ref="v2.0.0",
        trust_on_first_use=False,
    )

    engine.cmd_update(args, history.root)
    head = _commit(history.root, "real update outcome")
    _changed, consistency_reasons = _admission(engine, history, head)
    result = _ship(engine, history, head)

    assert consistency_reasons == []
    _assert_requires_verdict(result)


def _github_event_env(history, event_name: str, payload: dict, head: str) -> dict:
    payload.setdefault("repository", {"full_name": EVENT_REPOSITORY})
    if event_name == "pull_request":
        payload.setdefault("number", 7)
        pr = payload.get("pull_request")
        base = pr.get("base") if isinstance(pr, dict) else None
        if isinstance(base, dict):
            base.setdefault("ref", "main")
            base.setdefault("repo", {"full_name": EVENT_REPOSITORY})
        github_ref = f"refs/pull/{payload['number']}/merge"
    else:
        payload.setdefault("ref", "refs/heads/main")
        github_ref = "refs/heads/main"
    event_path = history.root / ".github-event.json"
    event_path.write_text(json.dumps(payload), encoding="utf-8")
    return {
        "GITHUB_ACTIONS": "true",
        "GITHUB_JOB": "ship-gate",
        "GITHUB_REPOSITORY": EVENT_REPOSITORY,
        "GITHUB_REF": github_ref,
        "GITHUB_WORKFLOW_REF": (
            f"{WORKFLOW_SOURCE_REPOSITORY}/.github/workflows/tess-gate.yml@"
            f"{WORKFLOW_SOURCE_REF}"
        ),
        "GITHUB_WORKFLOW_SHA": WORKFLOW_SOURCE_SHA,
        "TESS_JOB_CONTEXT_JSON": json.dumps({
            "workflow_ref": (
                f"{WORKFLOW_SOURCE_REPOSITORY}/.github/workflows/tess-gate.yml@"
                f"{WORKFLOW_SOURCE_REF}"
            ),
            "workflow_sha": WORKFLOW_SOURCE_SHA,
            "workflow_repository": WORKFLOW_SOURCE_REPOSITORY,
            "workflow_file_path": ".github/workflows/tess-gate.yml",
        }),
        "GITHUB_EVENT_NAME": event_name,
        "GITHUB_EVENT_PATH": str(event_path),
        "GITHUB_SHA": head,
    }


def _merge_wrapper(root: Path, base: str, attestation: str, *, tree: str | None = None) -> str:
    tree = tree or _git(root, "rev-parse", f"{attestation}^{{tree}}")
    result = subprocess.run(
        ["git", "-C", str(root), "commit-tree", tree, "-p", base, "-p", attestation],
        input="Tess admission merge wrapper\n", capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_local_gate_ci_is_explicitly_non_authoritative(engine, tmp_path):
    history = _new_history(tmp_path, engine)
    _write(history.root, "notes/local.txt", "diagnostic\n")
    head = _commit(history.root, "local diagnostic")

    result = _run_history_cli(
        history, "gate", "ci", "--base", history.base, "--head", head, "--json",
        extra_env={"GITHUB_ACTIONS": "false", "GITHUB_JOB": ""},
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["authoritative"] is False
    assert payload["diagnostic_only"] is True
    assert payload["blocked"] is False


def test_protected_gate_ci_accepts_only_exact_pr_event_range(engine, tmp_path):
    history = _new_history(tmp_path, engine)
    _write(history.root, "notes/event.txt", "event derived\n")
    attestation = _commit(history.root, "pull_request event")
    evaluation = _merge_wrapper(history.root, history.base, attestation)
    event_name = "pull_request"
    event = {
        "pull_request": {
            "base": {"sha": history.base},
            "head": {"sha": attestation},
        }
    }

    result = _run_history_cli(
        history, "gate", "ci", "--base", history.base, "--head", evaluation, "--json",
        extra_env=_github_event_env(history, event_name, event, evaluation),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["authoritative"] is True
    assert payload["blocked"] is False
    assert "diagnostic_only" not in payload


def test_protected_gate_ci_rejects_caller_selected_range(engine, tmp_path):
    history = _new_history(tmp_path, engine)
    _write(history.root, "notes/mismatch.txt", "mismatch\n")
    head = _commit(history.root, "event mismatch")
    evaluation = _merge_wrapper(history.root, history.base, head)
    event = {
        "pull_request": {
            "base": {"sha": history.base},
            "head": {"sha": head},
        }
    }

    result = _run_history_cli(
        history, "gate", "ci", "--base", history.base, "--head", head, "--json",
        extra_env=_github_event_env(history, "pull_request", event, evaluation),
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["authoritative"] is False
    assert payload["blocked"] is True
    assert payload["changed_paths_count"] == 0
    assert payload["reasons"] == [
        "CI_EVENT_RANGE_MISMATCH: the supplied range does not match the immutable CI event",
    ]


def test_workflow_dispatch_cannot_create_authoritative_gate_context(engine, tmp_path):
    history = _new_history(tmp_path, engine)
    _write(history.root, "notes/manual.txt", "manual\n")
    head = _commit(history.root, "manual dispatch")
    event = {"inputs": {"base": history.base, "head": head}}

    result = _run_history_cli(
        history, "gate", "ci", "--base", history.base, "--head", head, "--json",
        extra_env=_github_event_env(history, "workflow_dispatch", event, head),
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["authoritative"] is False
    assert payload["blocked"] is True
    assert payload["changed_paths_count"] == 0
    assert "changed_paths" not in payload
    assert payload["reasons"] == [
        "CI_PR_EVENT_REQUIRED: an authoritative pull request event is required",
    ]


def test_push_event_never_becomes_authoritative_gate_ci(engine, tmp_path):
    history = _new_history(tmp_path, engine)
    _write(history.root, "notes/first-push.txt", "first push\n")
    head = _commit(history.root, "first push event")
    event = {"before": "0" * len(head), "after": head}

    result = _run_history_cli(
        history, "gate", "ci", "--base", history.base, "--head", head, "--json",
        extra_env=_github_event_env(history, "push", event, head),
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["authoritative"] is False
    assert payload["blocked"] is True
    assert payload["changed_paths_count"] == 0
    assert "changed_paths" not in payload
    assert payload["reasons"] == [
        "CI_PR_EVENT_REQUIRED: an authoritative pull request event is required",
    ]


def _install_remote_head(history) -> None:
    _git(history.root, "remote", "add", "origin", "https://example.invalid/repo.git")
    _git(history.root, "update-ref", "refs/remotes/origin/main", history.base)
    _git(
        history.root, "symbolic-ref",
        "refs/remotes/origin/HEAD", "refs/remotes/origin/main",
    )


def _first_push_stdin(head: str) -> str:
    return f"refs/heads/feature {head} refs/heads/feature {'0' * len(head)}\n"


def test_pre_push_stdin_new_branch_uses_remote_head_merge_base(engine, tmp_path):
    history = _new_history(tmp_path, engine)
    _install_remote_head(history)
    _write(history.root, "notes/new-branch.txt", "ordinary feature\n")
    head = _commit(history.root, "new feature branch")

    result = _run_history_cli(
        history, "gate", "pre-push", "--remote", "origin", "--json",
        input_text=_first_push_stdin(head),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["blocked"] is False
    assert payload["changed_paths_count"] == 1
    assert "REMOTE_BASE_REQUIRED" not in result.stdout


def test_pre_push_stdin_new_branch_renderer_change_is_non_authoritative(engine, tmp_path):
    history = _new_history(tmp_path, engine)
    _install_remote_head(history)
    _write(history.root, SOURCE, "candidate first-push renderer bytes\n")
    head = _commit(history.root, "new branch renderer change")

    result = _run_history_cli(
        history, "gate", "pre-push", "--remote", "origin", "--json",
        input_text=_first_push_stdin(head),
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["blocked"] is True
    assert payload["reasons"] == [
        "ADMISSION_EVENT_SOURCE_REQUIRED: an authoritative admission event source is required",
        "COVERING_APPROVAL_MISSING: no covering APPROVE verdict found",
    ]


def test_pre_push_stdin_new_branch_without_remote_head_fails_before_renderer(engine, tmp_path):
    history = _new_history(tmp_path, engine)
    _write(history.root, SOURCE, "candidate without remote baseline\n")
    head = _commit(history.root, "new branch without remote HEAD")

    result = _run_history_cli(
        history, "gate", "pre-push", "--remote", "origin", "--json",
        input_text=_first_push_stdin(head),
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["blocked"] is True
    assert payload["changed_paths_count"] == 0
    assert len(payload["reasons"]) == 1
    assert payload["reasons"] == [
        "REMOTE_BASE_REQUIRED: an immutable remote baseline is required",
    ]
