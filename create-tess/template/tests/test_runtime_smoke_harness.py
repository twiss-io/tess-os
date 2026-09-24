"""
v0.2.0 (ws-rt2): tools/runtime-smoke/ — the offline runtime smoke.

No vendor CLI is needed: a fake `kimi` stands in for the real one, so these
tests run in CI. They pin the behaviour the conformance page relies on:

  * the mock endpoint records every request and answers streamed and
    non-streamed calls, and serves a scripted tool call exactly once;
  * the analysis only passes when the conductor's name AND the commands
    reached "the model", and tells AGENTS.md from CLAUDE.md;
  * the repo's own rendered AGENTS.md fits every documented budget and every
    rendered skill carries the frontmatter Kimi Code requires;
  * an instruction file above the install is refused (it would leak in);
  * offline runs never inherit a provider credential or the real HOME;
  * end to end, a CLI that loads AGENTS.md passes and one that loads nothing fails.
"""

from __future__ import annotations

import json
import stat
import sys
import textwrap
import urllib.request
from pathlib import Path

import pytest

from conftest import REPO_ROOT

SMOKE_DIR = REPO_ROOT / "tools" / "runtime-smoke"
sys.path.insert(0, str(SMOKE_DIR))

import mock_llm  # noqa: E402
import runtime_smoke  # noqa: E402
import smoke_lib  # noqa: E402

NONCE = "Smokeabc123"
COMMANDS = ["wake", "close", "add-mission"]


def _post(url: str, body: dict) -> str:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.read().decode()


def _install(root: Path, agents_text: str = None) -> Path:
    inst = root / "install"
    inst.mkdir(parents=True)
    (inst / "AGENTS.md").write_text(agents_text or (
        "# AGENTS.md\nThe dispatch rule binds only the top-level conductor (%s) and never a worker session here.\n"
        "Commands are rendered as Agent Skills under .agents/skills for every reader of this file.\n" % NONCE),
        encoding="utf-8")
    (inst / "CLAUDE.md").write_text(
        "# CLAUDE.md\nYou are %s, the conductor of this project, and this line exists only in CLAUDE.md.\n" % NONCE,
        encoding="utf-8")
    for name in COMMANDS:
        skill = inst / ".agents" / "skills" / ("tess-" + name)
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("---\nname: tess-%s\ndescription: run %s\n---\nbody\n" % (name, name),
                                        encoding="utf-8")
    return inst


def test_mock_records_and_answers_plain_and_streamed(tmp_path):
    log = tmp_path / "req.jsonl"
    with mock_llm.MockServer(str(log)) as mock:
        plain = json.loads(_post(mock.base_url + "/chat/completions", {"model": "m", "messages": []}))
        streamed = _post(mock.base_url + "/chat/completions", {"model": "m", "stream": True, "messages": []})
        bodies = mock.requests()
    assert plain["choices"][0]["message"]["content"] == mock_llm.REPLY
    assert mock_llm.REPLY in streamed and streamed.rstrip().endswith("data: [DONE]")
    assert [b.get("stream", False) for b in bodies] == [False, True]


def test_mock_serves_a_scripted_tool_call_once(tmp_path):
    script = [{"tool": "spawn_subagent", "arguments": {"prompt": "x"}}]
    tools = [{"type": "function", "function": {"name": "spawn_subagent"}}]
    with mock_llm.MockServer(str(tmp_path / "r.jsonl"), script) as mock:
        url = mock.base_url + "/chat/completions"
        no_tool = json.loads(_post(url, {"messages": []}))
        first = json.loads(_post(url, {"messages": [], "tools": tools}))
        second = json.loads(_post(url, {"messages": [], "tools": tools}))
    assert no_tool["choices"][0]["finish_reason"] == "stop"
    call = first["choices"][0]["message"]["tool_calls"][0]["function"]
    assert call["name"] == "spawn_subagent" and json.loads(call["arguments"]) == {"prompt": "x"}
    assert second["choices"][0]["finish_reason"] == "stop"


def test_analysis_needs_the_conductor_and_the_commands(tmp_path):
    inst = _install(tmp_path)
    agents = (inst / "AGENTS.md").read_text()
    skills = "\n".join("- tess-%s: run" % c for c in COMMANDS)
    good = [{"messages": [{"role": "system", "content": agents}, {"role": "user", "content": skills}]}]
    verdict = smoke_lib.judge_load(smoke_lib.analyse_requests(good, inst, NONCE))
    assert verdict["status"] == "PASS"
    assert verdict["agents_md_loaded"] and not verdict["claude_md_loaded"]
    no_skills = [{"messages": [{"role": "system", "content": agents}]}]
    assert smoke_lib.judge_load(smoke_lib.analyse_requests(no_skills, inst, NONCE))["status"] == "FAIL"
    nothing = [{"messages": [{"role": "user", "content": skills}]}]
    assert smoke_lib.judge_load(smoke_lib.analyse_requests(nothing, inst, NONCE))["status"] == "FAIL"


