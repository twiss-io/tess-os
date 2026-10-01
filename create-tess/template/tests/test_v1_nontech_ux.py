"""v1.0 non-technical end-to-end review: the fixes a person with no technical
background needs (B1, B3, S2, S3, S5, S6, S7, S8).

- B1: a refused push prints one plain summary naming the files (at most 5),
  what it means, the undo command, and a real doc; repeats are collapsed;
  every line only with --verbose; CI output never names files; the printed
  undo command really undoes the change so the next push passes.
- B3: Claude Code runs the Tess safety gate as a PreToolUse hook (deny for
  the hard blocks, ask for the approval cases), through the pinned launcher.
- S2: `update --check` says what WOULD change and that nothing was changed.
- S3: on-screen wizard answers are recorded as the operator's words.
- S5: `tessctl help` is a short everyday list; doctor drift is plain words.
- S6/S7/S8: allow list, onboarding, README and Codex save wording.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

import _brain_oobe_helpers as h

REPO = Path(__file__).resolve().parent.parent
CONTRACTS_SRC = REPO / "core" / "contracts"
HAS_GIT = shutil.which("git") is not None
HAS_NODE = shutil.which("node") is not None
GIT_ENV = {"GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@tess.test",
           "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@tess.test"}

POLICY = {"policy": {"version": 1, "rules": [{
    "id": "prod-src", "description": "test-only protected files", "globs": ["src/prod/**"],
    "classification": ["prod_touching"], "require_verdict": True, "allowed_verifiers": ["Reid"],
}], "hard_floor_rules": []}}


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                       env={**os.environ, **GIT_ENV})
    assert r.returncode == 0, r.stderr
    return r


def _tessctl(root: Path, *args: str, stdin: str | None = None, verbose: bool = False):
    env = {**os.environ, "TESS_ROOT": str(root)}
    env.pop("TESS_VERBOSE", None)
    if verbose:
        env["TESS_VERBOSE"] = "1"
    return subprocess.run([sys.executable, str(root / ".tess" / "bin" / "tessctl"), *args],
                          cwd=str(root), env=env, capture_output=True, text=True, input=stdin)


@pytest.fixture
def repo(project):
    root = project.root
    shutil.copytree(CONTRACTS_SRC, root / "core" / "contracts")
    (root / "core" / "policy").mkdir(parents=True)
    (root / "core" / "policy" / "policy.yaml").write_text(yaml.safe_dump(POLICY), encoding="utf-8")
    (root / "src" / "prod").mkdir(parents=True)
    for i in range(8):
        (root / "src" / "prod" / f"f{i}.py").write_text(f"x = {i}\n")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "commit.gpgsign", "false")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    return root


def _head(root):
    return _git(root, "rev-parse", "HEAD").stdout.strip()


def _commit(root, msg):
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", msg)
    return _head(root)


def _pre_push(root, head, base, verbose=False):
    return _tessctl(root, "gate", "pre-push", stdin=f"refs/heads/main {head} refs/heads/main {base}\n",
                    verbose=verbose)


# ── B1: plain refusals ───────────────────────────────────────────────────


@pytest.mark.skipif(not HAS_GIT, reason="git required")
def test_refused_push_is_plain_names_the_file_and_the_undo_really_works(repo):
    base = _head(repo)
    (repo / "src" / "prod" / "f0.py").write_text("x = 'edited'\n")
    head = _commit(repo, "edit a protected file")
    r = _pre_push(repo, head, base)
    assert r.returncode == 1
    out = r.stdout
    assert "Tess stopped this push because it changes 1 protected file(s):" in out
    assert "    src/prod/f0.py" in out
    assert "Nothing was sent." in out
    undo = f"git restore --source={base[:12]} -- src/prod/f0.py"
    assert undo in out and 'git commit -m "Undo change to protected Tess files" -- src/prod/f0.py' in out
    assert "More help: docs/WHEN_TESS_STOPS_A_PUSH.md" in out
    assert "Decision #6" not in out and "README.md 'tessctl gate'" not in out
    assert len(out.splitlines()) <= 16, out

    # Run the printed undo exactly as a person would, then push again: PASS.
    _git(repo, "restore", f"--source={base[:12]}", "--", "src/prod/f0.py")
    _git(repo, "commit", "-q", "-m", "Undo change to protected Tess files", "--", "src/prod/f0.py")
    again = _pre_push(repo, _head(repo), base)
    assert again.returncode == 0, again.stdout
    assert "tessctl gate pre-push — PASS" in again.stdout


@pytest.mark.skipif(not HAS_GIT, reason="git required")
def test_many_refused_files_collapse_and_verbose_lists_them_all(repo):
    base = _head(repo)
    for i in range(8):
        (repo / "src" / "prod" / f"f{i}.py").write_text(f"x = 'e{i}'\n")
    head = _commit(repo, "edit eight protected files")
    r = _pre_push(repo, head, base)
    assert r.returncode == 1
    out = r.stdout
    assert "changes 8 protected file(s):" in out
    assert "… and 3 more (`TESS_VERBOSE=1 git push` lists them all)" in out
    assert out.count("COVERING_APPROVAL_MISSING") == 1 and "(×8)" in out
    assert "git restore --source=<the commit before your change>" in out  # no 8-file undo line
    assert len(out.splitlines()) <= 18, out
    loud = _pre_push(repo, head, base, verbose=True)
    assert loud.stdout.count("COVERING_APPROVAL_MISSING") == 8
    assert all(f"file: src/prod/f{i}.py" in loud.stdout for i in range(8))
    flag = _tessctl(repo, "gate", "pre-push", "--verbose", "--base", base, "--head", head)
    assert flag.stdout.count("COVERING_APPROVAL_MISSING") == 8


@pytest.mark.skipif(not HAS_GIT, reason="git required")
def test_ci_refusal_never_names_files_and_json_is_unchanged(repo):
    base = _head(repo)
    (repo / "src" / "prod" / "f1.py").write_text("x = 'edited'\n")
    head = _commit(repo, "edit")
    r = _tessctl(repo, "gate", "ci", "--base", base, "--head", head)
    assert r.returncode == 1
    assert "src/prod/f1.py" not in r.stdout
    assert "Tess stopped this change because it changes 1 protected file(s)." in r.stdout
    assert "COVERING_APPROVAL_MISSING: no covering APPROVE verdict found" in r.stdout
    j = _tessctl(repo, "gate", "ci", "--base", base, "--head", head, "--json")
    payload = json.loads(j.stdout)
    assert payload["reasons"] == ["COVERING_APPROVAL_MISSING: no covering APPROVE verdict found"]
    assert "src/prod" not in j.stdout


def test_refusal_doc_exists_with_the_sections_the_messages_name():
    doc = (REPO / "docs" / "WHEN_TESS_STOPS_A_PUSH.md").read_text(encoding="utf-8")
    for heading in ("## If you did not mean to change that file", "## If you meant to change it",
                    "## First push of a new folder", "## Never skip the check"):
        assert heading in doc
    assert "TESS_VERBOSE=1 git push" in doc
    engine = (REPO / ".tess" / "bin" / "tessctl").read_text(encoding="utf-8")
    assert 'GATE_REFUSAL_DOC = "docs/WHEN_TESS_STOPS_A_PUSH.md"' in engine
    assert 'section \\"First push of a new folder\\"' in engine


# ── B3: the Tess gate runs in Claude Code ───────────────────────────────


def _claude_gate_hook(settings: dict) -> dict:
    for entry in settings["hooks"]["PreToolUse"]:
        for hook in entry["hooks"]:
            if "tess-gate.py" in hook["command"]:
                return {"matcher": entry["matcher"], **hook}
    raise AssertionError("no tess-gate.py PreToolUse hook")


@pytest.mark.parametrize("rel", [".tess/core/settings-core.json", ".claude/settings.json"])
def test_claude_settings_wire_the_gate_for_every_write_tool(rel):
    hook = _claude_gate_hook(json.loads((REPO / rel).read_text(encoding="utf-8")))
    assert hook["matcher"] == "^(Bash|Edit|Write|MultiEdit|NotebookEdit|Read|Grep|Glob|NotebookRead)$"
    assert ('run-pinned.py" --on-fail block -- .claude/hooks/tess-gate.py --runtime claude'
            in hook["command"])
    assert "exit 2" in hook["command"]  # no python3: the call is blocked, not waved through


@pytest.mark.parametrize("tool,tool_input,want", [
    ("Bash", {"command": "git commit --allow-empty --no-verify -m probe"}, "deny"),
    ("Edit", {"file_path": "conductor/guardrails.md", "old_string": "a", "new_string": "b"}, "deny"),
    ("MultiEdit", {"file_path": ".claude/settings.json", "edits": []}, "deny"),
    # HEAD to a local path: CI checks out a detached HEAD with no local `main`,
    # and the gate fails closed on a ref it cannot resolve.
    ("Bash", {"command": "git push --force ../tess-backup.git HEAD:main"}, "ask"),
    ("Bash", {"command": "ls -la"}, None),
])
def test_claude_gate_hook_blocks_and_asks_through_the_pinned_launcher(tool, tool_input, want):
    hook = _claude_gate_hook(json.loads((REPO / ".claude" / "settings.json").read_text()))
    payload = {"session_id": "s", "hook_event_name": "PreToolUse", "cwd": str(REPO),
               "permission_mode": "default", "tool_name": tool, "tool_input": tool_input}
    r = subprocess.run(["sh", "-c", hook["command"]], input=json.dumps(payload), capture_output=True,
                       text=True, env={**os.environ, "CLAUDE_PROJECT_DIR": str(REPO),
                                       "TESS_GATE_LOG": os.devnull}, cwd=str(REPO))
    assert r.returncode == 0, r.stderr
    if want is None:
        assert r.stdout.strip() == ""
        return
    decision = json.loads(r.stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == want, decision
    assert decision["permissionDecisionReason"].startswith("TESS GATE:")


# ── S2: update --check ──────────────────────────────────────────────────


def test_update_check_summary_says_would_and_nothing_changed(engine, capsys):
    text = "\n".join([
        "tessctl update — current: v2 v1.0.0",
        "  [fast-forward] a.md  — core-managed → fast-forward from staging",
        "  [fast-forward] b.md  — core-managed → fast-forward from staging",
        "  [merge       ] c.md  — locally-modified + upstream changed → 3-way merge",
        "", "update check: complete — " + engine.UPDATE_CHECK_RESULT,
    ])
    engine._print_update_summary(text, check=True)
    out = capsys.readouterr().out
    assert "Of Tess's own files, 2 would be updated, 1 would be merged with your changes." in out
    assert out.splitlines()[0] == "tessctl update — you have Tess OS v1.0.0"  # no "v2" track label
    assert "Nothing was changed: this was only a check." in out
    assert "update: complete" not in out and " 2 updated" not in out
    engine._print_update_summary("tessctl update — current: v2 v1.0.0\n", check=True)
    assert "No file would change." in capsys.readouterr().out


def test_update_check_without_a_fetch_never_calls_identical_files_updated(engine, capsys):
    # What a fresh install printed: "991 files checked: 991 updated. update: complete".
    text = "\n".join([
        "tessctl update — current: v2 v1.0.0",
        "  (dry-run: would fetch-and-verify 'v1.0.0' from https://example.test/tess-os.git)",
        "  [fast-forward] .claude/agents/ada.md  — no staging = treat as same as core",
        "  [fast-forward] .claude/agents/clio.md  — no staging = treat as same as core",
        "", "update check: complete — " + engine.UPDATE_CHECK_RESULT,
    ])
    engine._print_update_summary(text, check=True)
    out = capsys.readouterr().out
    assert "Every Tess file already matches the release (nothing to do)." in out
    assert "fetch-and-verify" not in out and "files checked" not in out  # e2e round 2
    assert "This check did not go online" in out and "Nothing was changed" in out
    assert "updated" not in out.replace("would be updated", "")


def test_update_check_end_line_is_honest_in_the_engine():
    src = (REPO / ".tess" / "bin" / "tessctl").read_text(encoding="utf-8")
    assert 'print("\\nupdate check: complete — " + UPDATE_CHECK_RESULT)' in src


# ── S3: on-screen answers are the operator's words ──────────────────────


@pytest.mark.skipif(not HAS_NODE, reason="node required")
def test_wizard_on_screen_answers_are_recorded_as_words_not_flags(tmp_path):
    root = h.mini_instance(tmp_path)
    js = ("import('%s').then(m => process.stdout.write(JSON.stringify(m.onScreenAnswers({"
          "mode: 'agency', preset: 'solo-consultant', operator: 'Rowan', conductor: 'Tess',"
          "said: {mode: 'My business, with clients', preset: 'Yes', operator: 'Rowan', conductor: null}}))))"
          % (REPO / "create-tess" / "src" / "brain.js").as_uri())
    data = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout
    answers = tmp_path / "answers.json"
    answers.write_text(data)
    r = h.onboard(root, "init", "--non-interactive", "--answers", str(answers))
    assert r.returncode == 0, r.stdout + r.stderr
    got = json.loads((root / "brain" / "brain.json").read_text())["onboarding"]["answers"]
    assert got["mode"]["quote"] == "My business, with clients" and got["mode"]["runtime"] == "setup-wizard"
    assert got["preset"]["quote"] == "Yes" and got["preset"]["value"] == "solo-consultant"
    assert got["operator_name"]["quote"] == "Rowan"
    assert got["assistant_name"] == {**got["assistant_name"], "value": "Tess", "quote": "", "runtime": "default"}
    assert not any(str(a.get("quote", "")).startswith("--") for a in got.values())


# ── S5: short help, plain doctor drift ──────────────────────────────────


def test_help_is_short_and_help_all_lists_everything(tmp_path):
    root = h.full_instance(tmp_path)
    short = _tessctl(root, "help")
    assert short.returncode == 0
    lines = short.stdout.strip().splitlines()
    assert len(lines) <= 14, short.stdout
    for cmd in ("tessctl doctor", "tessctl update --check", "tessctl update", "tessctl roster list",
                "tessctl --version", "tessctl help --all"):
        assert cmd in short.stdout
    assert "self-update" not in short.stdout and "vault" not in short.stdout
    full = _tessctl(root, "help", "--all")
    assert "self-update" in full.stdout and "vault" in full.stdout
    assert _tessctl(root).stdout == short.stdout


def test_doctor_security_drift_is_plain_words(tmp_path):
    root = h.full_instance(tmp_path)
    assert _tessctl(root, "render").returncode == 0
    (root / "CLAUDE.md").write_text((root / "CLAUDE.md").read_text() + "\nhand edit\n")
    r = _tessctl(root, "doctor")
    assert r.returncode != 0
    line = next(l for l in r.stdout.splitlines() if "CLAUDE.md" in l and "SECURITY DRIFT" in l)
    assert "QUARANTINE" not in line
    assert "delete the file and run `tessctl render`" in line and "tessctl approve" in line


# ── S6 / S7 / S8: wording a person relies on ────────────────────────────


def test_claude_allow_list_saves_without_prompting_and_stays_narrow():
    allow = json.loads((REPO / ".tess" / "core" / "settings-core.json").read_text())["permissions"]["allow"]
    assert "Bash(python3 scripts/brain/tessbrain.py save:*)" in allow
    for broad in ("Bash(python3:*)", "Bash(python3 scripts/brain/tessbrain.py:*)", "Bash(git commit:*)",
                  "Bash(git push:*)", "Bash(*)"):
        assert broad not in allow
    onboarding = (REPO / "docs" / "brain" / "ONBOARDING.md").read_text(encoding="utf-8")
    assert "counts as trusted" not in onboarding
    assert "`claude -p` does not count" in onboarding


def test_readme_first_steps_open_a_terminal_and_start_the_app():
    text = (REPO / "README.md").read_text(encoding="utf-8")
    for need in ("**Open a terminal.**", "type `Terminal`", "WSL", "cd my-os\n   claude",
                 "type `codex` instead of `claude`", "there is no default", "WHEN_TESS_STOPS_A_PUSH.md"):
        assert need in (" ".join(text.split()) if " is no " in need else text), need


def test_codex_save_is_escalated_on_the_first_attempt():
    for rel in (".claude/skills/brain-save/SKILL.md", ".agents/skills/brain-save/SKILL.md"):
        skill = " ".join((REPO / rel).read_text(encoding="utf-8").split())
        assert "the FIRST and only way you run this command is with escalated permissions" in skill
        assert "Do not try it inside the sandbox first" in skill
    agents = " ".join((REPO / "AGENTS.md").read_text(encoding="utf-8").split())
    assert "on the FIRST attempt (`sandbox_permissions: \"require_escalated\"`" in agents
