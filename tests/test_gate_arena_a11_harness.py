"""Regression coverage for the A11 trusted-engine corpus harness.

The corpus runs the committed GitHub Actions shell locally.  An unexpanded
Actions expression would make bash fail before the trusted BASE engine runs,
which must be reported as an invalid fixture rather than a blocked attack.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
ARENA_LIB = REPO_ROOT / "gate-arena" / "bypass" / "lib.py"


def _load_arena_lib():
    spec = importlib.util.spec_from_file_location("tess_gate_arena_lib", ARENA_LIB)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a11_trusted_command_substitutes_exact_actions_expressions():
    arena = _load_arena_lib()
    workflow_text = (REPO_ROOT / ".github" / "workflows" / "tess-gate.yml").read_text(
        encoding="utf-8",
    )
    command = arena._extract_workflow_step_run(
        workflow_text,
        "tessctl gate ci (trusted base-ref engine; untrusted pushed tree)",
    )

    rendered = arena._render_trusted_ci_gate_command(
        command,
        "/tmp/trusted-tessctl",
        "a" * 40,
        "b" * 40,
    )

    assert "${{" not in rendered
    assert 'python3 "/tmp/trusted-tessctl" gate ci' in rendered
    assert f'--base "{"a" * 40}"' in rendered
    assert f'--head "{"b" * 40}"' in rendered


def test_a11_trusted_command_rejects_unexpanded_actions_expression():
    arena = _load_arena_lib()
    with pytest.raises(ValueError, match="unexpanded GitHub Actions expression"):
        arena._render_trusted_ci_gate_command(
            "python3 ${{ steps.unknown.outputs.value }}",
            "/tmp/trusted-tessctl",
            "a" * 40,
            "b" * 40,
        )
