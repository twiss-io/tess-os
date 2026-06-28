# Changelog

All notable changes to Tess OS are documented here. This project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-06-28

Initial public foundation.

### Added
- **Governed agent organization** — the full conductor doctrine, 144 specialist
  agents (141 specified, 3 stubs) across guilds, six outcome orchestrators, dependency gates,
  the six-field dispatch-brief contract, mandatory verification routing, and the
  typed retry protocol (max 3 attempts, then escalate).
- **In-place upgrade engine (`tessctl`)** — pristine merge base (`.tess/core/`),
  per-file `tess.lock` status, snapshot-first 3-way merge, `doctor` hard-gate,
  conflict-halts-the-update, security-tier quarantine, hash-based drift detection,
  and atomic staging swap.
- **`create-tess` wizard** — the gamified `npm create tess` first-run experience
  (name / vibe / squad / conductor / pathway), staged into a temp dir first so a
  cancel leaves zero state.
- **Vault subsystem (`tessctl vault`)** — age/X25519 encrypted-at-rest secret
  store, `vault://` references, JIT `exec` injection, and pre-commit/pre-push
  guards as a leak backstop.
- **Roster management** — `tessctl recruit` / `roster apply` / `bench` to grow or
  focus the active crew without losing the benched specialists.
- **Project scaffold** — `clients/_template/`, a knowledge-base scaffold (`kb/`),
  guard hooks, a Claude Code permissions baseline, and a wired command system.
- **Launch / community & legal scaffolding** — `TRADEMARK.md` (name/marks policy,
  nominative-use carve-out), `SECURITY.md` (private responsible-disclosure +
  vault threat model), `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1), `CLA.md`
  (open-core CLA policy stub), GitHub issue/PR templates, and README sections for
  Community/Get help, Attribution, the official repository, and the open-core
  model. `TRADEMARK.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`,
  and `CLA.md` now ship in the npm package.

### Licensing
- Licensed under **Apache-2.0** (previously MIT during pre-release).
- Added [NOTICE](NOTICE) crediting third-party runtime dependencies (`pyrage`,
  `age`/`rage`, PyYAML, `@clack/prompts`, `picocolors`) and naming prior art that
  informed the vault's design (OpenBao / SOPS — MPL-2.0; Infisical — MIT;
  HashiCorp Vault — BUSL-1.1, concepts only, no code taken).

### Security
- **Hook coexistence (Cyra Finding 9, MEDIUM)** — `tessctl vault init` now splices
  its git guard *above* any pre-existing pre-commit/pre-push hook inside a
  containment subshell. A violation still blocks; a clean result falls through so
  the adopter's own linter / secret-scanner is never silently neutered. A clear
  notice is printed when a pre-existing hook is detected, and the legacy form is
  re-spliced on upgrade.

### Known limitations
- The over-the-wire framework **FETCH** and `tessctl self-update` are in progress.
- A real **two-tag upgrade has not yet been exercised end-to-end** on a live
  update; the upgrade engine is architecturally complete but unproven on a real
  over-the-wire update.
- The vault is a local-first store plus a backstop — a risk reducer, not a
  guarantee that a secret "cannot leak."
