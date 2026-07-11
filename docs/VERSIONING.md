# Tess OS — Versioning Policy

This document defines what a version number means in this repository, which
file is the source of truth for it, how the framework version relates to the
npm package versions, and what kind of change bumps MAJOR / MINOR / PATCH.
For the mechanics of actually cutting a release (tagging, signing, publishing),
see [`conductor/release-process.md`](../conductor/release-process.md).

---

## There are four version numbers in this repo. One is canonical.

| File | Field | What it versions | Canonical? |
|---|---|---|---|
| `.tess/tess.lock` | `framework.version` / `framework.upstream_ref` | **The framework itself** — doctrine, agents, `tessctl`, the gate spine, the vault. This is what `tess update --ref vX.Y.Z` pulls and what the signed git tag names. | **Yes** |
| `pyproject.toml` | `[project].version` | The Python distribution metadata for the `tessctl` engine (`name = "tess"`). Not published to PyPI today — the engine ships as source inside the git repo/npm scaffold, not as an installable Python package. | Mirrors framework version |
| `package.json` (root) | `.version` | The `tess-os` npm package — intentionally docs/metadata-only (see its own `"//"` comment; the runtime is **not** shipped through this package). Not currently published to npm. | Mirrors framework version |
| `create-tess/package.json` | `.version` | The `create-tess` wizard CLI (`npm create tess`) — the one package that **is** actually published to npm today. | Tracks framework version at release time; see below for why it can drift between releases |

`gui/package.json` (`tess-gui`, the optional local dashboard) versions
independently — it is not part of the framework release and is not published
to npm at all today. It is not part of this policy's synchronization rule.

**The rule:** at the moment a framework version is tagged (the
`conductor/release-process.md` "Maintainer Release Steps"), `tess.lock`,
`pyproject.toml`, and root `package.json` MUST all read the same version
number. `create-tess/package.json` MUST be bumped to the same MAJOR.MINOR
at that point too (see "Independent PATCH releases for `create-tess`" below
for the one case where its PATCH digit is allowed to lead).

### How this repo got out of sync (2026-07-11 correction)

Before this correction, `pyproject.toml` and root `package.json` were both
frozen at the `uv init`/`npm init` placeholder `0.1.0` through **two** tagged
releases (`v0.1.0`, `v0.1.1`) — nobody had bumped them when `v0.1.1` was cut,
because the "Maintainer Release Steps" in `release-process.md` only ever
named `tess.lock`, not the language-ecosystem manifest files. `pyproject.toml`'s
`description` was also still the literal uv scaffold string `"Add your
description here"`. Meanwhile `create-tess/package.json` had already been
bumped to `0.1.1` by the `ac1a8a3` merge-train commit — correctly anticipating
the next release — but that bump was never published to npm (the registry's
`create-tess` `latest` is still `0.1.0`).

This is now fixed as a **metadata correction** (not a new release): `pyproject.toml`
and root `package.json` were bumped to `0.1.1` to match the already-tagged,
already-GitHub-released `v0.1.1`, and the placeholder description was
replaced with an accurate one. `conductor/release-process.md`'s checklist
(below) now names all four files explicitly so this can't silently drift
again.

---

## Semantic Versioning — what bumps what

