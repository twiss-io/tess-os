# create-tess

The guided local setup wizard for **Tess OS**, a signed, fail-closed review gate
and model-neutral governance harness for coding-agent output.

```bash
npm create tess
# or
npx create-tess
```

The wizard asks a few friendly questions, stages a local Tess OS instance, and
opens a first mission. Narrative themes and starter squads personalize the
local experience; they do not change the gate's trust model or certify an agent
platform.

> **Technology preview:** `create-tess` scaffolds a local instance. It does not
> activate production trust, configure protected branches, or provision Tess
> Cloud or Tess Vault. The published package may lag repository `main`.

## What you get

- a local Tess OS repository with an operator profile;
- a selected starter roster and conductor persona;
- rendered Claude Code project files;
- an optional Telegram preference;
- local Git gate hooks when Git is available; and
- `tessctl doctor` and `tessctl verify` results at the end of setup.

The current default is Claude Code-oriented. Codex and generic `AGENTS.md`
targets exist in the repository but require explicit post-install opt-in. Read
the [platform support guide](https://github.com/twiss-io/tess-os/blob/main/docs/PLATFORM_SUPPORT.md)
before choosing a host.

## What setup asks

| Choice | Options | Automatic default with `--yes` |
|---|---|---|
| Your name | free text | `Operator` |
| Style | `rpg`, `command`, or `studio` | `rpg` |
| Starter path | `founders`, `builders`, or `operators` | `founders` |
| Conductor name | free text | `Tess` |
| Conductor pathway | `chief-of-staff`, `co-founder`, `strategist`, `guide`, or `operator` | `chief-of-staff` |

Changing the style changes the wording, not the installed security controls.
The starter path determines the starter roster.

## What happens during setup

1. The wizard stages the Tess OS template in a temporary directory and checks
   the answers before touching the destination.
2. After confirmation, it copies the template, writes
   `operator/profile.json`, applies the roster and persona, and renders the
   local files.
3. Unless disabled, it initializes Git when needed and installs local gate
   hooks plus the `tess-gate.yml` workflow.
4. It runs read-only health and integrity checks and prints the first-mission
   greeting.

Cancelling before confirmation leaves the destination untouched. If a
best-effort Git activation step cannot complete, the wizard reports that
separately instead of pretending the repository is protected.

## A blocked governed push can be correct

Fresh policy contains no authorized verifier or sign-off keys. A governed
change can therefore stop with:

```text
no covering APPROVE verdict found
```

That is a fail-closed result, not a wizard error. Do not create, register, or
self-sign a key or verdict merely to make the message disappear. Do not bypass
or disable a hook and then present the change as approved.

Production activation requires a designated human owner's external custody
decision (Xavier for this repository) plus independently required Git checks.
The wizard intentionally does not combine the proposer and reviewer roles.

For local experimentation, use an isolated, non-production repository. For a
governed or production-bound change, read
[trust setup](https://github.com/twiss-io/tess-os/blob/main/docs/TRUST_SETUP.md)
and the
[gate operation guide](https://github.com/twiss-io/tess-os/blob/main/docs/GATE_QUICKSTART.md).

## Automated setup

For CI or repeatable local setup:

```bash
npm create tess my-os -- --yes \
  --operator="Alex" --vibe=studio --path=builders \
  --conductor="Atlas" --pathway=co-founder
```

Without `--yes`, every setup choice is required in non-interactive mode. A
missing or invalid choice exits non-zero; the wizard does not silently invent
an answer.

Available flags:

- `--operator` or `--name`
- `--conductor` or `--assistant`
- `--vibe`
- `--path`
- `--pathway`
- `--telegram`
- `--target` or `--dir` (the first positional argument also works)
- `--template-source` or the `TESS_TEMPLATE_SOURCE` environment variable
- `--force`
- `--no-doctor`
- `--no-verify`
- `--no-git-init`
- `--no-gate-hooks`
- `--yes`

Use a local template source for offline development:

```bash
node bin/create-tess.mjs ./out --yes --operator=Alex \
  --vibe=studio --path=builders --conductor=Atlas --pathway=co-founder \
  --template-source=/path/to/tess-os
```

## Safety details

- `--force` clean-replaces framework-managed directories so stale managed
  files cannot survive. Operator files and unrelated files are preserved.
- A flag-shaped name is rejected.
- A template source beginning with `-` is rejected unless it is a real local
  directory, and the Git invocation uses an end-of-options guard.
- Secrets, runtime state, caches, generated evidence, and repository history
  are excluded from the produced instance.
- `--no-git-init` and `--no-gate-hooks` skip local activation and print the
  remaining manual steps; they do not claim equivalent protection.

## What the wizard does not provide

- native support or feature parity for every model host;
- a verifier, sign-off authority, first trust anchor, or required Git check;
- Tess Cloud, Tess Vault, or a hosted control plane;
- advanced shared memory or a parallel subagent scheduler; or
- credentials for an agent.

For source behavior and production limits, read the
[Tess OS README](https://github.com/twiss-io/tess-os#readme) and
[support status](https://github.com/twiss-io/tess-os/blob/main/docs/STATUS.md).
