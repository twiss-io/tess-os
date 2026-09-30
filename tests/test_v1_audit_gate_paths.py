"""v1.0 security audit (Cloudflare method), writer A2: gate path classification
and protection.

Findings covered (fingerprints from the audit's findings.json):

  * tess-gate.key_hit:path-string-identity-bypass: the key-directory guard
    compared case-sensitive path strings, so `~/.CONFIG/./TESS/...`, a Read of
    a case-variant path and `mv ~/.config ~/cfg` got past it;
  * tess-gate/protected_hit/case-sensitive-root-compare: the project root was
    compared case-sensitively on case-insensitive APFS, so a case-variant
    spelling of the root put protected files outside the protected set;
  * tess-gate/protected_globs/boot-allowlisted-script-unprotected: scripts/tess
    (run with no prompt at every session start) was in no protection layer;
  * tess-gate/decide-auto-mode-treated-as-interactive-ask: Claude Code `auto`
    mode got an "ask" that its classifier may settle without the operator;
  * tess-gate/rel_to_root/out-of-root-control-files-unclassified: a direct
    write of ~/.gitconfig (core.hooksPath) was never classified;
  * tessctl:vault-reveal-exec-agent-shell-extraction (gate half): `tessctl
    vault get --reveal` and `vault exec -- printenv` had no gate rule;
  * coverage critic: .github/scripts/** was unprotected; tessctl steps that
    change the recorded state of safety files were not operator-only.

Every end-to-end case runs the REAL rendered hook command in both runtimes
(helpers from test_v1_r2_security). HOME is a temp directory; the real
~/.config/tess is never touched.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from test_codex_gate import proj  # noqa: F401  (fixture)
from test_v1_r2_security import RUNTIMES, bash, run

REPO = Path(__file__).resolve().parent.parent
GATE = REPO / ".claude" / "hooks" / "tess-gate.py"


def _gate():
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("tess_gate_a2", str(GATE))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _case_insensitive(p: Path) -> bool:
    alt = p.parent / p.name.swapcase()
    return alt != p and alt.exists()


@pytest.fixture
def keyed(proj):  # noqa: F811
    kdir = proj / "home" / ".config" / "tess" / "operator"
    kdir.mkdir(parents=True)
    (kdir / "key").write_text("k" * 64)
    return proj


def _reason(root, runtime, tool, tin, mode="default"):
    """(decision, reason) from the rendered hook."""
    from test_codex_gate import _decision
    from test_v1_r2_security import CLAUDE_CMD, HOOK_CMD
    payload = {"session_id": "s", "hook_event_name": "PreToolUse", "cwd": str(root),
               "tool_name": tool, "tool_input": tin}
    if runtime == "codex":
        payload["turn_id"] = "t1"
    else:
        payload["permission_mode"] = mode
    env = {"HOME": str(root / "home"), "PATH": os.environ["PATH"],
           "TESS_GATE_LOG": str(root / "home" / "gate.log"), "CLAUDE_PROJECT_DIR": str(root)}
    r = subprocess.run(["sh", "-c", HOOK_CMD if runtime == "codex" else CLAUDE_CMD],
                       input=json.dumps(payload), capture_output=True, text=True,
                       cwd=str(root), env=env, timeout=120)
    return _decision(r) or (None, "")


# ------------------------------------------------------------------ finding 1: key dir identity

@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("cmd", [
    "cat ~/.CONFIG/./TESS/operator/key",
    "cat ~/.config/./tess/operator/key",
    "cat ~/.config/x/../tess/operator/key",
    "mv ~/.config ~/cfg && cat ~/cfg/tess/operator/key && mv ~/cfg ~/.config",
    "ditto ~/.config /tmp/cfg-copy",
])
def test_key_directory_aliases_are_denied_in_the_shell(keyed, runtime, cmd):
    assert bash(keyed, runtime, cmd) == "deny", (runtime, cmd)


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_key_directory_case_variant_path_is_denied_for_read_and_write(keyed, runtime):
    home = keyed / "home"
    if not _case_insensitive(home / ".config"):
        pytest.skip("case-sensitive file system: a case variant is another file")
    variant = str(home / ".Config" / "TESS" / "operator" / "key")
    assert run(keyed, runtime, "Read", {"file_path": variant}) == "deny"
    assert run(keyed, runtime, "Write", {"file_path": str(home / ".CONFIG" / "tess" / "new"),
                                         "content": "x"}) == "deny"
    assert bash(keyed, runtime, f"cat {variant}") == "deny"


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_key_directory_symlinked_parent_is_denied(keyed, runtime):
    link = keyed / "cfglink"
    link.symlink_to(keyed / "home" / ".config")
    assert run(keyed, runtime, "Read", {"file_path": str(link / "tess" / "operator" / "key")}) == "deny"


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_home_level_commands_stay_allowed(keyed, runtime):
    assert bash(keyed, runtime, "ls ~") is None
    assert bash(keyed, runtime, "grep -r needle ~") is None  # the stated same-user limit
    assert bash(keyed, runtime, "mv src/app.py src/main.py") is None
    assert run(keyed, runtime, "Read", {"file_path": str(keyed / "home" / ".config" / "other.txt")}) is None


def test_key_hit_uses_identity_not_spelling(tmp_path, monkeypatch):
    g = _gate()
    home = tmp_path / "h"
    (home / ".config" / "tess").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("TESS_BRAIN_PROVENANCE_DIR", raising=False)
    monkeypatch.setattr(g, "_os_home", lambda: str(home))
    assert g.key_hit(str(tmp_path), str(home / ".config" / ".." / ".config" / "tess" / "k"))
    assert g.key_hit(str(tmp_path), "~/.config", ancestors=True)
    assert g.key_hit(str(tmp_path), "~", ancestors=True) is None
    assert g.key_hit(str(tmp_path), str(tmp_path), ancestors=True) is None
    if _case_insensitive(home / ".config"):
        assert g.key_hit(str(tmp_path), str(home / ".CONFIG" / "TESS" / "operator" / "key"))
        assert g.key_hit(str(tmp_path), str(home / ".CONFIG"), ancestors=True)


# ------------------------------------------------------------------ finding 2: project root identity

@pytest.mark.parametrize("runtime", RUNTIMES)
def test_case_variant_project_root_is_still_protected(proj, runtime):  # noqa: F811
    if not _case_insensitive(proj):
        pytest.skip("case-sensitive file system")
    upper = proj.parent / proj.name.upper()
    lower_git = str(proj).lower() + "/.git/config"
    for p in (str(upper / ".claude" / "settings.json"), str(proj / ".CLAUDE" / "SETTINGS.JSON"),
              lower_git, f"../{proj.name.upper()}/.claude/hooks/tess-gate.py"):
        assert run(proj, runtime, "Write", {"file_path": p, "content": "x"}) == "deny", p
    assert bash(proj, runtime, f"echo x > {upper}/.gitleaks.toml") == "deny"
    assert bash(proj, runtime, "vim .GIT/CONFIG") == "deny"


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_symlink_into_the_project_is_still_protected(proj, runtime):  # noqa: F811
    link = proj.parent / "alias"
    link.symlink_to(proj)
    assert run(proj, runtime, "Write", {"file_path": str(link / ".claude" / "settings.json"),
                                        "content": "x"}) == "deny"


def test_rel_to_root_by_identity(tmp_path):
    g = _gate()
    root = tmp_path / "Proj"
    (root / ".claude").mkdir(parents=True)
    assert g._rel_to_root(root, str(root), ".claude/settings.json") == ".claude/settings.json"
    assert g._rel_to_root(root, str(root), str(tmp_path / "elsewhere")) is None
    if _case_insensitive(root):
        assert g._rel_to_root(root, str(tmp_path), "PROJ/.claude/new.json") == ".claude/new.json"
        assert g.protected_hit(root, str(tmp_path), "proj/.CLAUDE/settings.json")


# ------------------------------------------------------------------ findings 3 + 7: boot launcher, release helpers

@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("path", ["scripts/tess", "scripts/json.py", "scripts/shlex.pyc",
                                  "scripts/subprocess/__init__.py",
                                  ".github/scripts/verify_release_tag.sh",
                                  ".github/scripts/release_version_gate.py"])
def test_boot_launcher_and_release_helpers_are_protected(proj, runtime, path):  # noqa: F811
    assert run(proj, runtime, "Write", {"file_path": path, "content": "x"}) == "deny", path
    assert bash(proj, runtime, f"echo x > {path}") == "deny", path


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_other_scripts_stay_editable(proj, runtime):  # noqa: F811
    assert run(proj, runtime, "Write", {"file_path": "scripts/heartbeat/run.py", "content": "x"}) is None
    assert run(proj, runtime, "Write", {"file_path": "scripts/heartbeat.sh", "content": "x"}) is None


def test_policy_codeowners_and_gate_agree_on_the_new_paths():
    g = _gate()
    assert "scripts/tess" in g.PROTECTED_GLOBS and ".github/scripts/**" in g.PROTECTED_GLOBS
    for rel in ("core/policy/policy.yaml", ".tess/core/policy/policy.yaml"):
        text = (REPO / rel).read_text()
        rule = text.split("id: tess-os-security-tier-doctrine", 1)[1].split("\n    - id:", 1)[0]
        for glob in ("- .github/scripts/**", "- scripts/tess", "- scripts/*.py",
                     "- scripts/*/__init__.py"):
            assert glob in rule, (rel, glob)
    owners = (REPO / ".github" / "CODEOWNERS").read_text()
    for line in ("/.github/scripts/", "/scripts/tess", "/scripts/*.py"):
        assert line in owners, line


# ------------------------------------------------------------------ finding 4: auto mode

@pytest.mark.parametrize("mode", ["auto", "bypassPermissions", "dontAsk"])
def test_ask_in_a_mode_that_may_not_show_the_operator_is_a_deny(proj, mode):  # noqa: F811
    dec, why = _reason(proj, "claude", "Bash", {"command": "git remote add pub https://github.com/a/b.git"},
                       mode=mode)
    assert dec == "deny" and "run it yourself" in why, why
    if mode == "auto":
        assert "auto mode" in why and "default mode" in why, why


@pytest.mark.parametrize("mode", ["default", "acceptEdits", "plan"])
def test_ask_still_asks_in_modes_that_pause(proj, mode):  # noqa: F811
    assert bash(proj, "claude", "git remote add pub https://github.com/a/b.git", mode=mode) == "ask"


# ------------------------------------------------------------------ finding 5: out-of-project control files

@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("rel", [".gitconfig", ".config/git/config", ".claude/settings.json",
                                 ".claude.json", ".codex/config.toml", ".codex/rules/default.rules"])
def test_user_level_control_files_are_protected(proj, runtime, rel):  # noqa: F811
    target = proj / "home" / rel
    dec, why = _reason(proj, runtime, "Write", {"file_path": str(target), "content": "x"})
    assert dec == "deny", (rel, why)
    assert run(proj, runtime, "Edit", {"file_path": f"~/{rel}", "old_string": "a",
                                       "new_string": "b"}) == "deny", rel


@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("cmd", [
    "printf '[core]\\n\\thooksPath=/dev/null\\n' >> ~/.gitconfig",
    "echo '[alias] st = !sh' | tee -a ~/.config/git/config",
    "sed -i '' s/x/y/ ~/.gitconfig",
    "cp /tmp/evil ~/.gitconfig",
    "python3 -c \"open('/tmp/x','w');open(__import__('os').path.expanduser('~/.gitconfig'),'a').write('x')\"",
    "git config --global -e",
    "git config --global --edit",
    "git config --global init.templateDir /tmp/tpl",
    "git config --global core.hooksPath /dev/null",
    "git config --global include.path /tmp/x",
    "git config --global core.sshCommand 'sh -c x'",
    "git config --system core.fsmonitor /tmp/x",
])
def test_global_git_config_writes_are_denied(proj, runtime, cmd):  # noqa: F811
    assert bash(proj, runtime, cmd) == "deny", (runtime, cmd)


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_a_file_the_global_git_config_includes_is_protected(tmp_path, monkeypatch, runtime):
    g = _gate()
    home = tmp_path / "h"
    home.mkdir()
    (home / ".gitconfig").write_text("[user]\n\tname = me\n[include]\n\tpath = ~/.gitconfig.local\n"
                                     "[includeIf \"gitdir:~/w/\"]\n\tpath = work.inc\n")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(g, "_os_home", lambda: str(home))
    root = tmp_path / "p"
    root.mkdir()
    assert g.control_file_hit(root, str(root), str(home / ".gitconfig.local"))
    assert g.control_file_hit(root, str(root), str(home / "work.inc"))
    assert g.control_file_hit(root, str(root), str(home / "notes.txt")) is None
    assert g.control_file_hit(root, str(root), str(home)) is None  # `cp x ~` is fine


@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("cmd", ["git config --global user.name Me", "cat ~/.gitconfig",
                                 "git config --global --get core.hooksPath", "cp src/app.py ~",
                                 "echo hi > ~/notes.txt", "git config --global pull.rebase true"])
def test_ordinary_home_and_git_config_use_stays_allowed(proj, runtime, cmd):  # noqa: F811
    assert bash(proj, runtime, cmd) is None, (runtime, cmd)


# ------------------------------------------------------------------ finding 6: vault (gate half)

@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("cmd", [
    "./tessctl vault get --reveal github/token",
    "./tessctl vault get github/token --reveal | cat",
    "./tessctl vault get --rev github/token",
    "tessctl vault get --force github/token",
    "python3 .tess/bin/tessctl vault get --reveal github/token",
    "sh -c './tessctl vault get --reveal github/token'",
    "./tessctl vault exec --ref github/token -- printenv GITHUB_TOKEN",
    "./tessctl vault exec --ref github/token -- env",
    "./tessctl vault exec --ref github/token -- env FOO=1",
    "./tessctl vault exec --ref github/token printenv",
    "./tessctl vault exec --ref a/b -- echo x",
    "./tessctl vault exec --ref a/b -- bash -c 'echo $A_B'",
    "./tessctl vault exec --ref a/b -- zsh",
    "./tessctl vault exec --ref a/b -- python3 -c 'import os; print(os.environ)'",
    "./tessctl vault exec --ref a/b -- node -e 'console.log(process.env)'",
    "./tessctl vault exec --ref a/b -- nice -n 5 printenv",
    "./tessctl vault exec --ref a/b --as BASH_ENV -- bash deploy.sh",
    "./tessctl vault exec --ref a/b --as=PATH -- ls",
    "./tessctl vault exec --ref a/b --as NODE_OPTIONS -- node app.js",
])
def test_vault_value_extraction_is_denied(proj, runtime, cmd):  # noqa: F811
    dec, why = _reason(proj, runtime, "Bash", {"command": cmd})
    assert dec == "deny", (runtime, cmd, why)
    assert "vault" in why.lower() and "yourself" in why, why


@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("cmd", [
    "./tessctl vault exec --ref github/token -- gh pr list",
    "./tessctl vault exec --ref anthropic/api_key --as ANTHROPIC_API_KEY -- python3 app.py",
    "./tessctl vault exec --ref npm/token --as NPM_TOKEN -- npm publish",
    "./tessctl vault get github/token",
    "./tessctl vault list",
    "./tessctl vault doctor",
])
def test_ref_only_vault_use_stays_allowed(proj, runtime, cmd):  # noqa: F811
    assert bash(proj, runtime, cmd) is None, (runtime, cmd)


@pytest.mark.skipif(shutil.which("codex") is None, reason="codex CLI not installed")
@pytest.mark.parametrize("cmd,want", [("./tessctl vault get --reveal github/token", "forbidden"),
                                      ("tessctl vault get --force x", "forbidden"),
                                      ("./tessctl vault get github/token", None)])
def test_codex_rules_forbid_vault_reveal(cmd, want):
    r = subprocess.run(["codex", "execpolicy", "check", "--rules", str(REPO / ".codex/rules/tess.rules"),
                        "--", *cmd.split()], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout).get("decision") == want, (cmd, r.stdout)


# ------------------------------------------------------------------ finding 8: state-changing tessctl steps

@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("cmd", [
    "echo y | ./tessctl lock --regen",
    "yes | ./tessctl lock --reg",
    "./tessctl rollback < /dev/null",
    "printf 'y\\n' | ./tessctl reset CLAUDE.md",
    "./tessctl resolve CLAUDE.md --ours <<< y",
    "echo y | ./tessctl override conductor/guardrails.md",
    "echo y | ./tessctl restore --force",
    "echo y | ./tessctl publish --forc CLAUDE.md",
    "echo y | ./tessctl capture --auto",
    "script -q /dev/null ./tessctl rollback",
])
def test_state_changing_tessctl_steps_cannot_be_fed(proj, runtime, cmd):  # noqa: F811
    assert bash(proj, runtime, cmd) == "deny", (runtime, cmd)


@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("cmd", [
    "./tessctl lock --check < /dev/null",
    "./tessctl restore --dry-run < /dev/null",
    "echo x | ./tessctl capture --dry-run",
    "./tessctl diff | head",
    "./tessctl verify",
    "./tessctl rollback",
])
def test_unfed_or_read_only_tessctl_forms_stay_allowed(proj, runtime, cmd):  # noqa: F811
    assert bash(proj, runtime, cmd) is None, (runtime, cmd)


def test_operator_form_matches_flags_and_prefixes():
    g = _gate()
    assert g._operator_form(["lock", "--regen", "--yes"])
    assert g._operator_form(["lock", "--reg"])
    assert not g._operator_form(["lock", "--check"])
    assert g._operator_form(["restore", "--force"]) and not g._operator_form(["restore"])
    assert g._operator_form(["publish", "x", "--forc"]) and not g._operator_form(["publish", "x"])
    assert g._operator_form(["capture", "--auto"]) and not g._operator_form(["capture", "--dry-run"])
    for sub in ("override", "reset", "resolve", "rollback", "update", "approve", "anchor"):
        assert g._operator_form([sub, "x"]), sub
    assert not g._operator_form(["status"]) and not g._operator_form(["diff", "x"])
