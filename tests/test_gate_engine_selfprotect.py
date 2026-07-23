"""
honesty-capstone-audit-2026-07-08 §3-c — same-push ENGINE tamper.

`.github/workflows/tess-gate.yml` ran `python3 .tess/bin/tessctl gate ci`
FROM THE PUSHED CHECKOUT, and `.tess/bin/**` was in NO policy glob. A PR
that edited `_gate_run_ship_check` (or any gate logic in .tess/bin/tessctl)
to unconditionally report "not blocked", in the SAME push as an unreviewed
payload, would keep the required check green against a tampered engine —
the tampered engine is exactly what evaluates whether the tamper itself
should be blocked, so no policy rule alone can catch it (A8's disclosure
covered the workflow FILE; this is the ENGINE that file invokes, and the
A3 baseline-union fix cannot help either — the tampered engine is what
would run that fix's own logic).

Two-layer fix, both proven here:
  (i)  policy coverage — `.tess/bin/**` + the root `tessctl` wrapper are now
       in `core/policy/policy.yaml`'s `tess-os-security-tier-doctrine`
       globs, so an engine edit is itself `prod_touching` and needs its own
       covering, signed Reid/Cyra verdict.
  (ii) pinned/trusted engine execution — the CI workflow (v3) now extracts
       and runs the engine AS IT EXISTED AT THE PUSH'S BASE REF, never the
       pushed tree's own copy, via a dedicated "Extract trusted gate
       engine" step. This file parses and EXECUTES the real, committed
       `.github/workflows/tess-gate.yml`'s own shell steps (not a
       reimplementation) to prove this end-to-end.

Non-vacuous proof (per the dispatch brief): the SAME attack fixture is
evaluated two ways — "naively" (running the pushed HEAD's own, tampered
engine — exactly what the v2/unpatched workflow did) and via the REAL,
current `.github/workflows/tess-gate.yml`'s trusted-engine steps. The naive
path is NOT blocked (proves the vulnerability the fix closes); the real
workflow's own steps ARE blocked (proves the fix holds) — this is the
literal v2-vs-v3 difference, not a synthetic comparison.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_REL = ".github/workflows/tess-gate.yml"
REAL_POLICY_PATH = REPO_ROOT / "core" / "policy" / "policy.yaml"

HAS_GIT = shutil.which("git") is not None
pytestmark = pytest.mark.skipif(not HAS_GIT, reason="git required")

_COPY_IGNORE = shutil.ignore_patterns(".git", "tests", ".pytest_cache", "__pycache__")

# The engine's own ship-check entrypoint — patched to a hardcoded, always-
# clean early return. This is the EXACT attack the audit disclosed: an
# attacker editing `_gate_run_ship_check` (not just adding an unreviewed
# file) to self-attest "not blocked" regardless of what actually changed.
_NEUTER_MARKER = "def _gate_run_ship_check("
_NEUTER_INJECTION = (
    "def _gate_run_ship_check(\n"
    # `**_kwargs` (not a hand-copied positional list) tolerates whatever
    # keyword arguments the real callers currently pass (e.g. `gate ci`'s
    # `emit_receipts=True` — the emit_receipts gate-overlap fix) without
    # this fixture needing to track this function's own signature drift —
    # the point of this stub is "an attacker's always-pass replacement
    # still gets CALLED the same way the real one is," not an exact
    # parameter-list replica.
    "    *_args, **_kwargs,\n"
    "):\n"
    "    # SAME-PUSH ENGINE TAMPER (honesty-capstone-audit-2026-07-08 §3-c fixture):\n"
    "    # an attacker-inserted early return that self-attests clean, unconditionally.\n"
    "    return {\"blocked\": False, \"reasons\": [], \"changed_paths\": _args[1] if len(_args) > 1 else []}\n"
    "\n"
    "\n"
    "def _gate_run_ship_check_ORIGINAL_UNREACHABLE(\n"
)


def _git(root, *args, check=True):
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@tess.test",
        "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@tess.test",
    }
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, env=env)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr}\n{r.stdout}")
    return r


@pytest.fixture
def real_engine_root(tmp_path):
    """A fresh, isolated copy of the real Tess OS root (incl. .github/ and
    .tess/bin/), one initial commit — the pristine, untampered baseline."""
    dst = tmp_path / "os"
    shutil.copytree(REPO_ROOT, dst, ignore=_COPY_IGNORE)
    assert (dst / WORKFLOW_REL).exists()
    assert (dst / ".tess" / "bin" / "tessctl").exists()
    _git(dst, "init", "-q")
    _git(dst, "config", "user.email", "test@tess.test")
    _git(dst, "config", "user.name", "Test")
    _git(dst, "config", "commit.gpgsign", "false")
    _git(dst, "add", "-A")
    _git(dst, "commit", "-q", "-m", "initial (real shipped tree, untampered engine)")
    return dst


def _neuter_engine_in_place(root: Path) -> None:
    engine_path = root / ".tess" / "bin" / "tessctl"
    text = engine_path.read_text(encoding="utf-8")
    assert text.count(_NEUTER_MARKER) == 1, "fixture assumes exactly one _gate_run_ship_check def"
    text = text.replace(_NEUTER_MARKER, _NEUTER_INJECTION, 1)
    engine_path.write_text(text, encoding="utf-8")


def _run_naive(root: Path, base: str, head: str):
    """Exactly what the v2/unpatched CI workflow did: run the PUSHED
    checkout's own copy of .tess/bin/tessctl directly."""
    env = {**os.environ, "TESS_ROOT": str(root)}
    return subprocess.run(
        [sys.executable, str(root / ".tess" / "bin" / "tessctl"), "gate", "ci",
         "--base", base, "--head", head, "--json"],
        cwd=str(root), env=env, capture_output=True, text=True,
    )


