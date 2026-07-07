"""
HIGH-1 (Fable Phase-1 review) proof: the render-target seam is genuinely
load-bearing for a SECOND, non-Claude render target — not just for
`cmd_render`, which was the only subsystem consulting `RENDER_TARGETS`
before this fix.

Fable's review passed the Phase 1 crux (determinism, contracts wiring,
tamper detection, security-tier all verified) but BLOCKed on this: a Phase
2+ target (e.g. Codex) would render on demand but silently go STALE on
`tessctl update` and be invisible to / false-flagged by drift detection,
because doctor/verify's Check B, the render-generated remedy-routing set,
and `cmd_update`'s Step 7 were all Claude-hardcoded.

A `MockHarnessTarget` — registered into `engine.RENDER_TARGETS` only for the
duration of these tests, via `monkeypatch` — stands in for that future
target and proves the three fixed subsystems are genuinely registry-driven:

  (a) doctor/verify correctly drift-check its compiled artifact via
      `expected_live_bytes()`. Its `render()` does a bespoke compile
      (uppercase + a banner line) that a naive byte-copy of core would NOT
      reproduce — so a false positive here would prove the old, hardcoded
      comparison path is still in effect.
  (b) `cmd_update`'s Step 7 (which now calls the shared
      `_render_enabled_targets()` instead of the Claude-only `_do_render()`)
      re-renders it from the NEW upstream core, through a real signed
      fetch + update cycle.
  (c) per-install enablement (MED-3) gates it: absent from
      `tess.manifest.json`'s `render_targets.enabled`, neither `tessctl
      render` (no flags) nor `cmd_update`'s Step 7 ever touch its live file,
      and `render_generated_live_paths()` excludes its path.

NOTE: all `cmd_*` calls in this file are made IN-PROCESS (direct function
calls against the `engine` module), never via the `run_cli` subprocess
helper — a subprocess loads a separate copy of `.tess/bin/tessctl` and would
not see this process's `monkeypatch.setitem(engine.RENDER_TARGETS, ...)`.
"""

from __future__ import annotations

import json

import pytest

from conftest import Project, make_upstream, ns


MOCK_LIVE_REL = "conductor/_mock_harness/ARTIFACT.md"
MOCK_CORE_KEY = ".tess/core/mock/ARTIFACT.md.tpl"


class _MockHarnessTarget:
    """A second, non-Claude render target. Subclasses engine.RenderTarget at
    construction time (see _make_mock_target) so isinstance/interface checks
    behave like a real target — a stand-in for a future Phase 2 target (e.g.
    Codex), not a Claude Code specialization."""

    name = "mock-harness"

    def live_globs(self):
        return [MOCK_LIVE_REL]

    def expected_live_bytes(self, root, live_rel):
        if live_rel != MOCK_LIVE_REL:
            return None
        core_path = root / MOCK_CORE_KEY
        if not core_path.exists():
            return b""
        raw = core_path.read_text(encoding="utf-8")
        # A bespoke "compile" (uppercase + banner) — deliberately NOT a plain
        # byte-copy, so a comparison against raw core bytes (the pre-fix
        # fallback for any non-Claude target) would ALWAYS mismatch.
        return f"# MOCK-HARNESS COMPILED\n{raw.upper()}".encode("utf-8")

    def render_generated_paths(self, root):
        return {MOCK_LIVE_REL}

    def render(self, root, verbose=False):
        rendered = self.expected_live_bytes(root, MOCK_LIVE_REL) or b""
        # engine is bound as a class attribute by _make_mock_target below.
        self._engine.guarded_write(root, MOCK_LIVE_REL, rendered, op="render")
        return {"target": self.name, "status": "rendered"}


def _make_mock_target(engine):
    """Build a MockHarnessTarget that is a genuine engine.RenderTarget
    subclass (proves the base-class contract, not a duck-typed stand-in)."""
    cls = type("MockHarnessTarget", (engine.RenderTarget,), dict(_MockHarnessTarget.__dict__))
    cls._engine = engine
    return cls()


@pytest.fixture
def mock_target(engine, monkeypatch):
    """Registers 'mock-harness' into engine.RENDER_TARGETS for the duration
    of the test only — monkeypatch restores the registry afterward (removes
    the key, since it did not exist before)."""
    target = _make_mock_target(engine)
    monkeypatch.setitem(engine.RENDER_TARGETS, "mock-harness", target)
    return target


def _seed_mock_core(project, content):
    """Register the mock target's core source as a core-managed lock entry
    whose live_path is the mock's compiled output — mirrors how a real
    Phase-2 target's lock entry would look. render_live=False: the pristine
    live file is written explicitly (via mock_target.render()) once the
    manifest exists and enablement is set, so expected_live_bytes() is
    actually consulted for the initial state too."""
    return project.add(
        MOCK_LIVE_REL, content, core_key=MOCK_CORE_KEY, render_live=False,
    )


