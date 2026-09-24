"""Per-CLI adapters for the runtime smoke. See README.md for what each stage proves.

Every adapter answers four questions without logging in:
  version()  - is the CLI installed, and does it start with a scratch HOME?
  offline()  - what does it load from the install? (inspect command or mock endpoint)
  signed_in()- does the CLI itself say it is signed in? (True / False / None = cannot tell)
  live()     - opt-in: ask the real model "Who are you? List your commands."
"""

from __future__ import annotations

import itertools
import json
import os
import shutil
from pathlib import Path

from mock_llm import MockServer
from smoke_lib import (FAIL, OBSERVED, PASS, PROMPT, SKIPPED, UNVERIFIED, analyse_requests, fresh_home,
                       judge_load, judge_reply, offline_env, run, stage)

REAL_HOME = Path(os.path.expanduser("~"))
_RUN_IDS = itertools.count(1)
MOCK_KEY = "sk-mock-not-a-secret"
NOT_SIGNED_IN = ("not authenticated", "not signed in", "no model configured", "authentication required",
                 "please log in", "run `kimi` and use /login", "/auth")


class Cli:
    key = name = binary = npm = ""
    home_var = None  # the CLI's own config-root variable, redirected with HOME

    def __init__(self, ctx):
        self.ctx = ctx
        self.path = ctx.resolve(self.binary)
        self.live_path = None  # live runs use only the operator's own install (see live())

    def env(self, home: Path, extra: dict = None) -> dict:
        own = {self.home_var: str(home / ("." + self.key))} if self.home_var else {}
        own.update(extra or {})
        return offline_env(home, own, self.ctx.path_prefix)

    def version(self) -> dict:
        home = fresh_home(self.ctx.workdir, self.key + "-version")
        code, out, err = run([self.path, "--version"], self.env(home), self.ctx.workdir, 60)
        if code != 0:
            return stage(FAIL, "`--version` exited %s: %s" % (code, (err or out)[-200:]))
        return stage(PASS, (out or err).strip().splitlines()[0][:80])

    def offline(self) -> dict:
        return {"load": stage(UNVERIFIED, "no documented offline load check for this CLI")}

    def signed_in(self):
        return None, "the CLI has no documented sign-in status command"

    def live_command(self) -> list:
        return [self.live_path, "-p", PROMPT]

    def live_env(self) -> dict:
        return dict(os.environ)

    def live(self) -> dict:
        # Never a scratch-installed or --bin CLI: another version could migrate the operator's own
        # config directory. Only the CLI already on the operator's PATH talks to the operator's account.
        self.live_path = shutil.which(self.binary)
        if not self.live_path:
            return stage(SKIPPED, "not on the operator's PATH; live runs never use a scratch-installed CLI")
        state, why = self.signed_in()
        if state is False:
            return stage(UNVERIFIED, "not signed in (%s)" % why)
        code, out, err = run(self.live_command(), self.live_env(), self.ctx.install, 300)
        blob = (out + "\n" + err).lower()
        if code != 0 and any(m in blob for m in NOT_SIGNED_IN):
            return stage(UNVERIFIED, "not signed in: the CLI refused the run before any model call")
        if code != 0:
            return stage(FAIL, "live run exited %s: %s" % (code, (err or out)[-300:]))
        result = judge_reply(out, self.ctx.nonce, self.ctx.commands)
        result["live_binary"] = self.live_path
        return result

    def mock_run(self, cmd_for, script=None, env_extra=None) -> tuple:
        """Point the CLI at a local mock endpoint and return (exit code, stderr, analysis)."""
        home = fresh_home(self.ctx.workdir, self.key + "-mock")
        log = self.ctx.workdir / ("mock-%s-%d.jsonl" % (self.key, next(_RUN_IDS)))
        with MockServer(str(log), script) as mock:
            cmd = cmd_for(home, mock.base_url)
            code, _out, err = run(cmd, self.env(home, env_extra), self.ctx.install, 240)
            bodies = mock.requests()
        return code, err, bodies


