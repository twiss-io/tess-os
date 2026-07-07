"""
Goal #8 — mission trace log + OTel GenAI export (`.tess/bin/tessctl`'s
isolated TRACE region: `TRACE_EVENT_SCHEMA`, `_trace_*` helpers, `cmd_trace`).

Coverage (per the dispatch brief's acceptance list):
  * every `gate`/`validate` invocation appends >=1 schema-valid JSONL event
    — mission-scoped (missions/<id>/trace.jsonl) AND the no-mission-id
    fallback (.tess/trace/runs/<run_id>.jsonl)
  * `trace export --format otlp-json` produces OTLP-JSON that validates
    against the GenAI semconv agent-span attribute set
  * NO network call anywhere in the trace/export path (socket-guard tests +
    a static+dynamic import-scan of the engine source) — including the
    append path INSIDE `_trace_record` itself, not just its outer callers
    (2026-07 MEDIUM-finding fix: the guard's own signal exception used to
    be swallowed by `_trace_record`'s best-effort `except Exception`)
  * the existing suite stays green (this file only ADDS coverage)

Hooks/CI firing is out of scope here (already owned by test_gate_hooks.py);
this module exercises `gate pre-commit|pre-push|ci` and `validate` directly,
the same way test_gate_spine.py does, plus the new `trace` subcommand.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
from pathlib import Path

import pytest
import yaml

from conftest import ENGINE_SRC, ns

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACTS_SRC = REPO_ROOT / "core" / "contracts"

HAS_GIT = shutil.which("git") is not None
HAS_GPG = shutil.which("gpg") is not None
# `tessctl gate ...` hard-requires git+gpg on PATH regardless of whether a
# given test needs signing (`_TOOL_REQUIREMENTS["gate"]` in .tess/bin/tessctl) —
# same module-wide skip precedent test_gate_spine.py already uses.
pytestmark = pytest.mark.skipif(not (HAS_GIT and HAS_GPG), reason="git + gpg required")

_KNOWN_GEN_AI_OPERATION_NAMES = {
    "chat", "create_agent", "create_memory", "create_memory_store", "delete_memory",
    "delete_memory_store", "embeddings", "execute_tool", "generate_content",
    "invoke_agent", "invoke_workflow", "plan", "retrieval", "search_memory",
    "text_completion", "update_memory", "upsert_memory",
}


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


_TRACE_TEST_POLICY = {
    "policy": {
        "version": 1,
        "rules": [
            {
                "id": "prod-src",
                "description": "test-only prod rule",
                "globs": ["src/prod/**"],
                "classification": ["prod_touching"],
                "require_verdict": True,
                "allowed_verifiers": ["Reid"],
            },
        ],
        "hard_floor_rules": [],
    }
}


def _init_repo(root):
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@tess.test")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "commit.gpgsign", "false")


@pytest.fixture
def trace_repo(project):
    """A real git repo with the real core/contracts/*.schema.json + a
    test-scoped core/policy/policy.yaml, one initial commit — enough to run
    `gate pre-commit|pre-push|ci` and `validate` against for trace-log
    coverage. Deliberately does NOT wire verdict signing (test_gate_spine.py
    already owns that) — these tests only need pass/block/error OUTCOMES to
    exercise the tracer, not covering-verdict clearance."""
    root = project.root
    shutil.copytree(CONTRACTS_SRC, root / "core" / "contracts")
    (root / "core" / "policy").mkdir(parents=True, exist_ok=True)
    (root / "core" / "policy" / "policy.yaml").write_text(
        yaml.safe_dump(_TRACE_TEST_POLICY), encoding="utf-8",
    )
    _init_repo(root)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "initial")
    return root


def _base_sha(root):
    return _git(root, "rev-parse", "HEAD").stdout.strip()


def _commit_all(root, message):
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)
    return _git(root, "rev-parse", "HEAD").stdout.strip()


def _read_jsonl(path: Path) -> list:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _fallback_events(root: Path) -> list:
    events = []
    for p in sorted((root / ".tess" / "trace" / "runs").glob("*.jsonl")):
        events += _read_jsonl(p)
    return events


_VALID_BRIEF_TEXT = (
    "---\n"
    "objective: Do the thing.\n"
    "output_contract: /tmp/out.md — sections [A]\n"
    "tools_sources_constraints: Read /tmp/in.md; every number traces to a quoted row.\n"
    "not_responsible_for: The other thing.\n"
    "milestones: []\n"
    "escalation_trigger: If blocked, stop and ask.\n"
    "---\n\nBody.\n"
)

_INVALID_BRIEF_TEXT = "---\nobjective: Do the thing.\n---\n\nBody.\n"  # missing required fields


# ===========================================================================
# 1) Engine-level unit tests: schema, mission-id inference, event/append
# ===========================================================================


def test_trace_event_schema_accepts_a_well_formed_event(engine):
    event = engine._trace_build_event(
        phase="gate", action="gate.ci", outcome="pass", exit_code=0,
        duration_ms=12.3, mission_id="m1", subject={"changed_paths_count": 2},
        counts={"changed_paths": 2}, reasons=[],
    )
    violations = engine.schema_validate(event, engine.TRACE_EVENT_SCHEMA, engine.TRACE_EVENT_SCHEMA, REPO_ROOT)
    assert violations == []
    assert event["schema"] == engine.TRACE_SCHEMA_VERSION
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$", event["timestamp"])


def test_trace_event_schema_rejects_missing_required_field(engine):
    event = engine._trace_build_event(
        phase="validate", action="validate", outcome="pass", exit_code=0,
        duration_ms=1.0, mission_id=None,
    )
    del event["outcome"]
    violations = engine.schema_validate(event, engine.TRACE_EVENT_SCHEMA, engine.TRACE_EVENT_SCHEMA, REPO_ROOT)
    assert any("outcome" in v for v in violations)


def test_trace_event_schema_rejects_unknown_outcome_value(engine):
    event = engine._trace_build_event(
        phase="gate", action="gate.ci", outcome="maybe", exit_code=0,
        duration_ms=1.0, mission_id=None,
    )
    violations = engine.schema_validate(event, engine.TRACE_EVENT_SCHEMA, engine.TRACE_EVENT_SCHEMA, REPO_ROOT)
    assert any("outcome" in v for v in violations)


def test_infer_mission_id_picks_lexicographically_first_when_multiple(engine):
    assert engine._trace_infer_mission_id(
        ["missions/zeta/verdicts/x.verdict.md", "missions/alpha/briefs/y.brief.md"]
    ) == "alpha"


def test_infer_mission_id_none_when_no_mission_scoped_path(engine):
    assert engine._trace_infer_mission_id(["src/prod/app.py", "README.md"]) is None
    assert engine._trace_infer_mission_id([]) is None
    assert engine._trace_infer_mission_id(None) is None


def test_capped_reasons_truncates_and_marks_overflow(engine):
    reasons = [f"reason {i}" for i in range(30)]
    capped = engine._trace_capped_reasons(reasons)
    assert len(capped) == engine.TRACE_MAX_REASONS + 1
    assert "more (truncated" in capped[-1]


def test_capped_reasons_leaves_a_short_list_untouched(engine):
    assert engine._trace_capped_reasons(["a", "b"]) == ["a", "b"]
    assert engine._trace_capped_reasons(None) == []


def test_append_event_writes_to_mission_path_when_mission_id_present(engine, tmp_path):
    event = engine._trace_build_event(
        phase="gate", action="gate.pre-commit", outcome="block", exit_code=1,
        duration_ms=5.0, mission_id="m9", reasons=["x"],
    )
    written = engine._trace_append_event(tmp_path, event)
    assert written == tmp_path / "missions" / "m9" / "trace.jsonl"
    assert _read_jsonl(written) == [event]


def test_append_event_writes_to_fallback_path_when_no_mission_id(engine, tmp_path):
    event = engine._trace_build_event(
        phase="validate", action="validate", outcome="pass", exit_code=0,
        duration_ms=1.0, mission_id=None,
    )
    written = engine._trace_append_event(tmp_path, event)
    assert written == tmp_path / ".tess" / "trace" / "runs" / f"{event['run_id']}.jsonl"
    assert _read_jsonl(written) == [event]


def test_append_event_appends_not_overwrites(engine, tmp_path):
    e1 = engine._trace_build_event(phase="gate", action="gate.ci", outcome="pass", exit_code=0,
                                    duration_ms=1.0, mission_id="m1")
    e2 = engine._trace_build_event(phase="gate", action="gate.ci", outcome="block", exit_code=1,
                                    duration_ms=2.0, mission_id="m1")
    p1 = engine._trace_append_event(tmp_path, e1)
    p2 = engine._trace_append_event(tmp_path, e2)
    assert p1 == p2
    assert _read_jsonl(p1) == [e1, e2]


def test_append_event_raises_trace_error_on_schema_invalid_event(engine, tmp_path):
    bad_event = {"schema": engine.TRACE_SCHEMA_VERSION}  # missing everything else
    with pytest.raises(engine.TraceError):
        engine._trace_append_event(tmp_path, bad_event)
    assert not (tmp_path / ".tess" / "trace").exists()  # never partially written


def test_trace_record_is_best_effort_and_never_raises(engine, tmp_path, monkeypatch, capsys):
    """A tracer bug (forced here via a broken _trace_build_event) must never
    propagate out of `_trace_record` — the gate/validate command it observes
    must be unaffected. The failure is still surfaced (not silent) as a
    stderr WARNING."""
    def _boom(*a, **kw):
        raise RuntimeError("synthetic tracer bug")

    monkeypatch.setattr(engine, "_trace_build_event", _boom)
    engine._trace_record(
        tmp_path, phase="gate", action="gate.ci", outcome="pass", exit_code=0,
        duration_s=0.001, changed_paths=["x"],
    )
    captured = capsys.readouterr()
    assert "WARNING" in captured.err
    assert "synthetic tracer bug" in captured.err


# ===========================================================================
# 2) OTel GenAI mapping — unit tests
# ===========================================================================


def test_otlp_span_has_required_gen_ai_attributes_on_a_pass_event(engine):
    event = engine._trace_build_event(
        phase="gate", action="gate.ci", outcome="pass", exit_code=0,
        duration_ms=10.0, mission_id="m1", subject={"changed_paths_count": 1},
    )
    span = engine._trace_event_to_otlp_span(event)
    attrs = {a["key"]: a["value"] for a in span["attributes"]}
    assert attrs["gen_ai.operation.name"] == {"stringValue": "invoke_agent"}
    assert "invoke_agent" in _KNOWN_GEN_AI_OPERATION_NAMES
    assert attrs["gen_ai.agent.name"]["stringValue"]
    assert attrs["gen_ai.agent.id"]["stringValue"]
    assert attrs["gen_ai.agent.description"]["stringValue"]
    assert attrs["gen_ai.conversation.id"] == {"stringValue": "m1"}
    assert "error.type" not in attrs
    assert span["status"]["code"] == engine._OTLP_STATUS_OK
    # status.message is an OTLP error-description field — an OK span carries
    # none (closes a LOW finding: it used to duplicate `outcome` here too).
    assert "message" not in span["status"]


@pytest.mark.parametrize("outcome", ["block", "error"])
def test_otlp_span_sets_error_type_and_error_status_on_block_and_error(engine, outcome):
    event = engine._trace_build_event(
        phase="validate", action="validate", outcome=outcome, exit_code=1,
        duration_ms=3.0, mission_id=None, reasons=["something failed"],
    )
    span = engine._trace_event_to_otlp_span(event)
    attrs = {a["key"]: a["value"] for a in span["attributes"]}
    assert attrs["error.type"]["stringValue"]
    assert span["status"]["code"] == engine._OTLP_STATUS_ERROR
    assert span["status"]["message"] == outcome


def test_otlp_span_omits_conversation_id_when_no_mission(engine):
    event = engine._trace_build_event(
        phase="validate", action="validate", outcome="pass", exit_code=0,
        duration_ms=1.0, mission_id=None,
    )
    span = engine._trace_event_to_otlp_span(event)
    keys = {a["key"] for a in span["attributes"]}
    assert "gen_ai.conversation.id" not in keys


def test_otlp_ids_are_valid_hex_length_and_deterministic(engine):
    e1 = engine._trace_build_event(phase="gate", action="gate.ci", outcome="pass",
                                    exit_code=0, duration_ms=1.0, mission_id="m1")
    e2 = dict(e1)
    e2["event_id"] = "a-different-event-id"  # same run_id, different event

    s1 = engine._trace_event_to_otlp_span(e1)
    s2 = engine._trace_event_to_otlp_span(e2)

    assert re.fullmatch(r"[0-9a-f]{32}", s1["traceId"])
    assert re.fullmatch(r"[0-9a-f]{16}", s1["spanId"])
    assert s1["traceId"] == s2["traceId"]  # same run_id -> same trace
    assert s1["spanId"] != s2["spanId"]    # different event_id -> different span

    # Reproducible: re-mapping the SAME event always yields the SAME ids.
    assert engine._trace_event_to_otlp_span(e1) == s1


def test_otlp_json_document_structure(engine):
    events = [
        engine._trace_build_event(phase="gate", action="gate.ci", outcome="pass",
                                   exit_code=0, duration_ms=1.0, mission_id="m1"),
        engine._trace_build_event(phase="validate", action="validate", outcome="block",
                                   exit_code=1, duration_ms=2.0, mission_id=None, reasons=["bad"]),
    ]
    doc = engine._trace_events_to_otlp_json(events)
    resource_spans = doc["resourceSpans"]
    assert len(resource_spans) == 1
    resource_attrs = {a["key"]: a["value"] for a in resource_spans[0]["resource"]["attributes"]}
    assert resource_attrs["service.name"] == {"stringValue": "tess-os"}
    scope_spans = resource_spans[0]["scopeSpans"]
    assert len(scope_spans) == 1
    assert scope_spans[0]["scope"]["name"] == "tess-os.tessctl.trace"
    spans = scope_spans[0]["spans"]
    assert len(spans) == 2
    for span in spans:
        assert re.fullmatch(r"[0-9a-f]{32}", span["traceId"])
        assert re.fullmatch(r"[0-9a-f]{16}", span["spanId"])
        assert span["kind"] == engine._OTLP_SPAN_KIND_INTERNAL
        assert span["startTimeUnixNano"].isdigit()
        assert span["endTimeUnixNano"].isdigit()
        assert int(span["endTimeUnixNano"]) >= int(span["startTimeUnixNano"])


def test_otlp_json_is_json_serializable_round_trip(engine):
    event = engine._trace_build_event(phase="gate", action="gate.ci", outcome="pass",
                                       exit_code=0, duration_ms=1.0, mission_id="m1")
    doc = engine._trace_events_to_otlp_json([event])
    round_tripped = json.loads(json.dumps(doc))
    assert round_tripped == doc


# ===========================================================================
# 3) Integration: real gate/validate invocations append schema-valid events
# ===========================================================================


def test_gate_ci_block_on_prod_touching_change_appends_block_event_to_fallback(trace_repo, run_cli, engine):
    base = _base_sha(trace_repo)
    (trace_repo / "src" / "prod").mkdir(parents=True)
    (trace_repo / "src" / "prod" / "app.py").write_text("print('prod')\n")
    head = _commit_all(trace_repo, "add prod change, no verdict")

    r = run_cli(trace_repo, "gate", "ci", "--base", base, "--head", head, "--json")
    assert r.returncode == 1, r.stdout + r.stderr

    events = _fallback_events(trace_repo)
    assert len(events) >= 1
    gate_events = [e for e in events if e["phase"] == "gate" and e["action"] == "gate.ci"]
    assert len(gate_events) == 1
    event = gate_events[0]
    assert engine.schema_validate(event, engine.TRACE_EVENT_SCHEMA, engine.TRACE_EVENT_SCHEMA, trace_repo) == []
    assert event["outcome"] == "block"
    assert event["exit_code"] == 1
    assert event["mission_id"] is None  # src/prod/app.py isn't mission-scoped
    assert event["subject"]["changed_paths_count"] == 1
    assert event["counts"]["changed_paths"] == 1
    assert any("app.py" in r for r in event["reasons"])


def test_gate_ci_clean_change_appends_pass_event(trace_repo, run_cli, engine):
    base = _base_sha(trace_repo)
    (trace_repo / "docs").mkdir(parents=True)
    (trace_repo / "docs" / "notes.md").write_text("nothing special\n")
    head = _commit_all(trace_repo, "docs-only change")

    r = run_cli(trace_repo, "gate", "ci", "--base", base, "--head", head, "--json")
    assert r.returncode == 0, r.stdout + r.stderr

    events = _fallback_events(trace_repo)
    assert len(events) == 1
    assert events[0]["outcome"] == "pass"
    assert events[0]["exit_code"] == 0
    assert engine.schema_validate(events[0], engine.TRACE_EVENT_SCHEMA, engine.TRACE_EVENT_SCHEMA, trace_repo) == []


def test_gate_ci_fails_closed_on_bad_ref_appends_error_event(trace_repo, run_cli, engine):
    r = run_cli(trace_repo, "gate", "ci", "--base", "not-a-real-ref", "--head", "HEAD", "--json")
    assert r.returncode == 1

    events = _fallback_events(trace_repo)
    assert len(events) == 1
    assert events[0]["outcome"] == "error"
    assert events[0]["exit_code"] == 1
    assert events[0]["mission_id"] is None
    assert engine.schema_validate(events[0], engine.TRACE_EVENT_SCHEMA, engine.TRACE_EVENT_SCHEMA, trace_repo) == []


def test_gate_pre_commit_schema_invalid_staged_brief_appends_block_event_under_mission_path(trace_repo, run_cli, engine):
    brief_path = trace_repo / "missions" / "m1" / "briefs" / "task1.brief.md"
    brief_path.parent.mkdir(parents=True)
    brief_path.write_text(_INVALID_BRIEF_TEXT, encoding="utf-8")
    _git(trace_repo, "add", "-A")

    r = run_cli(trace_repo, "gate", "pre-commit", "--json")
    assert r.returncode == 1, r.stdout + r.stderr

    mission_trace = trace_repo / "missions" / "m1" / "trace.jsonl"
    assert mission_trace.exists()
    events = _read_jsonl(mission_trace)
    assert len(events) == 1
    event = events[0]
    assert event["phase"] == "gate"
    assert event["action"] == "gate.pre-commit"
    assert event["outcome"] == "block"
    assert event["mission_id"] == "m1"
    assert engine.schema_validate(event, engine.TRACE_EVENT_SCHEMA, engine.TRACE_EVENT_SCHEMA, trace_repo) == []
    # nothing leaked into the no-mission-id fallback for a fully mission-scoped change
    assert _fallback_events(trace_repo) == []


def test_gate_pre_push_stdin_protocol_appends_event(trace_repo, run_cli, engine):
    base = _base_sha(trace_repo)
    (trace_repo / "src" / "prod").mkdir(parents=True)
    (trace_repo / "src" / "prod" / "app.py").write_text("print('prod')\n")
    head = _commit_all(trace_repo, "prod change")

    stdin = f"refs/heads/main {head} refs/heads/main {'0' * 40}\n"
    r = run_cli(trace_repo, "gate", "pre-push", "--json", input_text=stdin)
    assert r.returncode == 1

    events = _fallback_events(trace_repo)
    gate_events = [e for e in events if e["action"] == "gate.pre-push"]
    assert len(gate_events) == 1
    assert gate_events[0]["outcome"] == "block"
    assert engine.schema_validate(gate_events[0], engine.TRACE_EVENT_SCHEMA, engine.TRACE_EVENT_SCHEMA, trace_repo) == []


def test_validate_valid_and_invalid_and_missing_file_outcomes(trace_repo, run_cli, engine):
    mission_dir = trace_repo / "missions" / "m2" / "briefs"
    mission_dir.mkdir(parents=True)
    valid = mission_dir / "ok.brief.md"
    valid.write_text(_VALID_BRIEF_TEXT, encoding="utf-8")
    invalid = mission_dir / "bad.brief.md"
    invalid.write_text(_INVALID_BRIEF_TEXT, encoding="utf-8")

    r_ok = run_cli(trace_repo, "validate", "brief", "missions/m2/briefs/ok.brief.md", "--json")
    assert r_ok.returncode == 0, r_ok.stdout + r_ok.stderr
    r_bad = run_cli(trace_repo, "validate", "brief", "missions/m2/briefs/bad.brief.md", "--json")
    assert r_bad.returncode == 1, r_bad.stdout + r_bad.stderr
    r_missing = run_cli(trace_repo, "validate", "brief", "missions/m2/briefs/does-not-exist.brief.md", "--json")
    assert r_missing.returncode == 2, r_missing.stdout + r_missing.stderr

    events = _read_jsonl(trace_repo / "missions" / "m2" / "trace.jsonl")
    by_outcome = {e["outcome"]: e for e in events}
    assert set(by_outcome) == {"pass", "block", "error"}
    for e in events:
        assert e["phase"] == "validate"
        assert e["action"] == "validate"
        assert e["mission_id"] == "m2"
        assert e["subject"]["contract_type"] == "brief"
        assert engine.schema_validate(e, engine.TRACE_EVENT_SCHEMA, engine.TRACE_EVENT_SCHEMA, trace_repo) == []
    assert by_outcome["pass"]["exit_code"] == 0
    assert by_outcome["block"]["exit_code"] == 1
    assert by_outcome["error"]["exit_code"] == 2


def test_validate_outside_missions_falls_back_to_per_run_path(trace_repo, run_cli):
    loose = trace_repo / "loose.brief.md"
    loose.write_text(_VALID_BRIEF_TEXT, encoding="utf-8")

    r = run_cli(trace_repo, "validate", "brief", "loose.brief.md", "--json")
    assert r.returncode == 0

    assert not (trace_repo / "missions").exists()
    events = _fallback_events(trace_repo)
    assert len(events) == 1
    assert events[0]["mission_id"] is None
    assert events[0]["subject"]["file"] == "loose.brief.md"


# ===========================================================================
# 4) `trace export --format otlp-json`
# ===========================================================================


def _assert_valid_gen_ai_agent_span(span: dict) -> None:
    attrs = {a["key"]: a["value"] for a in span["attributes"]}
    assert attrs["gen_ai.operation.name"]["stringValue"] in _KNOWN_GEN_AI_OPERATION_NAMES
    assert attrs["gen_ai.agent.name"]["stringValue"]
    assert attrs["gen_ai.agent.id"]["stringValue"]
    assert attrs["gen_ai.agent.description"]["stringValue"]
    is_error = span["status"]["code"] == 2
    assert ("error.type" in attrs) == is_error
    assert re.fullmatch(r"[0-9a-f]{32}", span["traceId"])
    assert re.fullmatch(r"[0-9a-f]{16}", span["spanId"])
    assert span["kind"] == 1


def test_trace_export_cli_produces_valid_otlp_json_with_gen_ai_attributes(trace_repo, run_cli):
    base = _base_sha(trace_repo)
    (trace_repo / "src" / "prod").mkdir(parents=True)
    (trace_repo / "src" / "prod" / "app.py").write_text("print('prod')\n")
    head = _commit_all(trace_repo, "prod change, no verdict")
    assert run_cli(trace_repo, "gate", "ci", "--base", base, "--head", head, "--json").returncode == 1

    valid = trace_repo / "missions" / "m3" / "briefs" / "ok.brief.md"
    valid.parent.mkdir(parents=True)
    valid.write_text(_VALID_BRIEF_TEXT, encoding="utf-8")
    assert run_cli(trace_repo, "validate", "brief", "missions/m3/briefs/ok.brief.md").returncode == 0

    r = run_cli(trace_repo, "trace", "export", "--format", "otlp-json")
    assert r.returncode == 0, r.stdout + r.stderr
    doc = json.loads(r.stdout)

    spans = doc["resourceSpans"][0]["scopeSpans"][0]["spans"]
    assert len(spans) == 2
    for span in spans:
        _assert_valid_gen_ai_agent_span(span)

    conv_ids = {
        next((a["value"]["stringValue"] for a in s["attributes"] if a["key"] == "gen_ai.conversation.id"), None)
        for s in spans
    }
    assert "m3" in conv_ids  # the mission-scoped validate call
    assert None in conv_ids  # the fallback (no mission id) gate ci call


def test_trace_export_unsupported_format_is_rejected(trace_repo, run_cli):
    r = run_cli(trace_repo, "trace", "export", "--format", "console")
    assert r.returncode != 0


def test_trace_export_mission_id_scoping(trace_repo, run_cli):
    for mid in ("alpha", "beta"):
        brief = trace_repo / "missions" / mid / "briefs" / "ok.brief.md"
        brief.parent.mkdir(parents=True)
        brief.write_text(_VALID_BRIEF_TEXT, encoding="utf-8")
        assert run_cli(trace_repo, "validate", "brief", f"missions/{mid}/briefs/ok.brief.md").returncode == 0

    r = run_cli(trace_repo, "trace", "export", "--format", "otlp-json", "--mission-id", "alpha")
    doc = json.loads(r.stdout)
    spans = doc["resourceSpans"][0]["scopeSpans"][0]["spans"]
    assert len(spans) == 1
    attrs = {a["key"]: a["value"] for a in spans[0]["attributes"]}
    assert attrs["gen_ai.conversation.id"] == {"stringValue": "alpha"}


def test_trace_export_out_file_writes_to_disk(trace_repo, run_cli, tmp_path):
    valid = trace_repo / "missions" / "m4" / "briefs" / "ok.brief.md"
    valid.parent.mkdir(parents=True)
    valid.write_text(_VALID_BRIEF_TEXT, encoding="utf-8")
    assert run_cli(trace_repo, "validate", "brief", "missions/m4/briefs/ok.brief.md").returncode == 0

    out_file = tmp_path / "export.otlp.json"
    r = run_cli(trace_repo, "trace", "export", "--format", "otlp-json", "--out", str(out_file))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "wrote 1 span" in r.stdout
    doc = json.loads(out_file.read_text(encoding="utf-8"))
    assert len(doc["resourceSpans"][0]["scopeSpans"][0]["spans"]) == 1


def test_trace_export_explicit_in_override(trace_repo, run_cli, engine):
    standalone = trace_repo / "somewhere" / "custom-trace.jsonl"
    standalone.parent.mkdir(parents=True)
    event = engine._trace_build_event(phase="gate", action="gate.ci", outcome="pass",
                                       exit_code=0, duration_ms=1.0, mission_id=None)
    standalone.write_text(json.dumps(event) + "\n", encoding="utf-8")

    r = run_cli(trace_repo, "trace", "export", "--format", "otlp-json", "--in", "somewhere/custom-trace.jsonl")
    assert r.returncode == 0, r.stdout + r.stderr
    doc = json.loads(r.stdout)
    assert len(doc["resourceSpans"][0]["scopeSpans"][0]["spans"]) == 1


def test_trace_export_skips_schema_invalid_or_unparsable_lines_without_crashing(trace_repo, run_cli, engine):
    good = engine._trace_build_event(phase="gate", action="gate.ci", outcome="pass",
                                      exit_code=0, duration_ms=1.0, mission_id=None)
    lines = [
        json.dumps(good),
        "{not valid json",
        json.dumps({"schema": engine.TRACE_SCHEMA_VERSION}),  # schema-invalid: missing fields
    ]
    p = trace_repo / "somewhere2" / "mixed-trace.jsonl"
    p.parent.mkdir(parents=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")

    r = run_cli(trace_repo, "trace", "export", "--format", "otlp-json", "--in", "somewhere2/mixed-trace.jsonl")
    assert r.returncode == 0, r.stdout + r.stderr
    doc = json.loads(r.stdout)
    assert len(doc["resourceSpans"][0]["scopeSpans"][0]["spans"]) == 1
    assert "SKIPPED" in r.stderr


def test_trace_export_no_events_produces_empty_but_valid_document(trace_repo, run_cli):
    r = run_cli(trace_repo, "trace", "export", "--format", "otlp-json")
    assert r.returncode == 0, r.stdout + r.stderr
    doc = json.loads(r.stdout)
    assert doc["resourceSpans"][0]["scopeSpans"][0]["spans"] == []


# ===========================================================================
# 5) No network, ever — socket-guard tests + a static import scan
# ===========================================================================


_FORBIDDEN_NETWORK_MODULES = ("socket", "http.client", "urllib.request", "urllib3", "requests", "httpx", "aiohttp")

# Static `import X` / `from X import Y` — the literal, most common form.
_STATIC_IMPORT_RE = re.compile(r"^\s*(?:import|from)\s+([\w\.]+)", re.MULTILINE)

# Dynamic imports evade the static scan above entirely — `__import__("socket")`
# needs no `import`/`from` keyword at all, and `importlib.import_module(...)`
# (or `import_module(...)` after `from importlib import import_module`) is
# the standard-library-blessed way to do the same thing. Both take the
# target module name as a plain string literal, which is what this matches.
_DYNAMIC_IMPORT_RE = re.compile(r"(?:__import__|import_module)\s*\(\s*['\"]([\w\.]+)['\"]")


def _forbidden_networking_imports(src: str, forbidden=_FORBIDDEN_NETWORK_MODULES) -> list:
    """Every forbidden networking module name referenced by ANY import
    form (static or dynamic) found in `src`. Shared by the real engine-source
    scan below and its own non-vacuousness proof, so the two can never
    silently drift apart."""
    imported_modules = {m.group(1) for m in _STATIC_IMPORT_RE.finditer(src)}
    imported_modules |= {m.group(1) for m in _DYNAMIC_IMPORT_RE.finditer(src)}
    return [
        name for name in forbidden
        if any(mod == name or mod.startswith(name + ".") for mod in imported_modules)
    ]


def test_engine_source_never_imports_networking_libraries():
    """Static guarantee, independent of any monkeypatching: the whole engine
    (not just the trace region) never imports a networking library — by a
    literal `import`/`from` line OR a dynamic `__import__(...)` /
    `importlib.import_module(...)` call. Guards against a FUTURE regression
    anywhere in the file, not just today's diff."""
    src = ENGINE_SRC.read_text(encoding="utf-8")
    hits = _forbidden_networking_imports(src)
    assert hits == [], f"tessctl imports networking module(s) it should never need: {hits}"


@pytest.mark.parametrize(
    "snippet, expected_hit",
    [
        ('__import__("socket")', "socket"),
        ("__import__('urllib.request')", "urllib.request"),
        ("importlib.import_module('socket')", "socket"),
        ('from importlib import import_module\nimport_module("socket")', "socket"),
    ],
)
def test_import_scan_is_non_vacuous_for_dynamic_imports(snippet, expected_hit):
    """Proves `_forbidden_networking_imports` (and therefore the real scan
    above) actually catches the dynamic-import forms a literal
    `import`/`from` regex alone would miss — without this, the scan's
    'guards against a FUTURE regression' claim would be untested."""
    assert _forbidden_networking_imports(snippet) == [expected_hit]


def test_import_scan_static_form_still_works_alongside_dynamic():
    """Sanity check that broadening the scan for dynamic imports didn't
    regress the original literal `import`/`from` detection it's layered on
    top of."""
    assert _forbidden_networking_imports("import socket\n") == ["socket"]
    assert _forbidden_networking_imports("from urllib import request\n") == []  # not a forbidden name itself
    assert _forbidden_networking_imports("import requests\n") == ["requests"]
    assert _forbidden_networking_imports("import json\nimport re\n") == []


class _SocketOpenedError(BaseException):
    """Raised by the test's socket patches. Rooted in `BaseException`, NOT
    `Exception` (closes a MEDIUM finding, 2026-07): `_trace_record`'s
    best-effort recorder in `.tess/bin/tessctl` deliberately catches only
    `Exception` — a genuine local trace-write failure (disk full,
    permissions, a tracer bug) must degrade to a stderr WARNING, but a live
    network attempt anywhere in that function's call graph must never be
    mistaken for one of those and swallowed the same way. Rooting this
    signal in `BaseException` makes that structural, not a matter of
    `_trace_record` correctly guessing which exceptions are "safe" to
    swallow — the type system enforces it regardless of how deep in the
    call graph the guard fires. See `test_trace_record_never_swallows_a_
    socket_open_on_the_append_path` below for the non-vacuous proof, and
    `_trace_record`'s docstring in `.tess/bin/tessctl` for the production
    side of this contract. Distinct from an ordinary `AssertionError`
    elsewhere in the call graph so the two are never confused with each
    other either."""


@pytest.fixture
def no_network(monkeypatch):
    """Patches every Python-level socket entry point that could initiate a
    network operation to instead raise. Subprocess children (git, gpg) are
    untouched — see the module docstring: the guarantee under test is that
    tessctl's OWN process (specifically the trace/export code path) never
    reaches for the network; git/gpg here only ever run against the local
    repo/keyring, never a remote."""
    def _raise(*a, **kw):
        raise _SocketOpenedError("network call attempted via socket module")

    monkeypatch.setattr(socket, "socket", _raise)
    monkeypatch.setattr(socket, "create_connection", _raise)
    monkeypatch.setattr(socket, "getaddrinfo", _raise)
    return _raise


def test_no_network_in_gate_ci_call_graph(trace_repo, engine, no_network):
    base = _base_sha(trace_repo)
    (trace_repo / "src" / "prod").mkdir(parents=True)
    (trace_repo / "src" / "prod" / "app.py").write_text("print('prod')\n")
    head = _commit_all(trace_repo, "prod change")

    with pytest.raises(SystemExit):
        engine._cmd_gate_ci(ns(base=base, head=head, json_out=True, verdict_dirs=None), trace_repo)

    # Proves the run actually happened (and thus exercised the trace call-site)
    # rather than having failed before reaching it.
    assert _fallback_events(trace_repo)


def test_no_network_in_validate_call_graph(trace_repo, engine, no_network):
    brief = trace_repo / "loose.brief.md"
    brief.write_text(_VALID_BRIEF_TEXT, encoding="utf-8")

    with pytest.raises(SystemExit):
        engine.cmd_validate(ns(contract_type="brief", file=str(brief), json_out=True), trace_repo)

    assert _fallback_events(trace_repo)


def test_no_network_in_trace_export_call_graph(trace_repo, engine, no_network):
    brief = trace_repo / "missions" / "m5" / "briefs" / "ok.brief.md"
    brief.parent.mkdir(parents=True)
    brief.write_text(_VALID_BRIEF_TEXT, encoding="utf-8")

    # Populate one real trace event (validate's own trace-write is exercised
    # under the SAME network guard here, proving it too is network-free),
    # then export it — also still under the guard.
    with pytest.raises(SystemExit):
        engine.cmd_validate(ns(contract_type="brief", file=str(brief), json_out=True), trace_repo)

    engine._cmd_trace_export(
        ns(export_format="otlp-json", mission_id=None, in_paths=None, out=None), trace_repo,
    )


def test_no_network_in_gate_pre_commit_call_graph(trace_repo, engine, no_network):
    brief_path = trace_repo / "missions" / "m6" / "briefs" / "task.brief.md"
    brief_path.parent.mkdir(parents=True)
    brief_path.write_text(_INVALID_BRIEF_TEXT, encoding="utf-8")
    _git(trace_repo, "add", "-A")

    with pytest.raises(SystemExit):
        engine._cmd_gate_pre_commit(ns(json_out=True), trace_repo)

    assert (trace_repo / "missions" / "m6" / "trace.jsonl").exists()


def test_trace_record_never_swallows_a_socket_open_on_the_append_path(engine, tmp_path, monkeypatch, no_network):
    """Non-vacuous proof closing the MEDIUM finding: `_trace_record`'s
    best-effort `except Exception` must never swallow a live network
    attempt made ANYWHERE inside its own try — including a hypothetical
    future step bolted on right after the local JSONL write succeeds (e.g.
    "also mirror this event to a remote collector"). That call-graph shape
    is exactly what the four `test_no_network_in_*_call_graph` tests above
    cannot see: they only assert on the OUTER command's `SystemExit` and on
    the trace file's existence, both of which would still hold even if a
    socket call buried inside `_trace_record` got silently caught and
    downgraded to a stderr WARNING.

    Simulates that future regression by wrapping the real
    `_trace_append_event` so it performs the genuine local write and THEN
    opens a socket — under `no_network` this raises `_SocketOpenedError`.

    Verified non-vacuous by hand against the pre-fix code: with the old
    `_SocketOpenedError(AssertionError)` hierarchy, `_trace_record`'s
    `except Exception` catches it, prints the WARNING, and returns
    normally — `pytest.raises` below finds nothing to catch and this test
    FAILS ("DID NOT RAISE"). With the fix
    (`_SocketOpenedError(BaseException)`, matching `_trace_record`'s
    "Guard-defeat hardening" docstring contract in `.tess/bin/tessctl`),
    the exception is structurally uncatchable by `except Exception` and
    propagates — this test PASSES.
    """
    real_append = engine._trace_append_event
    write_happened = []

    def _append_then_phone_home(root, event):
        written = real_append(root, event)  # the genuine local write still succeeds
        write_happened.append(written)
        socket.create_connection(("example.invalid", 80))  # simulated future regression
        return written

    monkeypatch.setattr(engine, "_trace_append_event", _append_then_phone_home)

    with pytest.raises(_SocketOpenedError):
        engine._trace_record(
            tmp_path, phase="gate", action="gate.ci", outcome="pass", exit_code=0,
            duration_s=0.001, changed_paths=["x"],
        )

    # The local write really did happen before the simulated regression
    # fired — this test is about the swallowed EXCEPTION, not a write
    # failure, and must not be satisfied by a write that never ran.
    assert write_happened, "expected the real local append to run before the simulated socket call"


def test_trace_record_still_swallows_a_genuine_tracer_bug(engine, tmp_path, monkeypatch, capsys):
    """Companion to the test above, proving the hardening didn't overcorrect:
    an ordinary internal tracer bug (any plain `Exception`, unrelated to the
    network guard) must still degrade to a stderr WARNING exactly as
    `test_trace_record_is_best_effort_and_never_raises` already covers —
    restated here, right next to the socket-guard proof, so the two
    contracts ("swallow genuine bugs" vs "never swallow a network attempt")
    are visibly tested side by side."""
    def _boom(*a, **kw):
        raise RuntimeError("synthetic tracer bug, not a network attempt")

    monkeypatch.setattr(engine, "_trace_build_event", _boom)
    engine._trace_record(  # must not raise
        tmp_path, phase="gate", action="gate.ci", outcome="pass", exit_code=0,
        duration_s=0.001, changed_paths=["x"],
    )
    assert "WARNING" in capsys.readouterr().err


# ===========================================================================
# 6) `_trace_rel_or_str` — out-of-tree path redaction
# ===========================================================================


def test_trace_rel_or_str_redacts_out_of_tree_absolute_paths(engine, tmp_path):
    """Closes the LOW finding alongside the MEDIUM: a `tessctl validate`
    call against a file outside `root` must not leak the file's raw
    absolute path (home dir, username, client/project names, ...) into the
    OTLP export's `tess.validate.file` attribute — only the filename,
    clearly tagged as out-of-tree."""
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "elsewhere" / "secret-client-name" / "loose.brief.md"
    outside.parent.mkdir(parents=True)
    outside.write_text("x", encoding="utf-8")

    result = engine._trace_rel_or_str(root, outside)

    assert result == "<out-of-tree>/loose.brief.md"
    assert "secret-client-name" not in result
    assert str(tmp_path) not in result


def test_trace_rel_or_str_returns_root_relative_path_when_in_tree(engine, tmp_path):
    root = tmp_path / "repo"
    inner = root / "missions" / "m1" / "briefs" / "task.brief.md"
    inner.parent.mkdir(parents=True)
    inner.write_text("x", encoding="utf-8")

    assert engine._trace_rel_or_str(root, inner) == "missions/m1/briefs/task.brief.md"