def _extract_step_run(workflow_text: str, step_name: str) -> str:
    doc = yaml.safe_load(workflow_text)
    for step in doc["jobs"]["ship-gate"]["steps"]:
        if step.get("name") == step_name:
            return step["run"]
    raise KeyError(step_name)


def _run_real_workflow_trusted_engine(root: Path, base: str, head: str):
    """Parses and EXECUTES the real, COMMITTED `.github/workflows/
    tess-gate.yml`'s own "Extract trusted gate engine" + final "tessctl
    gate ci" run: blocks — substituting the two GH Actions expressions this
    harness needs (steps.refs.outputs.{base,evaluation}, steps.trusted_engine.
    outputs.engine_path) with literal values / a real $GITHUB_OUTPUT file.
    This proves the ACTUAL committed workflow script (not a
    reimplementation) closes the gap — if the fix is ever reverted (the
    "Extract trusted gate engine" step removed), `_extract_step_run` raises
    KeyError and this test errors, which is the correct "fails on
    unpatched" signal."""
    workflow_text = (root / WORKFLOW_REL).read_text(encoding="utf-8")
    extract_script = _extract_step_run(
        workflow_text, "Extract trusted gate engine (base ref only — never the pushed tree)",
    )
    ci_script = _extract_step_run(
        workflow_text, "tessctl gate ci (trusted base-ref engine; untrusted pushed tree)",
    )

    extract_script = extract_script.replace("${{ steps.refs.outputs.base }}", base)
    gh_output_path = Path(tempfile.mkstemp(prefix="gh_output_")[1])
    gh_output_path.write_text("")
    env1 = {**os.environ, "GITHUB_OUTPUT": str(gh_output_path)}
    r1 = subprocess.run(["bash", "-c", extract_script], cwd=str(root), env=env1, capture_output=True, text=True)
    if r1.returncode != 0:
        return r1.returncode, r1.stdout + r1.stderr

    outputs = {}
    for line in gh_output_path.read_text().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            outputs[k] = v
    gh_output_path.unlink(missing_ok=True)
    engine_path = outputs.get("engine_path")
    assert engine_path, f"extract step did not emit engine_path — stdout/stderr: {r1.stdout}{r1.stderr}"

    ci_script2 = (
        ci_script
        .replace("${{ steps.trusted_engine.outputs.engine_path }}", engine_path)
        .replace("${{ steps.refs.outputs.base }}", base)
        .replace("${{ steps.refs.outputs.evaluation }}", head)
    )
    assert "${{" not in ci_script2, (
        "the trusted gate command must substitute every GitHub Actions "
        "expression before its shell is executed"
    )
    env2 = {**os.environ, "TESS_ROOT": str(root)}
    r2 = subprocess.run(["bash", "-c", ci_script2], cwd=str(root), env=env2, capture_output=True, text=True)
    return r2.returncode, r2.stdout + r2.stderr


# ---------------------------------------------------------------------------
# The core non-vacuous proof
# ---------------------------------------------------------------------------