class Grok(Cli):
    key, name, binary, npm, home_var = "grok", "Grok Build", "grok", "@xai-official/grok", "GROK_HOME"

    def env(self, home, extra=None):
        return super().env(home, dict({"GROK_DISABLE_AUTOUPDATER": "1"}, **(extra or {})))

    def _inspect(self, trust_gate_off: bool) -> dict:
        home = fresh_home(self.ctx.workdir, "grok-inspect")
        extra = {"GROK_FOLDER_TRUST": "0"} if trust_gate_off else {}
        code, out, err = run([self.path, "inspect", "--json"], self.env(home, extra), self.ctx.install, 120)
        if code != 0:
            raise RuntimeError("grok inspect exited %s: %s" % (code, err[-200:]))
        return json.loads(out)

    def offline(self) -> dict:
        try:
            trusted, untrusted = self._inspect(True), self._inspect(False)
        except (RuntimeError, ValueError) as exc:
            return {"inspect": stage(FAIL, str(exc))}
        names = sorted(Path(i["path"]).name.lower() for i in trusted.get("projectInstructions", []))
        skills = [s["name"] for s in trusted.get("skills", []) if s.get("name", "").startswith("tess-")]
        hooks = [h for h in trusted.get("hooks", []) if h.get("vendor") == "claude"]
        ok = "agents.md" in names and len(skills) >= len(self.ctx.commands)
        inspect = stage(PASS if ok else FAIL,
                        "trusted: instructions %s, %d tess-* skills, %d Claude hooks, %d agents; untrusted: %d "
                        "instruction files, %d skills" % (names, len(skills), len(hooks), len(trusted.get("agents", [])),
                                                          len(untrusted.get("projectInstructions", [])),
                                                          len(untrusted.get("skills", []))))
        return {"inspect": inspect, "load": self._mock_load(), "gate_probe": self._gate_probe()}

    def _write_mock_model(self, home: Path, base_url: str) -> None:
        cfg = home / ".grok"
        cfg.mkdir(parents=True, exist_ok=True)
        (cfg / "config.toml").write_text(
            '[models]\ndefault = "mock"\n\n[model.mock]\nmodel = "mock-model"\nbase_url = "%s"\n'
            'api_key = "%s"\napi_backend = "chat_completions"\ncontext_window = 128000\n' % (base_url, MOCK_KEY),
            encoding="utf-8")

    def _mock_cmd(self, prompt, turns):
        def build(home, base_url):
            self._write_mock_model(home, base_url)
            return [self.path, "-p", prompt, "-m", "mock", "--max-turns", str(turns), "--always-approve"]
        return build

    def _mock_load(self) -> dict:
        code, err, bodies = self.mock_run(self._mock_cmd(PROMPT, 1), env_extra={"GROK_FOLDER_TRUST": "0"})
        if code != 0:
            return stage(FAIL, "mock run exited %s: %s" % (code, err[-200:]))
        return judge_load(analyse_requests(bodies, self.ctx.install, self.ctx.nonce))

    def _gate_probe(self) -> dict:
        """Does Tess's vault-dispatch hook stop a secret-shaped subagent prompt under Grok?"""
        secret = "-----BEGIN " + "PRIVATE KEY-----"  # split so no scanner sees a key header in source
        script = [{"tool": "spawn_subagent", "arguments": {
            "prompt": "Use this key: %s and list files." % secret, "description": "gate probe", "background": False}}]
        code, err, bodies = self.mock_run(self._mock_cmd("Delegate the task.", 3), script,
                                          {"GROK_FOLDER_TRUST": "0"})
        reached = any(secret in (m.get("content") or "") for b in bodies[1:] for m in b.get("messages", [])
                      if m.get("role") == "user" and "Use this key" in (m.get("content") or ""))
        blocked = any("VAULT DISPATCH SCAN" in json.dumps(b) for b in bodies)
        if blocked:
            return stage(PASS, "vault-dispatch-scan blocked the subagent prompt")
        return stage(OBSERVED, "vault-dispatch-scan did not block: the secret-shaped prompt %s the subagent"
                     % ("reached" if reached else "may have reached"), exit_code=code)

    def signed_in(self):
        home = fresh_home(self.ctx.workdir, "grok-status")
        env = offline_env(home, {"GROK_HOME": str(REAL_HOME / ".grok"), "GROK_DISABLE_AUTOUPDATER": "1"})
        code, out, err = run([self.live_path, "models"], env, self.ctx.workdir, 60)
        if "not authenticated" in (out + err).lower() and "XAI_API_KEY" not in os.environ:
            return False, "`grok models` says not authenticated"
        return (True, "`grok models` ran signed in") if code == 0 else (None, "`grok models` exited %s" % code)

    def live_env(self):
        home = fresh_home(self.ctx.workdir, "grok-live")
        env = dict(os.environ, HOME=str(home), GROK_HOME=str(REAL_HOME / ".grok"), GROK_FOLDER_TRUST="0",
                   GROK_DISABLE_AUTOUPDATER="1")
        return env

    def live_command(self):
        return [self.live_path, "-p", PROMPT, "--max-turns", "3"]


