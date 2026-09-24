"""
v0.2.0 (ws-rt2): the extended runtime rows in adapters/CONFORMANCE.md.

  * Grok Build, Kimi Code, Qwen Code, DeepSeek Harness and Antigravity CLI
    each have a row in the per-runtime table with a real level and https docs.
  * The subscription table covers those five plus Gemini CLI, Claude Code and
    Codex, and every cell after the runtime name cites a source (an https link
    or the in-page runtime-smoke section).
  * No page offers Gemini CLI a consumer Google sign-in: Google ended it on
    2026-06-18, so the only paths named are a Gemini API key or Vertex AI.
  * README.md and docs/STATUS.md never make an unqualified "all frontier
    models" claim.
  * The rendered AGENTS.md, the only file Kimi Code and Qwen Code load, names
    each runtime's own syntax for running a Tess command.
"""

from __future__ import annotations

import re

import pytest

from conftest import REPO_ROOT

CONFORMANCE = REPO_ROOT / "adapters" / "CONFORMANCE.md"
NEW_RUNTIMES = {
    "Grok Build": "Advisory",
    "Kimi Code": "Advisory",
    "Qwen Code": "Advisory",
    "DeepSeek Harness": "Advisory",
    "Antigravity CLI": "Advisory",
}
SUBSCRIPTION_HEADER = ["Runtime", "Level", "Subscription path", "Headless command",
                       "Loads from a Tess install", "Known gaps"]


def _split_row(line: str) -> list:
    cells = re.split(r"(?<!\\)\|", line.strip())
    return [c.strip() for c in cells[1:-1]]


def _table(header: list) -> list:
    lines = CONFORMANCE.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if line.startswith("|") and _split_row(line) == header:
            rows = []
            for row in lines[i + 2:]:
                if not row.startswith("|"):
                    break
                cells = _split_row(row)
                assert len(cells) == len(header), row
                rows.append(dict(zip(header, cells)))
            return rows
    return []


def _runtime_rows() -> dict:
    header = ["Runtime", "Tess target", "Level", "How it reads Tess", "Why this level (limits)", "Docs"]
    return {r["Runtime"]: r for r in _table(header)}


@pytest.mark.parametrize("runtime, level", sorted(NEW_RUNTIMES.items()))
def test_new_runtime_rows_exist_with_a_level_and_docs(runtime, level):
    rows = {name: row for name, row in _runtime_rows().items() if name.startswith(runtime)}
    assert rows, "no per-runtime row for %s" % runtime
    (row,) = rows.values()
    assert row["Level"] == level
    assert re.search(r"\]\(https://[^)\s]+\)", row["Docs"]), row


def test_subscription_table_covers_every_runtime_and_cites_every_cell():
    rows = {r["Runtime"]: r for r in _table(SUBSCRIPTION_HEADER)}
    expected = set(NEW_RUNTIMES) | {"Gemini CLI", "Claude Code", "OpenAI Codex CLI"}
    assert expected <= set(rows), sorted(expected - set(rows))
    for name, row in rows.items():
        for column in SUBSCRIPTION_HEADER[1:]:
            cell = row[column]
            assert re.search(r"\]\((https://[^)\s]+|#runtime-smoke-2026-09-24)\)", cell), (name, column, cell)


def test_subscription_paths_match_the_verified_research():
    rows = {r["Runtime"]: r["Subscription path"] for r in _table(SUBSCRIPTION_HEADER)}
    assert rows["Grok Build"].startswith("**Allowed")
    assert rows["Kimi Code"].startswith("**Allowed")
    assert rows["DeepSeek Harness"].startswith("**Not available")
    assert rows["Antigravity CLI"].startswith("**Not available")
    assert "Gemini API key or Vertex AI only" in rows["Gemini CLI"]
    assert "2026-06-18" in rows["Gemini CLI"]


@pytest.mark.parametrize("page", ["adapters/CONFORMANCE.md", "README.md", "docs/STATUS.md"])
def test_no_page_offers_gemini_cli_a_consumer_google_sign_in(page):
    text = (REPO_ROOT / page).read_text(encoding="utf-8")
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if re.search(r"gemini", sentence, re.I) and re.search(
                r"login with google|google (account|sign-in|login)|ai (pro|ultra)|pro/ultra", sentence, re.I):
            assert re.search(r"ended|no longer|still describes|not ", sentence, re.I), sentence


@pytest.mark.parametrize("page", ["README.md", "docs/STATUS.md"])
def test_no_unqualified_all_frontier_models_claim(page):
    for line in (REPO_ROOT / page).read_text(encoding="utf-8").splitlines():
        if re.search(r"all frontier", line, re.I):
            assert re.search(r"unsupported|not |never", line, re.I), line


def test_rendered_agents_md_names_each_runtimes_skill_syntax():
    agents = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for syntax in ("$tess-<name>", "/skill:tess-<name>", "/tess-<name>"):
        assert syntax in agents, syntax
    for runtime in ("Kimi Code", "Grok Build", "Qwen Code"):
        assert runtime in agents, runtime