def _set_enabled(project, names):
    """Set tess.manifest.json's render_targets.enabled — must run AFTER
    project.write() (which is what puts tess.manifest.json on disk)."""
    mf_path = project.root / "tess.manifest.json"
    manifest = json.loads(mf_path.read_text(encoding="utf-8"))
    manifest.setdefault("render_targets", {})["enabled"] = list(names)
    mf_path.write_text(json.dumps(manifest), encoding="utf-8")


# ---------------------------------------------------------------------------
# (a) doctor/verify correctly drift-check the mock's compiled artifact via
#     expected_live_bytes() — not a naive byte-copy of core.
# ---------------------------------------------------------------------------

def test_mock_target_pristine_after_render_via_expected_live_bytes(project, engine, mock_target):
    """After render(), doctor/verify must be CLEAN. Before HIGH-1, doctor's
    Check B compared live bytes against a naive raw-copy of core (lowercase,
    no banner) for any target it didn't special-case — since the mock's
    render() UPPERCASES + adds a banner, that stale comparison would ALWAYS
    mismatch, false-flagging a correctly rendered file as drifted. A clean
    result here proves render_core_to_live() is consulting
    expected_live_bytes(), not the old two-special-case-only path."""
    _seed_mock_core(project, "hello mock world\n")
    project.write()
    _set_enabled(project, ["mock-harness"])

    mock_target.render(project.root, verbose=False)
    live_path = project.root / MOCK_LIVE_REL
    assert live_path.read_text(encoding="utf-8") == "# MOCK-HARNESS COMPILED\nHELLO MOCK WORLD\n"

    engine.cmd_doctor(ns(json_out=False, fix=False, path=None), project.root)  # must not sys.exit
    engine.cmd_verify(ns(), project.root)  # must not sys.exit


def test_mock_target_genuine_hand_edit_is_flagged_as_uncaptured_drift(project, engine, mock_target, capsys):
    """A genuine hand-edit of the mock's live artifact (content that does
    NOT match the target's compiled output) IS flagged — proving
    expected_live_bytes() performs a real comparison, not an always-clean
    stub. The remedy hint must be `tessctl render` (render-generated),
    reflecting render_generated_live_paths() including this path while the
    target is enabled."""
    _seed_mock_core(project, "hello mock world\n")
    project.write()
    _set_enabled(project, ["mock-harness"])
    mock_target.render(project.root, verbose=False)

    live_path = project.root / MOCK_LIVE_REL
    live_path.write_text("SOMEONE HAND-EDITED THIS DIRECTLY\n", encoding="utf-8")
    capsys.readouterr()

    with pytest.raises(SystemExit) as ei:
        engine.cmd_doctor(ns(json_out=False, fix=False, path=None), project.root)
    assert ei.value.code == 1
    out = capsys.readouterr().out
    assert MOCK_LIVE_REL in out
    assert "tessctl render" in out, "render-generated drift must recommend `tessctl render`, not `tessctl capture`"
    assert f"tessctl capture {MOCK_LIVE_REL}" not in out


def test_render_generated_live_paths_excludes_mock_when_disabled(project, engine, mock_target):
    """render_generated_live_paths() only includes an ENABLED target's paths
    (MED-3) — registering the mock in RENDER_TARGETS alone is not enough."""
    project.write()
    _set_enabled(project, [])  # nothing enabled — not even claude-code
    assert MOCK_LIVE_REL not in engine.render_generated_live_paths(project.root)

    _set_enabled(project, ["mock-harness"])
    assert MOCK_LIVE_REL in engine.render_generated_live_paths(project.root)


# ---------------------------------------------------------------------------
# (b) cmd_update's Step 7 re-renders the mock target from the NEW core.
# ---------------------------------------------------------------------------

def test_mock_target_rerendered_by_cmd_update_step7(project, engine, mock_target, gpg_key, tmp_path):
    """HIGH-1's actual claim: an upgrade re-renders EVERY enabled target's
    artifacts atomically. Exercised through the real cmd_update() function
    (Step 0-8, real signed fetch via make_upstream/gpg_key) — not a stand-in
    for it — so this proves Step 7's real call site, not just the shared
    helper in isolation."""
    _seed_mock_core(project, "hello mock world v1\n")
    project.framework["upstream"] = str(tmp_path / "upstream")
    project.framework["upstream_ref"] = "v2.0.0"
    project.framework["trusted_key_fingerprint"] = gpg_key.fpr
    project.write()
    _set_enabled(project, ["mock-harness"])  # claude-code excluded: no CLAUDE.md.tpl fixture here
    mock_target.render(project.root, verbose=False)
    assert "HELLO MOCK WORLD V1" in (project.root / MOCK_LIVE_REL).read_text(encoding="utf-8")

    make_upstream(
        tmp_path / "upstream", gpg_key, "v2.1.0", sign="signed",
        core_files={MOCK_CORE_KEY: "hello mock world v2\n"},
    )

    engine.cmd_update(
        ns(ref="v2.1.0", to=None, dry_run=False, check=False, trust_on_first_use=False),
        project.root,
    )

    live_content = (project.root / MOCK_LIVE_REL).read_text(encoding="utf-8")
    assert "HELLO MOCK WORLD V2" in live_content, (
        "cmd_update's Step 7 did not re-render the mock target from the new core"
    )
    assert "HELLO MOCK WORLD V1" not in live_content, "stale v1 content survived the upgrade"

    engine.cmd_doctor(ns(json_out=False, fix=False, path=None), project.root)  # must not sys.exit
    engine.cmd_verify(ns(), project.root)  # must not sys.exit


