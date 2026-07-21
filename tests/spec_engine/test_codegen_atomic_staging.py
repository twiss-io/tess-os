"""Kill-proof proof for the codegen atomic-staging fix (Gap B / DoD B.9):
`spec_engine.codegen.generate_app()` must never leave a genuinely partial
file tree — or, worse, a tree whose `.spec-engine/codegen-manifest.json`
already claims `codegen_status: "generated"` while other generated files
are still missing — sitting in `target_dir` if the process is killed
mid-generation. Also covers the rename-aside-swap recovery mechanism
(PR #156 review round 2, both reviewers HIGH): a kill between
`_publish_staged_app()`'s two `os.replace()` calls must not let the
NEXT `generate_app()` call silently destroy the orphaned original
`target_dir` content.

Three classes of proof:

  - **SIGKILL tests** (`test_kill_*`): spawn `generate_app()` in a real
    child process, instrumented to pause (via `time.sleep`) right after a
    specific file write (or rename) completes, `SIGKILL` it in that
    window (a signal Python cannot catch or clean up after), then assert
    on the resulting state — never a partial mix, and (for the
    rename-aside-swap window specifically) that the orphaned original
    content is RECOVERED, not destroyed, by the very next call. One test
    kills right after the VERY FIRST file write; one kills right after
    `.spec-engine/codegen-manifest.json` is written but BEFORE
    `write_scaffold_stub()`'s own writes (`SPEC.md`/`CLAUDE.md`/...) run
    — the precise historical bug scenario, where a manifest already
    claiming completeness could previously survive in `target_dir`
    alongside a missing rest-of-the-tree; one kills between
    `_publish_staged_app()`'s two renames when publishing over
    pre-existing `target_dir` content — the window both reviewers flagged
    HIGH on the first round of this PR.
  - **Clean-exception-path test**: a mid-generation `raise` (catchable,
    unlike SIGKILL) must ALSO leave `target_dir` untouched, and must not
    leave an orphaned staging directory behind either.
  - **Direct unit tests on `_recover_interrupted_publish()`**: the other
    interrupted-cleanup case (second rename succeeded, trailing
    `shutil.rmtree(aside, ...)` never ran), the fail-loud path for a
    genuinely ambiguous non-directory aside state, and the fail-loud path
    for a symlink planted at the aside path (PR #156 review round 2,
    Cyra, MEDIUM — a symlink there must never be followed), exercised
    directly rather than via a subprocess kill (nothing about any of
    these cases needs a real kill to reproduce).
  - **Direct unit test on `_publish_staged_app()`'s concurrent-call
    guard** (PR #156 review round 2, Reid, LOW — coverage symmetry with
    the `_recover_interrupted_publish()` unit tests above): the aside
    path unexpectedly already existing right before the swap must refuse
    to publish rather than clobber it.

Plus four smaller regression tests for the staging mechanism itself:
that `generate_app()` called against an already-populated `target_dir`
(the "regenerate on top of a hand-seeded starter template" case
`spec_engine.scaffold.write_scaffold_stub()`'s CLAUDE.md/AGENTS.md-merge
logic exists for) still swaps in atomically and preserves/merges
correctly; that a symlink planted ANYWHERE inside a pre-existing
`target_dir` — at one of the fixed generated-content paths (round 2,
Cyra, CRITICAL: write-through — a `symlinks=True` `copytree` regression)
or at any other, non-generated path (round 3, Cyra AND Reid,
independently reproduced, HIGH: read-dereference/disclosure — the
mirror-image gap in `symlinks=False`, the round-2 revert's own default)
— is refused outright by `_refuse_symlinks_in_existing_content()` before
`copytree()` ever runs, closing both vectors with one rule instead of a
different mitigation for each; and that `CodegenResult.written`'s
returned paths are real, live paths under `target_dir` after publish
(not stale staging-directory paths).
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

import spec_engine.codegen as codegen_module
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
    SpecEngineError,
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
# SIGKILL test — the rename-aside-swap window (_publish_staged_app()'s
# has_existing_content=True branch). PR #156 review round 2, both
# reviewers HIGH: a kill between the two os.replace() calls must not let
# the NEXT generate_app() call silently destroy the orphaned original
# target_dir content.
# --------------------------------------------------------------------------

_SWAP_WINDOW_CHILD_SCRIPT = r'''
import os
import sys
import time
import tempfile
from pathlib import Path

target_dir = sys.argv[1]
target_path = Path(target_dir)

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
    input_excerpt="Rename-aside-swap kill-window fixture",
    what_it_does=WhatItDoes(summary="Exercises the rename-aside-swap kill window."),
    how_it_looks=HowItLooks(description="One screen.", key_screens=[KeyScreen(name="Screen", description="A screen.")]),
    how_it_works=HowItWorks(description="One flow.", key_flows=[KeyFlow(name="Flow", steps=["Step one"])], integrations=[]),
    data_model=DataModel(entities=[Entity(name="Item", fields=[EntityField(name="value")])]),
    acceptance_criteria=["Baseline acceptance criterion"],
    summary_for_approval="summary",
    resolved_connectors=resolve_connectors([]),
)
approval = sign_local_approval(plan, approved_by="Xavier")
spec = build_spec(plan, approval)

_orig_replace = os.replace


def _instrumented_replace(src, dst):
    result = _orig_replace(src, dst)
    # Fires ONLY for the swap's FIRST rename (final_root -> aside): src is
    # target_dir itself. The swap's SECOND rename's src is stage_root, not
    # target_dir, so this match is unambiguous — it can only be the
    # window between the two renames, never before or after it.
    if str(src) == str(target_path):
        print("REACHED_SWAP_ASIDE", flush=True)
        # SIGKILL from the parent lands somewhere in here — unblockable,
        # un-catchable, no Python-level cleanup ever runs. target_dir is
        # absent and the original content is sitting only in the aside
        # sibling at exactly this instant.
        time.sleep(30)
    return result


os.replace = _instrumented_replace

codegen_module.generate_app(spec, target_dir)
print("COMPLETED", flush=True)
'''


def test_kill_between_rename_aside_swap_renames_recovers_original_content_on_next_run(tmp_path):
    """The exact window both reviewers flagged HIGH on PR #156's first
    review round: a kill between `_publish_staged_app()`'s two
    `os.replace()` calls (the `has_existing_content=True` branch).
    Pre-populates `target_dir` with sentinel content, SIGKILLs the child
    exactly after the first rename (`target_dir` swapped aside) but
    before the second (`stage_root` swapped in), then runs
    `generate_app()` again — normally, uninstrumented, exactly the
    natural "just re-run it" post-crash recovery action — and asserts the
    ORIGINAL sentinel content is RECOVERED (not destroyed) and the final
    tree is valid.

    Before the fix: this second call would see `target_dir` absent, take
    the `has_existing_content=False` fast path, and silently publish
    fresh content straight over the orphaned original — CLAUDE.md's
    sentinel line and README_HUMAN.txt gone forever, no error, no
    warning. After the fix: `_recover_interrupted_publish()` restores the
    aside into `target_dir` before this call ever decides
    `has_existing_content`, so it correctly takes the merge-and-swap path
    and the sentinel content survives."""
    target_dir = tmp_path / "app"
    target_dir.mkdir()
    sentinel_claude_md = "# Human-authored project notes\n\nDo not delete this.\n"
    (target_dir / "CLAUDE.md").write_text(sentinel_claude_md, encoding="utf-8")
    (target_dir / "README_HUMAN.txt").write_text("pre-existing unrelated file", encoding="utf-8")

    script_path = tmp_path / "_child_swap_window.py"
    script_path.write_text(
        _SWAP_WINDOW_CHILD_SCRIPT.replace("__COMPONENT_ROOT__", str(_spec_engine_paths.COMPONENT_ROOT)),
        encoding="utf-8",
    )
    proc = subprocess.Popen(
        [sys.executable, str(script_path), str(target_dir)],
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
                    f"child exited early (code {proc.returncode}) before reaching the swap-aside "
                    f"rename it was instrumented to pause at.\nstdout={out!r}\nstderr={err!r}"
                )
            line = proc.stdout.readline()
            if not line:
                time.sleep(0.02)
                continue
            if line.startswith("REACHED_SWAP_ASIDE"):
                marker = line.strip()
                break
        if marker is None:
            raise AssertionError("child never reached the swap-aside rename within the deadline")

        os.kill(proc.pid, signal.SIGKILL)
        proc.wait(timeout=10)
        assert proc.returncode != 0, "child should have been killed, not exited cleanly"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)

    # Post-kill, pre-recovery: this is the exact orphaned state both
    # reviewers independently reproduced — target_dir absent, original
    # content sitting in the deterministic aside sibling, fresh content in
    # a separate stage sibling.
    assert not target_dir.exists(), (
        "sanity: the child was killed between the two renames, so target_dir must be absent "
        "(it was renamed aside, and the second rename never ran)"
    )
    aside = codegen_module._swap_aside_path(target_dir)
    assert aside.is_dir(), "sanity: the original content must be sitting in the deterministic aside path"
    assert (aside / "CLAUDE.md").read_text(encoding="utf-8") == sentinel_claude_md
    assert (aside / "README_HUMAN.txt").read_text(encoding="utf-8") == "pre-existing unrelated file"

    # The natural post-crash recovery action: just re-run it, uninstrumented.
    spec = _rich_spec()
    result = generate_app(spec, target_dir)

    assert result.scaffold_plan.codegen_status == "generated"
    recovered_claude_md = (target_dir / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Do not delete this." in recovered_claude_md, (
        "the sentinel line from the pre-existing CLAUDE.md must survive the recover-then-merge — "
        f"got: {recovered_claude_md!r}"
    )
    assert "Human-authored project notes" in recovered_claude_md
    assert (target_dir / "README_HUMAN.txt").read_text(encoding="utf-8") == "pre-existing unrelated file", (
        "the pre-existing unrelated file must survive the recover-then-merge, not be silently dropped"
    )

    # The final tree is a valid, complete generated app — recovery doesn't
    # just preserve the old content, the regeneration on top of it is
    # fully correct too.
    assert (target_dir / "src" / "server.js").is_file()
    manifest_path = target_dir / ".spec-engine" / "codegen-manifest.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["codegen_status"] == "generated"

    # Exactly one leftover dir remains: the KILLED run's own orphaned stage
    # dir (it held the killed run's fully-generated-but-never-swapped-in
    # content; nothing in generate_app()'s contract cleans up a killed
    # process's own staging directory — same accepted disk-litter-but-
    # zero-data-loss outcome the other two SIGKILL tests above assert on
    # for their own leftover stage dirs). Critically, the aside/backup
    # path itself is gone — the recovery run's own publish cleaned it up
    # after a successful swap, exactly like any other successful publish.
    remaining = [p for p in tmp_path.iterdir() if p.is_dir() and p.name.startswith(".app.codegen-")]
    assert len(remaining) == 1, f"expected exactly the killed run's own orphaned stage dir, found {remaining}"
    assert remaining[0].name.startswith(".app.codegen-stage-"), (
        f"the one remaining dir should be the killed run's stage dir, not the aside/backup path: {remaining}"
    )


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
# Rename-aside-swap recovery — direct unit tests on
# `_recover_interrupted_publish()` for the two states it must reconcile
# without a real kill, and the one it must refuse to guess about.
# --------------------------------------------------------------------------


def test_recover_interrupted_publish_restores_orphaned_aside_when_target_dir_absent(tmp_path):
    """The primary recovery case, exercised directly rather than via a
    subprocess kill: `target_dir` absent, its real prior content sitting
    in the deterministic aside path (as the SIGKILL test above proves a
    real interrupted swap leaves behind) — recovery must restore it into
    `target_dir` rather than leave it to be silently overwritten by
    whatever calls `generate_app()` next."""
    target_dir = tmp_path / "app"
    assert not target_dir.exists()

    aside = codegen_module._swap_aside_path(target_dir)
    aside.mkdir()
    (aside / "CLAUDE.md").write_text("Do not delete this.\n", encoding="utf-8")

    codegen_module._recover_interrupted_publish(target_dir)

    assert target_dir.is_dir(), "the orphaned aside must be restored into target_dir"
    assert (target_dir / "CLAUDE.md").read_text(encoding="utf-8") == "Do not delete this.\n"
    assert not aside.exists(), "the aside path is consumed by the restore, not left behind too"


def test_recover_interrupted_publish_cleans_up_stale_aside_when_target_dir_already_correct(tmp_path):
    """The other interrupted-cleanup case: the swap's second rename
    already succeeded (`target_dir` holds the correct, complete new
    content) but the trailing `shutil.rmtree(aside, ...)` never ran. The
    stale aside must be discarded — never restored over the
    already-correct `target_dir`, and never left behind forever either."""
    target_dir = tmp_path / "app"
    target_dir.mkdir()
    (target_dir / "current.txt").write_text("real, already-published content", encoding="utf-8")

    aside = codegen_module._swap_aside_path(target_dir)
    aside.mkdir()
    (aside / "stale.txt").write_text("stale prior content that must be discarded", encoding="utf-8")

    codegen_module._recover_interrupted_publish(target_dir)

    assert not aside.exists(), "the stale aside must be cleaned up"
    assert (target_dir / "current.txt").read_text(encoding="utf-8") == "real, already-published content", (
        "target_dir's already-correct content must be left untouched"
    )


def test_recover_interrupted_publish_fails_loud_on_non_directory_aside(tmp_path):
    """If the reserved aside path exists but is not a directory — a state
    nothing in this module ever creates — recovery must fail loud
    (`SpecEngineError`) rather than guess whether it is safe to restore
    into `target_dir` or delete outright."""
    target_dir = tmp_path / "app"
    aside = codegen_module._swap_aside_path(target_dir)
    aside.write_text("not a directory", encoding="utf-8")

    with pytest.raises(SpecEngineError, match="not a directory"):
        codegen_module._recover_interrupted_publish(target_dir)

    assert aside.is_file(), "a genuinely ambiguous state must be left exactly as found, never touched"


def test_recover_interrupted_publish_fails_loud_on_symlink_aside(tmp_path):
    """PR #156 review round 2, Cyra, MEDIUM: a symlink planted at the
    deterministic aside path must never be followed by
    `_recover_interrupted_publish()`. `Path.exists()`/`Path.is_dir()` both
    resolve through symlinks, which would have let a planted symlink
    either bypass the stale-aside `rmtree` cleanup (`rmtree` refuses to
    operate on a top-level symlink and `ignore_errors=True` swallows that
    refusal) or — the more dangerous case exercised here, `target_dir`
    absent — get renamed straight onto `final_root` by the restore
    branch, making `target_dir` itself become a symlink to wherever the
    planted symlink pointed. A symlink at this exact, reserved path is
    never something `_publish_staged_app()` itself creates (its two
    `os.replace()` calls only ever move a real directory); recovery must
    treat it as the genuinely ambiguous state it is and fail loud,
    leaving both the symlink and `target_dir` untouched."""
    target_dir = tmp_path / "app"
    outside_dir = tmp_path / "outside_dir"
    outside_dir.mkdir()
    (outside_dir / "secret.txt").write_text("do not expose this", encoding="utf-8")

    aside = codegen_module._swap_aside_path(target_dir)
    os.symlink(str(outside_dir), str(aside))

    with pytest.raises(SpecEngineError, match="symlink"):
        codegen_module._recover_interrupted_publish(target_dir)

    assert os.path.islink(aside), "the planted symlink must be left exactly as found, never touched"
    assert not target_dir.exists(), "recovery must never restore/rename a symlink onto target_dir"


# --------------------------------------------------------------------------
# Concurrent-call guard — direct unit test on `_publish_staged_app()`
# itself (PR #156 review round 2, Reid, LOW: coverage symmetry with the
# three direct `_recover_interrupted_publish()` tests above). The branch
# exercised here is provably unreachable within a single `generate_app()`
# call — `_recover_interrupted_publish()` always clears/consumes the
# aside before `_publish_staged_app()` is ever reached — but it is
# `_publish_staged_app()`'s own last line of defense against a
# concurrent `generate_app()` call racing against the same `target_dir`
# (not a supported use of this function), and deserves its own direct
# test rather than relying on that reachability argument alone.
# --------------------------------------------------------------------------


def test_publish_staged_app_fails_loud_when_aside_already_exists(tmp_path):
    """If the reserved aside path unexpectedly already exists right
    before the rename-aside-swap — most likely a concurrent
    `generate_app()` call racing this one against the same `target_dir`
    — `_publish_staged_app()` must refuse to publish rather than risk
    clobbering the in-flight aside or losing track of `final_root`'s
    current content. Both `final_root` and the pre-existing aside must be
    left exactly as found."""
    final_root = tmp_path / "app"
    final_root.mkdir()
    (final_root / "current.txt").write_text("real, already-published content", encoding="utf-8")

    stage_root = tmp_path / "stage"
    stage_root.mkdir()
    (stage_root / "new.txt").write_text("freshly staged content", encoding="utf-8")

    aside = codegen_module._swap_aside_path(final_root)
    aside.mkdir()
    (aside / "racer.txt").write_text("another call's in-flight aside content", encoding="utf-8")

    with pytest.raises(SpecEngineError, match="already exists"):
        codegen_module._publish_staged_app(stage_root, final_root, has_existing_content=True)

    assert (final_root / "current.txt").read_text(encoding="utf-8") == "real, already-published content", (
        "final_root's current content must be left untouched by a refused publish"
    )
    assert (aside / "racer.txt").read_text(encoding="utf-8") == "another call's in-flight aside content", (
        "the pre-existing (racing) aside must be left untouched, not clobbered"
    )
    assert (stage_root / "new.txt").is_file(), "stage_root itself is left as found — nothing consumed it"


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


def test_regenerate_over_existing_symlink_write_through_is_blocked(tmp_path):
    """PR #156 review round 2, Cyra, CRITICAL: a prior revision of this
    fix set `shutil.copytree(..., symlinks=True)` when staging a
    regenerate-over-existing `target_dir`, intended to "preserve" any
    symlink in pre-existing content — but every generated-content write
    (`_write_file()` -> `Path.write_text()`) follows symlinks
    unconditionally and always targets the SAME fixed relative paths
    (e.g. `.spec-engine/codegen-manifest.json`) on every call. A symlink
    planted at one of those exact paths inside `target_dir`, pointing
    OUTSIDE `target_dir`, let an ordinary (no kill involved) regeneration
    write generated content straight THROUGH it, overwriting whatever
    file the symlink pointed at — verified working exploit against the
    `symlinks=True` revision.

    Round 3 (PR #156 review round 3, Cyra AND Reid, independently
    reproduced, HIGH) found that reverting to the default
    `symlinks=False` closes THIS vector but silently opens its mirror
    image on read (see
    `test_regenerate_over_existing_symlink_read_dereference_is_blocked`
    below). The holistic fix refuses ANY symlink found in pre-existing
    `target_dir` content outright, before `copytree()` ever runs — so
    this exact symlink, planted at a generated path, is now refused just
    like a symlink at any other path, rather than silently dereferenced
    and defanged. This test now asserts the refusal: a stronger
    guarantee than "successfully dereferenced, never overwritten",
    achieved by the same single rule that also closes the round-3
    read/exfil HIGH below."""
    spec = _rich_spec()
    target_dir = tmp_path / "app"
    target_dir.mkdir()

    outside_file = tmp_path / "outside_secret.txt"
    outside_file.write_text("original sensitive content -- must not be overwritten", encoding="utf-8")

    manifest_path = target_dir / ".spec-engine" / "codegen-manifest.json"
    manifest_path.parent.mkdir(parents=True)
    os.symlink(str(outside_file), str(manifest_path))
    assert os.path.islink(manifest_path), "sanity: the planted path must actually be a symlink"

    with pytest.raises(SpecEngineError, match="symlink"):
        generate_app(spec, target_dir)

    assert outside_file.read_text(encoding="utf-8") == "original sensitive content -- must not be overwritten", (
        "a symlink planted at a generated path inside target_dir must never let a regeneration "
        "write generated content through it to a file outside target_dir — whether via refusal "
        "(this fix) or via dereference-defanging (the round-3 behavior this test previously "
        "covered, before the holistic refuse-symlinks fix)"
    )
    assert manifest_path.is_symlink(), "a refused regeneration must leave target_dir exactly as found"
    leftovers = [p for p in tmp_path.iterdir() if p.is_dir() and p.name.startswith(".app.codegen-")]
    assert leftovers == [], f"a refused regeneration must not leave an orphaned staging directory: {leftovers}"


def test_regenerate_over_existing_symlink_read_dereference_is_blocked(tmp_path):
    """PR #156 review round 3, Cyra AND Reid, independently reproduced
    with separate PoCs, HIGH — the mirror image of the round-2 CRITICAL
    above. Reverting `copytree` back to its default `symlinks=False`
    (round 3, `0f0a589`) closed the write-through vector but opened the
    opposite one: `symlinks=False` DEREFERENCES any symlink it finds
    anywhere in the tree being copied, at ANY relative path — not just
    the small, fixed set of generated-content paths `_write_file()`
    targets. A symlink at a NON-generated path (e.g. a file under
    `notes/`, which codegen never writes to or overwrites afterward)
    survives the copy as a plain file holding its target's content,
    verbatim, in the staged AND — since nothing downstream ever
    regenerates that path — the published tree: a disclosure primitive,
    not a corruption one. Same actor, same trust boundary as the
    write-through CRITICAL (planting a path in target_dir before a
    regenerate call is this module's own documented, supported
    workflow, not a privileged position); broader blast radius (any
    path, not just the fixed generated ones).

    `_refuse_symlinks_in_existing_content()` closes this by refusing ANY
    symlink anywhere in pre-existing target_dir content, at ANY relative
    path, before `copytree()` ever runs — the secret's content is never
    read off disk by this module at all, let alone copied into an
    output tree."""
    spec = _rich_spec()
    target_dir = tmp_path / "app"
    target_dir.mkdir()

    outside_secret = tmp_path / "outside_secret.txt"
    secret_content = "TOP SECRET CREDENTIAL: sk-abc123-do-not-leak"
    outside_secret.write_text(secret_content, encoding="utf-8")

    # A NON-generated relative path — codegen never writes to `notes/`,
    # so (before this fix) a dereferenced copy here would never be
    # overwritten by a later generated-content write, unlike the
    # manifest-path case above.
    planted_link = target_dir / "notes" / "my-private-link.txt"
    planted_link.parent.mkdir(parents=True)
    os.symlink(str(outside_secret), str(planted_link))
    assert os.path.islink(planted_link), "sanity: the planted path must actually be a symlink"

    with pytest.raises(SpecEngineError, match="symlink"):
        generate_app(spec, target_dir)

    # The external secret itself must be unmodified — this is a
    # read/exfiltration vector, not a corruption one, but assert it
    # explicitly per the review's ask.
    assert outside_secret.read_text(encoding="utf-8") == secret_content, (
        "the external secret file must not be modified by a refused regeneration"
    )
    # target_dir must be left exactly as found by a refused regeneration
    # — the symlink is never dereferenced, never copied, never published.
    assert planted_link.is_symlink(), "a refused regeneration must leave target_dir exactly as found"
    assert not (target_dir / "src").exists(), (
        "a refused regeneration must not have generated or published anything at all"
    )
    # Defense-in-depth: the secret's content must not have been absorbed
    # into ANY file anywhere under tmp_path (staged, published, or a
    # leftover orphaned staging directory) — not just the two specific
    # locations checked above.
    for candidate in tmp_path.rglob("*"):
        if candidate == outside_secret or candidate.is_symlink() or not candidate.is_file():
            continue
        assert secret_content not in candidate.read_text(encoding="utf-8", errors="ignore"), (
            f"the external secret's content must not appear anywhere on disk under tmp_path "
            f"OUTSIDE the original secret file itself, found in {candidate}"
        )
    leftovers = [p for p in tmp_path.iterdir() if p.is_dir() and p.name.startswith(".app.codegen-")]
    assert leftovers == [], f"a refused regeneration must not leave an orphaned staging directory: {leftovers}"


def test_result_written_paths_are_real_live_paths_under_target_dir_after_publish(tmp_path):
    spec = _rich_spec()
    target_dir = tmp_path / "app"

    result = generate_app(spec, target_dir)

    assert result.written, "sanity: at least one file should be recorded"
    for rel, path in result.written.items():
        assert path == target_dir / rel
        assert path.is_file(), f"result.written[{rel!r}] = {path} does not exist on disk after publish"
