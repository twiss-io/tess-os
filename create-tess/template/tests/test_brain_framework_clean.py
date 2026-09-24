"""The framework repo never carries an operator's brain (spec 2, G7).

create-tess/template is `git ls-files` of this repo, so anything tracked
under brain/ here would ship inside every instance. The source-repo guard
must also hold here: onboarding and its hook stay off in tess-os itself.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def ls(*paths: str) -> list:
    out = subprocess.run(["git", "-C", str(REPO), "ls-files", "--", *paths], capture_output=True,
                         text=True, check=True).stdout
    return [p for p in out.splitlines() if p]


def test_no_brain_tracked_in_framework():
    assert ls("brain") == []
    assert [p for p in ls() if "/.private/" in "/" + p] == []


def test_memory_projects_ships_only_the_example():
    assert ls("memory/projects") == ["memory/projects/EXAMPLE.md"]


def test_this_repo_is_the_source_repo_and_onboarding_is_off():
    assert (REPO / "create-tess" / "package.json").exists()
    assert not (REPO / "brain" / "brain.json").exists()
    onboard = [sys.executable, str(REPO / "scripts" / "brain" / "onboard.py")]
    st = subprocess.run(onboard + ["status", "--json"], capture_output=True, text=True)
    assert json.loads(st.stdout)["status"] == "source-repo"
    hook = subprocess.run(onboard + ["hook", "session-start", "--runtime", "claude"], input="{}",
                          capture_output=True, text=True)
    assert hook.returncode == 0 and hook.stdout == ""


def test_templates_never_ship_a_live_entity_file():
    """Template AGENTS.md files end in .tpl so no runtime loads a placeholder brief."""
    tpl = REPO / "scripts" / "brain" / "templates"
    assert list(tpl.rglob("AGENTS.md")) == []
    assert len(list(tpl.rglob("AGENTS.md.tpl"))) >= 8
