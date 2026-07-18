"""Smoke tests for orchestrator.cli -- the manual-testing wrapper around
run_pipeline(), same role intent_router.cli / spec_engine.cli play for
their own components. Exercises the real pipeline end to end through the
CLI's own argument parsing and reporting. Every invocation passes an
explicit --identity-dir under tmp_path so the default
LocalIdentityApprovalGate never touches the real machine's
~/.tess-os/approval-identity/, and a monkeypatched `input` so the
interactive confirmation prompt is answered deterministically."""

from __future__ import annotations

import _orchestrator_paths  # noqa: F401 -- sys.path bootstrap
from _orchestrator_paths import EXAMPLE_ROUTING_TABLE, INTENT_ROUTER_ROOT, SPEC_ENGINE_ROOT

import orchestrator.cli as cli_module
from orchestrator.identity import IdentityError
from orchestrator.pipeline import PipelineError

CONFIDENT_INPUT = (
    "I'm seriously considering opening up in a completely new country next year, "
    "is that a smart expansion move for us right now?"
)
AMBIGUOUS_INPUT = "hello"


def _run_cli(monkeypatch, tmp_path, argv, answers=("APPROVE",)):
    answer_iter = iter(answers)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answer_iter))
    # --no-log: this suite must never write into the repo's own shared
    # intent-router/decisions/ or spec-engine/specs/ sinks -- a real bug
    # was caught here (running the full repo suite together, an earlier
    # orchestrator CLI test without --no-log left a stray
    # intent-router/decisions/log.jsonl on disk that broke an unrelated,
    # pre-existing test in tests/intent_router/test_pipeline.py asserting
    # that file does NOT exist).
    return cli_module.main(argv + ["--identity-dir", str(tmp_path / "identity"), "--no-log"])


def test_cli_run_generates_an_app_and_exits_zero(monkeypatch, tmp_path, capsys):
    target_dir = tmp_path / "generated-app"
    exit_code = _run_cli(monkeypatch, tmp_path, [
        "run", CONFIDENT_INPUT,
        "--table", str(EXAMPLE_ROUTING_TABLE),
        "--target-dir", str(target_dir),
    ])
    assert exit_code == 0
    assert (target_dir / "SPEC.md").is_file()
    out = capsys.readouterr().out
    assert "Generated app at" in out


def test_cli_run_reports_a_clarifying_question_and_exits_2(monkeypatch, tmp_path, capsys):
    exit_code = _run_cli(monkeypatch, tmp_path, [
        "run", AMBIGUOUS_INPUT,
        "--table", str(EXAMPLE_ROUTING_TABLE),
        "--target-dir", str(tmp_path / "generated-app"),
    ])
    assert exit_code == 2
    out = capsys.readouterr().out
    assert "clarifying question" in out.lower()


def test_cli_run_reports_a_rejection_and_exits_1(monkeypatch, tmp_path, capsys):
    exit_code = _run_cli(
        monkeypatch, tmp_path, [
            "run", CONFIDENT_INPUT,
            "--table", str(EXAMPLE_ROUTING_TABLE),
            "--target-dir", str(tmp_path / "generated-app"),
        ],
        answers=("REJECT", "not the right idea yet"),
    )
    assert exit_code == 1
    out = capsys.readouterr().out
    assert "rejected" in out.lower()
    assert not (tmp_path / "generated-app").exists()


def test_cli_no_log_flag_writes_nothing_to_the_shared_sinks(monkeypatch, tmp_path):
    """Regression test: a CLI run without --no-log used to silently write
    into the repo's own intent-router/decisions/log.jsonl and
    spec-engine/specs/*.jsonl (this component's shared, checked-out-repo
    default sinks) with no way to suppress it -- caught when running the
    full repo suite together broke an unrelated, pre-existing assertion in
    tests/intent_router/test_pipeline.py that these files stay absent
    after a --no-log run. --no-log must leave every one of these sinks
    exactly as it found them."""
    decisions_log = INTENT_ROUTER_ROOT / "decisions" / "log.jsonl"
    spec_sinks = [
        SPEC_ENGINE_ROOT / "specs" / "plans.jsonl",
        SPEC_ENGINE_ROOT / "specs" / "specs.jsonl",
        SPEC_ENGINE_ROOT / "specs" / "approvals.jsonl",
    ]
    before = {p: (p.read_bytes() if p.is_file() else None) for p in [decisions_log, *spec_sinks]}

    exit_code = _run_cli(monkeypatch, tmp_path, [
        "run", CONFIDENT_INPUT,
        "--table", str(EXAMPLE_ROUTING_TABLE),
        "--target-dir", str(tmp_path / "generated-app"),
    ])
    assert exit_code == 0

    after = {p: (p.read_bytes() if p.is_file() else None) for p in [decisions_log, *spec_sinks]}
    assert after == before


# --------------------------------------------------------------------------
# [Reid LOW] IdentityError / PipelineError CLI robustness -- a corrupt/
# missing/over-permissive local approval-identity key, or a wiring-level
# pipeline error, must report a clean stderr message + distinct exit code
# (4), never dump a raw Python traceback at a CLI user.
# --------------------------------------------------------------------------


def test_cli_reports_identity_error_cleanly_and_exits_4(monkeypatch, tmp_path, capsys):
    def _raise_identity_error(*args, **kwargs):
        raise IdentityError("approval identity key is corrupt (wrong length)")

    monkeypatch.setattr(cli_module, "run_pipeline", _raise_identity_error)
    exit_code = _run_cli(monkeypatch, tmp_path, [
        "run", CONFIDENT_INPUT,
        "--table", str(EXAMPLE_ROUTING_TABLE),
        "--target-dir", str(tmp_path / "generated-app"),
    ])
    assert exit_code == 4
    err = capsys.readouterr().err
    assert "IdentityError" in err
    assert "approval identity key is corrupt" in err


def test_cli_reports_pipeline_error_cleanly_and_exits_4(monkeypatch, tmp_path, capsys):
    def _raise_pipeline_error(*args, **kwargs):
        raise PipelineError("wiring-level failure")

    monkeypatch.setattr(cli_module, "run_pipeline", _raise_pipeline_error)
    exit_code = _run_cli(monkeypatch, tmp_path, [
        "run", CONFIDENT_INPUT,
        "--table", str(EXAMPLE_ROUTING_TABLE),
        "--target-dir", str(tmp_path / "generated-app"),
    ])
    assert exit_code == 4
    err = capsys.readouterr().err
    assert "PipelineError" in err
    assert "wiring-level failure" in err
