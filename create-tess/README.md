# create-tess

The gamified first-run wizard for **Tess OS**.

```bash
npm create tess
# or
npx create-tess
```

You name yourself, choose a world (a narrative skin), pick a starter squad of
real agents, name your conductor, choose how that conductor talks to you — and
land inside a locally scaffolded Tess OS instance with a first mission open.

`npm create tess` → keystone render → live agent OS.

> **Status:** `create-tess` is a local scaffolding wizard, not production
> onboarding for the Tess OS review gate. The published package currently lags
> repository `main`; do not use it to claim a production-protected workflow.
> Its rendered default is Claude Code-oriented. Codex and generic targets need
> explicit post-install opt-in and remain subject to the support limits in
> [the root README](../README.md#supported-surfaces).

## What it does

1. **Stages** the Tess OS template into a temp dir so the journey can read the
   real roster and validate names **before the target is ever touched**
   (cancel = zero state). By default this is a local copy of the template
   **bundled inside the `create-tess` package itself** — no network, no
   `git clone`. Pass `--template-source <git-url>` to opt into fetching from
   git instead (see "Non-interactive mode" below).
2. Runs the **journey** (interactive) or resolves all axes from **flags**
   (non-interactive / CI).
3. On confirm, **promotes** the template into the target (excluding `create-tess/`
   and the template's own `.git`), writes `operator/profile.json`, then drives
   the keystone:
   ```
   tessctl roster apply <path>     # install the starter squad + universal base
   tessctl set-operator <name>     # who the conductor addresses
   tessctl rename <conductor>      # only if conductor != Tess
   tessctl pathway <key>           # the conductor's persona
   tessctl render                  # bake CLAUDE.md + doctrine from operator stubs
   ```
4. **Installs local gate hooks** — `git init` (a fresh, history-less repo on branch
   `main`; skipped if the target is already inside a git work tree) followed
   by `tessctl gate install-hooks` (live pre-commit/pre-push hooks + the
   `tess-gate.yml` CI workflow). Hooks provide local feedback only. They do not
   create a verifier, establish the trust root, or make GitHub checks required.
   Best-effort: if this step cannot complete (for example, Git is unavailable),
   the wizard does not roll back an otherwise-good local instance. Opt out with
   `--no-git-init` / `--no-gate-hooks` when you will configure a non-production
   repository separately.
5. Runs `tessctl doctor` + `tessctl verify` and prints the conductor's
   **first-mission greeting in the chosen persona's voice**.

## Heads up: a blocked governed push is expected

A fresh instance ships with intentionally empty verifier and sign-off
registries. A governed change can therefore block with **"no covering APPROVE
verdict found"**. That is a correct fail-closed result, not a wizard error.

Do not generate, register, or self-sign a key or verdict to make the gate pass.
Do not use a bypass to present a protected change as approved. The initial
trust anchor is a human-owned Xavier custody ceremony, and GitHub required-check
enforcement remains a separate production prerequisite.

For experimentation, keep the scaffold in an isolated, non-production
repository. For any governed or production-bound change, stop and follow the
[gate custody boundary](../docs/GATE_QUICKSTART.md).

## What this wizard does not configure

- It does not select or certify a coding-agent platform. The default rendered
  workflow is Claude Code-oriented.
- It does not configure Codex/native-event parity, generic-host feature parity,
  Perplexity, Gemini, or every other coding-agent tool.
- It does not create a production trust root, verifier/sign-off authority, or
  required GitHub check.
- It does not provision Tess Cloud, Tess Vault, advanced shared memory, or
  credentials for an agent.

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
`--template-source` (env `TESS_TEMPLATE_SOURCE`), `--template-ref` (env
`TESS_TEMPLATE_REF`), `--force`, `--no-doctor`,
`--no-verify`, `--no-git-init`, `--no-gate-hooks`, `--yes`. A flags-mode
validation violation is a hard non-zero exit (no re-prompt). A non-TTY stdin
auto-enables non-interactive mode.

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

**The default source is bundled, not a git clone (P0 G-01 BUNDLE fix).**
Without `--template-source`, the wizard scaffolds from a local copy of the
template shipped INSIDE this npm package (`create-tess/template/`, generated
by `npm run build-template` — see the Release section below). This is what
makes a given `create-tess` version fully reproducible AND network-free: the
same published version always scaffolds from the exact same, already-CI-
passed bytes, with no clone, no tag, and no dependency on GitHub being
reachable. Pass `--template-source <git-url>` / set `TESS_TEMPLATE_SOURCE` to
explicitly opt into a live git fetch instead (your own fork, a mirror, a
specific upstream commit); that clone is pinned to `DEFAULT_TEMPLATE_REF`
(`src/scaffold.js`, in create-tess's own `create-tess-v*` tag namespace)
unless you pass `--template-ref`/`TESS_TEMPLATE_REF` yourself — note that tag
has historically not always been cut at release time (see `scaffold.js`'s
header comment), so an opt-in git fetch without an explicit `--template-ref`
can fail; the bundled default is unaffected either way.

Point `--template-source` at a local path to test a git-style fetch, or to
scaffold from a different tree entirely:

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

## Release (maintainers — Xavier-owned; never automated)

1. Bump `create-tess/package.json`'s `version` (and re-run `npm install` in
   `create-tess/` so `package-lock.json` picks it up). Confirm `npm test` is
   green. **The bundled template does not need a manual rebuild step here** —
   `npm run build-template` (`scripts/build-template.mjs`) runs automatically
   via the `prepack` lifecycle hook on every `npm pack`/`npm publish`, so the
   packed tarball's `template/` always reflects the exact tree being released.
   Run it by hand only to inspect the bundle locally (`npm run build-template`
   then `git status` under `create-tess/template/` to see what changed) or
   to regenerate the committed copy for review in a PR.
2. Cut and push the tag (create-tess's OWN namespace, `create-tess-v*` —
   never the framework's own `v*` tags):
   ```bash
   git tag create-tess-vX.Y.Z && git push origin create-tess-vX.Y.Z
   ```
   This fires `.github/workflows/publish-npm.yml`, which gates on the tag
   matching `package.json`'s version, runs the full test suite again, then
   publishes via npm Trusted Publishing (OIDC — no token). If npm's Trusted
   Publisher isn't configured yet for this exact repo + workflow
   (npmjs.com package settings), that final step fails closed with an auth
   error until it is — see the workflow file's header for the current state.
   **Do this step even if you expect to fall back to (3) below** — every
   published version through 0.1.3 was actually shipped via the manual
   fallback ALONE, silently skipping this tag cut each time; that gap is
   exactly what left `DEFAULT_TEMPLATE_REF` (the old git-clone pin, still
   used by the explicit `--template-source` git opt-in) pointing at a tag
   that was never cut, across three release cycles (P0 G-01). The 0.1.4
   BUNDLE fix (`create-tess/src/scaffold.js`) removes this dependency from
   the DEFAULT flow entirely, but the opt-in git path still relies on it.
3. **Manual fallback** (if Trusted Publishing isn't live yet): from
   `create-tess/`, checked out at the tag, run `npm publish --access public`
   as an npm-authenticated maintainer. `prepack` still regenerates
   `template/` first, same as the CI path.
4. **Deprecating a bad published version** (e.g. one later found to leak
   secrets): `npm deprecate create-tess@X.Y.Z "reason — upgrade to X.Y.Z+"`.
