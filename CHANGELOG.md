# Changelog

All notable changes to Tess OS are documented here. This project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Phase 1 of the Ultimate Framework Plan ("Portable core + render targets",
  Design Decision #1 — "doctrine compiles, never copied"):**
  - **`core/contracts/**` wired into the managed set** — the deferred
    Phase 0 item. `tess.manifest.json`'s `owned_globs` now includes
    `"core/contracts/**"`; a `.tess/core/contracts/**` pristine mirror was
    added with a `tess.lock` entry per file (`status: core-managed`).
    `brief.schema.json` and `verdict.schema.json` carry `tier: security`
    (they are the machine-checkable form of `conductor/dispatch-brief.md`
    and `conductor/verification-routing.md`, both already `tier: security`).
    `tessctl doctor` / `verify` / `lock --check` now cover all five contract
    files; `tessctl validate` is unaffected (still reads the live
    `core/contracts/` path).
  - **The render-target abstraction** (`RenderTarget` / `RENDER_TARGETS` in
    `.tess/bin/tessctl`) — the adapter seam Phase 2 (Codex) and Phase 3
    (Gemini, generic) plug into without touching core loading, the lock
    schema, or the manifest write gate. `ClaudeCodeRenderTarget` (`name =
    "claude-code"`) is the Tier A reference implementation, formalizing the
    engine's existing CLAUDE.md / `.claude/settings.json` / name-bearing
    conductor-file compile step. `tessctl render --target <name>`
    (repeatable) and `tessctl render --list-targets` are new; `tessctl
    render` with no flags is behavior-unchanged (renders every registered
    target — today, just `claude-code`).
  - **`adapters/README.md` + `adapters/claude-code/README.md`** — the
    documented `RenderTarget` interface contract and the Claude Code
    target's artifact map + documented render/restore scope boundary.
  - **`tests/test_render_targets.py`** (10 tests) + **`tests/test_contracts_wiring.py`**
    (9 tests) — determinism (same core → same output, independent of
    process/root), idempotency (repeat render produces identical bytes, no
    drift), manifest write-gate enforcement, and end-to-end doctor/verify/
    lock --check coverage against the real, shipped tree.
- **`core/contracts/`** — Phase 0 of the Ultimate Framework Plan
  ("Contracts-as-code", Design Decision #3): four JSON Schemas
  (`brief.schema.json`, `crew-plan.schema.json`, `verdict.schema.json`,
  `return-manifest.schema.json`), each grounded field-by-field in
  `conductor/dispatch-brief.md`, `conductor/orchestra-model.md` §3.1–§3.2,
  and `conductor/review-output-standards.md` + `conductor/verification-routing.md`
  respectively; `return-manifest` is a new contract this phase introduces
  (no prior doctrine file of its own).
- **`tessctl validate <contract-type> <file>`** — a dependency-free JSON Schema
  (draft-07 subset) validator built into `.tess/bin/tessctl` (no new pip
  dependency). Accepts `.json`, `.yaml`/`.yml`, or `.md` with YAML
  front-matter. Supports `if`/`then`/`else`, `contains`, and cross-file `$ref`
  (used to carry the six-field brief contract verbatim inside a crew-plan
  task, per orchestra-model.md §3.2 rule 1).
- **Schema-miss → `degraded_output` classification** — a contract instance
  that fails validation is classified per `conductor/subagent-failure-protocol.md`
  (`failure_state: degraded`, `cause_class: context-gap`,
  `same_brief_retry_forbidden: true`) and `tessctl validate` exits non-zero,
  so a git hook or CI action can gate on it. Full retry orchestration is
  deferred to Phase 1.
- **`tests/test_contracts_validate.py`** — 36 tests: schema load/valid-instance
  coverage for all four contracts, targeted invalid-instance rejections
  (missing brief field, wrong verdict enum, etc.), the four doctrine-mandated
  conditional rules, the crew-plan/verdict lint checks, cross-file `$ref`
  resolution, the classification shape, instance-file loading, and the CLI.

## [0.1.1] — 2026-06-29

### Added
- **`conductor/release-process.md`** — new core file documenting the signed-release
  channel: trust model (isolated GNUPGHOME, exact fingerprint pinning), maintainer
  release steps (git tag -s → gh release create), and adopter upgrade flow.
  Automatically adopted into `conductor/release-process.md` when existing installs
  run `tess update --ref v0.1.1`.
- **Conductor README framework-maintenance section** — links `release-process.md`
  into the conductor file index.

### Changed
- `tess.lock`: `framework.version` → `0.1.1`; `upstream_ref` → `v0.1.1`.

### Security
- Trust root established in v0.1.0 remains unchanged. The signing key fingerprint
  `EBEABC618C11B6A7340A7D1601DD637667B8CC89` is valid for this release.

---

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
