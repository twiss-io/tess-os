"""Default dependency-surface regression tests.

The shipped runtime deliberately has no browser automation integration.  This
test covers the reverse direction: a normal checkout and the npm-scaffolded
template must not carry the retired package, its advisory-bearing transitive
packages, or an enabled managed skill.
"""

from __future__ import annotations

from pathlib import Path

from conftest import REPO_ROOT


def _assert_no_retired_browser_surface(root: Path) -> None:
    assert not (root / ".claude" / "skills" / "browser-use" / "SKILL.md").exists()
    assert not (root / ".tess" / "core" / "skills" / "browser-use" / "SKILL.md").exists()

    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    lock = (root / "uv.lock").read_text(encoding="utf-8")
    tracked_core = (root / ".tess" / "tess.lock").read_text(encoding="utf-8")

    assert "browser-use" not in pyproject
    assert "browser-use" not in lock
    assert "pillow" not in lock.lower()
    assert "pyasn1" not in lock.lower()
    assert "browser-use" not in tracked_core


def test_default_runtime_excludes_retired_browser_surface():
    """This test is copied into a scaffold, so its own root is authoritative."""
    _assert_no_retired_browser_surface(REPO_ROOT)


def test_bundled_template_excludes_retired_browser_surface():
    """Source checkouts additionally verify the template they ship."""
    template_root = REPO_ROOT / "create-tess" / "template"
    if template_root.is_dir():
        _assert_no_retired_browser_surface(template_root)
