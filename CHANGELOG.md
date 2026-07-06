# Changelog

All notable changes to Tess OS are documented here. This project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Phase 2 of the Ultimate Framework Plan — the gate spine
  (Design Decision #2 "deterministic gate spine at git/CI" + Design
  Decision #6 "verification produces a gateable artifact"):**
  - **`tessctl gate`** — a new top-level subcommand family:
    `pre-commit` (schema+lint validates any staged brief/crew-plan/verdict/
    return-manifest/policy file — reuses `tessctl validate`'s engine
    directly), `pre-push` (**the ship-gate**: classifies every changed path
    against `core/policy/policy.yaml` and refuses the push if a
    `prod_touching`/`client_facing`/`externally_visible` path lacks a
    schema-valid, `disposition: APPROVE` verdict whose `covers_paths` glob
    matches it — reads git's own pre-push stdin protocol, or explicit
    `--base`/`--head`), and `ci` (identical ship-check over an explicit ref
    range — the harness-independent backstop that still catches
    `git push --no-verify`).
  - **`core/contracts/policy.schema.json`** — the plan's own deferred fifth
    contract (§B.2), built now alongside its only consumer. Path-glob rules
    with a `classification` enum (verbatim from `verification-routing.md`'s
    four mandatory-verification triggers) and `require_verdict`; a separate
    `hard_floor_rules[]` for `guardrails.md` Rule 18's four categories
    (credentials, money movement, destructive production data, client-
    external claims) — **never satisfiable by a verifier's verdict alone**.
    `core/policy/policy.yaml` is the shipped instance (deliberately narrow —
    one genuinely-live rule protecting this repo's own tier:security
    doctrine/schema/policy files, one worked placeholder example, matching
    `tess.manifest.json`'s own "hand-authored per spec, not auto-globbed"
    posture). Both wired into the managed set (`tess.manifest.json`
    `owned_globs`, `.tess/core` mirrors, `.tess/tess.lock` entries, tier:
    security) exactly like the original four Phase 0 contracts.
  - **`verdict.schema.json` gains `covers_paths`** (optional, additive — a
    verifier's declared scope as path globs) so a diff-driven gate can match
    a verdict against changed paths. A verdict with no `covers_paths` covers
    nothing (fail-closed by omission, not fail-open) — pre-Phase-2 verdicts
    stay schema-valid but never silently satisfy the ship-gate.
  - **Hard-floor sign-off artifacts** (`.tess/gate/signoffs/<rule-id>.signoff.json`)
    — the mechanical form of guardrails.md Rule 18's "ALWAYS gate on the
    operator's explicit go-ahead": a distinct, small, ad hoc-validated JSON
    shape (`rule_id`, `category`, `authorized_by`, `rationale`,
    `authorized_at`), deliberately NOT a sixth `tessctl validate` contract
    type — never substitutable by a verifier's verdict.
  - **`tessctl gate install-hooks`** — installs/upgrades the pre-commit +
    pre-push git hooks (a second, independently-implemented instance of the
    coexistence pattern `_vault_install_git_hooks` proved: splices ABOVE any
    pre-existing hook — including the vault guard itself — inside a
    containment subshell that BLOCKS on a gate violation and FALLS THROUGH
    on a clean result) and a `workflow_dispatch`-only `.github/workflows/tess-gate.yml`
    CI workflow template (manual-trigger-only by design — see the file's own
    header for why auto-triggering it against a repo's own history before
    that repo has real policy rules + real verdicts would self-gate it on a
    policy nobody has satisfied yet).
  - **Fail-closed throughout**: a failing git command, a missing/invalid
    policy file, or an unreadable verdict all resolve to `blocked: true` —
    ambiguity refuses, it never silently allows.
  - **52 new tests** — `tests/test_policy_contract.py` (14: schema/lint
    coverage for the fifth contract, mirroring `test_contracts_validate.py`'s
    style), `tests/test_gate_spine.py` (21: the ship-check decision engine —
    blocks-with-no-verdict, allows-with-covering-APPROVE, blocks-on-BLOCK/
    HIGH-unaccepted, blocks-on-schema-invalid-contract, policy path
    classification, hard-floor sign-off, fail-closed-on-error, the pre-commit/
    pre-push/ci CLI surfaces), `tests/test_gate_hooks.py` (12: hook install/
    splice/idempotency/coexistence-with-vault, the CI workflow template, and
    real end-to-end `git commit`/`git push` firing against a real bare
    remote — including the documented `--no-verify` bypass + CI-still-blocks
    case), plus 5 new tests extending `tests/test_contracts_wiring.py` for
    `core/policy/**`'s wiring. Full suite: **416 passed** (364 existing +
    52 new), zero regressions. `tessctl doctor` / `verify` / `lock --check`
    all clean against the live working tree.
  - **Scope note (honest re-scope, mirroring the Phase 1 precedent below):**
    this is the enforcement-spine SLICE of Phase 2 only. The Codex adapter
    (`tessctl dispatch --driver codex`) and `tessctl run <plan>` (the
    mechanical conductor loop) remain unbuilt — see
    `docs/ULTIMATE_FRAMEWORK_PLAN.md`'s Phase 2 honest re-scope note. The
    gate spine does not depend on either; it operates on git diffs and
    on-disk contract instances regardless of what produced them.
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
    render` with no flags renders every render target ENABLED for this
    install (today: `claude-code`, the only registered target — see MED-3
    below for per-install enablement).
  - **`adapters/README.md` + `adapters/claude-code/README.md`** — the
    documented `RenderTarget` interface contract and the Claude Code
    target's artifact map + documented render/restore scope boundary.
  - **`tests/test_render_targets.py`** (16 tests — 10 original + 6 added by
    the HIGH-1/LOW-3 fixes below) + **`tests/test_contracts_wiring.py`**
    (9 tests) — determinism (same core → same output, independent of
    process/root), idempotency (repeat render produces identical bytes, no
    drift), manifest write-gate enforcement, and end-to-end doctor/verify/
    lock --check coverage against the real, shipped tree.

### Fixed

- **HIGH-1 (Fable Phase-1 review, PR #36) — the render-target seam is now
  genuinely load-bearing, not "register-and-done".** Fable's adversarial
  review passed the Phase 1 crux (determinism + contracts wiring + tamper
  detection + security-tier all verified) but BLOCKed on this: only
  `cmd_render` consulted the `RENDER_TARGETS` registry — the three
  subsystems that make Decision #1's integrity promise real were Claude-
  hardcoded and bypassed it, so a Phase 2+ target would render on demand but
  silently go STALE on `tessctl update` and be invisible to / false-flagged
  by drift detection. Fixed by extending the `RenderTarget` interface with
  two methods (`expected_live_bytes()`, `render_generated_paths()`) and
  wiring all three subsystems to consult the registry through them:
  - **`render_core_to_live()`** (the function doctor/verify Check B, `diff`,
    `restore`, `capture`, `rollback`, etc. all call to compute "what SHOULD
    be at this live path") now tries every ENABLED target's
    `expected_live_bytes()` before falling back to the generic byte-copy +
    `{{TOKEN}}` substitution path — instead of two special-cased branches
    hardcoded for `CLAUDE.md` / `.claude/settings.json`. Those two special
    cases moved into `ClaudeCodeRenderTarget.expected_live_bytes()`, so this
    is a behavior-preserving refactor for Claude Code and a genuine fix for
    any future target.
  - **`RENDER_GENERATED_LIVE_PATHS`** (the "run `tessctl render`, not
    `tessctl capture`" remedy-routing set doctor/verify/`doctor --fix`
    consult) is no longer a Claude-only frozenset — `render_generated_live_paths(root)`
    now derives it as the union of every ENABLED target's
    `render_generated_paths()`.
  - **`cmd_update`'s Step 7** (and `doctor --fix`'s re-render remedy) now
    call a shared `_render_enabled_targets()` helper that renders every
    ENABLED target, instead of calling the Claude-only `_do_render()`
    directly — so a framework upgrade atomically re-renders every enabled
    harness's artifacts, the actual Decision #1 promise.
  - Proven by a second, non-Claude **mock render target**
    (`tests/test_render_target_seam_is_load_bearing.py`, 9 new tests) whose
    compiled artifact is (a) correctly drift-checked by doctor/verify via
    `expected_live_bytes()` — a naive byte-copy comparison would false-flag
    it as drifted immediately after a correct render, (b) re-rendered by
    `cmd_update`'s Step 7 (exercised through a real signed-fetch update
    cycle, not a stand-in for it), and (c) gated by per-install enablement —
    absent from `render_targets.enabled`, `tessctl render` and `cmd_update`'s
    Step 7 never emit/invoke it, proving a Claude-only install won't
    silently start emitting a future target's artifacts. 6 new tests in
    `tests/test_render_targets.py` cover `ClaudeCodeRenderTarget`'s own
    `expected_live_bytes()` / `render_generated_paths()` implementations and
    the `render()` return-contract (LOW-3, below).
- **MED-3 — per-install render-target enablement.** New
  `tess.manifest.json` key `render_targets.enabled` (default
  `["claude-code"]`); `tessctl render` with no flags and `cmd_update`'s
  Step 7 render only ENABLED targets. `tessctl render --target <name>`
  explicitly bypasses enablement (an operator naming a target by hand is an
  explicit ask, not the silent-default case this guards against).
  `tessctl render --list-targets` now flags which registered targets are
  enabled for this install. This is the mechanism that keeps a Claude-only
  install from emitting e.g. `codex`/`AGENTS.md` the moment a Phase 2+
  target is added to the registry — a target must be both registered AND
  enabled to render by default (also backs the plan's future wizard
  harness-select axis 6, still Phase 2 scope).
- **MED-1 — the `.local.md` shadow-append skip now routes through the
  canonical `is_security_tier()` predicate** instead of a second, independent
  `in SECURITY_TIER_PATHS` membership check inside `render_core_to_live()`.
  `doctor_check_file()` and `cmd_verify`'s per-file loop now pass the real
  `tess.lock` entry attrs through, so a file marked `tier: security` in the
  lock is protected from a `.local.md` shadow-append even if it is not (yet)
  also hardcoded into `SECURITY_TIER_PATHS` — closing a latent doctrine-
  weakening gap before a future security-tier `.md` file is added and
  someone forgets to update both places. Callers without the lock attrs
  handy keep the pre-existing (unchanged) behavior. 2 new tests in
  `tests/test_m2_polish.py` cover the lock-only-tier case (attrs supplied vs.
  not) and the end-to-end `doctor_check_file()` drift-flagging path.
- **LOW-2 — stale `{{TESS_ROOT}}` documentation corrected**
  (`tess.manifest.json`, `adapters/README.md`, `adapters/claude-code/README.md`,
  `.tess/core/MANIFEST.md`). Zero core files ship the literal `{{TESS_ROOT}}`
  template token today — the guard hooks and `settings-core.json` resolve
  their project root at runtime via `$CLAUDE_PROJECT_DIR` (a Claude Code
  env var), not via `tessctl`'s render-time token substitution. The docs
  previously implied the token was in active use for these files. Reworded
  to state accurately why rendered output is byte-identical across
  machines/roots: no absolute path is ever baked in at render time, not "the
  substitution happens to be consistent." The substitution mechanism itself
  is real and tested (`tests/test_render.py`) — it's simply unused by any
  file currently shipped.
- **LOW-3 — the `render()` return contract is now documented**: every
  `RenderTarget.render()` call returns `{"target": <name>, "status":
  "rendered"}` (see `ClaudeCodeRenderTarget.render()`); pinned in the
  `RenderTarget` interface doc block and `adapters/README.md`.
- **MED-2 + LOW-1 — honest re-scope note.** `docs/ULTIMATE_FRAMEWORK_PLAN.md`
  §E.2's Phase 1 roadmap line now carries an explicit delivered-vs-deferred
  callout: this phase shipped the render-target seam + the `claude-code`
  target + the `core/contracts/**` wiring — NOT the `codex`/`gemini`/`generic`
  targets, the `core/doctrine/` extraction, wizard axis 6, or
  `core/contracts/policy.schema.json` (never built; `CONTRACT_SCHEMAS` in
  `.tess/bin/tessctl` only covers brief/crew-plan/verdict/return-manifest).
  Those remain explicit Phase 2+ scope.
- **Acknowledged scope boundary (not fixed this pass):** `cmd_init`,
  `cmd_restore`, `cmd_identity`, `cmd_rename`, `cmd_set_operator`, and
  `cmd_pathway` still call the Claude-only `_do_render()` directly after
  scaffolding/identity changes, rather than the registry-driven
  `_render_enabled_targets()`. These are operator-initiated identity
  mutations (today inherently Claude-Code-shaped — "the conductor's name in
  CLAUDE.md"), not part of the three subsystems Fable's review named
  (doctor/verify Check B, the render-generated classification, `cmd_update`'s
  Step 7) — the "silently stale on `tessctl update`" risk HIGH-1 is about
  doesn't apply to a command the operator is explicitly running right now.
  Left out of this pass deliberately rather than silently: a Phase 2+ target
  with its own name-bearing artifacts will need an equivalent identity-
  re-render step, and these six call sites are exactly where to wire it once
  that target's own token/identity model exists to design against.
- Full suite: **364 passed** (347 existing + 17 new: 6 in
  `tests/test_render_targets.py`, 2 in `tests/test_m2_polish.py`, 9 in the
  new `tests/test_render_target_seam_is_load_bearing.py`), zero regressions.
  `tessctl doctor` / `tessctl verify` / `tessctl lock --check` all clean
  against the live working tree (`.tess/core/MANIFEST.md`'s `base_sha` was
  re-pinned via `tessctl lock --regen --yes` after the LOW-2 doc fix there —
  the one deliberate, reviewed core-content change this pass made).
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