def test_mock_target_disabled_is_not_rerendered_by_cmd_update(
    project, engine, mock_target, gpg_key, tmp_path, monkeypatch
):
    """(c) via cmd_update: with 'mock-harness' absent from
    render_targets.enabled, Step 7's target-specific render() must never be
    invoked for it — proving enablement gates Step 7's registry iteration.

    NOTE on scope: this test seeds the mock's core file as an ordinary
    lock-tracked core-managed entry (mirroring a real target's lock
    entries), so the PRE-EXISTING, target-agnostic Step 5-6 fast-forward
    sync (which applies to any lock-tracked core-managed file regardless of
    render-target enablement — that generic mechanism predates this fix and
    is out of scope for it) may still touch the live path via the generic
    byte-copy fallback. What per-install enablement (MED-3) gates is
    specifically whether the TARGET's own render()/expected_live_bytes()
    compile step runs — verified here via a call-count spy on render(),
    which isolates Step 7's behavior from Step 5-6's.
    """
    _seed_mock_core(project, "hello mock world v1\n")
    project.framework["upstream"] = str(tmp_path / "upstream")
    project.framework["upstream_ref"] = "v2.0.0"
    project.framework["trusted_key_fingerprint"] = gpg_key.fpr
    project.write()
    _set_enabled(project, [])  # mock-harness NOT enabled

    render_calls: list = []
    monkeypatch.setattr(mock_target, "render", lambda *a, **kw: render_calls.append((a, kw)))

    make_upstream(
        tmp_path / "upstream", gpg_key, "v2.1.0", sign="signed",
        core_files={MOCK_CORE_KEY: "hello mock world v2\n"},
    )

    engine.cmd_update(
        ns(ref="v2.1.0", to=None, dry_run=False, check=False, trust_on_first_use=False),
        project.root,
    )

    assert render_calls == [], (
        "a DISABLED target's render() must never be invoked by cmd_update's "
        "Step 7, even across a real fetch of a new upstream core version"
    )


# ---------------------------------------------------------------------------
# (c) per-install enablement gates `tessctl render` (no flags) directly.
# ---------------------------------------------------------------------------

def test_cmd_render_default_skips_disabled_mock_target(project, engine, mock_target):
    _seed_mock_core(project, "hello mock world\n")
    project.write()
    _set_enabled(project, [])  # nothing enabled

    engine.cmd_render(ns(list_targets=False, target=None), project.root)
    assert not (project.root / MOCK_LIVE_REL).exists(), (
        "`tessctl render` with no flags must never emit a registered-but-disabled "
        "target's artifact — a Claude-only install must not silently start "
        "emitting e.g. codex/AGENTS.md the moment a second target is registered"
    )


def test_cmd_render_default_renders_enabled_mock_target(project, engine, mock_target):
    _seed_mock_core(project, "hello mock world\n")
    project.write()
    _set_enabled(project, ["mock-harness"])

    engine.cmd_render(ns(list_targets=False, target=None), project.root)
    live_path = project.root / MOCK_LIVE_REL
    assert live_path.exists()
    assert live_path.read_text(encoding="utf-8") == "# MOCK-HARNESS COMPILED\nHELLO MOCK WORLD\n"


def test_cmd_render_explicit_target_bypasses_enablement(project, engine, mock_target, capsys):
    """An explicit `--target mock-harness` renders it even when the install
    has NOT enabled it — an explicit ask is not the silent-default case
    MED-3 guards against."""
    _seed_mock_core(project, "hello mock world\n")
    project.write()
    _set_enabled(project, [])  # not enabled

    capsys.readouterr()
    engine.cmd_render(ns(list_targets=False, target=["mock-harness"]), project.root)
    out = capsys.readouterr().out
    assert "not enabled for this install" in out

    live_path = project.root / MOCK_LIVE_REL
    assert live_path.exists()
    assert live_path.read_text(encoding="utf-8") == "# MOCK-HARNESS COMPILED\nHELLO MOCK WORLD\n"


def test_cmd_render_list_targets_flags_disabled_state(project, engine, mock_target, capsys):
    _seed_mock_core(project, "hello mock world\n")
    project.write()
    _set_enabled(project, [])  # not enabled

    capsys.readouterr()
    engine.cmd_render(ns(list_targets=True, target=None), project.root)
    out = capsys.readouterr().out
    assert "mock-harness" in out
    assert "[disabled for this install]" in out
    assert not (project.root / MOCK_LIVE_REL).exists(), "--list-targets must never render"
