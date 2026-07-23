"""Regression coverage for the A11 trusted-engine corpus harness.

The corpus runs the committed GitHub Actions shell locally.  An unexpanded
Actions expression would make bash fail before the trusted BASE engine runs,
which must be reported as an invalid fixture rather than a blocked attack.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
ARENA_LIB = REPO_ROOT / "gate-arena" / "bypass" / "lib.py"
ARENA_ATTACKS = REPO_ROOT / "gate-arena" / "bypass" / "attacks.py"


def _load_arena_lib():
    spec = importlib.util.spec_from_file_location("tess_gate_arena_lib", ARENA_LIB)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_arena_attacks():
    # `attacks.py` does `from lib import ...` — the same sys.path bootstrap
    # `gate-arena/bypass/run_bypass_corpus.py` itself uses.
    bypass_dir = ARENA_ATTACKS.parent
    if str(bypass_dir) not in sys.path:
        sys.path.insert(0, str(bypass_dir))
    spec = importlib.util.spec_from_file_location("tess_gate_arena_attacks", ARENA_ATTACKS)
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


# ---------------------------------------------------------------------------
# ★ Reid MED (gate-overlap re-reconciliation, round 3) — the exact signature-
# drift gap that let `attacks.py`'s A11 `_NEUTER_INJECTION` stub silently
# stop reflecting a real §3-c same-push-engine-tamper (raising `TypeError`
# on the `emit_receipts` kwarg instead of "slipping" as intended) while
# `gate-arena/results/bypass-scorecard.{md,json}` kept claiming 12/12. This
# is the single assertion that would have caught it: exec the injected
# stub in isolation and call it with the EXACT shape `_cmd_gate_ci` uses
# for a real ship-authorization call (`emit_receipts=True`). If a future
# `_gate_run_ship_check` signature change breaks this stub again, this
# test fails in CI — not silently, on the next manual gate-arena regen.
# ---------------------------------------------------------------------------

def test_a11_neuter_injection_stub_tolerates_real_gate_ci_call_shape():
    attacks = _load_arena_attacks()
    # `_NEUTER_INJECTION` is designed to be SPLICED into the real engine
    # file (it ends mid-signature, deliberately: `_gate_run_ship_check_
    # ORIGINAL_UNREACHABLE(` is completed by the original file's OWN
    # remaining bytes after the string-replace) — not to be exec'd
    # standalone. Isolate just the complete, syntactically valid first
    # function (the actual injected stub) for direct execution here.
    stub_src = attacks._NEUTER_INJECTION.split(
        "def _gate_run_ship_check_ORIGINAL_UNREACHABLE",
    )[0]
    namespace: dict = {}
    exec(stub_src, namespace)  # noqa: S102 (test-only, trusted source)
    stub = namespace["_gate_run_ship_check"]

    # `_cmd_gate_ci`'s own real call shape (.tess/bin/tessctl): root,
    # changed, verdict_dirs, [head], [base], admission_source,
    # [attestation_head], emit_receipts=True — a genuine ship-authorization
    # call, not a diagnostic one.
    result = stub(
        "/fake/root", ["src/prod/app.py"], None, ["b" * 40], ["a" * 40],
        object(), ["b" * 40], emit_receipts=True,
    )

    assert result == {
        "blocked": False, "reasons": [], "changed_paths": ["src/prod/app.py"],
    }
