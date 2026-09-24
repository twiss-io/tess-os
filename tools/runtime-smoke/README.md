# Runtime smoke

Does a fresh Tess OS install load in each vendor CLI? This harness answers
that without logging in to anything. Results for the v0.2.0 release are in
[`adapters/CONFORMANCE.md`](../../adapters/CONFORMANCE.md#runtime-smoke-2026-09-24).

```sh
npm --prefix create-tess ci          # once: the scaffold step uses create-tess
python3 tools/runtime-smoke/runtime_smoke.py                    # every CLI found on PATH
python3 tools/runtime-smoke/runtime_smoke.py --install-clis \
    --node-dir /path/to/node22/bin --cli grok,kimi,qwen         # install the npm CLIs into scratch first
python3 tools/runtime-smoke/runtime_smoke.py --live             # also ask signed-in CLIs, see below
```

Stdlib Python 3.9+, no dependencies. Kimi Code and Qwen Code need Node 22 or
newer (`--node-dir` puts a Node 22 `bin` directory first on the CLIs' `PATH`).

## What it does

1. **Scaffold.** Runs `create-tess` from this checkout into a new temp
   directory with a random conductor name (`Smoke<hex>`). The harness refuses
   to run if any directory above the install holds a `CLAUDE.md`, `AGENTS.md`,
   `GEMINI.md`, `QWEN.md` or `.git`: a CLI walking upward would load it and the
   smoke could pass for the wrong reason. `--install DIR --nonce NAME` reuses
   an existing scaffold instead.
2. **Static check.** `AGENTS.md` fits every documented budget (12,000
   characters for a Devin Desktop workspace rule; 32 KiB for Codex and Kimi
   Code; 65,536 bytes for DeepSeek Harness's `AGENTS.md` + `CLAUDE.md`
   baseline), and every `.agents/skills/tess-*/SKILL.md` carries the `name` and
   `description` that Kimi Code requires.
3. **Per CLI**, each stage reports `PASS`, `FAIL`, `SKIPPED`, `UNVERIFIED` or
   `OBSERVED` (a recorded fact that is neither a pass nor a failure):

| CLI | installed / version | Offline load check (no login, no model) | Live (`--live`) |
|---|---|---|---|
| Grok Build `grok` | `--version` | `grok inspect --json`, trusted and untrusted; a mock-endpoint run; a gate probe (below) | if `grok models` says signed in |
| Kimi Code `kimi` | `--version` | mock endpoint through a scratch `config.toml` provider | if the run is not refused for missing sign-in |
| Qwen Code `qwen` | `--version` | mock endpoint through `--auth-type openai --openai-base-url` | same |
| DeepSeek Harness `dsh` | `--version` | mock endpoint through `DEEPSEEK_API_KEY` + `DEEPSEEK_BASE_URL` | only if a headless profile already exists |
| Gemini CLI `gemini` | `--version` | `gemini skills list` in a folder trusted in the scratch HOME | only with `GEMINI_API_KEY` or Vertex AI set |
| Antigravity CLI `agy` | `--version` | none documented: `UNVERIFIED` | never |

**Mock endpoint.** [`mock_llm.py`](mock_llm.py) is a local, stdlib stand-in for
an OpenAI-compatible Chat Completions API. The CLI is configured, in a scratch
HOME only, to use it as its model. Every request body is logged, and the check
reads what reached "the model": which instruction file (by a line unique to
`AGENTS.md` or `CLAUDE.md`), how often the conductor's random name appears, and
how many `tess-*` skills are listed. `PASS` needs the conductor name and all
but at most two of the commands.

**Gate probe (Grok Build).** The mock answers with a `spawn_subagent` call whose
prompt carries a secret-shaped string, then checks whether Tess's
`vault-dispatch-scan.py` stopped it. Grok passes Claude hooks its own tool
names, so on Grok 1.0.41 the prompt reaches the subagent; the stage records
that as `OBSERVED`.

**Live.** `--live` asks each CLI "Who are you? List your commands." in the
scratch install and passes when the reply names the conductor and at least
three commands. It runs only:

- with the CLI already on the operator's `PATH` (never a scratch-installed or
  `--bin` copy, which might migrate the operator's config to another version);
- when the CLI does not report itself signed out (Grok Build: `grok models`;
  the others refuse the run before any model call, which is reported as
  `UNVERIFIED`);
- with `HOME` redirected to a scratch directory and only the CLI's own config
  root (`GROK_HOME`, `KIMI_CODE_HOME`) pointing at the operator's, so the
  operator's other agent files (`~/.claude`, `~/.agents`) are not loaded.
  Grok runs with `GROK_FOLDER_TRUST=0`, so no trust grant is recorded.

A live run spends a little of the operator's plan quota. The CLI writes what it
normally writes to its own config root (a session record, and a refreshed
login if it decides to refresh one); the harness itself writes nothing there.

## What it never does

- Log in, run a login command, or pass a login flag.
- Open, read, copy or print a vendor auth file (`~/.claude/.credentials.json`,
  `~/.codex/auth.json`, `~/.grok/auth.json`, `~/.kimi-code/credentials/`, ...).
  Whether a CLI is signed in is asked of the CLI itself.
- Write to the operator's CLI configuration. Offline stages use a scratch HOME
  and remove provider API keys from the environment, so a mock run cannot fall
  through to a real model.
- Run Antigravity CLI live: its terms treat use "in connection with products
  not provided by us" as abuse.
- Run Claude Code or Codex. Their smoke is a separate release step.

## Output

A table on stdout and, with `--json FILE`, the full report (every stage, the
counts behind it, and a reply excerpt for live runs). The exit code is 1 if any
stage is `FAIL`, else 0; `SKIPPED`, `UNVERIFIED` and `OBSERVED` never fail a run.
