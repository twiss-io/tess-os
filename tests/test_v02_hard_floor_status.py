"""
v0.2 Cyra fix round 3: no lock status keeps a weakened security-tier hard floor.

CLAUDE.md carries templates/claude-md/hard-floor.md, which v0.2 registers as
tier security (bug 10). Before this fix, three status paths let an edit that
deletes the "Clarification hard floor" line pass every mechanical check:

  * `tessctl publish CLAUDE.md` kept the hand-edited file as the published
    version and flipped every entry to user-published; doctor then printed a
    "drift hint", verify printed "no security-tier tampering", and render,
    restore and restore --force all kept the weakened text with exit 0.
  * a lock that already says user-published (an earlier publish) did the same.
  * `tessctl override CLAUDE.md` recorded a patch-override that render,
    restore and init kept with exit 0.

Fixed contract, on a copy of the real tree (the real lock):

  * publish refuses every live path whose lock entries include a security-tier
    entry, by path, by --tag and with --force, and writes nothing;
  * user-published or patch-override never keeps a security-tier live file:
    doctor raises SECURITY-TIER ALERT, verify reports SECURITY DRIFT with the
    `tessctl reset <path>` remedy, lock --check fails, render/restore/init
    exit non-zero, and restore --force re-renders the authoritative text;
  * `tessctl reset CLAUDE.md` puts the authoritative text back.
"""

from __future__ import annotations

import pytest
import yaml

from test_v02_integrity import _cli, real_tree  # noqa: F401  (fixture re-export)

HARD_FLOOR_MARK = "**Clarification hard floor**"


def _lock(root):
    return yaml.safe_load((root / ".tess" / "tess.lock").read_text(encoding="utf-8"))


def _claude_statuses(root):
    return {k: a.get("status", "core-managed")
            for k, a in _lock(root)["files"].items() if a.get("live_path") == "CLAUDE.md"}


def _weaken(root):
    p = root / "CLAUDE.md"
    text = p.read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines(keepends=True) if HARD_FLOOR_MARK not in ln]
    assert len(lines) < len(text.splitlines()), "hard-floor line not found in CLAUDE.md"
    weak = "".join(lines)
    p.write_text(weak, encoding="utf-8")
    return weak


