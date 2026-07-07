# Changelog

All notable changes to Tess OS are documented here. This project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **`codex` + `generic` render targets — AGENTS.md emission (Goal #4:
  "plug-and-play for Codex and frontier models"), proving the Phase 1
  RenderTarget seam is genuinely load-bearing for a second and third real
  target, not just a mock.** Tess OS's render-target layer had exactly one
  target (`claude-code`); AGENTS.md is the Linux-Foundation-stewarded
  standard read natively by Codex, Cursor, Copilot, Gemini CLI, Zed, and
  Devin (60,000+ repos) — GitHub Spec Kit supports 30+ agents, Tess OS
  supported one.
  - `CodexRenderTarget` (Tier B) and `GenericRenderTarget` (Tier C) in
    `.tess/bin/tessctl`, registered in `RENDER_TARGETS` alongside
    `claude-code`. `tessctl render --target codex` emits `AGENTS.md`
    (≤2,000 words, doctrine-linked, Rule Zero + the Doctrine
    Gates/Verification/Retries/Hard-Floor sections reused VERBATIM from the
    same core fragments CLAUDE.md composes — zero duplicated doctrine text),
    `.codex/prompts/*.md` (mirroring the 26 command bodies into Codex's
    native custom-prompt convention), and a `.codex/config.toml` fragment
    (`approval_policy = "on-request"`, `sandbox_mode = "workspace-write"`,
    verified against Codex's real config precedence/trust model).
    `tessctl render --target generic` emits the SAME `AGENTS.md` (see
    `render_agents_md()`'s docstring — harness-neutral by design, no
    ordering hazard if both targets are ever enabled at once) plus a plain
    `prompts/*.md` mirror.
  - New shared core fragment `.tess/core/templates/claude-md/hard-floor.md`,
    extracted from CLAUDE.md.tpl's previously-inline "Doctrine Gates" /
    "Verification, Retries, and the Hard Floor" sections (byte-identical
    CLAUDE.md output verified before/after) — now genuinely reused by BOTH
    CLAUDE.md and AGENTS.md via a new `{{CORE_HARD_FLOOR}}` token.
  - `tess.manifest.json`'s `owned_globs` extended with `AGENTS.md`,
    `.codex/prompts/**`, `.codex/config.toml`, `prompts/**`. Neither target
    is in `render_targets.enabled` by default (registered-but-off — the
    future harness-select wizard axis, not a hardcoded global default, is
    meant to make this call per-install; adopt today via
    `tessctl render --target codex` / `--target generic`, or add the name
    yourself).
  - New `_check_untracked_render_generated()` doctor/verify/`lock --check`
    pass: `.codex/prompts/*.md` / `prompts/*.md` mirror `.tess/core/commands/*.md`
    bodies that are ALREADY tess.lock-tracked under a different live_path
    (`.claude/commands/*.md`) — the lock schema has no way to give a second
    live destination to an already-tracked core_key, so this new pass
    drift-checks those paths independently (a not-yet-rendered path is
    tolerated, not flagged; an existing-but-hand-edited path IS flagged,
    remedy `tessctl render`). Verified NOT to regress `claude-code`'s own
    (fully lock-tracked) artifacts.
  - `adapters/codex/README.md`, `adapters/generic/README.md` — full artifact
    maps, matching `adapters/claude-code/README.md`'s existing format;
    `adapters/README.md` updated (shipped-targets list, added step 7 to
    "Adding a target", fixed a stale `~/.codex/prompts` reference).
  - Tests: `tests/test_render_targets_codex_generic.py` (25 new tests —
    registry/interface shape, AGENTS.md shared-bytes proof, expected_live_bytes
    parity, CLI render for both targets, determinism, idempotency, write-gate
    enforcement, the untracked-render-generated pass in all three call sites,
    and a real signed-fetch `tessctl update` cycle proving a doctrine edit
    re-propagates into AGENTS.md). `tests/test_render_targets.py` updated for
    the 3-target registry (was asserting exactly one target; `"codex"` is no
    longer a valid "unknown target" fixture). Full suite: 479 → 504, all
    green.

- **`tessctl verdict keygen` — turnkey verifier onboarding, closing the
  "cannot turn the gate on without manual GPG surgery" adoption gap.**
  `core/policy/policy.yaml` ships `verifier_keys: {}` deliberately empty —
  honest, but it left a fresh adopter with no mechanical path from "I want a
  real verifier" to a registered signing key short of hand-running
  `gpg --full-gen-key`/`gpg --export` and editing TWO copies of
  `policy.yaml` (the live one and the `.tess/core` pristine mirror) without
  tripping `doctor`/`verify`/`lock --check`. `tessctl verdict keygen
  --verifier <Name>` does the whole sequence in one command:
  - Generates a fresh, sign-only (no encrypt-capability), no-passphrase-by-
    default local GPG identity for the named verifier (RSA-4096; `--gnupg-
    home <PATH>` for an explicit/test keyring, ambient keyring by default).
    tessctl never stores, backs up, or transmits the resulting PRIVATE key —
    same custody posture as the release-signing key.
  - Exports the PUBLIC half to `.tess/keys/verifiers/<name>.asc`.
  - Registers `{fingerprint, public_key_file}` under
    `policy.verifier_keys.<Name>` in BOTH `core/policy/policy.yaml` (live)
    and `.tess/core/policy/policy.yaml` (the pristine core mirror) via a new
    anchor-based, **comment-preserving** text patch
    (`_policy_yaml_upsert_verifier_key`) — a plain `yaml.safe_load` +
    `yaml.safe_dump` round-trip would silently destroy `policy.yaml`'s own
    extensive header/rule documentation, so this is a targeted insert/replace
    on the `verifier_keys:` block only, leaving every other line untouched.
  - Re-pins ONLY the one `tess.lock` entry this change touches, via a new
    scoped `only=` mode on the shared re-pin helper behind both
    `tessctl lock --regen` and `keygen` (see "Fixed" below) — `doctor`/
    `verify`/`lock --check` are clean immediately afterward, every time.
  - Validates the verifier name against the same six-name enum
    `_lint_policy` already enforces, and refuses (fail-loud) BEFORE writing
    anything if the patched policy fails its own schema/lint or a
    core/live `policy.yaml` drift already exists.
  - Idempotent: refuses to clobber an existing public-key file or policy
    registration for that verifier without `--force` (which generates a NEW
    keypair and REPLACES both — a manual key rotation, automated).
  - `gpg` missing from PATH is a clear, fail-closed preflight error, not a
    raw traceback.
- **`docs/GATE_QUICKSTART.md`** — a copy-paste-able, end-to-end walkthrough
  (`tessctl init` → `verdict keygen` → add a real `require_verdict` rule →
  `gate install-hooks` → cover the framework's OWN pre-existing
  `tess-os-security-tier-doctrine` surface, since it is genuinely live in
  this repo from minute one, not a placeholder — the "bootstrap warning"
  `conductor/verdict-signing.md` already disclosed, now shown end to end →
  an uncovered `src/prod/**` change BLOCKED at `git push` → the same change,
  signed, CLEARED). Every command is runnable verbatim against a local
  scratch bare remote; a new doc-test (`test_gate_quickstart_doc_runs_
  verbatim_end_to_end`) extracts the doc's own fenced script and runs it,
  unmodified, proving the walkthrough is truthful command-for-command, not
  just a hand-written mirror of what it claims.
- **19 new tests** — `tests/test_verdict_keygen.py` (16: the comment-
  preserving text patcher, unit-level; the CLI's generate/register/re-pin
  path with doctor/verify/lock-check asserted clean; idempotent refusal and
  `--force` rotation; unknown-verifier-name and missing-`gpg` fail-closed
  paths; core/live drift refused before any write; JSON policy instance and
  missing-policy-instance refusals; a keygen-GENERATED key actually clearing
  `tessctl gate ci` when properly signed, a wrong-key signature and a
  post-signing tamper still blocking it; the quickstart doc-test), plus
  `tests/test_lock.py` (3: `lock --regen --only` scopes to the named
  entry/entries by core_key or live_path, leaves every other entry
  untouched — proving a scoped regen can never silently bless an unrelated
  tamper — and reproduces the exact prior all-entries behavior when `--only`
  is omitted). Full suite: **479 passed** (460 existing + 19 new), zero
  regressions. `tessctl doctor` / `verify` / `lock --check` all clean
  against the live working tree (`conductor/verdict-signing.md`
  [`tier: normal`] — updated with the turnkey onboarding path — is the one
  core-managed file this round touches; re-baselined via the new scoped
  `tessctl lock --regen --only conductor/verdict-signing.md --yes`).

### Fixed
- **`tessctl lock --regen` gains a scoped `--only <core-key-or-live-path>`
  mode** (repeatable), refactoring the re-pin logic into a shared
  `_lock_regen_core(root, only=...)` helper. Motivation: the unscoped
  `--regen` re-baselines EVERY lock entry's `base_sha` to whatever core is
  currently on disk — correct for a genuine full re-baseline, but wrong for
  a narrow command like `verdict keygen` that only ever writes ONE core file
  it just produced itself; calling the unscoped form there would silently
  "bless" any OTHER file's unrelated drift/tamper as a side effect, exactly
  what `--regen`'s own warning already cautions against. `only=None`
  (the default) reproduces the prior all-entries behavior byte-for-byte —
  zero behavior change for existing callers/tests.

### Added
- **Phase 2b — gate spine hardening: verdict signing + CI auto-enforce**
  (closes the two MORE-SECURE fixes flagged as the main residual by Fable's
  Phase 2 adversarial review — "verdict + sign-off files are committer-
  authored with NO signing" and "the CI workflow is `workflow_dispatch`-only
  — advisory, not auto-enforcing"):
  - **Verdict signing** — a covering verdict must now carry a `signature`
    (`verdict.schema.json`'s new, optional `$defs.VerdictSignature`: a GPG
    detached signature over the verdict's canonical content —
    `verdict_canonical_bytes()`, compact key-sorted JSON minus the
    `signature` key itself) that verifies against the registered public key
    for its claimed `verifier` in `policy.schema.json`'s new
    `policy.verifier_keys` map (the allowed-key set). Reuses the repo's
    existing keystone signed-update primitives (`_parse_gpg_fingerprint`,
    the isolated-GNUPGHOME-per-check pattern, exact 40-hex fingerprint
    equality) rather than inventing a new scheme — see
    `conductor/verdict-signing.md` for the full trust model. Fail-closed,
    same "optional at schema, functionally required to cover anything"
    posture already established for `covers_paths`/`artifact_hashes`: an
    unsigned verdict, a malformed signature block, a signature from an
    unregistered verifier, a signature made by the wrong key, or a verdict
    edited after signing (tamper — caught via `signed_content_sha256`
    mismatch) all resolve to "does not cover this path," never a silent
    pass. Signing ties to `allowed_verifiers`: a genuinely valid signature
    from a real, registered verifier who is simply not permitted for the
    matched rule still does not clear it.
  - **`tessctl verdict sign`/`verdict verify`** — new subcommands. `sign`
    produces the `signature` block for a verdict file (preserving its
    `.json`/`.yaml`/`.md`-front-matter format) using a local GPG identity
    (`--key-id`); `verify` independently checks a verdict's signature
    against the registered `verifier_keys` without running the full gate.
  - **`.tess/keys/verifiers/<name>.asc`** — bundled public-key convention
    per verifier, mirroring `.tess/keys/twiss-release-key.asc`. NOT
    keystone-tracked (same posture as the release key), but covered by
    `core/policy/policy.yaml`'s `tess-os-security-tier-doctrine` rule
    (`.tess/keys/verifiers/**` added to its globs) — editing the key
    registry requires its own covering, signed Reid/Cyra verdict.
  - **Disclosed, deferred piece:** `core/policy/policy.yaml` ships
    `verifier_keys: {}` — deliberately empty, not an oversight. This repo's
    own `tess-os-security-tier-doctrine` rule (`allowed_verifiers: [Reid,
    Cyra]`) is therefore unsatisfiable by any verdict until real Reid/Cyra
    signing keys are generated and registered — a disclosed, fail-closed
    consequence (a maintainer private-key-custody decision), not a
    fabricated throwaway identity standing in for a real trust anchor.
  - **CI auto-enforce** — `.github/workflows/tess-gate.yml` (template
    marker bumped `v1` → `v2`) now triggers on `push` (protected branches)
    and `pull_request`, in addition to `workflow_dispatch` (kept for ad hoc
    ref-range checks). `tessctl gate install-hooks` actively UPGRADES an
    existing v1 (workflow_dispatch-only) installation to v2 rather than
    silently skipping it forever. A new "Resolve base/head for this
    trigger" workflow step computes the correct `--base`/`--head` for each
    of the three trigger types (`workflow_dispatch` inputs;
    `pull_request`'s `base.sha`/`head.sha`; `push`'s `before`/`after`, with
    an empty-tree fallback for a brand-new ref). Materialized into this
    repo's own `.github/workflows/tess-gate.yml` (previously undeployed —
    the mechanism existed in the install-hooks template but had never
    actually been installed here). Branch-protection required-status-check
    setup (the job name `tessctl gate ci`) is documented
    (`conductor/verdict-signing.md`) but is a repo-admin action, not
    automated by this change.
  - **71 new tests** — `tests/test_verdict_signing.py` (19: valid-signature-
    clears, unsigned/hand-faked/wrong-key/tampered-all-blocked, signing-
    ties-to-allowed_verifiers, unit coverage of
    `_gate_verify_verdict_signature`'s every failure branch, `_lint_policy`'s
    `verifier_keys` name check, `tessctl verdict sign`/`verify` CLI round-
    trips), plus updates across `tests/test_gate_spine.py` and
    `tests/test_gate_hooks.py` (existing covering-verdict tests now sign
    their verdicts with real, per-verifier throwaway GPG keys —
    `verifier_gpg_keys`/`sign_verdict_for_test` in `conftest.py`) and a new
    `test_install_ci_workflow_upgrades_v1_to_v2`. Full suite: **447 passed**
    (427 existing + 20 new test functions, net of the CI-workflow-template
    assertion updates), zero regressions. `tessctl doctor` / `verify` /
    `lock --check` all clean against the live working tree (the three
    tier:security core files this touches — `verdict.schema.json`,
    `policy.schema.json`, `core/policy/policy.yaml` — plus the new
    `conductor/verdict-signing.md` doc, were re-baselined via
    `tessctl lock --regen` per that command's documented maintainer flow).

### Fixed
- **Fable's Phase 2b follow-up review — one MEDIUM, one LOW, both closed:**
  - **MEDIUM-1 — the gate's own CI workflow was not covered by
    `require_verdict`:** `.github/workflows/tess-gate.yml` (the required
    check's own definition) was not matched by any glob in
    `core/policy/policy.yaml`'s `tess-os-security-tier-doctrine` rule —
    once branch protection names "tessctl gate ci" as a required check, a
    PR could keep that exact check name while neutering its step (e.g.
    swap the real run for `exit 0`) IN THE SAME PR, and the required-
    check-by-name mechanism alone could not catch it (the universal
    GitHub self-gating trap: a required check can never fully protect its
    own definition through the required-check mechanism alone). Fixed by
    adding `.github/workflows/**` to `tess-os-security-tier-doctrine`'s
    globs (mirrored in `.tess/core/policy/policy.yaml`, re-pinned via
    `tessctl lock --regen`): any change to a workflow file is now
    `prod_touching` and needs its own covering, signed Reid/Cyra verdict,
    same as `conductor/guardrails.md` or `.tess/keys/verifiers/**`.
    `conductor/verdict-signing.md` gains a new "Defense-in-depth — gating
    the gate's own workflow file" section documenting the recommended
    CODEOWNERS entry + branch-protection "Require review from Code
    Owners" (and, optionally, a path-scoped ruleset) as an independent,
    GitHub-native belt-and-suspenders control over the same paths — a
    repo-admin action, not automated by this change.
  - **LOW-1 — `public_key_file` had no containment check:** in
    `_gate_verify_verdict_signature`, `key_path = root / key_file` alone
    let an ABSOLUTE `public_key_file` (`Path.__truediv__` silently
    discards `root` for an absolute right-hand side) or a `../`-bearing
    relative one resolve OUTSIDE `root`. Not exploitable today — the
    registry lives in `core/policy/policy.yaml`, itself gated by
    `tess-os-security-tier-doctrine`, and an escaped key still has to
    produce a signature whose fingerprint matches the REGISTERED one —
    but fixed fail-closed anyway, same C1-containment discipline
    `check_manifest_write_gate`/`cmd_rollback` already apply elsewhere:
    reject any `public_key_file` that is absolute or contains a literal
    `..` component, then resolve the remaining candidate and reject it too
    if it still falls outside `root` (catches a symlink-based escape with
    no literal `..` in the string).
  - **13 new tests** (`tests/test_gate_own_workflow_coverage.py`, 8: the
    real shipped policy now globs `.github/workflows/**` and stays
    schema-valid + byte-identical across its core/live mirror; the OLD
    glob list provably did NOT match the workflow path while the NEW one
    does; end-to-end against a full copy of the real shipped tree —
    including `.github/`, unlike the existing `real_root` fixture —
    proves editing `tess-gate.yml` with no verdict is blocked on the real,
    unmodified policy (whose `verifier_keys` still ships empty) while an
    unrelated docs change is unaffected; a synthetic policy scoped to the
    same glob proves the rule is satisfiable, not a permanent block, once
    a valid covering signed verdict exists. `tests/test_verdict_signing.py`,
    5: absolute and `../`-traversal `public_key_file` values are rejected
    even when the escaped path is a real, existing file — both as pure
    unit checks on `_gate_verify_verdict_signature` and end-to-end through
    `tessctl gate ci` with an otherwise honestly, validly-signed verdict;
    a symlink-based escape with no literal `..` is caught by the same
    resolve-then-contain check; a normal in-tree path is not falsely
    rejected.) Full suite: **460 passed** (447 existing + 13 new), zero
    regressions. `tessctl doctor` / `verify` / `lock --check` all clean
    against the live working tree (`core/policy/policy.yaml`
    [`tier: security`] and `conductor/verdict-signing.md`
    [`tier: normal`] — the two core-managed files this round touches —
    were re-baselined via `tessctl lock --regen` after the deliberate,
    reviewed edit).

### Fixed
- **Fable's adversarial review of Phase 2 (the gate spine) — one BLOCK, two
  MEDIUMs, one LOW, all closed:**
  - **HIGH-1 (BLOCK) — coverage was diff-unbound, not per-change:**
    `_gate_find_covering_approved_verdicts` walked the ENTIRE working tree
    (`rglob`) for any schema-valid `disposition: APPROVE` verdict whose
    `covers_paths` glob matched a changed path — it answered "does a
    covering verdict exist ANYWHERE," not "was THIS change reviewed."
    Consequences: a single verdict permanently cleared its glob for every
    future push (re-editing a covered file, or adding a brand-new file
    under the same glob, was silently waved through); `covers_paths: ["**"]`
    was a master key; and for `pre-push`, the covering verdict did not even
    need to be committed. Fixed on three fronts:
    - **(a) Coverage bound to the reviewed content** — `verdict.schema.json`
      gains `artifact_hashes` (optional, additive — mirrors `covers_paths`'s
      own introduction), mapping a repo-relative path to the exact git blob
      SHA-1 the verifier reviewed. This is the content-hash loop-closer
      `docs/ULTIMATE_FRAMEWORK_PLAN.md` §C2 named but deferred ("the
      `artifacts_read` field with content hashes makes 'the verifier
      actually read the primary artifact' itself checkable"). The gate now
      requires the recorded hash to equal the path's CURRENT blob SHA at the
      pushed head — a verdict for an OLD version of a file, or a path never
      named in `artifact_hashes` at all, does not clear it. Verification is
      genuinely per-change.
    - **(b) Over-broad `covers_paths` rejected** — `_lint_verdict` refuses
      `**`, bare `*`, `**/*`, and `**/**` as `covers_paths` entries (via new
      `is_overbroad_glob`); a verdict carrying one is schema/lint-invalid as
      a whole and can never satisfy the ship-gate for any path, never mind
      "every" path.
    - **(c) Committed verdicts only, resolved against the pushed ref(s)** —
      covering-verdict discovery moved from `root.rglob("*")` over the
      on-disk working tree to `git ls-tree -r` over the actual pushed head
      sha(s) (new `_gate_git_ls_tree` / `_gate_git_tree_index` / rewritten
      `_gate_iter_verdict_files` / `_gate_find_covering_approved_verdicts`,
      reading blob content via `git cat-file`, not the filesystem). An
      uncommitted (even `git add`-staged) verdict, or one committed only on
      a different branch, can no longer clear the ship-gate. This also
      closes **LOW-1** (symlink-following): `git ls-tree` reports a symlink
      as its own non-blob mode, and `_gate_git_ls_tree` excludes it outright
      — the gate never resolves a symlink to decide coverage.
  - **M1 — `allowed_verifiers` is now enforced, not advisory:** the covering
    verdict's `verifier` field (already required by Phase 0's schema) must
    be in the matched policy rule's `allowed_verifiers`; a wrong-domain
    APPROVE (Fable's example: Lysandra, a creative-taste reviewer, clearing
    a `prod-api` rule requiring `[Reid, Quinn]`) no longer clears the gate.
    `policy.schema.json`'s own field description and `core/policy/policy.yaml`'s
    header — which previously documented this as a "deliberately deferred
    Phase 2+ tightening" — are updated to match.
  - **M2 — glob-matcher semantics fixed:** `path_matches_globs`'s previous
    implementation (`fnmatch.translate` + a NUL-placeholder trick for `**`)
    had two bugs, both with visible pre-existing workarounds elsewhere in
    the file (the vault guard's separate `_age_by_extension` check and
    `_VAULT_SENSITIVE_GLOBS_NORMALIZED` list existed specifically because
    `**/*.age` "misses" root-level files). Replaced with a hand-rolled
    per-segment translator (`_glob_segment_regex` / `_glob_to_regex`):
    (1) `**` now matches zero-or-more whole path segments in ANY position
    (leading/middle/trailing), so `**/*.env` now ALSO gates a root-level
    `.env` (previously it required at least one directory component — this
    directly fixes `core/policy/policy.yaml`'s own credentials hard-floor
    glob, no glob-string changes needed); (2) a bare `*`/`?` inside any
    other segment is now `/`-excluded, so `src/*` covers direct children of
    `src/` only and no longer behaves identically to `src/**`.
  - **LOW-2 — documented, not just fixed:** a new optional
    `verifier_signoff_note` field on the verdict schema, plus explicit
    README.md/CHANGELOG.md disclosure, states plainly that `verifier` /
    `covers_paths` / `artifact_hashes` are PROCESS-VALUE fields (a
    deliberate, rule-following artifact) — not a forgery-resistance
    mechanism. Nothing here cryptographically signs a verdict or proves a
    specific human/agent authored it; a committer controlling their own
    branch can still hand-author any verdict content. The gate raises the
    floor against an honest, rule-following review flow; it is not an
    unbypassable wall against a dishonest one — the same disclosure posture
    `allowed_verifiers` always carried, now applied project-wide.
  - **11 new tests** proving: a verdict clears only the exact reviewed
    content and a subsequent edit re-blocks (per-change verification); a
    brand-new file under an already-covered glob is not silently covered; a
    `**`/blanket `covers_paths` is rejected at both the CLI and the lint
    level; `allowed_verifiers` is enforced (wrong-domain APPROVE doesn't
    clear, the same shape from the allowed verifier does); the two glob
    fixes (root `.env` gated end-to-end through the real hard-floor glob
    shape; `src/*` doesn't span into `src/prod/deep/`); an uncommitted
    (even staged) pre-push verdict doesn't clear; a verdict committed only
    on a different branch doesn't clear; and the stdin pre-push protocol
    path (not just explicit `--base`/`--head`) correctly threads the pushed
    head sha(s) through to the covering-verdict check. Full suite:
    **427 passed** (416 existing + 11 new), zero regressions. `tessctl
    doctor` / `verify` / `lock --check` all clean against the live working
    tree (the three tier:security core files this fix touches —
    `verdict.schema.json`, `policy.schema.json`, `core/policy/policy.yaml`
    — were re-baselined via `tessctl lock --regen` after the deliberate,
    reviewed edit, per that command's own documented maintainer flow).

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
