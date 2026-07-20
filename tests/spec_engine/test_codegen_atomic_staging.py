"""Kill-proof proof for the codegen atomic-staging fix (Gap B / DoD B.9):
`spec_engine.codegen.generate_app()` must never leave a genuinely partial
file tree — or, worse, a tree whose `.spec-engine/codegen-manifest.json`
already claims `codegen_status: "generated"` while other generated files
are still missing — sitting in `target_dir` if the process is killed
mid-generation.

Two classes of proof:

  - **SIGKILL tests** (`test_kill_*`): spawn `generate_app()` in a real
    child process, instrumented to pause (via `time.sleep`) right after a
    specific file write completes, `SIGKILL` it in that window (a signal
    Python cannot catch or clean up after), then assert `target_dir` is
    exactly as it was before the call — never a partial mix. One test
    kills right after the VERY FIRST file write; the other kills right
    after `.spec-engine/codegen-manifest.json` is written but BEFORE
    `write_scaffold_stub()`'s own writes (`SPEC.md`/`CLAUDE.md`/...) run
    — the precise historical bug scenario, where a manifest already
    claiming completeness could previously survive in `target_dir`
    alongside a missing rest-of-the-tree.
  - **Clean-exception-path test**: a mid-generation `raise` (catchable,
    unlike SIGKILL) must ALSO leave `target_dir` untouched, and must not
    leave an orphaned staging directory behind either.

Plus two smaller regression tests for the staging mechanism itself: that
`generate_app()` called against an already-populated `target_dir` (the
"regenerate on top of a hand-seeded starter template" case
`spec_engine.scaffold.write_scaffold_stub()`'s CLAUDE.md/AGENTS.md-merge
logic exists for) still swaps in atomically and preserves/merges correctly,
and that `CodegenResult.written`'s returned paths are real, live paths
under `target_dir` after publish (not stale staging-directory paths).
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time

import pytest

import _spec_engine_paths  # noqa: F401 -- sys.path bootstrap; COMPONENT_ROOT used below

from spec_engine.codegen import generate_app
from spec_engine.connector_resolver import resolve_connectors
from spec_engine.content import (
    DataModel,
    Entity,
    EntityField,
    HowItLooks,
    HowItWorks,
    KeyFlow,
    KeyScreen,
    WhatItDoes,
    new_id,
    utc_now_iso,
)
from spec_engine.gate_approval import sign_local_approval
from spec_engine.spec_builder import build_spec
from spec_engine.types import Plan

MANIFEST_REL_PATH = ".spec-engine/codegen-manifest.json"


def _rich_spec():
    """A spec with several entities/screens/flows/integrations — enough
    distinct `_write_file` calls that "kill right after write #1" and
    "kill right after the manifest write" land at genuinely different,
    unambiguous points in the generation sequence."""
    plan = Plan(
        plan_id=new_id("plan"),
        mission_id=None,
        created_at=utc_now_iso(),
        source_type="structured_brief",
        input_excerpt="Atomic staging test fixture",
        what_it_does=WhatItDoes(summary="Exercises many file writes for the atomic-staging tests."),
        how_it_looks=HowItLooks(
            description="Several screens.",
            key_screens=[KeyScreen(name=f"Screen {i}", description=f"Screen number {i}.") for i in range(4)],
        ),
        how_it_works=HowItWorks(
            description="Several flows and integrations.",
            key_flows=[KeyFlow(name=f"Flow {i}", steps=["Step one", "Step two"]) for i in range(4)],
            integrations=[f"Integration{i}" for i in range(4)],
        ),
        data_model=DataModel(
            entities=[Entity(name=f"Entity{i}", fields=[EntityField(name="value")]) for i in range(4)]
        ),
        acceptance_criteria=["Baseline acceptance criterion"],
        summary_for_approval="summary",
        resolved_connectors=resolve_connectors([f"Integration{i}" for i in range(4)]),  # none registered -> stubs
    )
    approval = sign_local_approval(plan, approved_by="Xavier")
    return build_spec(plan, approval)


# --------------------------------------------------------------------------
# SIGKILL tests — real child process, real unblockable signal.
# --------------------------------------------------------------------------

_CHILD_SCRIPT = r'''
import os
import sys
import time
import tempfile

target_dir = sys.argv[1]
trigger = sys.argv[2]  # "FIRST" or an exact rel_path, e.g. ".spec-engine/codegen-manifest.json"

# Mirror tests/spec_engine/_spec_engine_paths.py's own bootstrap: this
# child has NO pytest/conftest machinery at all, so it must set up its own
# sys.path and its own throwaway approval-identity dir (never touching
# this machine's real ~/.tess-os/approval-identity/) before importing
# spec_engine.
os.environ.setdefault("TESS_OS_APPROVAL_IDENTITY_DIR", tempfile.mkdtemp(prefix="codegen-kill-test-identity-"))
sys.path.insert(0, "__COMPONENT_ROOT__")

from spec_engine.gate_approval import sign_local_approval
from spec_engine.content import (
    DataModel, Entity, EntityField, HowItLooks, HowItWorks, KeyFlow, KeyScreen, WhatItDoes, new_id, utc_now_iso,
)
from spec_engine.connector_resolver import resolve_connectors
from spec_engine.types import Plan
from spec_engine.spec_builder import build_spec
import spec_engine.codegen as codegen_module

plan = Plan(
    plan_id=new_id("plan"),
    mission_id=None,
    created_at=utc_now_iso(),
    source_type="structured_brief",
    input_excerpt="Kill-proof staging fixture",
    what_it_does=WhatItDoes(summary="Exercises many file writes for the kill-proof atomicity test."),
    how_it_looks=HowItLooks(
        description="Several screens.",
        key_screens=[KeyScreen(name="Screen " + str(i), description="Screen number " + str(i)) for i in range(6)],
    ),
    how_it_works=HowItWorks(
        description="Several flows and integrations.",
        key_flows=[KeyFlow(name="Flow " + str(i), steps=["Step one", "Step two"]) for i in range(6)],
        integrations=["Integration" + str(i) for i in range(6)],
    ),
    data_model=DataModel(entities=[Entity(name="Entity" + str(i), fields=[EntityField(name="value")]) for i in range(6)]),
    acceptance_criteria=["Baseline acceptance criterion"],
    summary_for_approval="summary",
    resolved_connectors=resolve_connectors(["Integration" + str(i) for i in range(6)]),
)
approval = sign_local_approval(plan, approved_by="Xavier")
spec = build_spec(plan, approval)

_orig_write_file = codegen_module._write_file
_state = {"count": 0}


def _instrumented_write_file(root, rel_path, content):
    result = _orig_write_file(root, rel_path, content)
    _state["count"] += 1
    fire = (trigger == "FIRST" and _state["count"] == 1) or (trigger == rel_path)
    if fire:
        print("REACHED:" + rel_path, flush=True)
        # SIGKILL from the parent lands somewhere in here — unblockable,
        # un-catchable, no Python-level cleanup ever runs.
        time.sleep(30)
    return result


codegen_module._write_file = _instrumented_write_file

codegen_module.generate_app(spec, target_dir)
print("COMPLETED", flush=True)
'''


def _spawn_and_kill_mid_write(tmp_path, target_dir, trigger):
    """Runs `generate_app()` in a child process instrumented to print
    `REACHED:<rel_path>` and then sleep right after the write matching
    `trigger` ("FIRST" or an exact rel_path) completes; SIGKILLs the child
    as soon as that marker is observed. Returns the rel_path that was
    reached. Fails the test outright if the child exits (for any reason)
    before reaching the marker — that would mean the kill never actually
    landed mid-generation, and the test would be proving nothing."""
    script_path = tmp_path / f"_child_{abs(hash(trigger))}.py"
    script_path.write_text(
        _CHILD_SCRIPT.replace("__COMPONENT_ROOT__", str(_spec_engine_paths.COMPONENT_ROOT)),
        encoding="utf-8",
    )
    proc = subprocess.Popen(
        [sys.executable, str(script_path), str(target_dir), trigger],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    deadline = time.monotonic() + 30
    marker = None
    try:
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                out = proc.stdout.read()
                err = proc.stderr.read()
                raise AssertionError(
                    f"child exited early (code {proc.returncode}) before reaching the write it "
                    f"was instrumented to pause at (trigger={trigger!r}).\nstdout={out!r}\nstderr={err!r}"
                )
            line = proc.stdout.readline()
            if not line:
                time.sleep(0.02)
                continue
            if line.startswith("REACHED:"):
                marker = line.strip()[len("REACHED:"):]
                break
        if marker is None:
            raise AssertionError(f"child never reached the instrumented write within the deadline (trigger={trigger!r})")

        os.kill(proc.pid, signal.SIGKILL)
        proc.wait(timeout=10)
        assert proc.returncode != 0, "child should have been killed, not exited cleanly"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)
    return marker


def test_kill_mid_first_write_leaves_target_dir_absent_never_partial(tmp_path):
    target_dir = tmp_path / "app"
    assert not target_dir.exists(), "sanity: target_dir must not pre-exist for this test"

    marker = _spawn_and_kill_mid_write(tmp_path, target_dir, "FIRST")

    assert not target_dir.exists(), (
        "target_dir must remain absent — the write the child was killed mid-sleep-after "
        "went into a STAGING sibling directory, never into target_dir itself"
    )
    stage_dirs = [p for p in tmp_path.iterdir() if p.is_dir() and p.name.startswith(".app.codegen-stage-")]
    assert len(stage_dirs) == 1, f"expected exactly one leftover staging dir, found {stage_dirs}"
    written_files = [p for p in stage_dirs[0].rglob("*") if p.is_file()]
    assert len(written_files) == 1, (
        f"expected exactly the one file the child was killed right after writing, found {written_files}"
    )
    assert written_files[0].relative_to(stage_dirs[0]).as_posix() == marker


def test_kill_right_after_manifest_write_leaves_target_dir_absent_never_partial(tmp_path):
    """The precise historical bug scenario this fix closes: pre-fix, a
    kill landing right after `.spec-engine/codegen-manifest.json` was
    written (already claiming `codegen_status: "generated"`) but before
    `write_scaffold_stub()`'s own writes (`SPEC.md`, `spec.json`,
    `CLAUDE.md`, `AGENTS.md`) would have left `target_dir` holding a
    manifest that OVERCLAIMS completeness while the rest of the tree is
    still missing — exactly the "partial tree that looks complete by
    manifest alone" DoD B.9 forbids. Post-fix, that same kill point only
    ever touches the STAGING dir; `target_dir` stays fully absent."""
    target_dir = tmp_path / "app"
    assert not target_dir.exists(), "sanity: target_dir must not pre-exist for this test"

    marker = _spawn_and_kill_mid_write(tmp_path, target_dir, MANIFEST_REL_PATH)
    assert marker == MANIFEST_REL_PATH

    assert not target_dir.exists(), (
        "target_dir must remain absent even though the manifest was already fully written — "
        "in the staging dir, never in target_dir"
    )

    stage_dirs = [p for p in tmp_path.iterdir() if p.is_dir() and p.name.startswith(".app.codegen-stage-")]
    assert len(stage_dirs) == 1, f"expected exactly one leftover staging dir, found {stage_dirs}"
    stage_dir = stage_dirs[0]

    manifest_path = stage_dir / MANIFEST_REL_PATH
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["codegen_status"] == "generated"
    # Proves the kill genuinely landed exactly where intended: the
    # historically-dangerous "manifest says generated, rest is missing"
    # state really does exist here — but ONLY in the staging dir, which
    # is invisible under target_dir's own path (asserted absent above).
    assert not (stage_dir / "SPEC.md").exists()
    assert not (stage_dir / "CLAUDE.md").exists()
    assert not (stage_dir / "spec.json").exists()


# --------------------------------------------------------------------------
# Clean-exception-path test — a catchable, in-process failure.
# --------------------------------------------------------------------------


def test_exception_mid_generation_leaves_target_dir_untouched_and_no_orphan_stage_dir(tmp_path, monkeypatch):
    import spec_engine.codegen as codegen_module

    spec = _rich_spec()
    target_dir = tmp_path / "app"
    assert not target_dir.exists(), "sanity: target_dir must not pre-exist for this test"

    call_count = {"n": 0}
    orig_write_file = codegen_module._write_file

    def _boom(root, rel_path, content):
        call_count["n"] += 1
        if call_count["n"] == 3:
            raise RuntimeError("simulated mid-generation crash")
        return orig_write_file(root, rel_path, content)

    monkeypatch.setattr(codegen_module, "_write_file", _boom)

    with pytest.raises(RuntimeError, match="simulated mid-generation crash"):
        codegen_module.generate_app(spec, target_dir)

    assert not target_dir.exists(), "a mid-generation exception must leave target_dir exactly as found (absent)"
    leftover = [p for p in tmp_path.iterdir() if p.is_dir() and p.name.startswith(".app.codegen-stage-")]
    assert leftover == [], f"staging dir was not cleaned up after the exception: {leftover}"

    # And a subsequent, un-instrumented call succeeds normally — the failed
    # attempt left nothing behind to interfere with a real run.
    result = codegen_module.generate_app(spec, target_dir)
    assert result.scaffold_plan.codegen_status == "generated"
    assert (target_dir / ".spec-engine" / "codegen-manifest.json").is_file()


# --------------------------------------------------------------------------
# Staging-mechanism regression tests (non-kill) — the two branches
# `_publish_staged_app()` / `generate_app()` add.
# --------------------------------------------------------------------------


def test_regenerate_over_existing_populated_dir_merges_and_swaps_atomically(tmp_path):
    """`target_dir` already holding real content (the scenario
    `write_scaffold_stub()`'s CLAUDE.md/AGENTS.md-merge logic exists for)
    must still publish atomically: pre-existing unrelated files survive,
    CLAUDE.md is merged (directive appended) rather than clobbered, and no
    staging/backup directories are left behind on success."""
    spec = _rich_spec()
    target_dir = tmp_path / "app"
    target_dir.mkdir()
    (target_dir / "CLAUDE.md").write_text("# Human-authored project notes\n\nDo not delete this.\n", encoding="utf-8")
    (target_dir / "README_HUMAN.txt").write_text("pre-existing unrelated file", encoding="utf-8")

    result = generate_app(spec, target_dir)

    assert result.scaffold_plan.codegen_status == "generated"
    assert (target_dir / "README_HUMAN.txt").read_text(encoding="utf-8") == "pre-existing unrelated file"
    claude_md = (target_dir / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Human-authored project notes" in claude_md
    assert "CODE IS GENERATED FROM" in claude_md
    assert (target_dir / "src" / "server.js").is_file()
    assert (target_dir / ".spec-engine" / "codegen-manifest.json").is_file()

    leftovers = [p for p in tmp_path.iterdir() if p.is_dir() and p.name.startswith(".app.codegen-")]
    assert leftovers == [], f"leftover staging/backup dirs after a successful publish: {leftovers}"


def test_result_written_paths_are_real_live_paths_under_target_dir_after_publish(tmp_path):
    spec = _rich_spec()
    target_dir = tmp_path / "app"

    result = generate_app(spec, target_dir)

    assert result.written, "sanity: at least one file should be recorded"
    for rel, path in result.written.items():
        assert path == target_dir / rel
        assert path.is_file(), f"result.written[{rel!r}] = {path} does not exist on disk after publish"