def _set_claude_status(root, status):
    """What an earlier `publish CLAUDE.md` / `override CLAUDE.md` left in the lock."""
    path = root / ".tess" / "tess.lock"
    lock = _lock(root)
    for attrs in lock["files"].values():
        if attrs.get("live_path") == "CLAUDE.md":
            attrs["status"] = status
    path.write_text(yaml.safe_dump(lock, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _has_hard_floor(root):
    return HARD_FLOOR_MARK in (root / "CLAUDE.md").read_text(encoding="utf-8")


def test_real_lock_marks_the_claude_md_hard_floor_security_tier(real_tree):
    lock = _lock(real_tree)
    hf = lock["files"][".tess/core/templates/claude-md/hard-floor.md"]
    assert hf["live_path"] == "CLAUDE.md" and hf["tier"] == "security"
    assert _has_hard_floor(real_tree)


@pytest.mark.parametrize("argv", [
    ("publish", "CLAUDE.md"),
    ("publish", "CLAUDE.md", "--force"),
    ("publish", "--tag", "entry-point"),
])
def test_publish_refuses_a_weakened_claude_md(real_tree, argv):
    """91a0aa0: `publish CLAUDE.md` exit 0 and the weakened file became the
    published version (every CLAUDE.md entry user-published)."""
    before = _claude_statuses(real_tree)
    weak = _weaken(real_tree)

    r = _cli(real_tree, *argv)

    both = r.stdout + r.stderr
    assert r.returncode != 0, f"{argv} exited 0:\n{both[-2000:]}"
    assert "SECURITY" in both and "capture" in both, both[-2000:]
    assert _claude_statuses(real_tree) == before, "publish flipped a security-tier entry"
    assert (real_tree / "CLAUDE.md").read_text(encoding="utf-8") == weak, \
        "a refused publish must write nothing"
    r = _cli(real_tree, "doctor")
    assert r.returncode != 0 and "SECURITY DRIFT" in r.stdout, r.stdout[-2000:]


@pytest.mark.parametrize("status", ["user-published", "patch-override"])
def test_status_never_keeps_a_weakened_hard_floor(real_tree, status):
    """A lock that says user-published (an earlier publish) or patch-override
    (`tessctl override CLAUDE.md`) must not turn the hard-floor deletion into
    'OK'. 91a0aa0: doctor, verify and lock --check exit 0 for user-published;
    render, restore, restore --force and init keep the weakened text with
    exit 0 for both statuses."""
    _set_claude_status(real_tree, status)
    _weaken(real_tree)

    r = _cli(real_tree, "doctor")
    assert r.returncode != 0, r.stdout[-2000:]
    assert "SECURITY-TIER ALERT" in r.stdout and "doctor: OK" not in r.stdout, r.stdout[-2000:]

    r = _cli(real_tree, "verify")
    assert r.returncode != 0, r.stdout[-2000:]
    assert "no security-tier tampering" not in r.stdout
    sec = [ln for ln in r.stdout.splitlines() if "SECURITY DRIFT" in ln and "CLAUDE.md" in ln]
    assert sec and "tessctl reset CLAUDE.md" in sec[0], r.stdout[-2000:]
    assert "run `tessctl render`" not in sec[0], sec[0]

    r = _cli(real_tree, "lock", "--check")
    assert r.returncode != 0, r.stdout[-2000:]

    for argv in (("render",), ("restore",), ("init",)):
        r = _cli(real_tree, *argv)
        kept = not _has_hard_floor(real_tree)
        assert not (kept and r.returncode == 0), \
            f"{argv} kept the weakened hard floor with exit 0:\n{r.stdout[-2000:]}"
    for argv in (("restore",), ("init",)):
        r = _cli(real_tree, *argv)
        assert r.returncode != 0, f"{argv} exited 0:\n{r.stdout[-2000:]}"
        assert "CLAUDE.md" in r.stdout and "WOULD CLOBBER" in r.stdout, r.stdout[-2000:]

    r = _cli(real_tree, "restore", "--force")
    assert _has_hard_floor(real_tree), \
        f"restore --force kept the weakened hard floor:\n{r.stdout[-2000:]}"


@pytest.mark.parametrize("status", ["user-published", "patch-override"])
def test_reset_puts_the_hard_floor_back(real_tree, status):
    """The remedy verify names: reset re-pins every CLAUDE.md entry to core
    and re-renders; doctor and verify are clean again."""
    _set_claude_status(real_tree, status)
    _weaken(real_tree)

    r = _cli(real_tree, "reset", "CLAUDE.md")
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr
    assert _has_hard_floor(real_tree)
    assert set(_claude_statuses(real_tree).values()) == {"core-managed"}
    for argv in (("verify",), ("doctor",)):
        r = _cli(real_tree, *argv)
        assert r.returncode == 0, (argv, r.stdout[-2000:])


def test_override_on_claude_md_then_restore_is_not_kept(real_tree):
    """Round-3 MEDIUM, the real command: `tessctl override CLAUDE.md` on a
    weakened hard floor, then restore and init exit non-zero and never report
    'skip [patch-override]'. 91a0aa0: both exit 0 and keep the weakened text."""
    _weaken(real_tree)
    r = _cli(real_tree, "override", "CLAUDE.md")
    assert r.returncode == 0, r.stdout + r.stderr   # override's tier check: v0.2.1
    assert set(_claude_statuses(real_tree).values()) == {"patch-override"}

    for argv in (("restore",), ("init",)):
        r = _cli(real_tree, *argv)
        assert r.returncode != 0, f"{argv} exited 0:\n{r.stdout[-2000:]}"
        assert not _has_hard_floor(real_tree)       # refused, never silently healed
    r = _cli(real_tree, "verify")
    assert r.returncode != 0 and "tessctl reset CLAUDE.md" in r.stdout, r.stdout[-2000:]
