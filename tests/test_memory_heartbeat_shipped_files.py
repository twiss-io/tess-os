"""Regression guard: assert the actual SHIPPED files under memory/ and
scripts/heartbeat/ are present and valid — not just that the modules behave
correctly in isolation under tmp_path fixtures.

Written after this port's own build process briefly lost the shipped
`memory/` directory (a `git revert` correcting an unrelated accidental push
also removed these then-tracked files from the working tree) without any
test catching it — every other test in this suite operates on synthetic
tmp_path fixtures and would have stayed green regardless. This file exists
so that specific class of mistake fails CI loudly instead of shipping.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from heartbeat import cards, config as config_mod, registry_gen, tier2_classify  # noqa: E402


def test_memory_directory_exists_with_expected_files():
    assert (REPO_ROOT / "memory" / "README.md").exists()
    assert (REPO_ROOT / "memory" / "registry.md").exists()
    assert (REPO_ROOT / "memory" / "projects" / "EXAMPLE.md").exists()


def test_shipped_registry_has_the_tail_marker():
    text = (REPO_ROOT / "memory" / "registry.md").read_text(encoding="utf-8")
    assert registry_gen.TAIL_MARKER in text


def test_shipped_registry_regenerates_without_error():
    """Proves the shipped registry.md is well-formed enough for `regenerate()`
    to run against it without hitting the hard-stop RegistryGenError."""
    from datetime import datetime, timezone

    text = (REPO_ROOT / "memory" / "registry.md").read_text(encoding="utf-8")
    result = registry_gen.regenerate([], text, datetime.now(timezone.utc))
    assert registry_gen.TAIL_MARKER in result


def test_shipped_example_card_parses_and_is_excluded_from_processing():
    example_path = REPO_ROOT / "memory" / "projects" / "EXAMPLE.md"
    card = cards.read_card(example_path)  # must not raise
    assert card.slug == "example-project"
    found = cards.list_card_paths(REPO_ROOT / "memory" / "projects")
    assert example_path not in found


def test_shipped_heartbeat_config_matches_safe_defaults():
    assert config_mod.DEFAULT_CONFIG_PATH.exists()
    cfg = config_mod.load()
    assert cfg.activated is False
    assert cfg.notify.channel == "none"
    assert cfg.daily_recompile.org_repo_scan == []


def test_shipped_empty_mcp_config_is_genuinely_empty():
    assert tier2_classify._EMPTY_MCP_CONFIG.exists()
    data = json.loads(tier2_classify._EMPTY_MCP_CONFIG.read_text(encoding="utf-8"))
    assert data == {"mcpServers": {}}
