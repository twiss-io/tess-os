"""Unit tests for scripts/heartbeat/daily_recompile.py.

All git operations here run against a throwaway `git init`-only repo under
pytest's `tmp_path` fixture — there is deliberately NO `git remote` configured,
so even if a test exercises the non-dry-run commit path, `git push` fails
harmlessly (the module calls it with `check=False`) instead of ever reaching
a real remote. This mirrors the exact mistake this port's own manual testing
made once (running the activated/real path against an origin-connected
clone) and is written specifically so that mistake cannot recur via the
automated suite.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from heartbeat import config as config_mod  # noqa: E402
from heartbeat import daily_recompile, registry_gen  # noqa: E402

NOW = datetime(2026, 1, 10, tzinfo=timezone.utc)


def _init_local_only_repo(tmp_path: Path) -> Path:
    """A git repo with NO remote configured — `git push` inside it can never
    reach a real network destination."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "memory").mkdir()
    (tmp_path / "memory" / "registry.md").write_text(
        f"# placeholder\n\n{registry_gen.TAIL_MARKER}\n\nplaceholder tail\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=tmp_path, check=True)
    assert "origin" not in subprocess.run(
        ["git", "remote"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout
    return tmp_path


def test_dry_run_never_writes_registry_or_commits(tmp_path):
    repo_root = _init_local_only_repo(tmp_path)
    registry_path = repo_root / "memory" / "registry.md"
    before = registry_path.read_text(encoding="utf-8")
    cfg = config_mod.HeartbeatConfig()  # notify.channel defaults to "none"

    result = daily_recompile.run(
        all_cards=[], now=NOW, dry_run=True,
        repo_root=repo_root, registry_path=registry_path, cfg=cfg,
    )

    assert registry_path.read_text(encoding="utf-8") == before  # untouched
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=repo_root, capture_output=True, text=True, check=True
    ).stdout
    assert log.count("\n") == 1  # still just the one seed commit
    assert "0 open, 0 stalled, 0 P0" in result["digest"]


def test_real_run_writes_and_commits_locally_but_push_fails_harmlessly(tmp_path, monkeypatch):
    """dry_run=False exercises the real git-write path. Tier-2's
    `daily_recompile_synthesis` is monkeypatched to a canned response so
    this test — which specifically isolates the git write/commit/push
    behavior — never spawns a real `claude -p` process (that fail-closed
    invocation itself is covered, mocked, in test_memory_heartbeat_tier2_safety.py;
    conflating the two here would make this test slow, non-deterministic,
    and dependent on a local `claude` install + live auth, none of which
    this test is about)."""
    repo_root = _init_local_only_repo(tmp_path)
    registry_path = repo_root / "memory" / "registry.md"
    cfg = config_mod.HeartbeatConfig()

    def _fake_synthesis(**kwargs):
        return {"unregistered_candidates": [], "stale_card_suspects": []}

    monkeypatch.setattr(
        "heartbeat.daily_recompile.tier2_classify.daily_recompile_synthesis",
        _fake_synthesis,
    )

    result = daily_recompile.run(
        all_cards=[], now=NOW, dry_run=False,
        repo_root=repo_root, registry_path=registry_path, cfg=cfg,
    )

    assert "# Open Projects Registry" in registry_path.read_text(encoding="utf-8")
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=repo_root, capture_output=True, text=True, check=True
    ).stdout
    assert "daily recompile" in log
    # No remote existed, so the module's own `git push` call (check=False)
    # failed silently rather than reaching any network destination —
    # confirmed by the repo still having zero remotes afterward.
    remotes = subprocess.run(
        ["git", "remote"], cwd=repo_root, capture_output=True, text=True, check=True
    ).stdout
    assert remotes.strip() == ""
    assert result["notify"]  # notify.send was still invoked (channel="none" -> no-op)
