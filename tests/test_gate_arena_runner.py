"""Regression tests for the bypass-corpus runner's process-status contract."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
from pathlib import Path


RUNNER_PATH = Path(__file__).resolve().parents[1] / "gate-arena" / "bypass" / "run_bypass_corpus.py"


def _load_runner():
    loader = importlib.machinery.SourceFileLoader("tess_gate_arena_runner_test", str(RUNNER_PATH))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _outcome(blocked: bool) -> dict:
    return {
        "id": "T1",
        "name": "test attack",
        "description": "test-only runner outcome",
        "blocked": blocked,
        "mechanism": "test-only",
        "evidence": {},
    }


def test_bypass_runner_returns_nonzero_and_records_a_slipped_attack(monkeypatch, tmp_path):
    runner = _load_runner()
    monkeypatch.setattr(runner.lib, "load_engine", lambda: object())
    monkeypatch.setattr(runner, "RESULTS_DIR", tmp_path)
    monkeypatch.setattr(runner, "ALL_ATTACKS", [lambda _base, _engine: _outcome(False)])

    assert runner.main() == 1
    scorecard = json.loads((tmp_path / "bypass-scorecard.json").read_text(encoding="utf-8"))
    assert scorecard["blocked"] == 0
    assert scorecard["slipped_through"] == 1


def test_bypass_runner_returns_zero_only_when_every_attack_is_blocked(monkeypatch, tmp_path):
    runner = _load_runner()
    monkeypatch.setattr(runner.lib, "load_engine", lambda: object())
    monkeypatch.setattr(runner, "RESULTS_DIR", tmp_path)
    monkeypatch.setattr(runner, "ALL_ATTACKS", [lambda _base, _engine: _outcome(True)])

    assert runner.main() == 0
    scorecard = json.loads((tmp_path / "bypass-scorecard.json").read_text(encoding="utf-8"))
    assert scorecard["blocked"] == 1
    assert scorecard["slipped_through"] == 0
