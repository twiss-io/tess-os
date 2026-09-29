# Tess OS

[![License: Apache-2.0](https://img.shields.io/github/license/twiss-io/tess-os)](LICENSE)
[![create-tess on npm](https://img.shields.io/npm/v/create-tess?label=create-tess)](https://www.npmjs.com/package/create-tess)
[![Latest release](https://img.shields.io/github/v/release/twiss-io/tess-os)](https://github.com/twiss-io/tess-os/releases)
[![CI](https://img.shields.io/github/actions/workflow/status/twiss-io/tess-os/ci.yml?label=CI)](https://github.com/twiss-io/tess-os/actions/workflows/ci.yml)

Tess OS gives you your own AI assistant and a small team of AI specialists
that work inside a folder on your computer. You name the assistant, tell it
about yourself or your business once, and it remembers: everything it learns
is saved as plain files in that folder, with a history of every change, not
in someone else's cloud. It runs inside an AI app you already use, Claude Code
or Codex, and it checks its own work before anything important goes out. It
does not make the AI model itself smarter; it gives it a memory, a team and a
routine.

## What you need

- **macOS or Linux; Windows via WSL.**
- **Node.js 18 or newer** — [download](https://nodejs.org/en/download). This
  runs the one-time setup.
- **git** — keeps the history of your folder. On a Mac, if it is missing, open
  Terminal, type `xcode-select --install` and follow the prompt; elsewhere,
  [download git](https://git-scm.com/downloads).
- **Python 3.9 or newer** — macOS already has it (the same
  `xcode-select --install` step above sets it up if your Mac asks); on Windows
  or Linux, [download Python](https://www.python.org/downloads/).
- **An AI app:** [Claude Code](https://docs.claude.com/en/docs/claude-code/overview) or
  [Codex](https://github.com/openai/codex), signed in with your own
  account. Tess OS needs no API keys of its own.

## Quickstart

1. **Run one command** in a terminal:

   ```bash
   npm create tess@latest my-os
   ```

2. **Answer the questions.** Your name, your assistant's name, and how you
   want it to work with you. Enter keeps the suggested answer. The setup
   checks every file and ends with a screen that says what to do next. If
   something is missing (git or Python), it says so and installs nothing.

3. **Open the folder `my-os` in Claude Code or Codex and say hi.** Your
   assistant takes it from there: tell it what you are working on, or give it
   a first task. The first time, Claude Code asks whether you trust the
   folder: say yes. In Codex, trust the folder and approve Tess's hooks when
   asked (or type `/hooks`); Tess's safety checks run in Codex only after
   that, and Codex asks again after each Tess update.

To check your install later, run `./tessctl doctor` inside the folder
("All good" means nothing is broken). `./tessctl help` lists every command.

## Updating

Inside your folder:

```bash
./tessctl self-update --ref v1.0.0
./tessctl update --ref v1.0.0
```

Updates only come from a release signed by the Tess OS release key, and are
checked on your computer before anything changes. Changes you made to your
own files are kept.

## More detail

- **How it works, its limits, runtimes and the roster:**
  [Technical overview](docs/TECHNICAL_OVERVIEW.md).
- **Security, the review gate and the release trust model:**
  [SECURITY.md](SECURITY.md). Using Tess OS to protect real production code
  needs extra setup first; start there.
- **What is supported today:** [Support and status](docs/STATUS.md).
- **Working on Tess OS itself:**
  [Local development quickstart](docs/LOCAL_DEV_QUICKSTART.md) and
  [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache-2.0. Forks must follow the [trademark policy](TRADEMARK.md).