class Kimi(Cli):
    key, name, binary, npm, home_var = "kimi", "Kimi Code", "kimi", "@moonshot-ai/kimi-code", "KIMI_CODE_HOME"

    def env(self, home, extra=None):
        return offline_env(home, dict({"KIMI_CODE_HOME": str(home / ".kimi-code")}, **(extra or {})),
                           self.ctx.path_prefix)

    def offline(self) -> dict:
        def build(home, base_url):
            cfg = home / ".kimi-code"
            cfg.mkdir(parents=True, exist_ok=True)
            (cfg / "config.toml").write_text(
                'default_model = "mock"\n\n[providers.mock]\ntype = "openai"\nbase_url = "%s"\napi_key = "%s"\n\n'
                '[models.mock]\nprovider = "mock"\nmodel = "mock-model"\nmax_context_size = 128000\n'
                % (base_url, MOCK_KEY), encoding="utf-8")
            return [self.path, "-p", PROMPT]
        code, err, bodies = self.mock_run(build)
        if code != 0:
            return {"load": stage(FAIL, "mock run exited %s: %s" % (code, err[-200:]))}
        return {"load": judge_load(analyse_requests(bodies, self.ctx.install, self.ctx.nonce))}

    def live_env(self):
        home = fresh_home(self.ctx.workdir, "kimi-live")
        return dict(os.environ, HOME=str(home), KIMI_CODE_HOME=str(REAL_HOME / ".kimi-code"))


class Qwen(Cli):
    key, name, binary, npm = "qwen", "Qwen Code", "qwen", "@qwen-code/qwen-code"

    def offline(self) -> dict:
        def build(home, base_url):
            return [self.path, PROMPT, "--auth-type", "openai", "--openai-api-key", MOCK_KEY,
                    "--openai-base-url", base_url, "-m", "mock-model"]
        code, err, bodies = self.mock_run(build)
        if code != 0:
            return {"load": stage(FAIL, "mock run exited %s: %s" % (code, err[-200:]))}
        return {"load": judge_load(analyse_requests(bodies, self.ctx.install, self.ctx.nonce))}

    def live_command(self):
        return [self.live_path, PROMPT]


class DeepSeek(Cli):
    key, name, binary, npm, home_var = "dsh", "DeepSeek Harness", "dsh", "@deepseek-ai/dsh", "DSH_HOME"

    def offline(self) -> dict:
        """The default route reads DEEPSEEK_API_KEY and DEEPSEEK_BASE_URL: point both at the mock."""
        home = fresh_home(self.ctx.workdir, "dsh-mock")
        with MockServer(str(self.ctx.workdir / "mock-dsh.jsonl")) as mock:
            extra = {"DEEPSEEK_API_KEY": MOCK_KEY, "DEEPSEEK_BASE_URL": mock.base_url}
            code, _out, err = run([self.path, "--profile", "headless", PROMPT], self.env(home, extra),
                                  self.ctx.install, 300)
            bodies = mock.requests()
        if code != 0:
            return {"load": stage(FAIL, "mock run exited %s: %s" % (code, err[-200:]))}
        return {"load": judge_load(analyse_requests(bodies, self.ctx.install, self.ctx.nonce))}

    def live(self) -> dict:
        profile = Path(os.environ.get("DSH_HOME", str(REAL_HOME / ".dsh"))) / "profiles" / "headless"
        if not profile.is_dir():
            return stage(SKIPPED, "no existing headless profile; running would create one under DSH_HOME")
        return super().live()

    def live_command(self):
        return [self.live_path, "--profile", "headless", PROMPT]


class Antigravity(Cli):
    key, name, binary = "agy", "Antigravity CLI", "agy"

    def live(self) -> dict:
        return stage(SKIPPED, "never run: Antigravity's terms bar use in connection with products not provided "
                              "by Google, and a Tess smoke is such a use")


class Gemini(Cli):
    key, name, binary, npm = "gemini", "Gemini CLI", "gemini", "@google/gemini-cli"

    def offline(self) -> dict:
        """`gemini skills list` needs no auth; project skills load only in a trusted folder."""
        home = fresh_home(self.ctx.workdir, "gemini-skills")
        (home / ".gemini").mkdir()
        (home / ".gemini" / "trustedFolders.json").write_text(
            json.dumps({str(self.ctx.install): "TRUST_FOLDER"}), encoding="utf-8")
        code, out, _err = run([self.path, "skills", "list"], self.env(home), self.ctx.install, 120)
        listed = sum(1 for c in self.ctx.commands if ("tess-" + c) in out)
        context = "GEMINI.md present" if (self.ctx.install / "GEMINI.md").is_file() else \
            "no GEMINI.md, so AGENTS.md is not loaded unless context.fileName names it"
        ok = code == 0 and listed >= len(self.ctx.commands)
        return {"load": stage(PASS if ok else FAIL, "trusted folder: %d/%d tess-* skills listed; %s"
                              % (listed, len(self.ctx.commands), context))}

    def live(self) -> dict:
        if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_GENAI_USE_VERTEXAI")):
            return stage(SKIPPED, "needs GEMINI_API_KEY or Vertex AI; consumer Login with Google for "
                                  "Gemini CLI ended 2026-06-18")
        return super().live()

    def live_env(self):
        home = fresh_home(self.ctx.workdir, "gemini-live")
        return dict(os.environ, HOME=str(home))

    def live_command(self):
        return [self.live_path, "-p", PROMPT, "--skip-trust"]


ADAPTERS = {c.key: c for c in (Grok, Kimi, Qwen, DeepSeek, Antigravity, Gemini)}
