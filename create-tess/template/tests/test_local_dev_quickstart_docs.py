"""Static guardrails for the local developer quickstart.

This test intentionally reads documentation only. It never invokes the CLI,
Git, Node, a package manager, a network, or a trace writer.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
QUICKSTART_PATH = REPO_ROOT / "docs" / "LOCAL_DEV_QUICKSTART.md"
README_PATH = REPO_ROOT / "README.md"
CONTRIBUTING_PATH = REPO_ROOT / "CONTRIBUTING.md"


def _executable_blocks(document: str) -> list[str]:
    return re.findall(r"```(?:bash|sh|shell|zsh)\n(.*?)\n```", document, flags=re.DOTALL)


def test_local_dev_quickstart_has_grounded_setup_and_validation_commands():
    document = QUICKSTART_PATH.read_text(encoding="utf-8")
    executable = "\n".join(_executable_blocks(document))

    for required_text in (
        "**Python 3.9 or newer.**",
        '`requires-python = ">=3.9"`',
        "**Node.js 18 or newer, only when testing `create-tess`.**",
        "Git** and a Bash-compatible shell",
        "WSL",
        "Start from a fresh contributor clone.",
        "intentionally\nmutating",
        "no covering APPROVE verdict found",
        "[gate operation and custody guide](GATE_QUICKSTART.md)",
        "[support and status guide](STATUS.md)",
    ):
        assert required_text in document

    for command in (
        "git clone https://github.com/twiss-io/tess-os.git",
        "cd tess-os",
        "python3 -m venv .venv",
        "source .venv/bin/activate",
        "python -m pip install -r requirements-dev.txt",
        "./tessctl init",
        "python -m pytest",
        "(cd create-tess && npm ci && npm test)",
        "./tessctl doctor",
        "./tessctl verify",
        "npm pack --dry-run",
    ):
        assert command in executable


def test_local_dev_executable_blocks_do_not_offer_bypasses_or_release_actions():
    document = QUICKSTART_PATH.read_text(encoding="utf-8")
    executable = "\n".join(_executable_blocks(document)).lower()

    for forbidden in (
        "keygen",
        "register",
        "sign",
        "verdict",
        "--no-verify",
        "--no-gate-hooks",
        "lock --regen",
        "npm publish",
        "twine upload",
        "npm install",
        "init --from",
    ):
        assert forbidden not in executable

    assert "(cd create-tess && npm ci && npm test)" in executable
    assert re.search(r"^npm (?:install|test)\b", executable, flags=re.MULTILINE) is None
    assert "certified" not in document.lower()
    assert "production-ready" not in document.lower()


def test_readme_and_contributing_point_to_the_local_dev_quickstart():
    expected = "docs/LOCAL_DEV_QUICKSTART.md"

    assert expected in README_PATH.read_text(encoding="utf-8")
    assert expected in CONTRIBUTING_PATH.read_text(encoding="utf-8")