Tess OS follows [SemVer 2.0.0](https://semver.org/spec/v2.0.0.html). Two
caveats specific to this project:

1. **We are pre-1.0.** Per the SemVer spec itself (§4), a `0.y.z` major
   version means "anything MAY change at any time" and the public API
   "SHOULD NOT be considered stable." We do not invoke that escape hatch
   casually — MINOR and PATCH below are applied with the same discipline a
   post-1.0 project would use — but it is the honest reason a `0.x → 0.x`
   bump can still include a shape change that would be a MAJOR bump after
   `1.0.0`. `1.0.0` itself will be cut deliberately, not by accident of
   reaching a round number — see "What has to be true for 1.0.0" below.
2. **The "public API" for this project is the adopter-facing surface**, not
   every internal Python function: `tessctl`'s CLI subcommands and their
   flags/exit codes, the shape of `core/contracts/*.schema.json`, the
   `tess.lock` schema, the `.tess/core/` file set an install merges against,
   and the doctrine files an adopter's own `CLAUDE.md`/`AGENTS.md` reference
   by path.

| Bump | When |
|---|---|
| **MAJOR** | A breaking change to the adopter-facing surface above — a `tessctl` subcommand removed or its flags reinterpreted incompatibly, a contract schema field removed/retyped, `tess.lock`'s schema version incremented in a way `tessctl update` can't auto-migrate, or a doctrine file renamed/removed that adopters' own configs reference by path. |
| **MINOR** | Backwards-compatible new capability: a new `tessctl` subcommand or flag, a new `RenderTarget` (e.g. the `codex`/`generic` targets currently in `[Unreleased]`), a new contract, a new optional `tess.lock`/`policy.yaml` field, new agents added to the roster. This is also the bump used for a batch of accumulated fixes/features too large to characterize as "just patches" — see the `0.2.0` proposal in `CHANGELOG.md` for a worked example of that judgment call. |
| **PATCH** | Bug fixes, security patches (including dependency bumps like PR #56), documentation, and internal refactors with no adopter-visible surface change. |

### Independent PATCH releases for `create-tess` — already wired

`create-tess` is a thin wizard (first-run prompts + scaffolding) that can
have its own bugs independent of the framework it scaffolds — e.g. a typo in
a prompt, a Node compatibility fix, a broken `npm create tess` install path.
This is not hypothetical: `.github/workflows/publish-npm.yml` already keys
publishing off its **own tag namespace**, `create-tess-v*` — deliberately
separate from the framework's `v*` tags, so a `create-tess-v0.1.2` tag can
never collide with, or be mistaken for, a framework release tag. That
workflow:

- fires on a `create-tess-v*` push tag, or an explicit `workflow_dispatch`
  where the operator types the exact version to publish (a confirmation
  step, not a bare button),
- **fails closed on a version mismatch** — the tag/input must exactly equal
  `create-tess/package.json`'s `version`, or the job errors out before
  publishing anything,
- runs the wizard's own smoke test (`npm test`) as a gate before publish,
- publishes via **npm Trusted Publishing (OIDC)** — no `NPM_TOKEN` secret is
  read or needed; npm auto-generates provenance attestations for a Trusted
  Publishing–based publish.

**This workflow is "wired, not fired"** (its own header comment): until
npm's Trusted Publisher is configured for this exact repo + this exact
workflow file (an npmjs.com package-settings action — Xavier's to do, not a
docs/code change), the final `npm publish` step will fail closed with an
auth error if the workflow is ever triggered. That npm-side configuration is
a **blocking prerequisite** for publishing `create-tess`'s already-staged
local `0.1.1` (see the sync table above) — not something this PR can
complete, since it requires npmjs.com dashboard access.

When a `create-tess`-only fix needs to ship faster than the next framework
release, it MAY get its own PATCH bump and `create-tess-v*` tag
**without** a corresponding framework tag, provided:

- the fix is genuinely wizard-only (no change to what gets scaffolded from
  `.tess/core/`, which is framework surface, not wizard surface), and
- the next framework release still bumps `create-tess` to match its own
  MAJOR.MINOR (i.e. an independent `create-tess` PATCH release is a
  temporary lead, not a permanently separate version line).

An independent `create-tess`-only release has not happened yet in this
repo's history — documented here because the alternative (silently
forbidding it) would block a legitimate fast-follow fix to the
npm-published entry point while a framework release is still being staged.

### What has to be true for `1.0.0`

Not committed to a date. At minimum: the gate spine's residual trust-boundary
items closed (real `verifier_keys`/`signoff_keys` registered — see
`core/policy/policy.yaml`'s own header for the current deliberately-empty
state), `tessctl run` past v1 scope (parallel stage execution, SYNTHESIS
wiring), and at least one more real over-the-wire `tess update` exercised
across a MINOR boundary (today's only proof is the `v0.1.0 → v0.1.1` PATCH
upgrade — see README "Status").

---

## Known gaps (disclosed, not fixed by this policy doc)

- `pyproject.toml`'s `requires-python = ">=3.9"` does not match what the
  committed `uv.lock` can actually resolve (`>=3.13`, per PR #56's own
  flagged note) or what `browser-use` requires (`>=3.11`). Reconciling this
  is a support-policy decision for a maintainer, not something this
  versioning policy resolves on its own.
- `browser-use` (the sole runtime dependency in `pyproject.toml`) is not
  exercised by the test suite or the `tessctl` engine (confirmed in PR #56's
  own description, corroborated by `requirements-dev.txt` listing only
  `pytest`, `pyyaml`, `pyrage`) — it appears to be leftover `uv init`
  scaffolding (the untouched `main.py` — `print("Hello from tess!")` — is
  the same leftover). Whether to remove it is a maintainer call outside this
  documentation task's scope; flagged here so it doesn't read as an
  oversight.