def test_live_reply_must_name_the_conductor_and_three_commands():
    ok = smoke_lib.judge_reply("I am %s. Try /tess-wake, /close or $tess-add-mission." % NONCE, NONCE, COMMANDS)
    assert ok["status"] == "PASS"
    no_name = smoke_lib.judge_reply("I am a coding agent. /tess-wake /tess-close /tess-add-mission", NONCE, COMMANDS)
    assert no_name["status"] == "FAIL"


def test_repo_agents_md_fits_every_documented_budget_and_skills_have_frontmatter():
    result = smoke_lib.static_checks(REPO_ROOT)
    assert result["status"] == "PASS", result["detail"]
    assert result["skills"] == len(list((REPO_ROOT / ".tess" / "core" / "commands").glob("*.md")))


def test_static_check_fails_an_oversized_agents_md(tmp_path):
    inst = _install(tmp_path, agents_text="x" * 12001)
    assert smoke_lib.static_checks(inst)["status"] == "FAIL"


def test_instruction_files_above_the_install_are_refused(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("ancestor doctrine", encoding="utf-8")
    inst = tmp_path / "deeper" / "install"
    inst.mkdir(parents=True)
    assert str(tmp_path / "CLAUDE.md") in smoke_lib.ancestor_hits(inst)


def test_offline_env_drops_provider_keys_and_redirects_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "must-not-leak")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.invalid")
    env = smoke_lib.offline_env(tmp_path, {"KIMI_CODE_HOME": str(tmp_path / ".kimi-code")})
    assert "XAI_API_KEY" not in env and "OPENAI_BASE_URL" not in env
    assert env["HOME"] == str(tmp_path) and env["KIMI_CODE_HOME"] == str(tmp_path / ".kimi-code")


FAKE_KIMI = textwrap.dedent('''\
    #!{python}
    """A fake `kimi`: reads the scratch provider config, sends {what} to it."""
    import json, os, re, sys, urllib.request
    from pathlib import Path
    if sys.argv[1:] == ["--version"]:
        print("9.9.9-fake"); sys.exit(0)
    cfg = (Path(os.environ["KIMI_CODE_HOME"]) / "config.toml").read_text()
    url = re.search(r'base_url = "([^"]+)"', cfg).group(1) + "/chat/completions"
    parts = []
    if {load}:
        parts.append(Path("AGENTS.md").read_text())
        parts += ["- %s: skill" % p.name for p in sorted(Path(".agents/skills").iterdir())]
    body = {{"model": "mock-model", "messages": [{{"role": "system", "content": "\\n".join(parts)}},
                                                 {{"role": "user", "content": sys.argv[-1]}}]}}
    req = urllib.request.Request(url, json.dumps(body).encode(), {{"Content-Type": "application/json"}})
    print(json.load(urllib.request.urlopen(req, timeout=10))["choices"][0]["message"]["content"])
''')


def _fake_cli(tmp_path: Path, load: bool) -> Path:
    path = tmp_path / ("fake-kimi-%s" % ("loads" if load else "blind"))
    path.write_text(FAKE_KIMI.format(python=sys.executable, load=load,
                                     what="AGENTS.md and the skills" if load else "nothing"), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


@pytest.mark.parametrize("load, expected", [(True, "PASS"), (False, "FAIL")])
def test_end_to_end_with_a_fake_cli(tmp_path, load, expected):
    inst = _install(tmp_path)
    report = tmp_path / "report.json"
    code = runtime_smoke.main(["--cli", "kimi", "--install", str(inst), "--nonce", NONCE,
                               "--workdir", str(tmp_path / "work"), "--bin", "kimi=%s" % _fake_cli(tmp_path, load),
                               "--json", str(report)])
    kimi = json.loads(report.read_text())["clis"]["kimi"]
    assert kimi["version"]["status"] == "PASS" and "9.9.9-fake" in kimi["version"]["detail"]
    assert kimi["load"]["status"] == expected
    assert kimi["live"]["status"] == "SKIPPED"  # never without --live
    assert code == (0 if expected == "PASS" else 1)
    # the mock provider was configured in the scratch HOME, never the operator's
    assert (tmp_path / "work" / "homes" / "kimi-mock" / ".kimi-code" / "config.toml").is_file()
