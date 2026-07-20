# Changelog

All notable changes to Tess OS are documented here. This project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Phase 0.4 — the external-harness-worker LANE + `tessctl tasks handoff`
  (issue #125)**, built on top of the Phase 0.2 TASK STORE + ACCOUNTABILITY
  LEDGER and #121's Codex render-target mount: makes an external harness
  (first: Codex) a first-class task WORKER lane, not just a session that
  can read the shared board.
  - **`target_harness` (task.schema.json)** — a new required, enum-
    constrained field (`codex | claude-code | any`) recording which harness
    a task is EARMARKED for, distinct from `created_by.harness` (who
    created it) and `claim`/the ledger `claim` event's `actor.harness` (who
    actually claimed it). Named `target_harness`, not `harness` — that name
    is already taken (the ACTOR's identity) on `tasks new|set|claim|
    release`. Default `any` (eligible for every harness) — a task nobody
    explicitly earmarks behaves byte-for-byte as it did before this field
    existed. A LEGACY task record (written before this field existed —
    `.tess/state/tasks/**` is gitignored instance data, so a real deployed
    install genuinely has these) heals to `any` on its next touch:
    `_task_read` backfills the missing key in memory (same "legacy, not
    tampered" discipline the ledger's own seq-absent shard handling already
    uses), and `set`/`claim`/`release`/`handoff` persist the healed value
    to disk as a side effect of the mutation already happening.
  - **`tessctl tasks new|set --lane <codex|claude-code|any>`** sets it;
    **`tessctl tasks pull --lane <codex|claude-code>`** filters to a task's
    own lane PLUS every unmarked (`any`) task — omitting `--lane` applies
    no filter at all, so every existing `pull` call is unaffected.
    `tessctl tasks claim` is UNCHANGED: the lane is advisory routing via
    `pull`, never claim-time enforcement — a task earmarked `codex` can
    still be claimed by a `claude-code` actor.
  - **`tessctl tasks handoff <id> --harness <codex|claude-code>`** —
    PREPARES (never spawns) a handoff: earmarks the lane (idempotent),
    logs a `handoff` ledger event, and prints the exact copy-pasteable
    invocation (`tasks claim` → `tasks set` → `tasks release`) an operator
    hands to a fresh session of that harness, pointing it at the same
    shared brain the render-target mounts. `any` is not a valid handoff
    target (a handoff is addressed to ONE specific worker). The printed
    invocation captures `$HOST`/`$PID`/`$UUID` once and threads the SAME
    identity through `claim` and `release`, so the block is actually
    runnable end to end as a single copy-pasted shell script.
  - **Accountability** — two new ledger event classes, `earmarked` and
    `handoff`, both logged through the EXISTING `_ledger_auto_log` →
    `_log_append_event` hash-chain append path (no fork of the chain
    algorithm, no new shard format). `earmarked` uses the same
    only-this-changed structural classification `--heartbeat` already
    established, not a string match. The task-record write path
    (`_tasks_write_locked`, `tasks new`) now validates a mutation's
    CANDIDATE record BEFORE committing it to disk, never after — a
    validation failure leaves nothing on disk and produces no ledger entry,
    matching the ordering `_ledger_self_validate_or_raise` has always used
    on the ledger side.
  - **`BOARD.md` / `tasks pull`** surface the lane (`[lane: <harness>]` on
    an earmarked board line, a `lane=<harness|any>` pull column) — an
    unmarked task's board line is unchanged from before this field
    existed.
  - **Honest constraint (mirrors #121):** no live Codex-runtime end-to-end
    run is possible in the environment this was built in. This verifies the
    LANE MECHANISM + wiring; a live Codex smoke test is a deferred
    follow-up. No Codex process-spawner or daemon was built — `handoff`
    prints an invocation, it does not execute one.
  - `tests/test_task_lane_handoff.py` — 39 tests: earmark at creation/via
    `set`, `pull` filtering (incl. combined with `--unclaimed`, and the
    no-`--lane`-at-all no-op case), `claim` lane-mismatch tolerance,
    `handoff` (idempotency, `any`-target rejection, unknown-task refusal,
    exact printed invocation shapes including `$HOST`/`$PID`/`$UUID`
    threading, JSON output), `_render_handoff_invocation` determinism,
    `BOARD.md` marker, full `log verify` chain integrity after the two new
    event classes, schema/lint coverage, and a dedicated legacy-record
    section (all four mutating verbs heal + log correctly against a record
    missing `target_harness`; `pull`/`render` heal in memory without
    writing back; the standalone `validate task` command still flags it by
    design; an engine-level proof that a validation failure of ANY kind
    now leaves the on-disk record byte-for-byte untouched with zero ledger
    entries).

### Security
- **HIGH — `templates/agents-md/*` core fragments had no `tess.lock` entry;
  core-tamper Check A never ran against them (issue #122, Cyra PoC)** —
  the 7 files composing `AGENTS.md` (`AGENTS.md.tpl`, `worker-hard-floor.md`,
  `gate-compliance.md`, `harness-note.md`, `session-memory.md`,
  `shared-tasks.md`, `codex-config.toml.tpl`) had no `base_sha` pinned in
  `.tess/tess.lock`, so tampering the SOURCE fragment, then re-rendering
  (`tessctl render --target codex`) so the live `AGENTS.md` became
  self-consistent with the tamper, went completely undetected by
  `doctor`/`verify`/`lock --check` — `.tess/core/MANIFEST.md` self-disclosed
  the gap. #121 just made `codex` an enabled-by-default render target for
  every `npm create tess` scaffold, so this stopped being an opt-in edge
  case and became the default path for new installs.
  - **`.tess/tess.lock`** — added a `base_sha`-pinned, `live_path: null`
    entry per file (the same R1 core-internal pattern `personas/*.md`
    already uses), generated via `tessctl lock --regen --only <path> --yes`
    (the repo's own re-pin mechanism, not hand-edited hashes).
  - **`cmd_lock`'s `--check` loop (a second, independent bug this same fix
    closes)** — it unconditionally skipped EVERY entry with `live_path:
    null`, even pre-existing ones with a `base_sha` (the 6 `personas/*.md`
    entries), so `lock --check` was never actually "equivalent to running
    doctor in fail-fast mode" (its own docstring's claim) for this whole
    class of file. Now mirrors `doctor`/`verify`'s own R1 branch — skips
    only when there is truly nothing to check.
  - **`MANIFEST.md`** — removed the self-disclosed "Known gap" caveat.
  - Acceptance: the exact PoC (tamper `shared-tasks.md`, re-render, check)
    now fails closed — `doctor`/`verify`/`lock --check` all report CORE
    TAMPER named at the fragment. Reverting restores a clean pass on all
    three.

### Added
- **Phase 0.2 — the cross-harness TASK STORE + ACCOUNTABILITY LEDGER
  (`tessctl tasks`/`log`)**, ported from Hermes' kanban design
  (`kb/wiki/synthesis/2026-07-19-hermes-codebase-fork-study.md`) onto the
  `.tess/state/` store PR #105 + #111 fenced: "task list, updates,
  accountability list, whoever picked up a task and progress, cleared or
  stuck, resumable by any agent." A sibling of the existing MISSION LEDGER
  region (`tessctl mission`/`gate-status`/`retry`) — reuses the same
  contracts-as-code + dogfood-validate + atomic-write discipline that
  region already proved out, applied to a much more granular unit (one task,
  not one mission).
  - **`tessctl tasks new|set|claim|release|pull|render`** — file-per-task
    JSON at `.tess/state/tasks/<id>.json` (`core/contracts/task.schema.json`,
    id `T-<YYYYMMDD>-<slug>-<4hex>`, status enum
    `backlog|ready|in_progress|blocked|review|done|cancelled`). `set` is a
    rev-CAS optimistic-concurrency write — `--expected-rev N` refuses with
    `TASK_CAS_CONFLICT` (no mutation) if the on-disk rev has moved past N,
    the caller reloads and retries itself (an ETag-style workflow, not a
    silent auto-retry that could paper over a real conflict). `claim` writes
    a claim-lease (`host:pid:uuid` + `claimed_at`/`heartbeat_at`) and
    auto-advances `backlog`/`ready` to `in_progress`; a live claim held by a
    DIFFERENT claimant is refused unless it is stale (`--stale-after`,
    default 900s) or `--force`d, in which case it is a `reclaimed` event, not
    a silent overwrite. `render` regenerates `.tess/state/tasks/BOARD.md`, a
    DERIVED, GENERATED-marked kanban view — never a source of truth. Every
    mutation is serialized by a per-task advisory flock
    (`.tess/state/locks/task-<id>.lock`, stale-pruned on the same `find
    -mmin +N -delete` precedent `.claude/hooks/task-lock-set.sh` already
    uses) — contention is scoped to writers of the SAME task, never a global
    lock. A real two-OS-process concurrency test proves no lost update.
  - **`tessctl log append|view|verify`** — a hash-chained, append-only JSONL
    ledger at `.tess/state/ledger/<YYYY-MM>.<origin>.jsonl`
    (`core/contracts/ledger-event.schema.json`), sharded per calendar month
    AND per writer origin so two machines/harnesses writing concurrently
    never contend on the same file at all. `append` computes
    `hash = sha256(prev_hash + canonical_json(event minus hash))` (the same
    "canonical bytes minus the field being computed" construction
    `verdict_canonical_bytes` already uses, applied to a hash chain instead
    of a signature); `verify` walks a shard's chain and reports the first
    tamper or `prev_hash` break it finds. `tasks new|set|claim|release`
    auto-log the corresponding
    `task_transition|claim|heartbeat|release|completed|crashed|reclaimed`
    event on every real (non-no-op) write, so the accountability trail can
    never be silently skipped by a caller who mutated a task but forgot a
    separate logging step.
  - **`core/contracts/task.schema.json` + `core/contracts/ledger-event.schema.json`**
    (the eighth and ninth contracts, keystone-tracked in `.tess/tess.lock`
    the same way `mission.schema.json`/`retry.schema.json` already are — see
    `core/contracts/README.md`).
  - **Fence held, not weakened**: `.tess/state/**` was already in
    `tess.manifest.json`'s `never_touch`, `.gitignore`'s content-ignore rules
    (#111), and `_PUBLISH_CLEAN_PRIVATE_GLOBS` (#93) before this PR — no
    change needed to any of the three. `tests/test_task_ledger_fence.py`
    proves the SAME fence blocks a genuinely CLI-produced task file and
    ledger shard (not just a synthetic placeholder): invisible to `git add
    -A`, and still refused by `tessctl doctor --publish-clean` if
    force-added.
  - **Deliberately NOT built here** (separate, later PRs — Xavier's own
    scope fence): memory-adopt (`.tess/state/memory/**`) and the
    orphan-sweeper that would scan claim-leases for dead-PID claims and
    auto-resume/re-dispatch abandoned work. This PR builds only the
    substrate a future sweeper would read (claim-lease + heartbeat fields,
    `claim`/`heartbeat`/`reclaimed`/`crashed` ledger events) — never a
    daemon that acts on them.
  - **Tests**: `tests/test_task_store.py` (36 tests — CRUD, CAS conflict +
    reload-and-retry, claim/heartbeat/reclaim/force, release reason
    classification, pull filters, render, a REAL two-process concurrency
    proof, C1 containment, schema/lint), `tests/test_accountability_ledger.py`
    (25 tests — genesis + chaining, sharding, view filters/sort, verify
    clean/tamper/reorder, schema/lint), `tests/test_task_ledger_fence.py` (5
    tests — the data-leak fence against real CLI-produced content).

- **Phase 0.3 — the cross-harness MEMORY LINK (`tessctl memory adopt`)**,
  closing the memory half of the shared-brain build (the task/ledger half
  landed as Phase 0.2 above). A sibling of the TASK LEDGER region — same
  `.tess/state/` store, same fail-closed discipline — but memory is
  different from tasks/ledger in one respect: Claude Code (and, eventually,
  other harnesses) already had a WORKING harness-private memory convention
  before this region existed, so the job here is "adopt" (move + symlink an
  existing directory into the canonical store), not "invent a new format."
  - **`tessctl memory adopt`** — moves an existing harness memory
    directory's contents into `.tess/state/memory/` and replaces the
    original with a symlink pointing at it, so that harness's own native
    memory reads/writes transparently land in the ONE canonical store every
    harness mounts. Dry-run by default (`--yes` to mutate; the entire
    planning phase — idempotency check, source/target enumeration,
    per-file conflict detection — is read-only, so even a refused call
    never touches disk); refuses `--from`/`--to` resolving to the same path
    or one nested inside the other, before any mutation, by INODE IDENTITY
    (`os.path.samefile`) rather than string equality — a self-targeted
    adopt would otherwise treat the source's own content as "already
    present," copy nothing elsewhere, then delete the only copy, and a
    string compare alone is bypassable on the real deployment filesystems
    (macOS APFS, Windows NTFS), which are case-insensitive and treat
    differently-cased spellings of the same directory as one and the same
    file even though `Path.resolve()` preserves as-typed case; refuses a
    non-empty target without `--merge` (bootstrap calls with no source
    content are exempt — nothing is being merged); refuses a source entry
    that is a symlink (never silently dereferenced); refuses any real
    filename+content conflict outright, with zero partial writes;
    idempotent against an already-adopted source (a clean no-op); every
    `OSError` reachable from planning or the mutate-for-real path —
    including the rmtree → symlink → manifest-write swap, made crash-safe
    via a manifest written before the source is ever touched and a
    verified temporary-sibling symlink created before the original
    directory is removed — is converted to a typed `MemoryAdoptError`,
    never a raw traceback, and a failure anywhere in that swap leaves the
    source fully intact rather than half-deleted; a post-adopt round-trip
    read/write check through the new symlink triggers an automatic full
    rollback (via the same revert path) if it ever fails, so no
    half-adopted state can survive. `--harness` defaults to Claude Code's
    own well-known per-project path
    (`~/.claude/projects/<flattened-root>/memory/`) but any path is
    supported via `--from`.
  - **`tessctl memory adopt --revert`** — dry-run by default, symmetric
    with forward-adopt (`--yes` required to mutate) — undoes an adopt from
    THAT adopt's own recorded manifest
    (`.tess/state/memory/.tess-memory-adopt.<harness-slug>.<source-path-hash>.json`
    — one per adopted (harness, source-path) pair; the hash keeps two
    differently-spelled `--harness` names that slugify identically, e.g.
    `Claude-Code`/`claude_code`, from clobbering each other's manifest),
    restoring exactly the files that manifest recorded — never the store's
    current full contents, which may since have grown from a different
    harness's own adopt or ordinary shared writes. Of those files, only the
    ones THIS adopt itself copied in are CANDIDATES for removal from the
    store; a file that was already present (byte-identical) before this
    adopt ran is copied back into the restored directory but left in the
    store, since another still-adopted harness may depend on it — and that
    protection is symmetric: a file THIS adopt itself copied in is ALSO
    copied-back-but-left-in-store, not removed, if any OTHER still-live
    harness's manifest references the same filename in its own
    `source_files` (the reverse case — this harness was the original
    owner, and a second harness later deduped against it). Refuses (no
    mutation, no guessing) if the recorded source path has drifted since
    adopt (already reverted, or manually altered).
  - **`tessctl doctor` memory-link check** — non-fatal, informational only,
    in every case (not-adopted, adopted-and-clean, or adopted-but-broken
    never affect doctor's errors/warnings/exit code): per adopted harness,
    symlink present + resolving, store writable, and
    `.tess/state/memory/MEMORY.md`'s own index coherence against what is
    actually on disk (broken links, unindexed files).
  - **Codex/generic AGENTS.md pointer** —
    `.tess/core/templates/agents-md/AGENTS.md.tpl` gains a "Session Memory
    (Shared)" section (`{{WORKER_SESSION_MEMORY}}`,
    `.tess/core/templates/agents-md/session-memory.md`) telling a
    worker-profile harness to read `.tess/state/memory/MEMORY.md` at
    session start and write durable learnings back to the same store —
    Claude Code needs no equivalent (its own harness already auto-reads
    its memory index natively). A pure repo/state fact, not orchestration
    doctrine — verified clean against the G3 worker-profile
    doctrine-denylist.
  - **Fence held, not weakened**: `.tess/state/memory/**` was already in
    `tess.manifest.json`'s `never_touch`, `.gitignore`'s content-ignore
    rules (#111), and `_PUBLISH_CLEAN_PRIVATE_GLOBS` (#93) before this PR —
    no change needed to any of the three. `tests/test_memory_adopt_fence.py`
    proves the SAME fence blocks a genuinely CLI-adopted memory file and
    its adopt manifest (source directory deliberately outside the git
    working tree, mirroring a real harness home-directory layout):
    invisible to `git add -A`, and still refused by `tessctl doctor
    --publish-clean` if force-added.
  - **Running an actual adopt against any specific instance's own live
    memory remains a separate, later, opt-in operation** — this PR ships
    only the mechanism, exercised entirely against disposable `tmp_path`
    fixtures.
  - **Tests**: `tests/test_memory_adopt.py` (41 tests — dry-run purity,
    bootstrap + real adopt, idempotency, every refusal (including a
    symlinked source entry and `--from`/`--to` self-collision/nesting),
    `--merge` skip-on-identical-content, `--revert` (dry-run-by-default +
    `--yes` gate, multi-harness disambiguation including the
    harness-slug-collision case, drifted-state refusal, and the
    two-harness shared-file preservation case in BOTH directions),
    automatic rollback on a simulated round-trip failure, crash-safety of
    the rmtree → symlink → manifest-write swap under injected `OSError`
    failures, a guarded `read_bytes()` failure during planning, the
    doctor memory-link check's four states, the `--from`/`--to`
    self-destruct guard's inode-identity check on a case-insensitive
    filesystem (exact-same-dir and nested variants), and the
    reverse-direction two-harness shared-file preservation case),
    `tests/test_memory_adopt_fence.py` (8 tests — the data-leak fence
    against real CLI-adopted content, plus the AGENTS.md render
    assertions). **49 tests total** (15 added responding to PR #117's
    two-reviewer REJECT — Cyra/security found the `--from`==`--to`
    self-destruct (H1) and the revert over-removal of a second harness's
    shared file (M1); Reid/quality independently found the same
    self-destruct as CRITICAL plus the unguarded rmtree → symlink →
    manifest-write region (HIGH), the harness-slug manifest collision, the
    missing revert dry-run/`--yes` gate, and an unguarded `read_bytes()`
    during planning — all fixed and regression-tested. Cyra's
    re-verification of that fix (commit `18a3fea`) then found two more
    holes: HOLE 1/HIGH — the self-destruct guard compared resolved path
    STRINGS, bypassable on a case-insensitive filesystem (macOS APFS /
    Windows NTFS, this project's real deployment FS), fixed with inode
    identity (`os.path.samefile`); HOLE 2/MEDIUM — the shared-file revert
    protection only held in one direction, fixed by making it symmetric —
    both fixed and regression-tested before this PR ships).

### Security
- **MEDIUM — `.tess/state/{memory,tasks,ledger}/` missing content-level
  `.gitignore` fence (issue #110, found reviewing #105)** — PR #105's
  `.gitignore` reconciliation only content-ignored `.tess/state/locks/*`;
  `memory/`, `tasks/`, and `ledger/` were left un-gitignored at the content
  level, relying solely on the `tessctl doctor --publish-clean` pre-commit
  hook (`tessctl gate install-hooks`) — opt-in, not guaranteed installed on
  every clone/re-init. On an instance without the hook, a plain
  `git add -A` would silently STAGE real memory/task/ledger data;
  `docs/STATE_LAYER.md`'s "can never leak regardless of gitignore state"
  claim overclaimed for those three subdirs.
  - **`.gitignore`** — added `.tess/state/memory/*` / `.tess/state/tasks/*`
    / `.tess/state/ledger/*` (each with a `!.../.gitkeep` re-include),
    mirroring the existing `.tess/state/locks/*` pattern and the
    `kb/wiki/**` / `missions/**` / `operator/**` precedent buckets. New
    files under any of the four subdirs are now structurally invisible to
    `git add`, independent of whether the pre-commit hook is installed.
  - **`docs/STATE_LAYER.md`** — reconciled the fence description from a
    "three-part fence + gitignore only for locks/" framing to the accurate
    four-part fence (never_touch, gitignore, publish-clean, scaffold-empty)
    now applying symmetrically to all four subdirectories.
  - **`tests/test_gitignore_reconciliation.py`** — extended with
    `.tess/state/{memory,tasks,ledger,locks}` cases (ignored-content +
    tracked-`.gitkeep` parametrizations) and a new
    `test_git_add_dash_a_never_stages_real_state_content_no_hook` — a real
    fresh git repo, no pre-commit hook installed, real files written under
    all four subdirs, `git add -A`, asserts none staged (`git diff --cached
    --name-only`) and none surfaced in `git status`, while each `.gitkeep`
    stays the only tracked entry.

- **HIGH+MEDIUM+LOW×4 — TASK STORE + ACCOUNTABILITY LEDGER hardening
  (issue #114, found reviewing #113; fixed in #115)** — a consolidated fix
  for all six findings from #113's two-reviewer gate (Reid + Cyra), before
  any consumer — in particular the future orphan-sweeper — trusts
  `claim.heartbeat_at` or the ledger's integrity guarantees:
  1. **[Reid HIGH]** `tessctl tasks set --heartbeat` had no claimant-identity
     check — a forgeable liveness signal; anyone who merely knew a task id
     could renew a DIFFERENT claimant's claim. Now requires
     `--host`/`--pid`/`--uuid` matching the current claim
     (`TASK_NOT_CLAIMANT` otherwise, or `--force`).
  2. **[Reid MEDIUM]** `tessctl tasks claim`'s default `--uuid` was a fresh
     `uuid4()` per call, so a same-process re-claim (e.g. after a restart)
     was never recognized as itself. Now a stable `uuid5` derived from
     `(host, pid)`.
  3. **[Cyra M1]** The ledger's pure `prev_hash` chain walk was blind to a
     removed TAIL line or a whole shard deleted outright — neither leaves a
     chain-break trace. Added a per-event monotonic `seq`, a per-shard
     `.tip` sidecar, and a ledger-wide `.registry.json`; `log verify`
     cross-checks all three.
  4. **[Cyra M2]** `_prune_stale_locks` had a TOCTOU window (check-then-
     unlink) and a safety comment incorrectly claiming that unlinking a
     lock file can never disturb a live holder. Fixed with a
     non-blocking-flock-then-inode-recheck gate before any unlink; the
     comment is corrected.
  5. **[Cyra L1]** Reworded "tamper-evident"/"instead of a signature"
     overclaims in the ledger-event schema, engine comments, and
     `docs/STATE_LAYER.md` — an unsigned hash chain detects non-re-chained
     edits, not an adversary who also rewrites the `.tip`/registry
     consistently with a shortened chain, and it is not a signature.
  6. **[Cyra L2]** Documented the trust boundary explicitly: claim-leases
     are advisory coordination (filesystem write access is the real
     boundary), not authentication.
  - Full suite green (1555 passed) at the time, `doctor`/`verify`/`lock
    --check` green. Closes #114.
  - **Follow-up LOWs from the same #115 review, closed in a later
    consolidated PR:** a shard written before this hardening (no `seq` on
    any line) false-reported `TAMPERED` under `log verify` and hard-refused
    `log append` — now read as `LEGACY` and backfilled, not refused
    (Cyra-LOW/Reid-MED); a `--force`/non-claimant heartbeat's ledger event
    was misclassified as `task_transition` by exact string-equality on
    `changes` — now classified by an explicit structural boolean, so it
    still logs under `heartbeat` (Reid-LOW).

- **P0 G-01 — npm scaffold key-leak (readiness audit, 2026-07-19)** — the
  published `create-tess` 0.1.0 (npm, 2026-06-28) clones `twiss-io/tess-os`
  main HEAD **UNPINNED**, and every `main` commit since PR #91 (which
  registers this repo's own verifier, Cyra, so this repo's gate can accept
  her verdicts on its OWN doctrine changes) carries the real bundled PUBLIC
  key file `.tess/keys/verifiers/cyra.asc`. Neither the scaffold copy filter
  (`create-tess/src/ignore.js`) nor the policy reset (`create-tess/src/
  policy-reset.js`, which only rewrites the two `policy.yaml` YAML maps back
  to `{}`, never a raw key FILE) ever stripped that file, so every
  `npm create tess` run shipped a scaffolded project trusting the Twiss
  maintainer's own verifier key as if it were the scaffolded project's OWN
  trust root — public-key-only, ~zero adoption, so low realized risk, but the
  exact "governance vendor leaks its scaffold" launch landmine.
  - **`create-tess/src/ignore.js`** — `.tess/keys/verifiers` and
    `.tess/keys/signoffs` added as whole-subtree `EXCLUDE_DIR_PREFIXES`
    (mirroring the existing `.claude/tess-secrets` / `.claude/channels`
    treatment). The unrelated, intentionally-bundled release-verification key
    (`.tess/keys/twiss-release-key.asc`, used by `tessctl update` to verify an
    upstream fetch) is deliberately NOT excluded — this is a targeted fix, not
    a blanket "never copy `.tess/keys/`" hammer.
  - **`create-tess/test/scaffold-key-guard.test.js` (new, permanent CI
    guard)** — a real, non-interactive, end-to-end scaffold run whose output
    is scanned for (a) ANY PGP key-block marker or the registered Cyra
    fingerprint ANYWHERE in the produced tree (not just the two known paths —
    catches a future leak wherever it recurs) and (b) confirms
    `.tess/keys/verifiers`/`.tess/keys/signoffs` do not exist at all while
    `.tess/keys/twiss-release-key.asc` still ships intact. Wired into the
    existing `create-tess` CI job (node 18/24) automatically — Node's test
    runner discovers any `test/*.test.js`.
  - **Pinned clone (reproducibility)** — `create-tess/src/scaffold.js`'s
    git-clone path previously had NO ref at all (`git clone --depth 1
    <source>`, whatever the default branch's HEAD tip happened to be at the
    exact moment a user ran the wizard). Added `DEFAULT_TEMPLATE_REF`
    (`create-tess-v0.1.2` — create-tess's own tag namespace, per
    `.github/workflows/publish-npm.yml`, decoupled from the framework's own
    `v*` release tags) plus `resolveTemplateRef()`/`buildCloneArgs()`: the
    default source now clones a pinned, tagged release — the exact same
    tess-os commit every time, one that has already passed this repo's own
    CI (including the new guard test) — never an in-flight main tip. New
    `--template-ref` flag / `TESS_TEMPLATE_REF` env var let an operator
    override to a different ref; a custom `--template-source` is left
    unpinned (its own branch tip) unless a ref is explicitly given, so a
    fork/mirror/CI-fixture source is unaffected.
  - **`create-tess` bumped 0.1.1 → 0.1.2** (package.json was already
    unpublished-bumped to 0.1.1 by an earlier merge-train; this fix bumps it
    further since the earlier bump was never published). npm publish itself
    is NOT run by this change — remains Xavier's credentialed action (`git
    tag create-tess-v0.1.2 && git push origin create-tess-v0.1.2`, or
    `workflow_dispatch` with `confirm_version: 0.1.2`, per
    `.github/workflows/publish-npm.yml`).
  - **8 new / extended tests** (units.test.js: key-exclusion unit coverage +
    ref-pinning unit coverage; scaffold-key-guard.test.js: the end-to-end
    regression lock). Full create-tess suite: **33 passed**, zero
    regressions; `tessctl doctor`/`verify` clean on every produced scaffold.
- **DATA-LEAK-SAFETY (issue #92)** — the write-gate (`check_manifest_write_gate`
  / `guarded_write`) was solid: `tessctl` itself already refuses to write to a
  `never_touch` path. The COMMIT boundary (`.gitignore`) had drifted from it —
  `operator/*.md`, `operator/profile.json`, `*.local.md`, and
  `kb/wiki/log.md` were not gitignored, and there was no commit-side control
  at all (gitleaks was secrets-only and CI/post-push only). A plain
  `git add -A && git commit` in a freshly scaffolded (or self-hosted) Tess OS
  instance could commit private operator/client data to a public repo — the
  blocker for safely dogfooding an instance with real data.
  - **`.gitignore` reconciled** with the manifest's `never_touch` set: added
    `operator/**` (four static doc-template stubs explicitly re-included by
    name — `build-facts-stub.md`, `identity-stub.md`, `org-channels.md`,
    `user-profile.md` — but deliberately NOT `operator/profile.json`, the one
    file `create-tess`'s onboarding wizard unconditionally overwrites with
    real operator identity), `*.local.md` / `**/*.local.md`, `missions/*`
    (`!missions/README.md`), `UPGRADE-NOTES.md`, `.mcp.json`. Removed the
    previous `!kb/wiki/index.md` / `!kb/wiki/log.md` overrides — `log.md` is
    the file a live instance appends real mission/client entries to, not a
    static template. Deliberately did NOT gitignore the rest of `never_touch`
    (`docs/**`, `adapters/**`, `starter/**`, `README.md`, `main.py`,
    `pyproject.toml`, `uv.lock`, ...) — those are legitimately tracked,
    public, framework-repo content that `tessctl` is merely out of scope to
    manage, not private data; doing so was tried during development and
    produced ~155 false violations against this repo's own history.
  - **`tessctl doctor --publish-clean`** — the commit-side PUBLISH-CLEAN gate,
    symmetric to the write-gate. FAILS if a staged path matches a curated
    private-data subset (operator identity, `kb/**`, `clients/**`, `.env*`,
    `*.local.md`, vault material, `missions/**`) — deliberately a curated
    subset of `never_touch`, not the full list, for the same reason the
    `.gitignore` reconciliation above stayed curated. Default scope is
    STAGED changes (`git diff --cached --diff-filter=ACMR`) so a
    pre-existing grandfathered tracked file (this repo's own generic
    `operator/profile.json`) doesn't re-fail every future unrelated commit;
    `--publish-clean-all` audits the full `git ls-files` set instead.
  - **`tessctl gate install-hooks`** now also installs the publish-clean
    guard as a pre-commit hook (`tess-publish-guard`) and a local `gitleaks`
    guard as a pre-push hook (`tess-gitleaks-guard`, secrets-only, clearly
    labeled as NOT covering PII — falls through with a warning if `gitleaks`
    isn't installed locally, since CI's `secret-scan` job is the enforced
    backstop regardless). Both are independent splice implementations (own
    marker, own end sentinel) using the same containment-subshell coexistence
    pattern the vault guard and contract gate guard already proved — four
    independently-shipped hook installers now compose on the same
    pre-commit/pre-push files without any of them neutering another.
  - **`docs/DATA_LEAK_SAFETY.md`** — the framework + private-overlay model:
    private data lives ONLY in overlay dirs (`clients/`, `kb/`, `operator/`,
    `.env`, `*.local.md`); framework-owned dirs (`agents/`, `conductor/`,
    `.claude/agents|commands|hooks|skills`, `CLAUDE.md`, `prompts/`,
    `AGENTS.md`, `core/contracts|policy`) are overwritten on update — Cyra
    proved a planted `agents/*.md` secret gets silently clobbered by the next
    upstream file at that path.
  - **87 new tests** — `tests/test_publish_clean_gate.py` (44: curated-glob
    consistency, per-path unit coverage, CLI exit codes, real
    pre-commit-hook-fires e2e, three-guard coexistence),
    `tests/test_gitleaks_local_prepush.py` (6: splice/idempotency, real
    secret-blocks-a-push e2e, missing-binary warn-and-fall-through), and
    `tests/test_gitignore_reconciliation.py` (37: `git check-ignore
    --no-index` proof for every private path, proof every shipped template
    stays tracked, proof non-private framework content stays untouched).

### Fixed
- **`dispatch-guard.sh` — headless / no-subagent-available exception**
  (Ada, Lead Backend Engineer, 2026-07-07, closing a finding from Ada's own
  Proving Ground benchmark run, `proving-ground/reports/2026-07-07.md`):
  the hook's warn-mode "RULE ZERO WARNING — stop and dispatch" `systemMessage`
  fired on every non-safe-listed `Bash`/`Edit`/`Write` call regardless of
  whether the calling context actually HAD a subagent-dispatch capability to
  act on the warning. Rule Zero ("always dispatch, never execute solo")
  correctly targets the real Tess orchestrator (which holds the Agent/Task
  tool) but is structurally inapplicable in a headless single-agent
  execution context (a `claude -p` worker, `codex exec`, or any harness with
  no subagent layer) — there the model has nothing to dispatch TO, so every
  warning is pure friction with zero corrective action available. The
  benchmark measured this directly: a 3.1-3.2x cost/latency overhead on
  every task under the `tess-os` scaffold vs. `bare`, at both model tiers,
  plus a reproducible fabrication regression (`05-research-roster-facts`:
  `strong+tess-os` failed all 3 attempts an unassisted `strong+bare` run
  passed cleanly on attempt 1) most plausibly caused by the model spending
  attention re-litigating "should I be doing this myself" against a
  contextually-wrong warning instead of the task's actual instructions.
  - **The fix:** both shipped copies (`.tess/core/hooks/dispatch-guard.sh`,
    the core master, and its live mirror `.claude/hooks/dispatch-guard.sh`)
    now check for an explicit, opt-in **`TESS_HEADLESS=1`** environment
    flag (alias: `TESS_NO_SUBAGENTS=1` — either is sufficient) as the very
    FIRST decision in the script, ahead of even the existing
    dispatch-in-flight lock check, and short-circuit to a pure no-op (exit
    0, no `systemMessage`) when set. Stdin is still fully consumed first
    (protocol contract) either way. This is presence-based, not
    boolean-parsed — the string `"0"` still counts as "set"; only unset or
    empty (`""`) leaves headless mode off — documented inline and pinned by
    a dedicated test so the quirk is never "fixed" by accident. The
    real Tess orchestrator session never sets either variable, so its
    warn-mode behavior is byte-for-byte unchanged; only an explicitly
    opted-in headless caller is affected.
  - **`tessctl lock --regen --only <path>` (repeatable, new flag):** the
    maintainer re-baseline verb previously only supported an unscoped,
    whole-tree `--regen` — which "blesses" every lock entry's `base_sha` to
    current core, including any unrelated, unreviewed drift elsewhere as a
    side effect. Added `--only PATH` (matches either `core_key` or
    `live_path`, same resolution rule `tessctl reset` already used) to scope
    a re-baseline to a named, reviewed set of files; unresolved paths fail
    loud (`sys.exit`) rather than silently no-op'ing. Used here to re-pin
    ONLY `dispatch-guard.sh`'s entry — `tessctl lock --regen --only
    .claude/hooks/dispatch-guard.sh --yes`. Unscoped `--regen` is unchanged
    and still available for genuinely repo-wide re-baselines.
  - **Coordination point (not built here, flagged for the next Proving
    Ground re-run):** the harness's `tess-os` scaffold
    (`proving-ground/pg_lib/scaffolds.py`, branch `goal-proving-ground`,
    not yet merged to `main`) mounts `.claude/` verbatim into each headless
    trial's workdir but does not currently set `TESS_HEADLESS`/
    `TESS_NO_SUBAGENTS` in the `claude -p` subprocess environment
    (`pg_lib/claude_driver.py`). A re-run intended to measure this fix's
    effect needs that harness-side env var added — this is Proving Ground
    surface, owned by whoever picks up that branch next, not touched by
    this change.
  - **20 new tests** (`tests/test_dispatch_guard_headless.py`, 15: default
    warn-mode behavior is unchanged for both `Bash` and `Edit`, the
    pre-existing doctrine safe-list is unaffected, both flags/aliases
    silence the warning for both tool types, the flag's presence-based
    (not boolean-parsed) semantics including the `"0"` quirk and the
    empty-string non-suppression case, the hook never blocks regardless of
    headless state, the two shipped copies stay byte-identical and both
    honor the flag, and the headless check structurally precedes both the
    stdin-read and the dispatch-lock check in source; `tests/test_lock.py`,
    4: `--only` scopes a re-baseline to a named entry while
    leaving an untouched, still-tampered entry alone, accepts the
    `core_key` form as well as `live_path`, fails loud on an unresolvable
    path, and remains gated behind `--yes`/interactive confirmation exactly
    like unscoped `--regen`). Full suite: **479 passed** (460 existing + 19
    new), zero regressions. `tessctl doctor` / `verify` / `lock --check` all
    clean against the live working tree — `dispatch-guard.sh`'s single lock
    entry was re-baselined via the new scoped `tessctl lock --regen --only`
    (not an unscoped regen), leaving every other entry's `base_sha`
    untouched.

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
- **G3 (2026-07-08) — the AGENTS.md payload initially shipped for the new
  `codex`/`generic` render targets (see "Added" below) exported the exact
  harm a 2026-07-07 proving-ground benchmark measured, and was re-scoped to
  a lean WORKER doctrine profile before this branch merged.** Two fair
  benchmark runs (`proving-ground/reports/2026-07-07*.md`) disproved the
  "structure makes weak agents better" thesis and identified the specific
  mechanism: mounting the full orchestration doctrine ("always dispatch,
  never execute solo," six outcome orchestrators, the mission-ceremony
  command table) into a single-agent harness is not neutral — in the fair
  run's verification probes, the mounted CLAUDE.md caused a weak model to
  attempt an actual nested subagent spawn on a task that only asked for
  `python3 --version`. The Codex/generic AGENTS.md render initially shipped
  that exact payload, verbatim, to Codex, Cursor, Copilot, Gemini CLI, Zed,
  and Devin — none of which can dispatch at all.
  - **`RenderTarget.doctrine_profile`** — new field, `"orchestrator"` or
    `"worker"` (`DOCTRINE_PROFILES`). Data on the target class, not a CLI
    flag someone forgets. `claude-code` → `"orchestrator"` (the genuine
    case — Claude Code holds the Agent/Task tool). `codex` / `generic` →
    `"worker"` (no in-session subagent tool). A new
    `RenderTarget.doctrine_digest_paths()` hook names the subset of a
    target's rendered artifacts that carry actual doctrine prose (as
    opposed to mirrored, individually-authored files it also happens to
    write) — `{"CLAUDE.md"}` for `claude-code`, `{"AGENTS.md"}` for
    `codex`/`generic`.
  - **AGENTS.md.tpl re-cut to the lean worker profile** (~57 rendered
    lines, was ~180+): two new WORKER-ONLY fragments —
    `.tess/core/templates/agents-md/worker-hard-floor.md` (the ~5-line hard
    floor: credentials, money movement, destructive production data,
    client-external claims — the four genuinely universal safety gates) and
    `.tess/core/templates/agents-md/gate-compliance.md` (the ship-gate's
    compliance facts: which paths require a signed verdict, which files a
    worker must never touch) — plus a new operator-fillable, empty-by-
    default `operator/build-facts-stub.md` zone (`{{OPERATOR_BUILD_FACTS}}`)
    for the one "environment fact" this framework cannot know on a
    downstream project's behalf. `{{CORE_RULE_ZERO}}`, `{{CORE_SYSTEM_LAWS}}`,
    the inline "Outcome Orchestrators" section, and the 26-row
    `{{COMMAND_TABLE}}` are REMOVED from `AGENTS_TOKEN_MAP` / the template —
    all name or assume a dispatchable crew that does not exist for a
    worker-profile harness. `{{CORE_DIRECTORY}}` is also dropped (not
    harmful, just heavy — ~45 lines — to stay inside budget). Per the
    reckoning's honest constraint, nothing new was added on a performance
    bet: every line is a repo/gate fact or a safety floor, none is a
    behavioral claim. `.codex/prompts/*.md` / `prompts/*.md` still mirror
    every command body verbatim, unchanged — auditing those mirrors is
    separately tracked future work (reckoning §2.5), not part of this fix.
    Now-dead helpers `_parse_command_description()`, `_command_catalog()`,
    `_render_command_table()` removed (no longer called).
  - **Worker-profile denylist drift check** — `_check_worker_profile_denylist()`,
    wired into `tessctl doctor`, `verify`, and `lock --check` (new
    `WORKER_DOCTRINE_DENYLIST`: "always dispatch", "never execute solo",
    "rule zero", "outcome orchestrator", "dispatch brief contract",
    "dispatch-guard.sh"). Runs against every REGISTERED worker-profile
    target's `doctrine_digest_paths()` via the same pure
    `expected_live_bytes()` function doctor/verify's existing drift-checking
    already calls — fires even before a worker target is enabled for a
    given install, so a future template edit can never silently re-export
    this harm. Fails loud (exit 1) in all three commands; `doctor --json`
    carries the same `"DOCTRINE LEAK"` marker as the human-readable mode
    (the same "must count explicitly or human-mode fails open" discipline
    `missing_count` already established).
  - The orchestrator profile (`CLAUDE.md`, Claude Code as Tess) is
    UNCHANGED — untouched fragments, byte-identical render, verified by
    `tests/test_render_target_doctrine_profile.py`'s positive control.
  - **34 new tests** — `tests/test_render_target_doctrine_profile.py` (6:
    registry sweep, known profile values, base-class defaults,
    `doctrine_digest_paths()` per target, orchestrator-profile-unchanged
    positive control) and `tests/test_worker_profile_denylist.py` (12: the
    real shipped render is clean, a synthetic regression fixture is
    genuinely caught — not a check that always passes — case-insensitivity,
    runs-regardless-of-enablement, and `doctor`/`verify`/`lock --check` all
    fail loud on it). `tests/test_render_targets_codex_generic.py` updated
    for the new fragment/token set (25 → 30, net of the dropped
    command-table assertion replaced with a "table is absent" assertion).
    Full suite: 504 → 527 (some renumbering from the prior 479→504 line),
    zero regressions. `tessctl doctor` / `verify` / `lock --check` all clean
    against the live working tree; `tess.lock` re-baselined via
    `tessctl lock --regen --yes` (4 entries: the two edited templates plus
    the two new fragment files).

### Added
- **Proving Ground — the measurement harness for the weak-model+structure thesis**
  (`proving-ground/`, PR #40): 10 seeded tasks spanning bug-with-failing-test,
  feature-vs-spec, research-with-checkable-facts, and two planted traps
  (tenant isolation, SQL injection), each gradeable without human judgment
  via `proving-ground/grade.py`. `proving-ground/run.py` is the matrix runner
  (weak/strong model tiers x bare/tess-os scaffolds, 4 cells) driving headless
  `claude -p` trials; `pg_lib.report.aggregate_by_cell` is the only path a
  number reaches a report through — no hand-typed stats. 64 harness unit
  tests green; a full 4-cell x 10-task benchmark run is a separate, later
  step (out of scope for this PR — see the harness `README.md`'s cost
  estimate). The dispatch-guard headless-exception fix above was discovered
  running this harness and has already shipped separately.
- **Goal #11 (roster honesty) — `model_tier` vocabulary, a `coding-squad` roster preset, and stale-count fixes.**
  This slice is scoped to `agents/`, `conductor/` (doctrine text), and top-level
  docs only — no `.tess/bin/tessctl` engine changes. The `tessctl recruit`
  render-into-every-adapter change and `model_tier` **consumption** logic
  (an adapter actually reading the field to set a model) are explicitly
  deferred to a follow-up, mechanism-level change.
  - **`model_tier` frontmatter vocabulary** (`strong` / `cheap`, mapped from
    role — conduct→strong, execute→cheap, verify→strong; documented in
    `agents/README.md` § Model Tier) applied to the core coding squad's
    `agents/<name>/README.md` frontmatter (previously none existed) and to
    `conductor/identity.md` (the conductor): Leah/Eva/conductor = `strong`;
    Ada/Iris/Vega = `cheap`; Reid/Cyra/Quinn = `strong`. Distinguished in
    `conductor/agent-lifecycle.md` §10 from the pre-existing, unrelated
    `model:` harness alias (`haiku`/`sonnet`/`opus`) in `.claude/agents/*.md`.
  - **`coding-squad` roster preset** — a new entry in
    `.tess/core/roster-paths.json` (`ada, iris, reid, cyra, quinn, vega` +
    the universal base + `product-delivery-orchestrator`), distinct from the
    existing `builders` wizard path (which omits Cyra/Vega). Verified
    end-to-end against the real config: `roster apply coding-squad` installs
    exactly 9 agents, stages the other 141, and `doctor`/`verify` report
    clean. **Known gap, disclosed:** `tessctl roster apply`'s CLI argument
    still has a hardcoded `choices=["founders","builders","operators"]` in
    `.tess/bin/tessctl` — a one-line addition needed before `coding-squad` is
    reachable from the CLI. That line lives in the engine file this slice is
    barred from touching; flagged for the next tessctl-scoped change.
  - **Roster-count drift fixed**, hand-verified against the tree (no
    generation mechanism exists yet — that would itself be a `tessctl`
    change): `conductor/orchestra-model.md` (`.tess/core` mirror included)
    corrected "~165 agents" / "165 persona specs; 42 dispatchable today" /
    "123 non-dispatchable personas" (stale — predates the 2026-06-27
    all-150-dispatch-capable fix already recorded in `agents/README.md`) to
    144 persona specs + 6 orchestrators = 150 dispatch-capable, and rewrote
    §6's "bench depth" description from "Eva promotes a persona to a
    dispatchable definition" (the old two-class model) to the current
    staged/installed model (`tessctl recruit`/`bench`). `.tess/core/MANIFEST.md`
    corrected "165 persona directories" — actually 165 total top-level
    entries under `agents/` (144 persona directories + 21 guild/doctrine
    `.md` files), a miscount that conflated the two. `docs/ULTIMATE_FRAMEWORK_PLAN.md`
    (§B.2 tree sketch, §C7, and the E.1 gap-analysis table's public-repo-hygiene
    row) updated to match. `agents/README.md` and root `README.md` gained an
    explicit "dispatch-capable ≠ installed" clarification (only a curated
    subset, as few as 7, is ever live in `.claude/agents/` for one instance).
  - `tessctl doctor`/`verify`/`lock --check` all clean after re-pinning the
    13 touched core-managed entries via `tessctl lock --regen --yes` (the
    scoped `--only <path>` flag referenced in this goal's brief ships in a
    separate, not-yet-merged PR — `--regen` without `--only` only changes
    `base_sha` for files whose bytes actually differ, so the effect was
    identical: exactly 13 entries re-pinned, confirmed via `git diff`). Full
    suite: 460 passed, 0 regressions.
- **`tessctl run <crew-plan>` — the mechanical CONDUCTOR LOOP (Goal #6).**
  The framework's structural bet: the conductor loop (gate check → dispatch
  → read the returned artifact back → mandatory verification → typed retry
  → halt/escalate) was doctrine a strong Claude Code session enforced
  through discipline. It is now DETERMINISTIC CODE — a gate cannot be
  "decided around" at 3am, a schema-miss cannot be waved through, and a
  verifier's BLOCK cannot be quietly stepped past, regardless of which CLI
  (or how strong a model) is dispatching.
  - A new `DispatchDriver` seam (abstract `dispatch(brief, output_schema=
    None) -> dict`) with three implementations: `ClaudeCliDriver` (`claude
    -p --output-format stream-json`, Tier A), `CodexExecDriver` (`codex exec
    --experimental-json --output-schema <file>`, Tier B — implemented
    strictly against this repo's own documented-verified flags; NOT
    live-tested, since the `codex` binary is not installed in this build
    environment — a documented follow-up), and `FakeDriver` (deterministic,
    no real CLI, scriptable per task to "good" / "schema-missing" /
    "missing-file" / "blocking" / "error" — the core test-coverage vehicle).
  - `tessctl run` loads + validates a crew-plan, requires its `mission_id`
    to already exist as a mission record (`tessctl mission new` first),
    then executes each stage in order: gate check against the SAME mission
    record `gate-status` reads (never starts early), dispatches each task
    (and its mandatory verifier, when `verifier.required: true`) via the
    chosen driver, reads the contracted return-manifest/verdict artifact
    back off disk itself (never trusts the driver's own summary), and
    on a schema-miss enters the EXISTING typed-retry ledger (`_retry_
    precheck`/the retry-log machinery, unmodified) — changed brief for
    every non-transient cause, capped at 3 attempts, never dispatching a
    4th time past the cap. A verifier's genuine `disposition: BLOCK` is an
    immediate hard halt (not auto-retried); either halt reason writes a
    full per-attempt escalation record to `missions/<id>/escalations/` and
    flips the mission record's own `state` to the existing `code-red` FSM
    value (no `mission.schema.json` change needed).
  - v1 scope, documented: stages dispatch sequentially (real OS-level
    concurrency for `parallel: true` stages is a follow-up — it only
    changes wall-clock time, not correctness); SYNTHESIS (orchestra-
    model.md §4 step 5) is out of scope — `run` executes EXECUTE STAGES
    only.
  - All new logic is isolated in one contiguous "RUN" region of
    `.tess/bin/tessctl`, directly below the MISSION LEDGER region — no
    other region (KEYGEN, RENDER, TRACE, MISSION LEDGER) is touched beyond
    the same three additive touch points those regions themselves already
    established (dispatch table, `build_parser()`, `main()`'s exception
    catch tuple). No new contract type; `run` validates against the six
    contracts (crew-plan, brief, return-manifest, verdict, mission, retry)
    that already exist.
  - 13 new tests (`tests/test_run.py`): a 2-stage plan running end-to-end
    against `FakeDriver` (including a mandatory verifier dispatch); a
    schema-missing return retrying to the 3-attempt cap then escalating
    (asserting the ledger entries, that no 4th dispatch call is ever made,
    and the escalation record + `code-red` state); a verifier BLOCK halting
    before the next stage ever dispatches; a gate left uncleared halting
    with zero dispatch calls; CLI wiring (`tessctl run --driver fake
    --fake-script ...`) end-to-end via subprocess; `missions/**` (including
    the new `returns/`/`escalations/` subdirs) staying invisible to
    `doctor`/`verify`/`lock --check`, exactly like `retries/` already does
    for Goal #5; and two regression tests (added after the live smoke run
    below caught a real bug) proving `ClaudeCliDriver` always constructs its
    CLI invocation with an explicit `--allowed-tools` allowlist, never the
    blanket `--dangerously-skip-permissions` bypass. Full suite green (545
    total, was 532).
  - A live smoke run against the real `claude -p` CLI was performed manually
    during this build (a trivial 1-task plan) — not wired into the
    automated suite (a paid, network-dependent call has no place running
    unattended on every test invocation); a `codex`-driven live smoke is a
    documented follow-up. It caught a genuine bug the FakeDriver tests
    structurally cannot: a headless `claude -p` dispatch with no explicit
    `--allowed-tools` silently DENIES a tool call (e.g. `Write`) with no
    prompt surfaced — the first live attempt burned all 3 retry attempts
    with `failure_state: empty` (the dispatched session never got to write
    its return-manifest at all) before this was diagnosed and fixed by
    passing an explicit, least-privilege `--allowed-tools` allowlist
    (`Read Write Edit Bash Grep Glob` by default, overridable) rather than
    `--dangerously-skip-permissions`. The re-run completed on the first
    attempt, writing a schema-valid return-manifest that independently
    passes `tessctl validate return-manifest`.
- **`tessctl mission` + the typed-retry ledger — mission records as code
  (Goal #5).** Converts two pieces of doctrine PROSE (`conductor/
  doctrine.md`'s five gates, `conductor/subagent-failure-protocol.md`'s
  typed retry protocol) into DETERMINISTIC CHECKS: a weak conductor can no
  longer skip a gate or loop a failed retry, because the tool itself
  refuses to let it.
  - `tessctl mission new <name>` scaffolds a mission record
    (`missions/<id>/mission.md` + `mission.json` — two serializations of
    the same fields, id derived as `<YYYY-MM-DD>-<slug>` with collision
    suffixing) and dogfood-validates what it writes before returning.
    `tessctl mission status <id>` reads it back (human or `--json`),
    including a retry-ledger summary.
  - `tessctl gate-status <id>` — read-only report of which of the five
    canonical gates (the SAME `gate_in` strings `crew-plan.schema.json`
    already defines) are cleared. `tessctl gate clear <gate> --mission <id>
    --evidence <path>` — the write side, added to the existing `gate`
    subcommand group — REFUSES without `--evidence` (argparse-level) and
    REFUSES when the evidence path does not exist on disk; records
    who/when/evidence in the mission record on success.
  - `tessctl retry log <task> --mission <id> --cause <type> --failure-state
    <state> --brief <path>` writes `missions/<id>/retries/<task>.attempt-
    N.md`, refusing (writing nothing) past the 3-attempt cap or for a
    same-brief retry on a non-transient cause (a literal, whitespace-
    trimmed string comparison against the immediately preceding attempt's
    stored brief text — transient causes are explicitly exempted, matching
    subagent-failure-protocol.md). `tessctl retry check` dry-runs the exact
    same decision without writing anything, and without `--cause`/`--brief`
    reports a cap-only check.
  - Two new contracts, `core/contracts/mission.schema.json` and
    `retry.schema.json` (`tier: normal`, matching `crew-plan.schema.json`'s
    precedent), wired into `tessctl validate`/`doctor`/`verify`/
    `lock --check` exactly like the original five. A mission-record lint
    (`_lint_mission`) closes the same class of gap `return-manifest.schema.
    json`'s artifact-existence check already closes: a gate claiming
    `cleared: true` with an `evidence` path that does not exist on disk is
    schema/lint-invalid.
  - `missions/<id>/` is per-project mission DATA, not framework doctrine —
    added to `tess.manifest.json`'s `never_touch` (same fenced-off
    treatment `kb/**`/`clients/*/**` already get), invisible to `tessctl
    restore`/`render`/`update`. `missions/README.md` documents the
    convention.
  - All new command logic is isolated in one contiguous "MISSION LEDGER"
    region of `.tess/bin/tessctl` (directly below `cmd_gate()`), separate
    from the file's existing render-target and verdict-signing regions, to
    keep future rebases across in-flight goals low-conflict.
  - 28 new tests (`tests/test_mission_ledger.py`); full suite green (532
    total, was 504).
  - Scope note: this build does NOT wire `missions/<id>/briefs/`/`verdicts/`
    scaffolding — `core/contracts/brief.schema.json`/`verdict.schema.json`
    already exist and `tessctl validate brief|verdict <file>` already works
    against a file at any path; adding a command that scaffolds those files
    under `missions/<id>/` automatically remains a follow-on (C1/C2's CLI
    wiring, per `docs/ULTIMATE_FRAMEWORK_PLAN.md`).
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
    same core fragments CLAUDE.md composes — zero duplicated doctrine text)
    **[SUPERSEDED 2026-07-08 — see "Fixed" below: this payload measured as
    harmful to a single-agent harness and was re-scoped to a lean worker
    digest before this branch merged]**,
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
    green. (The G3 doctrine-profile fix above — 504 → 527 — is logged under
    "Fixed" at the top of this section, not duplicated here.)
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
- **Goal #8 — mission trace log + OTel GenAI export** (observability, no
  phone-home): `.tess/bin/tessctl` gains an isolated `TRACE` region —
  `tessctl gate pre-commit|pre-push|ci` and `tessctl validate` now append
  exactly one schema-valid JSONL event (`TRACE_EVENT_SCHEMA`, `schema:
  "tess.trace.v1"`) per invocation to `missions/<id>/trace.jsonl` (when a
  mission id is inferable from the `missions/<id>/...` convention) or a
  per-run fallback under `.tess/trace/runs/` (local runtime state, same
  gitignored bucket as `.tess/snapshots/**`/`.tess/staging/**`). New
  `tessctl trace export --format otlp-json` maps the JSONL to [OTel GenAI
  semantic-convention](https://github.com/open-telemetry/semantic-conventions-genai)
  `invoke_agent` internal agent spans (OTLP/JSON, verified against the
  canonical `opentelemetry-proto` example) — legible to any APM that
  understands `gen_ai.*` (Datadog, Honeycomb, New Relic, the OTel Collector)
  without Tess OS ever making a network call: the export is a pure local
  JSON reshape of on-disk JSONL, proven by a static no-networking-import
  scan of the whole engine plus socket-guard tests that monkeypatch
  `socket.socket`/`create_connection`/`getaddrinfo` and call the
  gate/validate/export code paths directly. `tessctl run` (the mechanical
  conductor loop) is not instrumented because it does not exist yet in this
  engine — see this file's own Phase 2 honest re-scope note below. Full
  capture list, the exact attribute mapping, and the no-network guarantee:
  `docs/OBSERVABILITY.md`. 38 new tests (`tests/test_trace_otel.py`); the
  full suite remains green.
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
