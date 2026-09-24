"""
v0.2 bug 9: the write gate must never follow a symlink.

On 5c2d698 check_manifest_write_gate computed norm_rel from the RESOLVED
target, so a write to `AGENTS.md -> CLAUDE.md` passed the allowlist as
`CLAUDE.md` and guarded_write replaced CLAUDE.md's bytes. guarded_remove had
the same shape: removing a symlink deleted the file it pointed at.

Each test below asserts behaviour (what got written or deleted), not just
that an exception type exists.
"""

from __future__ import annotations

import json
import shutil

import pytest

from conftest import MANIFEST_SRC

CLAUDE_BYTES = b"# CLAUDE.md\noriginal operator content\n"


@pytest.fixture
def gate_root(tmp_path):
    shutil.copy2(MANIFEST_SRC, tmp_path / "tess.manifest.json")
    return tmp_path


@pytest.fixture
def manifest():
    return json.loads(MANIFEST_SRC.read_text())


def _agents_link_to_claude(root):
    (root / "CLAUDE.md").write_bytes(CLAUDE_BYTES)
    (root / "AGENTS.md").symlink_to("CLAUDE.md")


def test_guarded_write_refuses_final_component_symlink(engine, gate_root):
    """AGENTS.md -> CLAUDE.md: the write is refused and CLAUDE.md is untouched.
    On 5c2d698 this wrote b'x' into CLAUDE.md."""
    _agents_link_to_claude(gate_root)
    with pytest.raises(engine.GateError) as ei:
        engine.guarded_write(gate_root, "AGENTS.md", b"x", op="test")
    assert "symlink" in str(ei.value).lower()
    assert (gate_root / "CLAUDE.md").read_bytes() == CLAUDE_BYTES
    assert (gate_root / "AGENTS.md").is_symlink()


def test_gate_refuses_final_component_symlink(engine, gate_root, manifest):
    """The gate itself refuses, and never reports the link target as norm_rel.
    On 5c2d698 it returned 'CLAUDE.md' for a request to write 'AGENTS.md'."""
    _agents_link_to_claude(gate_root)
    with pytest.raises(engine.GateError) as ei:
        engine.check_manifest_write_gate(gate_root, manifest, "AGENTS.md", op="test")
    assert "symlink" in str(ei.value).lower()


def test_gate_refuses_dangling_final_symlink(engine, gate_root):
    """A dangling in-tree link is not written through either. On 5c2d698 the
    write created the link's (owned) target file."""
    (gate_root / "conductor").mkdir()
    (gate_root / "conductor" / "x.md").symlink_to("not-yet-there.md")
    with pytest.raises(engine.GateError):
        engine.guarded_write(gate_root, "conductor/x.md", b"poison", op="test")
    assert not (gate_root / "conductor" / "not-yet-there.md").exists()
    assert (gate_root / "conductor" / "x.md").is_symlink()


def test_gate_refuses_dangling_directory_symlink(engine, gate_root):
    """A dangling DIRECTORY link is a symlink component too. The old
    `exists() and is_symlink()` check skipped it, and the write landed in
    agents/newdir/ (a path the caller never named)."""
    (gate_root / "conductor").mkdir()
    (gate_root / "agents").mkdir()
    (gate_root / "conductor" / "linkdir").symlink_to("../agents/newdir")
    with pytest.raises(engine.GateError) as ei:
        engine.guarded_write(gate_root, "conductor/linkdir/p.md", b"poison", op="test")
    assert "symlink" in str(ei.value).lower()
    assert not (gate_root / "agents" / "newdir").exists()


def test_guarded_remove_does_not_delete_link_target(engine, gate_root):
    """Removing a symlinked path is refused; the file it points at survives.
    On 5c2d698 guarded_remove('AGENTS.md') deleted CLAUDE.md."""
    _agents_link_to_claude(gate_root)
    removed = engine.guarded_remove(gate_root, "AGENTS.md")
    assert removed is False
    assert (gate_root / "CLAUDE.md").read_bytes() == CLAUDE_BYTES


def test_guarded_write_rechecks_symlink_after_gate(engine, gate_root, monkeypatch):
    """guarded_write refuses a symlink target on its own, even if the gate were
    bypassed or a link appeared after the gate ran (TOCTOU narrowing)."""
    _agents_link_to_claude(gate_root)
    monkeypatch.setattr(
        engine, "check_manifest_write_gate",
        lambda root, manifest, live_rel, op="write": live_rel,
    )
    with pytest.raises(engine.GateError):
        engine.guarded_write(gate_root, "AGENTS.md", b"x", op="test")
    assert (gate_root / "AGENTS.md").is_symlink()
    assert (gate_root / "CLAUDE.md").read_bytes() == CLAUDE_BYTES


def test_norm_rel_is_lexical_not_resolved(engine, gate_root, manifest):
    """norm_rel is the normalised path the caller named ('./', '//' folded)."""
    (gate_root / "conductor").mkdir()
    (gate_root / "conductor" / "guardrails.md").write_text("G\n")
    assert engine.check_manifest_write_gate(
        gate_root, manifest, "./conductor//guardrails.md", op="test"
    ) == "conductor/guardrails.md"


@pytest.mark.parametrize("rel", ["", ".", "./"])
def test_gate_refuses_the_root_itself(engine, gate_root, manifest, rel):
    with pytest.raises(engine.GateError):
        engine.check_manifest_write_gate(gate_root, manifest, rel, op="test")


def test_regular_files_still_written(engine, gate_root):
    """No over-blocking: a regular owned file is still written, atomically."""
    (gate_root / "CLAUDE.md").write_bytes(CLAUDE_BYTES)
    engine.guarded_write(gate_root, "CLAUDE.md", b"new\n", op="test")
    assert (gate_root / "CLAUDE.md").read_bytes() == b"new\n"
    engine.guarded_write(gate_root, "agents/leah/README.md", b"L\n", op="test")
    assert (gate_root / "agents" / "leah" / "README.md").read_bytes() == b"L\n"


def test_symlinked_root_is_not_a_symlink_component(engine, tmp_path):
    """The Tess root itself may be reached through a symlink (macOS /var ->
    /private/var, a linked checkout). Only components BELOW the root count."""
    real = tmp_path / "real"
    real.mkdir()
    shutil.copy2(MANIFEST_SRC, real / "tess.manifest.json")
    link = tmp_path / "link"
    link.symlink_to(real)
    engine.guarded_write(link, "CLAUDE.md", b"via-linked-root\n", op="test")
    assert (real / "CLAUDE.md").read_bytes() == b"via-linked-root\n"
