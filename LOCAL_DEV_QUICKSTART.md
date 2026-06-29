# Local Development Quickstart

> 🚀 A step-by-step guide for first-time contributors to Tess OS.
> Follow these steps to get a working local dev environment, run the quality
> gates, and test your changes end-to-end.

---

## 1. Prerequisites

Before you start, install these on your machine:

| Tool | Why | Minimum version | How to check |
|------|-----|----------------|--------------|
| **Python 3** | Runs the engine, `tessctl`, and tests | ≥ 3.9 | `python3 --version` |
| **Node.js + npm** | Builds and tests the `create-tess` wizard | Node ≥ 18, npm ≥ 9 | `node --version && npm --version` |
| **Git** | Version control | Any recent version | `git --version` |

> ⚠️ **If `python3` doesn't work on your system**, try `python`. Tess OS
> targets Python 3.9+; Python 2 is not supported.

---

## 2. Clone & Enter the Project

```bash
git clone https://github.com/twiss-io/tess-os.git
cd tess-os
```

> 💡 **For your own fork**: replace the URL with your fork's clone URL (e.g.
> `git clone https://github.com/YOUR_USERNAME/tess-os.git`), then add the
> upstream remote:
> ```bash
> git remote add upstream https://github.com/twiss-io/tess-os.git
> ```

---

## 3. Set Up Python

### 3.1 Install Python dependencies

Tess OS keeps its Python dependencies minimal by design — `tessctl` itself
requires only the standard library plus **PyYAML**:

```bash
pip install pyyaml
# or on some systems:
# pip3 install pyyaml
```

If you are using a virtual environment (recommended):

```bash
python3 -m venv .venv
source .venv/bin/activate   # Linux / macOS
# .venv\Scripts\activate    # Windows (PowerShell)
pip install pyyaml
```

### 3.2 Verify the engine parses cleanly

```bash
python3 -c "import ast; ast.parse(open('.tess/bin/tessctl').read())"
```

If this prints nothing, the engine is syntactically valid. ✅

---

## 4. Set Up Node.js (for `create-tess`)

The `create-tess` npm package lives in its own subdirectory and ships the
gamified first-run wizard:

```bash
cd create-tess
npm install
cd ..
```

### 4.1 Verify

```bash
cd create-tess && npm test && cd ..
```

This runs the create-tess test suite. All tests should pass before you open a PR.

---

## 5. Configure Your Environment

### 5.1 Copy the environment template

```bash
cp .env.example .env
```

### 5.2 Fill in your credentials

Open `.env` in your editor and replace the placeholders:

```env
# Required for Tess to communicate with Claude
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Optional: Telegram notifications (create a bot via @BotFather)
TELEGRAM_BOT_TOKEN=your-bot-token-here
TELEGRAM_DM_CHAT_ID=your-dm-chat-id-here

# Optional: local timezone (IANA name, e.g. America/New_York). Defaults to UTC
TESS_LOCAL_TZ=UTC
```

> ⚠️ **NEVER commit `.env`** — it is in `.gitignore` and CI will reject it.
> Use `.env.example` as the public template.

---

## 6. Run `tessctl` Commands

`tessctl` is the keystone CLI for framework lifecycle management. Once your
Python environment is ready, verify the core commands:

```bash
# Initialize the project (writes lock + manifest + operator stubs, renders CLAUDE.md)
./tessctl init

# Framework health check (SHA-integrity, flags security-tier drift)
./tessctl doctor

# Verify .tess/core bytes against base_sha — integrity gate
./tessctl verify

# Render CLAUDE.md and settings.json from templates
./tessctl render

# List starter squads
./tessctl roster list
```

> 💡 Run `./tessctl --help` for the full command reference. Each subcommand
> also has its own `--help` (e.g. `./tessctl init --help`).

---

## 7. Run the Full Quality Gates

These must **all pass** before your PR is mergeable. Run them locally to catch
issues early:

