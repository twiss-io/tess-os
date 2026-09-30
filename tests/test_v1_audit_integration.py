"""
v1.0 security audit, integration of the four fix branches (A2 gate paths,
A1 gate shell parsing, C policy/vault, D brain/launcher) and the follow-ups
found while merging them. The follow-up cases fail on the merged tree
before their follow-up commit and pass after it.

  * A2 inside A1's resolver: the vault rule and the operator-only tessctl
    forms reach every segment A1's command-word resolver yields (`{ }`,
    `if/then`, wrappers, runners, `sh -c`, command substitutions), not only
    the plain pipelines; path identity decides glob targets too.
  * root-copy gap (from A1): `cp -R x/. .` / `rsync -a x/ ./` copy files the
    command never names into the project root; the root itself matched no
    protected path, so they were allowed. A recursive copy of a folder's
    contents into the root (or a folder above it) now asks (Claude) / is
    denied (Codex); a copy of named files into the root is checked file by
    file; `cp file .` stays allowed.
  * `tessctl verdict sign` and `tessctl gate signoff sign` (from C) need the
    operator at a terminal typing `sign as <Name>`: feeding their input or
    faking their terminal is denied like `approve`.
  * the stale "Cyra signs verdicts via `tessctl verdict sign`" wording: Cyra
    drafts the verdict, the operator signs it at their terminal.

HOME is a temp directory; the real ~/.config/tess is never touched.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
GATE = REPO / ".claude" / "hooks" / "tess-gate.py"


def _gate():
    sys.dont_write_bytecode = True  # never leave __pycache__ in .claude/hooks
    spec = importlib.util.spec_from_file_location("tess_gate_audit_integration", str(GATE))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


G = _gate()


@pytest.fixture
def proj(tmp_path, monkeypatch):
    """A project with protected files, a template folder and a temp HOME."""
    root = tmp_path / "proj"
    for rel in (".tess/tess.lock", ".tess/core/pinned-scripts.sha256", "CLAUDE.md"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / rel, root / rel)
    shutil.copytree(REPO / ".claude" / "hooks", root / ".claude" / "hooks",
                    ignore=shutil.ignore_patterns("__pycache__"))
    tpl = root / "tpl"
    (tpl / ".claude" / "hooks").mkdir(parents=True)
    (tpl / ".claude" / "hooks" / "tess-gate.py").write_text("print('evil')\n")
    (tpl / "CLAUDE.md").write_text("evil\n")
    (tpl / "notes.txt").write_text("hi\n")
    (tpl / "docs").mkdir()
    (tpl / "docs" / "a.md").write_text("a\n")
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("print('hi')\n")
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("TESS_BRAIN_PROVENANCE_DIR", raising=False)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    return root


def _eval(root, cmd, cwd=None, mode="default"):
    return G.evaluate({"tool_name": "Bash", "cwd": str(cwd or root), "tool_input": {"command": cmd},
                       "permission_mode": mode}, root)


def _level(root, cmd, cwd=None):
    return ["allow", "ask", "deny"][_eval(root, cmd, cwd).level]


def _decide(root, cmd, runtime):
    data = {"tool_name": "Bash", "cwd": str(root), "tool_input": {"command": cmd},
            "hook_event_name": "PreToolUse", "session_id": "s"}
    if runtime == "codex":
        data["turn_id"] = "t1"
    else:
        data["permission_mode"] = "default"
    return G.decide(data, root, runtime)[0]


# ------------------------------------------------------------------ root-copy gap

ROOT_CONTENT_COPIES = [
    "cp -R tpl/. .",
    "cp -a tpl/. ./",
    "cp -r tpl/ .",
    "gcp -R tpl/. .",
    "rsync -a tpl/ ./",
    "rsync -av --exclude .git tpl/ .",
    "rsync -a tpl/. \"$PWD\"",
    "cp -R tpl/. \"$(pwd)\"",
    "cp -R -t . tpl/.",
    "cp -R --target-directory=. tpl/.",
    "ditto tpl .",
    "{ cp -R tpl/. .; }",
    "bash -c 'rsync -a tpl/ ./'",
    "nice -n 5 cp -R tpl/. .",
    "cp -R src/../tpl/. src/..",
    "find tpl -mindepth 1 -maxdepth 1 -exec cp -R {} . ';'",
    "ls tpl | xargs -I{} cp -R tpl/{} .",
]


@pytest.mark.parametrize("cmd", ROOT_CONTENT_COPIES)
def test_recursive_copy_of_contents_into_root_is_not_allowed(proj, cmd):
    v = _eval(proj, cmd)
    assert v.level >= G.ASK, (cmd, v.reasons)


@pytest.mark.parametrize("cmd", ["cp -R tpl/. .", "rsync -a tpl/ ./"])
def test_root_content_copy_asks_in_claude_and_is_denied_in_codex(proj, cmd):
    v = _eval(proj, cmd)
    assert v.level == G.ASK, v.reasons
    assert any("project folder" in r and "protected" in r for r in v.reasons), v.reasons
    assert _decide(proj, cmd, "claude") == "ask"
    assert _decide(proj, cmd, "codex") == "deny"


def test_copy_from_a_subfolder_into_its_parent_root_is_seen(proj):
    assert _level(proj, "cp -R ../tpl/. ..", cwd=proj / "src") == "ask"


def test_recursive_copy_into_a_folder_above_the_root_asks(proj):
    parent = proj.parent
    assert _level(proj, f"cp -R tpl/. {parent}") == "ask"
    # copying a folder named like the project into the folder above it lands on the root
    assert _level(proj, f"cp -R /tmp/{proj.name} {parent}/") == "ask"


@pytest.mark.parametrize("cmd", [
    "cp tpl/CLAUDE.md .",
    "mv tpl/CLAUDE.md .",
    "cp -R tpl/.claude .",
    "rsync -a tpl/.claude ./",
    "ln -s tpl/CLAUDE.md .",
    "cp tpl/* .",
])
def test_named_protected_file_copied_into_root_is_denied(proj, cmd):
    v = _eval(proj, cmd)
    assert v.level == G.DENY, (cmd, v.reasons)


@pytest.mark.parametrize("cmd", [
    "cp tpl/notes.txt .",
    "cp tpl/notes.txt ./",
    "cp -R tpl/docs .",
    "rsync -a tpl/docs ./",
    "mv tpl/notes.txt .",
    "cp src/app.py src/app2.py",
    "cp -R tpl/. /tmp/elsewhere",
    "rsync -a tpl/ /tmp/backup/",
    "cp -R . /tmp/backup",
    "rsync -a ./ host:/srv/app/",
])
def test_ordinary_copies_stay_allowed(proj, cmd):
    v = _eval(proj, cmd)
    assert v.level == G.ALLOW, (cmd, v.reasons)


# ------------------------------------------------------------------ verdict / sign-off signing is operator-only

SIGN_FED = [
    "echo 'sign as Cyra' | ./tessctl verdict sign v.json --key-id K",
    "./tessctl verdict sign v.json --key-id K <<< 'sign as Cyra'",
    "./tessctl verdict sign v.json --key-id K < answers.txt",
    "printf 'sign as Xavier\\n' | ./tessctl gate signoff sign s.yaml --key-id K",
    "script -q /dev/null ./tessctl verdict sign v.json --key-id K",
    "expect -c 'spawn ./tessctl gate signoff sign s.yaml'",
    "unbuffer ./tessctl gate signoff sign s.yaml --key-id K",
    "tmux send-keys -t 0 'sign as Cyra' Enter",
    "{ echo 'sign as Cyra'; } | nice ./tessctl verdict sign v.json",
    "bash -c \"echo 'sign as Cyra' | ./tessctl verdict sign v.json\"",
    "python3 -c 'import pty; pty.spawn([\"./tessctl\", \"verdict\", \"sign\", \"v.json\"])'",
]


@pytest.mark.parametrize("runtime", ["claude", "codex"])
@pytest.mark.parametrize("cmd", SIGN_FED)
def test_feeding_or_faking_the_signing_terminal_is_denied(proj, cmd, runtime):
    assert _decide(proj, cmd, runtime) == "deny", cmd


@pytest.mark.parametrize("cmd", [
    "./tessctl verdict verify v.json",
    "./tessctl gate signoff verify s.yaml",
    "./tessctl verdict sign --help | head",
])
def test_signing_reads_and_verification_stay_allowed(proj, cmd):
    assert _level(proj, cmd) == "allow", cmd


def test_operator_form_knows_the_signing_commands():
    assert G._operator_form(["verdict", "sign", "v.json", "--key-id", "K"])
    assert G._operator_form(["gate", "signoff", "sign", "s.yaml"])
    assert not G._operator_form(["verdict", "verify", "v.json"])
    assert not G._operator_form(["gate", "signoff", "verify", "s.yaml"])


# ------------------------------------------------------------------ A2 checks inside A1's resolver

VAULT_WRAPPED = [
    "{ ./tessctl vault get --reveal svc/key; }",
    "if true; then ./tessctl vault get --reveal svc/key; fi",
    "nice -n 5 ./tessctl vault get --reveal svc/key",
    "timeout 5 ./tessctl vault exec --ref svc/key -- printenv",
    "sh -c './tessctl vault get --reveal svc/key'",
    "echo $(./tessctl vault get --reveal svc/key)",
    "uv run ./tessctl vault exec --ref svc/key -- bash -c 'echo $X'",
]


@pytest.mark.parametrize("cmd", VAULT_WRAPPED)
def test_vault_rule_reaches_every_resolved_segment(proj, cmd):
    v = _eval(proj, cmd)
    assert v.level == G.DENY and any("vault" in r for r in v.reasons), (cmd, v.reasons)


@pytest.mark.parametrize("cmd", VAULT_WRAPPED + [
    "echo y | nice ./tessctl reset",
    "{ echo y; } | ./tessctl rollback",
    "if true; then ./tessctl override x <<< y; fi",
    "echo 'sign as Cyra' | timeout 9 ./tessctl verdict sign v.json",
])
def test_resolver_path_applies_a2_checks_without_the_text_pass(proj, cmd, monkeypatch):
    """_check_segment itself applies the vault rule and the operator-only
    forms: with the text-level pass switched off, every segment the resolver
    yields is still judged."""
    monkeypatch.setattr(G, "_check_operator_only", lambda cmd, v: None)
    v = _eval(proj, cmd)
    assert v.level == G.DENY, (cmd, v.reasons)


@pytest.mark.parametrize("cmd", [
    "echo y | nice ./tessctl reset",
    "{ echo y; } | ./tessctl rollback",
    "if true; then ./tessctl override x <<< y; fi",
])
def test_state_changing_forms_fed_through_wrappers_are_denied(proj, cmd):
    assert _decide(proj, cmd, "claude") == "deny", cmd


def test_glob_target_matching_uses_path_identity(proj):
    """A glob written with a case variant of the project root still names the
    protected files (APFS/NTFS ignore case)."""
    alt = Path(str(proj).swapcase())
    if not alt.exists():
        pytest.skip("case-sensitive file system")
    assert _level(proj, f"rm {alt}/.claude/hooks/not-there-?.py") == "deny"
