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

1. **Open a terminal.** A terminal is a window where you type commands.
   - **Mac:** press Command (⌘) and Space, type `Terminal`, press Return.
   - **Windows:** Tess OS is tested on macOS and Linux only. On Windows, use
     WSL (Windows Subsystem for Linux) and type the commands below in its
     terminal (for example "Ubuntu" in the Start menu).
   - **Linux:** open your Terminal app.

2. **Run one command.** Type or paste this and press Return:

   ```bash
   npm create tess@latest my-os
   ```

   `my-os` is the name of the folder it makes; you can pick another name.

3. **Answer the questions.** Your name first: type it and press Return (there
   is no default, so it waits for you). Then your assistant's name (Return
   keeps "Tess"), how it should talk to you, and who it is for. The setup
   checks every file and ends with a screen that says what to do next. If
   something is missing (git or Python), it says so and installs nothing.

4. **Start your assistant in that folder.** In the same terminal, type:

   ```bash
   cd my-os
   claude
   ```

   `cd my-os` moves into the folder; `claude` starts Claude Code. If you use
   Codex, type `codex` instead of `claude`. You can also open the folder
   `my-os` in Claude Code or Codex and say hi from the app. Your assistant
   takes it from there: tell it what you are working on, or give it a first
   task. The first time, Claude Code asks whether you trust the folder: say
   yes. **In Codex this step is required:** trust the folder, then type
   `/hooks` and approve Tess's hooks. Tess's safety checks run in Codex only
   after that, and Codex asks again after each Tess update. Until you do,
   Tess starts its first reply with a warning that the checks are OFF.

To check your install later, run `./tessctl doctor` inside the folder
("All good" means nothing is broken). `./tessctl help` lists the everyday
commands. If Tess ever stops a push, see
[When Tess stops a push](docs/WHEN_TESS_STOPS_A_PUSH.md).

## Updating

Inside your folder:

```bash
./tessctl self-update --ref v1.0.0
./tessctl update --ref v1.0.0
```

`--ref v1.0.0` names the version to move to; use the version number from the
release notes. `self-update` first updates the `tessctl` tool itself, then
`update` updates the rest of Tess.

After an update, Codex users type `/hooks` in Codex once more and approve
Tess's hooks again. Hooks are the small checks Tess runs automatically before
and after each action your assistant takes (for example, stopping a secret
from being saved); Codex turns them off after any change until you approve
them. Claude Code needs nothing extra.

Updates only come from a release signed by the Tess OS release key, and are
checked on your computer before anything changes. Changes you made to your
own files are kept.

If a new version changes Tess's safety rules (which changes need a review
before they can be pushed), the update stops before changing anything and
lists each rule change in plain words. To accept, run the update yourself in
a terminal and type `accept <version>` when asked (for example
`accept v1.1.0`), then commit the update together with the file it names in
`.tess/gate/policy-approvals/`. To wait instead, press Enter: you stay on
your current version, which keeps working. Your AI assistant cannot give
this approval for you; it has to be typed in a terminal.

The approval is signed with a key kept on your computer, outside the project
(`~/.config/tess/operator/key`, created the first time you accept). A copied
or hand-written approval file does not count, so a collaborator or a CI job
that can push to your repository cannot approve rule changes for you. The
limit: a program running as you on your own computer can read that key, just
as it could run `tessctl` as you. Because the key never leaves your
computer, a CI check cannot confirm the approval; push the update from the
computer where you typed `accept`.

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