```bash
# Gate 1 — Python test suite (engine + vault + render + merge + hooks)
python3 -m pytest

# Gate 2 — create-tess wizard suite
cd create-tess && npm test && cd ..

# Gate 3 — Engine integrity + parse
python3 -c "import ast; ast.parse(open('.tess/bin/tessctl').read())"
./tessctl doctor
./tessctl verify

# Gate 4 — npm pack integrity (checks nothing secret/bloated ships)
cd create-tess && npm pack --dry-run && cd ..
```

> 📋 **Tip**: Create a shortcut script in your local environment:
> ```bash
> # Save as ./qa.sh and run: bash qa.sh
> echo "🔍 Running quality gates..."
> python3 -m pytest && \
> cd create-tess && npm test && cd .. && \
> ./tessctl doctor && ./tessctl verify && \
> echo "✅ All gates passed!"
> ```

---

## 8. Test the End-to-End Flow

The ultimate integration test: run the wizard as a user would.

```bash
# From the repository root
cd create-tess
npm start -- ../my-test-instance
```

This simulates `npm create tess@latest` targeting a temp directory. The wizard
walks through five choices (Name → Vibe → Squad → Conductor → Pathway), stages
the template, validates, and promotes on confirm. **Cancel leaves zero state**
behind — the temp directory is cleaned up.

After confirming, verify the output:

```bash
ls ../my-test-instance/
# Should contain: .tess/ CLAUDE.md .env.example .gitignore ...
cd ../my-test-instance
./tessctl doctor   # verify the instance integrity
cd ../tess-os      # back to the repo
```

Clean up when done:

```bash
rm -rf ../my-test-instance
```

---

## 9. Common Issues & Troubleshooting

### `python3: command not found`

Install Python 3 from [python.org](https://python.org) or via your package
manager:

```bash
# macOS (Homebrew)
brew install python@3

# Ubuntu / Debian
sudo apt install python3 python3-pip
```

---

### `ModuleNotFoundError: No module named 'yaml'`

Install PyYAML (or ensure your virtual environment is activated):

```bash
pip install pyyaml
```

---

### `npm: command not found`

Install Node.js from [nodejs.org](https://nodejs.org) or via a version manager:

```bash
# Using nvm (recommended)
nvm install 20
nvm use 20
```

---

### `./tessctl: Permission denied`

Make the script executable:

```bash
chmod +x .tess/bin/tessctl
```

---

### `tessctl doctor` reports drift

`tessctl doctor` checks SHA integrity of the `.tess/core` tree against the
lockfile. If it reports drift, you likely edited framework files directly.
Run `tessctl restore` to re-sync, or `tessctl capture` + `tessctl diff` to
review and commit intentional changes.

---

### `npm test` fails in `create-tess/`

Ensure you ran `npm install` inside `create-tess/` first. If node_modules is
present but tests still fail, check the error output — it may be a Node version
mismatch (Node ≥ 18 required).

---

### Missing `ANTHROPIC_API_KEY`

`tessctl` commands like `init` and `render` are offline and work without an API
key. You only need `ANTHROPIC_API_KEY` set in `.env` when running Tess inside
Claude Code (`claude`). For local development (writing code, running tests),
the key is optional.

---

## 10. Next Steps

- 📖 Read `CONTRIBUTING.md` for the full contribution workflow (quality gates,
  licensing rules, branching strategy)
- 🏗️ Pick an issue from the [open issues](https://github.com/twiss-io/tess-os/issues)
  — look for `good first issue` labels
- 💬 Ask questions in [GitHub Discussions](https://github.com/twiss-io/tess-os/discussions/categories/q-a)
- 📋 Understand the architecture: `conductor/` for doctrine, `agents/` for
  specialist specs, `.tess/core/` for the pristine merge base

---

> 🔧 **Something broken in this guide?** Open an issue or PR — this document
> lives alongside the code and should improve with every contributor who sets
> up the project.
