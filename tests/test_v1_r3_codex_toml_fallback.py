"""`tessctl doctor`'s Codex hook-trust warning works without tomllib.

CI on 30 Sep 2026 (py3.9 legs, Linux and stock macOS): #223's check imported
tomllib (Python 3.11+) and returned "cannot tell" when it was missing, so on
stock macOS python3 (3.9), the main non-technical install, doctor never said
that Codex had not approved Tess's hooks. tessctl now falls back to a small
TOML reader (`_toml_subset_loads`) for the parts the check needs. These tests
force that fallback on every Python, and compare it with tomllib where tomllib
exists.
"""
from __future__ import annotations

import sys

import pytest

from test_v1_r2_ux_fixes import REPO, _codex_home

try:
    import tomllib
except ImportError:  # Python < 3.11: the parity checks below are skipped
    tomllib = None

USER_CONFIG = r'''
# a real-looking ~/.codex/config.toml with the constructs the reader skips
model = "gpt-6"
model_reasoning_effort = 'high'
notify = ["notify-send", "Codex # not a comment", "]"]
tool_output_token_limit = 12_000
temperature = 0.2
updated = 2026-09-30T08:00:00Z
profile_note = """
multi-line with "quotes", [brackets] and # hashes
"""
[mcp_servers.docs]
command = "npx"
args = [
  "-y",   # a comment inside an array
  "docs-server",
]
env = { API_BASE = "https://example.invalid", RETRIES = 3 }

[projects."/Users/op/my os"]
trust_level = "trusted"

[projects.'/tmp/other']
trust_level = "untrusted"

[hooks.state."/Users/op/my os/.codex/config.toml:session_start:0:0"]
trusted_hash = "sha256:abc1"
enabled = false

[hooks.state."/Users/op/my os/.codex/config.toml:stop:0:0"]
trusted_hash = "sha256:def"  # trailing comment
'''

EXPECTED = {
    "projects": {"/Users/op/my os": {"trust_level": "trusted"},
                 "/tmp/other": {"trust_level": "untrusted"}},
    "hooks": {"state": {
        "/Users/op/my os/.codex/config.toml:session_start:0:0": {"trusted_hash": "sha256:abc1",
                                                                 "enabled": False},
        "/Users/op/my os/.codex/config.toml:stop:0:0": {"trusted_hash": "sha256:def"}}},
}


@pytest.fixture
def no_tomllib(monkeypatch):
    monkeypatch.setitem(sys.modules, "tomllib", None)  # `import tomllib` raises ImportError


def test_fallback_reads_the_keys_the_trust_check_needs(engine):
    got = engine._toml_subset_loads(USER_CONFIG)
    assert {k: got[k] for k in EXPECTED} == EXPECTED
    assert got["model"] == "gpt-6" and got["tool_output_token_limit"] == 12000
    assert got["mcp_servers"]["docs"]["command"] == "npx"


@pytest.mark.skipif(tomllib is None, reason="parity with tomllib needs Python 3.11+")
@pytest.mark.parametrize("path", [".codex/config.toml",
                                  ".tess/core/templates/agents-md/codex-config.toml.tpl"])
def test_fallback_matches_tomllib_on_the_shipped_codex_config(engine, path):
    text = (REPO / path).read_text(encoding="utf-8")
    assert engine._toml_subset_loads(text)["hooks"] == tomllib.loads(text)["hooks"]


@pytest.mark.skipif(tomllib is None, reason="parity with tomllib needs Python 3.11+")
def test_fallback_matches_tomllib_on_a_user_config(engine):
    want = tomllib.loads(USER_CONFIG)
    got = engine._toml_subset_loads(USER_CONFIG)
    assert {k: got[k] for k in EXPECTED} == {k: want[k] for k in EXPECTED}


@pytest.mark.parametrize("bad", ['[projects."x"\ntrust_level = "trusted"\n', 'a = "open\n',
                                 "a = [1, 2\n", 'a = "x" b = 1\n', "= 1\n"])
def test_fallback_refuses_text_it_cannot_follow(engine, bad):
    with pytest.raises(ValueError):
        engine._toml_subset_loads(bad)


def test_doctor_warning_without_tomllib(tmp_path, engine, no_tomllib):
    home = _codex_home(tmp_path, engine)
    assert engine._codex_hook_trust_warning(REPO, home) == engine.CODEX_HOOKS_OFF_WARNING
    home = _codex_home(tmp_path, engine, approve=lambda h: "sha256:" + "0" * 64)
    assert {kind for _, kind in engine._codex_hook_trust_findings(REPO, home)} == {"changed"}
    home = _codex_home(tmp_path, engine, approve=lambda h: h)
    assert engine._codex_hook_trust_findings(REPO, home) == []
    assert engine._codex_hook_trust_warning(REPO, home) == ""
    home = _codex_home(tmp_path, engine, trusted=False)
    assert "trust the folder, then type /hooks" in engine._codex_hook_trust_warning(REPO, home)


def test_unreadable_user_config_is_quiet_not_a_crash(tmp_path, engine, no_tomllib):
    home = tmp_path / "codex-home"
    home.mkdir()
    (home / "config.toml").write_text('[projects."x"\n', encoding="utf-8")
    assert engine._codex_hook_trust_findings(REPO, home) is None
    assert engine._codex_hook_trust_warning(REPO, home) == ""