def test_same_push_engine_tamper_slips_past_naive_execution_but_not_the_real_workflow(real_engine_root):
    """The central proof for §3-c: the SAME attack (engine neutered +
    payload, one push) evaluated two ways.
      * naive (pushed tree's own engine, i.e. what v2/unpatched CI did):
        NOT blocked — the attack succeeds.
      * the REAL, current .github/workflows/tess-gate.yml's own trusted-
        engine steps: BLOCKED — the attack fails.
    """
    root = real_engine_root
    base = _git(root, "rev-parse", "HEAD").stdout.strip()

    _neuter_engine_in_place(root)
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "src" / "app.py").write_text("print('shipped alongside a neutered engine')\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "chore: tidy engine internals (payload hidden in same commit)")
    head = _git(root, "rev-parse", "HEAD").stdout.strip()

    naive = _run_naive(root, base, head)
    naive_payload = json.loads(naive.stdout) if naive.stdout.strip() else None
    naive_blocked = naive_payload["blocked"] if naive_payload else (naive.returncode != 0)
    assert naive_blocked is False, (
        f"fixture invariant broken: the naive (pushed-tree) engine should have been "
        f"successfully neutered — got blocked={naive_blocked}, stdout={naive.stdout}"
    )

    trusted_rc, trusted_out = _run_real_workflow_trusted_engine(root, base, head)
    assert trusted_rc != 0, (
        f"REGRESSION: the real committed .github/workflows/tess-gate.yml's own "
        f"trusted-engine steps did not block a same-push engine tamper — {trusted_out}"
    )
    # Public gate output is deliberately redacted: the trusted BASE engine
    # still blocks its candidate-tree replacement, but does not disclose the
    # protected path through the CI log.
    assert "COVERING_APPROVAL_MISSING: no covering APPROVE verdict found" in trusted_out
    assert "bad substitution" not in trusted_out
    assert "${{" not in trusted_out
    assert ".tess/bin/tessctl" not in trusted_out


def test_unmodified_engine_and_ordinary_payload_still_correctly_evaluated(real_engine_root):
    """Sanity / no-regression: with NO engine tamper, the trusted-engine
    path (base-ref extraction) produces the SAME verdict an ordinary,
    honest run would — an ordinary docs-only change is not blocked."""
    root = real_engine_root
    base = _git(root, "rev-parse", "HEAD").stdout.strip()

    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "scratch-note.md").write_text("an ordinary docs note\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "docs: ordinary unrelated change")
    head = _git(root, "rev-parse", "HEAD").stdout.strip()

    rc, out = _run_real_workflow_trusted_engine(root, base, head)
    assert rc == 0, out


def test_trusted_engine_extraction_fails_closed_when_no_baseline_engine_exists(real_engine_root):
    """Bootstrap edge case, documented in the workflow's own header: if the
    base ref predates the gate's adoption (no .tess/bin/tessctl there at
    all), the "Extract trusted gate engine" step must FAIL CLOSED — never
    silently fall back to trusting the pushed tree's own engine."""
    root = real_engine_root
    empty_tree_sha = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
    head = _git(root, "rev-parse", "HEAD").stdout.strip()

    rc, out = _run_real_workflow_trusted_engine(root, empty_tree_sha, head)
    assert rc != 0
    assert "refusing to fall back" in out or "no gate engine found" in out


# ---------------------------------------------------------------------------
# Policy coverage half (i): `.tess/bin/**` + `tessctl` are governed
# ---------------------------------------------------------------------------

def test_real_policy_yaml_globs_include_engine_paths():
    instance = yaml.safe_load(REAL_POLICY_PATH.read_text(encoding="utf-8"))
    rule = next(r for r in instance["policy"]["rules"] if r["id"] == "tess-os-security-tier-doctrine")
    assert ".tess/bin/**" in rule["globs"]
    assert "tessctl" in rule["globs"]
    assert rule["require_verdict"] is True
    assert set(rule["allowed_verifiers"]) == {"Reid", "Cyra"}


def test_editing_the_engine_with_no_covering_verdict_is_blocked_end_to_end(real_engine_root, run_cli):
    """Uses the REAL, unmodified shipped policy.yaml (verifier_keys ships
    empty, so this is unconditional): editing .tess/bin/tessctl with no
    covering verdict at all must BLOCK, independent of any tamper attempt —
    the policy-coverage layer alone already catches an honest engine edit."""
    root = real_engine_root
    base = _git(root, "rev-parse", "HEAD").stdout.strip()

    engine_path = root / ".tess" / "bin" / "tessctl"
    engine_path.write_text(engine_path.read_text(encoding="utf-8") + "\n# a harmless comment\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "chore: comment tweak to the engine")
    head = _git(root, "rev-parse", "HEAD").stdout.strip()

    r = run_cli(root, "gate", "ci", "--base", base, "--head", head, "--json")
    assert r.returncode == 1, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    assert payload["blocked"] is True
    assert "COVERING_APPROVAL_MISSING: no covering APPROVE verdict found" in payload["reasons"]
    assert ".tess/bin/tessctl" not in json.dumps(payload)
