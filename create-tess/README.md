# create-tess

The gamified first-run wizard for **Tess OS**.

```bash
npm create tess
# or
npx create-tess
```

You name yourself, choose a world (a narrative skin), pick a starter squad of
real agents, name your conductor, choose how that conductor talks to you — and
land inside a working agent OS with a first mission open.

`npm create tess` → keystone render → live agent OS.

## What it does

1. **Stages** the Tess OS template (default: `https://github.com/twiss-io/tess-os.git`)
   into a temp dir so the journey can read the real roster and validate names
   **before the target is ever touched** (cancel = zero state).
2. Runs the **journey** (interactive) or resolves all axes from **flags**
   (non-interactive / CI).
3. On confirm, **promotes** the template into the target (excluding `create-tess/`
   and `.git`), writes `operator/profile.json`, then drives the keystone:
   ```
   tessctl roster apply <path>     # install the starter squad + universal base
   tessctl set-operator <name>     # who the conductor addresses
   tessctl rename <conductor>      # only if conductor != Tess
   tessctl pathway <key>           # the conductor's persona
   tessctl render                  # bake CLAUDE.md + doctrine from operator stubs
   ```
4. Runs `tessctl doctor` + `tessctl verify` and prints the conductor's
   **first-mission greeting in the chosen persona's voice**.

## The five axes

| Axis | Values | `--yes` default |
|---|---|---|
| operator name | free text | `Operator` |
| vibe | `rpg` · `command` · `studio` | `rpg` |
| starter path | `founders` · `builders` · `operators` | `founders` |
| conductor name | free text | `Tess` |
| pathway | `chief-of-staff` · `co-founder` · `strategist` · `guide` · `operator` | `chief-of-staff` |

The **install set is a function of the starter path alone** — vibe only relabels
the same agents in flavour text (the load-bearing invariant, design doc §1.3).

## Non-interactive mode (CI / power users)

```bash
npm create tess my-os -- --yes \
  --operator="Alex" --vibe=studio --path=builders \
  --conductor="Atlas" --pathway=co-founder
```

Flags: `--operator`/`--name`, `--conductor`/`--assistant`, `--vibe`, `--path`,
`--pathway`, `--telegram`, `--target`/`--dir` (or first positional),
`--template-source` (env `TESS_TEMPLATE_SOURCE`), `--force`, `--no-doctor`,
`--no-verify`, `--yes`. A flags-mode validation violation is a hard non-zero
exit (no re-prompt). A non-TTY stdin auto-enables non-interactive mode.

**Defaults are `--yes`-gated.** Per design doc §5.4, defaults apply only with
`--yes`. In non-interactive mode **without** `--yes`, every axis is required
(`--operator`, `--conductor`, `--vibe`, `--path`, `--pathway`) — an unset axis is
a hard error, never a silent default. With `--yes`, any unset axis falls back to
its default (`Operator` / `Tess` / `rpg` / `founders` / `chief-of-staff`).

**`--force` clean-replaces managed dirs.** Forcing a re-scaffold over an existing
install does not merge — it first clears the framework-managed paths
(`.claude/agents`, `.claude/commands`, `conductor/`, `.tess/core`, `CLAUDE.md`)
so stale files (a renamed agent, a removed doctrine file) cannot survive. Your
operator space (`operator/**`) and other non-managed files are preserved.

**`--template-source` safety.** A source that begins with `-` is rejected unless
it is a real local directory, and the git clone uses a `--` end-of-options guard
— a flag-shaped source can never be read as a `git` option.

Point `--template-source` at a local path to test offline:

```bash
node bin/create-tess.mjs ./out --yes --operator=Alex \
  --vibe=studio --path=builders --conductor=Atlas --pathway=co-founder \
  --template-source=/path/to/tess-os
```

## Ordering note

The wizard runs **vibe → operator → starter path → conductor → pathway →
telegram → recap**. This reconciles the task brief with the authoritative design
doc (`kb/wiki/synthesis/2026-06-27-tess-os-onboarding-experience.md`):

- **Vibe first** (design doc §5.2) so it reskins every downstream step,
  including the operator-name prompt.
- **Path before conductor** (task order) so the C3 name-collision check has the
  real install set and the squad reveal lands before the conductor is named.

All seven journey beats from the brief are present; the only design-doc
divergence is the path/conductor pairing, chosen because it makes the C3 check
implementable at conductor-naming time.
