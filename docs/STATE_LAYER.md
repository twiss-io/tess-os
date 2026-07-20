# The state layer: one canonical store, every harness mounts it

> **Status: Phase 0.6 — the fenced store, the task store + accountability
> ledger, the memory link, the external-harness-worker LANE, the structured
> STUCK-PACKET, PLUS the SKILL DRAFT SCAFFOLD.** Phase 0.1 built the four
> empty, fenced directories and their leak-proofing. Phase 0.2 landed the
> first two real subsystems on top of that store: `tessctl tasks` (the
> shared task graph, `.tess/state/tasks/`) and `tessctl log` (the
> hash-chained accountability ledger, `.tess/state/ledger/`). Phase 0.3
> lands the third: `tessctl memory adopt` (`.tess/state/memory/`) — the
> mechanism that moves an existing harness-private memory directory's
> contents into the canonical store and replaces the original with a
> symlink, so Claude Code and Codex (or any other adopted harness) read and
> write the SAME memory. Phase 0.4 (issue #125) lands the LANE: earmarking a
> task for a specific worker harness (`target_harness`, `tessctl tasks
> new|set --lane`), filtering a pull to that lane (`tasks pull --lane`), and
> `tessctl tasks handoff` — which PREPARES, never spawns, an external worker
> invocation. Phase 0.5 (issue #129) lands the STUCK-PACKET: `tessctl tasks
> block <id>` — `handoff`'s sibling ("here's a task, go do it" vs. "I got
> stuck, here's everything you need to continue") — transitions a task to
> `blocked` AND records a structured, resumable-by-any-agent packet (why it
> stopped, last-known progress, what was already tried, what's needed to
> unblock). Phase 0.6 (this page's own next section, issue #131) lands the
> SKILL DRAFT SCAFFOLD: `tessctl skill from-task <id>` — the demo-to-skill
> pattern — turns a completed task + its REAL ledger trail into a
> scaffolded, DRAFT, human-reviewed reusable skill under a FIFTH
> `.tess/state/**` subsystem (`.tess/state/skills/`), fenced the same way,
> deliberately never `.claude/skills/` (the live skill set) — never
> auto-activated. Running an actual adopt against any specific instance's
> live memory, and running an actual external-harness process from a
> prepared handoff, are both separate, later, opt-in operations this page
> documents the MECHANISM for, not the live execution of. Any orphan-sweeper
> daemon (or Codex process-spawner/daemon) — INCLUDING one that would
> auto-resume a stuck task the Phase 0.5 packet makes visible, or a curator
> that would auto-promote a Phase 0.6 draft into the live skill set —
> remains NOT built; see "What's deliberately NOT built yet" below.

## The principle

Tess OS is meant to run identically well from Claude Code, Codex, or any
other AGENTS.md-reading harness (`docs/ULTIMATE_FRAMEWORK_PLAN.md`'s adapter
model). For that to be true of *state* — memory, tasks, the retry/mission
ledger, coordination locks — and not just doctrine, the state has to live
somewhere **both harnesses can see and mount**, not inside one harness's
private home directory (`~/.claude/`, `~/.codex/`, etc.). A harness-private
location makes "shared" state an illusion: Claude Code and Codex would each
silently keep their own fork of "memory," and the two would drift the moment
either side wrote something the other never saw.

The rule this page exists to state: **shared state lives in harness-neutral
files inside the project, mounted by every harness — never in a harness's
private home directory.**

## The canonical root: `.tess/state/`

```
.tess/state/
├── memory/     ← cross-harness memory (adopted, not duplicated — Phase 0.3)
├── tasks/      ← the shared task graph (Phase 0.2 CLI)
├── ledger/     ← mission/retry ledger, harness-neutral form (Phase 0.2+)
├── locks/      ← coordination locks between concurrent harness sessions
├── skills/
│   └── drafts/ ← generated DRAFT skills (`tessctl skill from-task` — Phase
│                 0.6); never `.claude/skills/`, never auto-activated
└── receipts/
    └── chain.jsonl ← the ship-gate's own auto-emitted Agent Receipt chain
                       (PR-2, `_gate_emit_receipts_on_clear` in .tess/bin/
                       tessctl, wrapping `tools/receipt-emit/`): one hash-
                       chained, GPG-signed receipt per policy rule the gate
                       accepts as CLEARED (a covering signed APPROVE
                       verdict, or a hard-floor signed sign-off), appended
                       automatically on every `tessctl gate pre-push|ci`
                       PASS. A SIXTH `.tess/state/**` subsystem — same
                       fence, same "auto-generated, machine-local, verified
                       independently of git" operating model as `ledger/`
                       immediately above, not a deliberately-authored
                       committed artifact like a verdict or sign-off (see
                       "Classification" below).
```

This sits inside `.tess/` (already the engine's own runtime-state root:
`.tess/core`, `.tess/bin`, `.tess/snapshots`, `.tess/staging`, `.tess/trace`)
rather than at the project root, because it is the same kind of thing: local
runtime state the keystone engine and its render targets are aware of, not
doctrine content that gets rendered or merged.

## Classification: instance DATA, not framework

`.tess/state/**` is real operator/mission data the moment either harness
starts writing to it — the same category as `missions/**` and `kb/**`, per
the overlay model in `docs/DATA_LEAK_SAFETY.md`. Phase 0.1 wires the same
four-part fence those paths already get, before anything writes to it for
real:

1. **`tess.manifest.json`'s `never_touch`** — `.tess/state/**` is listed
   there, so the framework updater/renderer (`tessctl update` / `render` /
   `restore`) can never read, write, or publish it. There is no
   `.tess/core/state/**` mirror; nothing here is compiled from core.
2. **`.gitignore`** ignores `.tess/state/{memory,tasks,ledger,locks}/*`
   outright (keeping only each subdir's `.gitkeep`) — the same
   content-ignore treatment the `kb/wiki/**` / `missions/**` / `operator/**`
   precedent buckets already get elsewhere in the same file. New files under
   any of the four subdirs are structurally invisible to `git add`,
   independent of every other layer below. (Until issue #110 — found
   reviewing #105 — this only covered `locks/`; `memory/`, `tasks/`, and
   `ledger/` relied on layer 3 alone, which is a pre-commit hook and
   therefore not guaranteed installed on every clone/re-init. A plain
   `git add -A` on an instance that never ran that hook would have silently
   staged real memory/tasks/ledger data. Closed by extending this same
   content-ignore pattern to all four subdirs.)
3. **The publish-clean gate** — `.tess/state/**` is in
   `_PUBLISH_CLEAN_PRIVATE_GLOBS` (`.tess/bin/tessctl`), the commit-side
   control from issue #92/#93. `tessctl doctor --publish-clean` (installed as
   a pre-commit hook by `tessctl gate install-hooks`) refuses a commit that
   stages anything under `.tess/state/**`, regardless of `.gitignore` state
   — a second, independent guarantee for any content that somehow still gets
   staged (e.g. `git add -f`).
4. **The public scaffold ships it EMPTY** — `create-tess` copies the
   template's `.tess/state/{memory,tasks,ledger,locks}/` directories (each
   holding only a `.gitkeep`) but strips any content underneath
   (`EXCLUDE_CONTENT_PREFIXES` in `create-tess/src/ignore.js`), the same
   scaffold-strip treatment `.tess/snapshots`/`.tess/staging` already get.
   Adopters inherit the canonical structure; they never inherit another
   instance's actual memory, tasks, or ledger entries.

All four layers now apply symmetrically to `memory/`, `tasks/`, `ledger/`,
and `locks/` — none of the four subdirectories depends on the pre-commit
hook (layer 3) being installed to stay off a fresh `git add -A`.

## What's built today (Phase 0.1 + Phase 0.2 + Phase 0.3 + Phase 0.4 + Phase 0.5 + Phase 0.6)

Phase 0.1 — the fenced store:

- The four empty, fenced directories above.
- The never_touch / publish-clean / scaffold-strip / gitignore protections
  described above.
- `test_state_never_publishable` (`tests/test_publish_clean_gate.py`) +
  companion coverage in `tests/test_write_gate.py` and
  `create-tess/test/units.test.js` — proves the write-gate denies tessctl
  writes into `.tess/state/**`, the publish-clean gate blocks a commit that
  stages anything under it, and a local-source scaffold never copies real
  content into a produced instance's `.tess/state/**`.
- `tests/test_gitignore_reconciliation.py` — proves the `.gitignore`
  content-level layer itself, independent of the publish-clean hook: a
  fresh file under any of `.tess/state/{memory,tasks,ledger,locks}/` is
  `git check-ignore`d and never appears in `git add -A` staging, while each
  subdir's `.gitkeep` stays trackable (issue #110).

Phase 0.2 — the TASK STORE + ACCOUNTABILITY LEDGER (TASK LEDGER region,
`.tess/bin/tessctl`, directly below the RUN region — a sibling of the
MISSION LEDGER region), ported from Hermes' kanban design
(`kb/wiki/synthesis/2026-07-19-hermes-codebase-fork-study.md` §"their
kanban"):

- **`tessctl tasks new|set|claim|release|pull|render`** — file-per-task JSON
  at `.tess/state/tasks/<id>.json` (`core/contracts/task.schema.json`,
  id `T-<YYYYMMDD>-<slug>-<4hex>`, status enum
  `backlog|ready|in_progress|blocked|review|done|cancelled`). `set` is a
  rev-CAS optimistic-concurrency write (`--expected-rev N` refuses with
  `TASK_CAS_CONFLICT` — no mutation — if the on-disk rev has moved); `claim`
  writes a claim-lease (`host:pid:uuid` + `claimed_at`/`heartbeat_at`) and
  auto-advances `backlog`/`ready` to `in_progress`, refusing a live claim
  held by someone else unless it is stale (`--stale-after`) or `--force`d;
  `render` regenerates `.tess/state/tasks/BOARD.md`, a DERIVED, GENERATED-
  marked kanban view — never a source of truth. Every mutation is
  serialized by a per-task advisory flock
  (`.tess/state/locks/task-<id>.lock`) — contention is scoped to writers of
  the SAME task, never a global lock.
- **`tessctl log append|view|verify`** — a hash-chained, append-only JSONL
  ledger at `.tess/state/ledger/<YYYY-MM>.<origin>.jsonl`
  (`core/contracts/ledger-event.schema.json`), sharded per calendar month
  AND per writer origin so concurrent writers on different machines/
  harnesses never contend on the same file. `append` computes
  `hash = sha256(prev_hash + canonical_json(event minus hash))`; `verify`
  walks a shard's chain and reports the first tamper/break it finds — plus
  (Phase 0.2 hardening below) a removed tail line or a whole deleted shard.
  `tasks new|set|claim|release` auto-log the corresponding
  `task_transition|claim|heartbeat|release|completed|crashed|reclaimed`
  event on every real (non-no-op) write, so the "who picked up a task and
  progress, cleared or stuck" trail can never be silently skipped by a
  caller who forgot a separate logging step.
- **Phase 0.2 hardening (closes the #113 review gate, issue #114)** — five
  fixes to the substrate above before any consumer (in particular the
  future orphan-sweeper) trusts it:
  - `tasks set --heartbeat` now requires `--host`/`--pid`/`--uuid` matching
    the CURRENT claim (refused `TASK_NOT_CLAIMANT` otherwise, or `--force`)
    — the previous version refreshed a claim's heartbeat with no identity
    check at all, a forgeable liveness signal that let anyone who knew a
    task id renew a claim they never held, defeating `--stale-after`
    reclaim (Reid HIGH).
  - `tasks claim`'s default `--uuid` (when not explicitly given) is now a
    STABLE uuid5 derived from `(host, pid)`, not a fresh `uuid4()` per call
    — a same-process re-claim is now correctly recognized as the same
    claimant (a clean heartbeat) instead of misclassified as a stranger
    (Reid MEDIUM).
  - Each ledger event now carries a monotonic per-shard `seq`; every append
    also writes a co-located `.tip` sidecar and upserts a ledger-wide
    `.registry.json` (`{seq, count, hash}` per shard). `log verify`
    cross-checks the tail it actually finds against both, so a removed TAIL
    line (which a pure `prev_hash` walk cannot notice — nothing remains to
    break a chain link against) or an entire deleted shard (undiscoverable
    by directory-globbing alone) is DETECTED, not silently reported OK
    (Cyra M1).
  - `_prune_stale_locks` no longer unlinks a lock file on mtime alone: it
    first confirms, via its OWN non-blocking flock attempt, that nobody
    currently holds it, then re-checks the path still resolves to the SAME
    inode it just locked before unlinking — closing a TOCTOU where a
    concurrent unlink+recreate could let two different processes each
    believe they hold the sole lock on "the same" path via two different,
    non-excluding inodes (Cyra M2).
  - Wording fixes (no behavior change): the schema/engine no longer says
    "tamper-evident" or "instead of a signature" without qualification —
    see "Trust boundary" below (Cyra L1/L2).
  - **Migration note (Cyra-LOW/Reid-MED, #115 review, closed later):** a
    shard written before this hardening landed has NO `seq` key on any of
    its lines at all — that is a LEGACY on-disk shape, not tampering.
    `log verify` reports a shard containing legacy lines as `LEGACY`
    (hash chain still fully verified), never `TAMPERED`; `log append` to a
    legacy shard backfills the next `seq` from the shard's own line count
    instead of hard-refusing. No manual migration step is required — the
    very next append to an old shard silently upgrades it to the
    seq-aware format from that line onward.
- `tests/test_task_store.py`, `tests/test_accountability_ledger.py`,
  `tests/test_task_ledger_fence.py` — CRUD + schema validation, claim-lease
  + a REAL two-process concurrency proof (no lost update), hash-chain
  append/verify/tamper-detection, and — the last file — proof that the
  SAME #105/#111 fence blocks a genuinely CLI-produced task file and ledger
  shard, not just a synthetic placeholder.

## Trust boundary — what this substrate does NOT guarantee

Two precise scope notes (Cyra L1/L2, closing the #113 review gate):

- **Claim-leases are advisory coordination, not authentication.** A
  `claim`'s `host:pid:uuid` + `heartbeat_at` is a cooperative bookkeeping
  convention for well-behaved callers sharing the same `.tess/state/`
  filesystem — `tasks claim`'s "refuse unless stale/`--force`" and `tasks
  set --heartbeat`'s claimant-identity check (Phase 0.2 hardening above)
  prevent one COOPERATING agent from accidentally stepping on another's
  live claim. Neither is a security boundary: the real trust boundary is
  filesystem write access to `.tess/state/**` itself — anything that can
  write there can write any `host`/`pid`/`uuid` triple it likes, claimed or
  not. Do not treat a claim-lease as proof of who is actually doing the
  work, only as a coordination signal among cooperating callers.
- **The ledger's hash chain is unsigned.** `tessctl log verify` (with the
  Phase 0.2 seq/tip/registry hardening above) detects a NON-RE-CHAINED
  edit to an already-appended line, a removed/reordered line, a removed
  tail line, or a deleted whole shard. It does NOT detect a determined
  adversary with filesystem write access who recomputes the entire
  downstream chain to match an edited or shortened history — such a
  fully-and-consistently re-chained forgery would still `verify` OK. This
  is an integrity/accident-detection mechanism, not a cryptographic
  signature: it carries no signer identity and makes no non-repudiation
  claim (contrast with `verdict.schema.json`'s actual GPG-signed
  verdicts, which do).
- **`.tess/state/receipts/chain.jsonl` (PR-2) does NOT share the ledger's
  "unsigned" limitation above — but it inherits `tools/receipt-emit/`'s own
  documented one: EVERY receipt carries a real GPG signature (the embedded
  decision's own signature PLUS a second, envelope-level `receipt_signature`
  — `core/contracts/agent-receipt.schema.json`), independently verifiable
  via `tools/receipt-verify/receipt_verify.py verify-chain` with no
  dependency on `.tess/state/**`, git, or this repo's own policy.yaml at
  all. What it is NOT is trust-anchored: `core/policy/policy.yaml`'s
  `verifier_keys`/`signoff_keys` ship empty by design, so "this receipt's
  signature verifies" never by itself means "a trusted party's approval is
  enforced by policy" until a real key-ceremony registration happens
  (Xavier-gated, not performed by any automation in this repository) — see
  `tools/receipt-emit/README.md`'s "Honest label" and
  `docs/TRUST_BOOTSTRAP_SECURITY_DESIGN.md`. A receipt-emit FAILURE (no
  matching private key in the ambient keyring — routinely true on an
  unattended CI runner, since the six named verifiers' private keys are
  deliberately never staged there) is deliberately NON-BLOCKING for the
  ship-gate's own PASS/BLOCK decision, but is never silent either — see
  `_gate_emit_receipts_on_clear`'s own docstring in `.tess/bin/tessctl` for
  the full fail-closed-the-SHIP-decision vs. non-silent-the-RECEIPT-gap
  split, surfaced as a structured `receipt_gaps` entry in `tessctl gate`'s
  own output and trace log.

Phase 0.3 — `tessctl memory adopt` (MEMORY ADOPT region, `.tess/bin/tessctl`,
a sibling of the TASK LEDGER region): the cross-harness MEMORY LINK.

- **The mechanism, not a new memory format.** Claude Code (and, eventually,
  other harnesses) already maintain a harness-private memory convention — an
  auto-managed directory of topic files plus an index (`MEMORY.md`) at a
  well-known per-project path. `tessctl memory adopt` does not invent a new
  format; it makes the EXISTING one canonical: it moves that directory's
  contents into `.tess/state/memory/` and replaces the original with a
  symlink pointing at it, so the harness's own native memory reads/writes
  transparently land in the ONE store every harness mounts from then on.
- **Safe by construction.** Dry-run by default for BOTH directions —
  forward-adopt and `--revert` alike require `--yes` to mutate anything —
  and the planning phase (idempotency check, source/target enumeration,
  per-file conflict detection) is read-only start to finish, so even a
  refused call never touches disk. Refuses `--from` and `--to` resolving
  to the same path, or one nested inside the other, BEFORE any mutation —
  a self-targeted adopt would otherwise treat the source's own content as
  "already present," copy nothing elsewhere, then delete the only copy of
  it. That comparison is by INODE IDENTITY (`os.path.samefile`), never by
  string equality of the resolved paths — `Path.resolve()` preserves
  as-typed case, but the real deployment filesystems (macOS APFS, Windows
  NTFS, both default case-insensitive) treat differently-cased spellings
  of the same directory as one and the same file on disk, which a string
  compare would miss (falls back to a case-fold-aware string compare only
  when a path does not yet exist, since `samefile` requires both sides to
  exist). Refuses a non-empty target without `--merge` (but a bootstrap call
  with no source content never needs `--merge` just because a DIFFERENT
  harness already adopted). Refuses a source entry that is a symlink —
  never silently dereferenced; only a flat directory of real memory files
  is supported. Refuses any real filename+content conflict outright,
  atomically, with zero partial writes. Idempotent against an
  already-adopted source (a clean no-op, not an error). Every `OSError`
  reachable from planning or the mutate-for-real path — including the
  rmtree → symlink → manifest-write swap — is converted to a typed
  `MemoryAdoptError`, never a raw traceback; that swap is made crash-safe
  by writing the manifest BEFORE the source is ever touched (every copied
  file is already durably in the store by then) and by creating the
  target symlink at a verified temporary sibling path before removing the
  original directory, so a failure anywhere in the swap leaves the source
  fully intact rather than half-deleted with nothing to show for it.
  Verifies a real round-trip read/write THROUGH the new symlink after
  adopting, and automatically rolls the whole adopt back (via the same
  revert path) if that check ever fails.
- **`--revert`** undoes an adopt from THAT adopt's own recorded manifest
  (`.tess/state/memory/.tess-memory-adopt.<harness-slug>.<source-path-hash>.json`
  — one per adopted (harness, source-path) pair, never a single shared
  file two harnesses could clobber each other's revert record with; the
  source-path hash exists because `--harness` is free-text with no fixed
  choice set, so two differently-spelled names for what a human intends as
  the same or different harness — e.g. `Claude-Code` / `claude_code` — can
  slugify identically, and the hash keeps them from clobbering each
  other's manifest filename even though their slugs collide; `--revert
  --harness X` with no `--from` locates the manifest by slug PREFIX, not
  by reconstructing the hash, and refuses if that slug has more than one
  recorded source path) — restoring exactly the files that manifest
  recorded, never the store's current full contents (a second harness's
  own separately adopted/merged content, or ordinary post-adopt shared
  writes, is left untouched). Of the recorded files, only the strict
  subset THIS adopt itself copied in (`newly_copied_files`) is a
  CANDIDATE for removal from the store on revert; a file that was already
  byte-identical in the store before this adopt ran is copied back into
  the restored private directory but LEFT in the store, because another
  still-adopted harness may be symlinked to it and depend on it. That
  protection is symmetric, not one-directional: a `newly_copied_files`
  candidate (this harness's OWN original copy) is also downgraded to
  copy-back-but-leave-in-store if ANY OTHER still-live harness's manifest
  references the same filename in its own `source_files` — the reverse
  case where THIS harness was the original owner and a second harness
  later deduped against it. Refuses (no mutation, no guessing) if the
  recorded source path is not currently a symlink resolving to the store
  — that means state already drifted since adopt.
- **`tessctl doctor`'s memory-link check** — non-fatal, informational only
  (never affects doctor's errors/warnings/exit code, in either the
  not-adopted or the adopted-but-broken case): per adopted harness, is the
  expected symlink present and resolving, is the store writable, and does
  `.tess/state/memory/MEMORY.md`'s own index cohere with what's actually on
  disk (broken links, unindexed files) — surfaced for a human to notice,
  never gated on.
- **Codex/generic pointer** — `.tess/core/templates/agents-md/AGENTS.md.tpl`
  (`{{WORKER_SESSION_MEMORY}}`) tells a worker-profile harness to read
  `.tess/state/memory/MEMORY.md` at session start and write durable
  learnings back to the same store, never a private copy. Claude Code needs
  no equivalent: its own harness already auto-reads its memory index
  natively — this pointer exists because Codex/generic harnesses have no
  such built-in behavior. A pure repo/state fact, not orchestration doctrine
  — `tests/test_memory_adopt_fence.py` proves it introduces no
  worker-profile doctrine-denylist violation (G3).
- **Shared Tasks pointer (issue #118)** — the same `AGENTS.md.tpl`
  (`{{WORKER_SHARED_TASKS}}`, `.tess/core/templates/agents-md/shared-tasks.md`)
  is `{{WORKER_SESSION_MEMORY}}`'s sibling for the TASK STORE half of the
  shared brain: it tells a worker-profile harness to `tessctl tasks pull`
  before starting new work, `tessctl tasks claim <id>` with its OWN
  `--host`/`--pid` before working a task, and `tessctl tasks set` /
  `tessctl log append` to record progress back to the SAME shared board —
  never a private, harness-only list. `codex` is enabled by default in this
  repo's own `tess.manifest.json` as of this issue (a deliberate manifest
  edit — see `render_targets._doc`), so a rendered Codex session's
  `AGENTS.md` now carries both cross-harness state-mount pointers end to
  end. Same category as the memory pointer above — a repo/CLI fact, not
  orchestration doctrine (nothing from `WORKER_DOCTRINE_DENYLIST`).
- Running an actual adopt against any specific instance's own live memory
  (e.g. a real `~/.claude/projects/<flattened>/memory/`) is explicitly OUT
  OF SCOPE for the PR that built this mechanism — a separate, later, opt-in
  instance operation each adopter runs (or is run for them) deliberately,
  not something this mechanism's existence performs on its own.
- `tests/test_memory_adopt.py` — dry-run purity, bootstrap + real adopt,
  idempotency, every refusal (ambiguous existing symlink, non-directory
  source, non-file source entries including symlinks, non-empty target
  without `--merge`, `--from`/`--to` resolving to the same path or one
  nested inside the other, a real merge conflict), `--merge`
  skip-on-identical-content, `--revert` (dry-run-by-default + `--yes` gate,
  multi-harness disambiguation including the harness-slug-collision case,
  drifted-state refusal, and the two-harness shared-file preservation
  case), automatic rollback on a simulated round-trip failure, crash-safety
  of the rmtree → symlink → manifest-write swap under injected `OSError`
  failures (proven fully-intact, never half-adopted), a guarded
  `read_bytes()` failure during planning, the doctor memory-link check's
  four states (not-adopted / clean / broken-symlink / index-coherence
  gaps), the `--from`/`--to` self-destruct guard's inode-identity check on
  a case-insensitive filesystem (both the exact-same-dir and the nested
  variant — skipped, not falsely passed, on a genuinely case-sensitive
  filesystem where the repro cannot occur), and the reverse-direction
  two-harness shared-file preservation case (the harness that ORIGINALLY
  OWNED a file reverting while a second, still-live harness had since
  deduped against it).
- `tests/test_memory_adopt_fence.py` — the SAME #105/#111 fence proof
  `test_task_ledger_fence.py` gives the task store/ledger, against a
  genuinely CLI-adopted memory file and its adopt manifest (source
  directory deliberately outside the git working tree, mirroring a real
  harness home-directory layout) — plus the AGENTS.md render assertions
  above.

Phase 0.4 — the external-harness-worker LANE (TASK LEDGER region, issue
#125): making a worker harness (first: Codex) a first-class ROUTING target
on top of the Phase 0.2 task store, not a new subsystem of its own.

- **`target_harness` — a task-record field, not a label/tag.** Adds one new
  required, enum-constrained field to `task.schema.json`
  (`codex | claude-code | any`), the minimal representation that fits the
  existing schema: a scalar field gets `enum` validation for free and reads
  identically to every other structured task field (`status`, `owner`), a
  free-text label/tag would need its own ad hoc "exactly one routing tag"
  convention layered on top of a facility (`evidence`, generic `notes`)
  this store doesn't have. Named `target_harness`, deliberately NOT
  `harness` — that name is already taken on `tasks new|set|claim|release`
  (required, meaning the ACTING harness — who created/claimed/mutated a
  task, recorded in `created_by`/the ledger's `actor.harness`); reusing it
  for a routing lane would collide with that established meaning on the
  very same subcommands. `any` (`DEFAULT_TASK_LANE` in `.tess/bin/tessctl`)
  is the default `tessctl tasks new` seeds when `--lane` is omitted —
  eligible for every harness, i.e. the exact PRE-LANE behavior: a task
  nobody explicitly earmarks is filtered and claimed identically to before
  this field existed.
- **Legacy-record backward compatibility (Cyra + Reid, PR #126 review,
  independently reproduced).** A task written before this field existed —
  `.tess/state/tasks/**` is gitignored instance data, so a real deployed
  install genuinely has these — has no `target_harness` key on disk at
  all. `_task_read` (the ONE shared read path every write, `pull`, and
  `render` call goes through) now does
  `record.setdefault("target_harness", DEFAULT_TASK_LANE)`, healing it in
  memory on first touch — the exact same "legacy, not tampered; heal on
  next write, no manual migration" discipline this region's own ledger
  side already established for a seq-absent shard line (see the Phase 0.2
  hardening's "Migration note" above). `tessctl tasks set|claim|release|
  handoff` against a legacy record now succeed and heal the field to `any`
  on disk as a side effect of the mutation already happening; `pull`/
  `render` heal it in memory only (read-only commands never write back).
  The standalone `tessctl validate task <path>` command is a deliberate
  exception — it still flags a missing `target_harness` on an arbitrary
  file, since its whole purpose is surfacing a genuine schema deviation,
  not silently patching its input.
- **Validate-before-write, never the reverse.** The FIRST version of this
  region's write path (`_tasks_write_locked`, and `_cmd_tasks_new`) wrote
  the candidate record to disk, THEN dogfood-validated the file it had
  just written — so a validation failure left a genuinely mutated record
  committed to disk with NO corresponding ledger event (every caller's
  `_ledger_auto_log` runs only after the write helper returns
  successfully), a silent state/ledger divergence first reproduced against
  a legacy record missing `target_harness`. Both write paths now validate
  the CANDIDATE record BEFORE `_task_atomic_write` ever commits it
  (`_validate_task_instance_or_raise`) — a failure now aborts with nothing
  persisted, closing the whole CLASS of write-then-fail divergence, not
  just this one field's trigger. This brings the TASK STORE's own write
  path into the SAME already-correct ordering `_ledger_self_validate_or_
  raise` has always used for ledger events (validate the in-memory value,
  then append) — the task side was the outlier, not the ledger side.
- **`tessctl tasks new|set --lane <codex|claude-code|any>`** sets it (the
  CLI flag is `--lane`, not `--harness`, on both subcommands — `new`/`set`
  already require `--harness` for the ACTOR; `--lane` avoids the collision
  and matches the vocabulary this whole feature is scoped under). `set
  --lane` is a rev-CAS write through the SAME `_tasks_write_locked` path
  every other `tasks set` mutation uses — no forked write logic.
- **`tessctl tasks pull --lane <codex|claude-code>`** filters to a task
  earmarked for that harness PLUS every task earmarked `any` — "a Codex
  worker pulls its lane" also means it sees every unmarked task, not just
  ones explicitly earmarked `codex`. Omitting `--lane` (the default)
  applies no lane filter at all; every existing `pull` invocation keeps
  returning exactly what it always did.
- **`tessctl tasks claim` is UNCHANGED — the lane is advisory routing, not
  claim-time enforcement.** A task earmarked `codex` can still be claimed
  by a `claude-code` actor; `claim` records whichever `--harness` the
  claimant supplies, same trust-boundary class the existing claim-lease
  documentation above already states (a cooperative bookkeeping
  convention, not authentication).
- **`tessctl tasks handoff <id> --harness <codex|claude-code>`** — PREPARES
  (never spawns) a handoff to an external worker harness: earmarks the
  lane (idempotent — a no-op if already earmarked that way, via the SAME
  CAS-write path `set --lane` uses), logs a `handoff` ledger event, and
  prints the exact copy-pasteable invocation (`tasks claim` →
  `tasks set --status in_progress` → `tasks set --status review` →
  `tasks release`) an operator hands to a fresh session of that harness,
  pointing it at the SAME shared brain (`.tess/state/tasks/`,
  `.tess/state/memory/`) the render-target mounts. `--harness` here means
  the TARGET (`TASK_HANDOFF_LANES` — `codex`/`claude-code`, `any` excluded:
  a handoff is inherently addressed to ONE specific worker); a separate
  `--by-harness` (default `orchestrator`) records who is PREPARING it, kept
  distinct from `--harness` so `handoff`'s literal invocation shape needs
  no second required flag. This command has NO process-spawning
  capability — see "What's deliberately NOT built yet" below. The printed
  invocation captures `$HOST`/`$PID`/`$UUID` into shell variables ONCE and
  threads the SAME identity through `claim` and `release` (Reid LOW, PR
  #126 review — the first version had `release` reference a
  "<same --uuid claim used>" placeholder `claim` never actually surfaced,
  so the block was not literally copy-paste-runnable end to end).
- **Accountability — two new ledger event classes, the SAME append path.**
  `earmarked` (logged by `tasks new --lane`/`tasks set --lane` when the
  lane is the ONLY thing that changed — the SAME structural
  only-this-changed classification `--heartbeat` already uses, not a
  string match) and `handoff` (logged by `tasks handoff`) both go through
  the EXISTING `_ledger_auto_log` → `_log_append_event` hash-chain append
  path — no fork of the chain algorithm, no new shard format. "Who
  earmarked, target harness" is the `earmarked`/`handoff` event's own
  actor + summary; "who claimed, which harness" is the pre-existing
  `claim` event, unchanged.
- **`BOARD.md` / `tasks pull`** — `tasks render` adds a `[lane: <harness>]`
  marker to a board line ONLY for a task actually earmarked to one
  harness (an unmarked task's line is byte-for-byte what it rendered as
  before this field existed); `tasks pull`'s human-readable output gains a
  `lane=<harness|any>` column.
- `tests/test_task_lane_handoff.py` — earmark (at creation and via `set`)
  → `pull` lane filtering (including combined with `--unclaimed`, and the
  "no --lane at all" no-op-filter case) → `claim` still records whichever
  harness actually claims a task, lane mismatch or not → `handoff`
  (idempotent earmark, rejects `any` as a target, unknown-task refusal,
  the printed invocation's exact command shapes including `$HOST`/`$PID`/
  `$UUID` threading between `claim` and `release`, JSON output) →
  `_render_handoff_invocation` pure-function determinism → `BOARD.md`
  lane marker → full `log verify` chain integrity after
  `earmarked`/`handoff` events → schema/lint coverage for the new field
  and the two new ledger event classes → a dedicated legacy-record section
  (`set`/`claim`/`release`/`handoff` all heal + log correctly against a
  record missing `target_harness`; `pull`/`render` heal in memory without
  writing back; the standalone `validate task` command still flags it by
  design; an engine-level proof that `_tasks_write_locked` leaves disk
  byte-for-byte untouched, with no ledger entry, when a candidate record
  fails validation for ANY reason).
- **Honest constraint (mirrors #121's own framing):** no live Codex-runtime
  end-to-end run is possible in the environment this was built in — there
  is no Codex runtime to spawn or drive here. This verifies the LANE
  MECHANISM + wiring (a real Codex worker reading its earmarked lane via
  `pull --lane codex`, or acting on a prepared handoff, WOULD pick up the
  work) — a live smoke test with an actual Codex session is a deferred
  follow-up, not claimed as done here.

Phase 0.5 — the STRUCTURED STUCK-PACKET (TASK LEDGER region, issue #129):
`tessctl tasks handoff`'s sibling — `handoff` routes a task FORWARD ("here's
a task, go do it"); `tasks block` captures a resumability packet AT THE
POINT OF FAILURE ("I got stuck, here's everything you need to continue").
Directly serves the TASK LEDGER region's own header comment — quoting
Xavier's re-aimed vision — "task list, updates, accountability list, whoever
picked up a task and progress, cleared or **stuck, resumable by any
agent**":

- **`task.schema.json`'s new `blocked` field** — `null` unless the task was
  blocked via `tessctl tasks block`, otherwise a `BlockedPacket`: `reason`
  (enum — `required_input | failed_dependency | gate | decision_needed |
  other`), `summary` (one-line), `progress` (last-known state — what was
  accomplished, where it stopped), `attempted` (array — what was already
  tried, may be empty), `needed` (what unblocks it), `blocked_at`
  (timestamp), `blocked_by` (`{harness, session}`, the SAME shape
  `created_by` already uses). Added as a REQUIRED (but nullable) field —
  the exact same "new required field, healed on read" pattern
  `target_harness` established in Phase 0.4, not a new convention.
- **Distinct from the pre-existing `status: "blocked"` enum value.** A task
  can still reach `blocked` status via a BARE `tessctl tasks set --status
  blocked` — unchanged, fully supported, and leaves `blocked: null` (proven
  by a dedicated backward-compat test, since Phase 0.5 adds a schema/lint
  constraint that could plausibly have broken this pre-existing call
  shape). `tessctl tasks block` is a richer, ADDITIVE way to reach the same
  status: it captures the resumable context a bare status transition alone
  cannot.
- **`tessctl tasks block <id> --reason ... --summary ... --progress ...
  --needed ... [--attempted ... ...] --harness ...`** — transitions
  `status` to `blocked` (a no-op status-wise if already there) and writes a
  FRESH packet through the SAME `_tasks_write_locked` CAS path every other
  mutator uses (no forked write logic). `--reason`/`--summary`/
  `--progress`/`--needed` are all required; `--attempted` is repeatable and
  optional. A RE-block (calling `tasks block` again on an already-blocked
  task) REPLACES the packet — `blocked_at` is always the current call's
  timestamp, never preserved/merged like a claim heartbeat — because a
  re-block is a genuinely NEW stuck event, not a liveness refresh of the
  same one; each call logs its own `blocked` ledger line.
- **Accountability — one new ledger event class, the SAME append path.**
  `blocked` (logged by `tessctl tasks block`) goes through the EXISTING
  `_ledger_auto_log` → `_log_append_event` hash-chain append path — no fork
  of the chain algorithm, no new shard format, same pattern `earmarked`/
  `handoff` already established in Phase 0.4. A packet being CLEARED is
  NOT a separate event class — see the next bullet.
- **Resumability — visibility + an explicit clearing decision, never
  implicit.** `tessctl tasks pull --status blocked` (an EXISTING filter,
  no new flag needed) surfaces every stuck task — the accountability-list
  visibility Xavier's vision calls for, so nothing stuck is silently
  stranded. `tessctl tasks claim` on a blocked task does NOT clear the
  packet (mirrors the pre-existing "claiming a blocked task does not
  silently un-block it — that is an explicit `tasks set --status`
  decision" precedent, CLAIM_AUTO_ADVANCE_FROM's own docstring, applied
  here to the packet too). `tessctl tasks set --status <away-from-blocked>`
  and `tessctl tasks release --status <away-from-blocked>` (BOTH write
  paths that can move a task's status — release's own `--status` flag is a
  second, independent path from `set`) DO clear a present packet, as an
  explicit side effect of that SAME write — logged under the status
  change's own `task_transition` (or `earmarked`) event, never a separate
  `unblocked` ledger class. Re-setting status to the SAME `blocked` value
  is correctly recognized as NOT a departure and leaves the packet
  untouched.
- **`_lint_task`'s new relational invariant is ONE-DIRECTIONAL.** A packet
  present implies `status == "blocked"` (catches a hand-edited or
  otherwise-inconsistent record — plain JSON Schema cannot express a
  cross-field rule like this). The REVERSE is explicitly NOT required —
  `status == "blocked"` with `blocked: null` is valid, preserving the bare
  `set --status blocked` path described above.
- **Legacy-record backward compatibility** — the SAME pattern Phase 0.4
  established for `target_harness`: a task record written before `blocked`
  existed has no such key at all; `_task_read` heals it to `null` in
  memory on first touch (no separate migration command), and `tasks
  set|block` against such a record succeeds and heals + logs correctly —
  no state/ledger divergence.
- **Explicit scope boundary (Xavier's own fence, unchanged from Phase 0.2's
  original one — see "What's deliberately NOT built yet" below).** This
  phase builds the stuck-packet MECHANISM only: structured capture,
  ledger accountability, and `pull`-based visibility/resumability. It does
  NOT build an autonomous orphan-sweeper that would auto-resume a stuck
  task unattended — WHO/WHAT triggers a resume of visible stuck work stays
  a separate, later, Xavier-gated trust-boundary decision, exactly as it
  already was for claim-lease staleness.
- `tests/test_task_stuck_packet.py` — `block` basics (packet fields,
  required flags, `--reason` enum, `--attempted` repeatable/optional,
  human + JSON output, claim-independence) → re-blocking replaces the
  packet and logs a second event → resumability (`pull --status blocked`,
  claim does not clear, `set`/`release --status` away-from-blocked DOES
  clear, re-setting to the same `blocked` value does not) → backward
  compatibility (the bare `set --status blocked` path) → a dedicated
  legacy-record section (`set`/`block`/`pull` all heal `blocked: null`
  correctly against a record missing the field; an engine-level proof that
  `_tasks_write_locked` leaves disk byte-for-byte untouched, with no
  ledger entry, when a candidate `blocked` value fails validation) →
  schema/lint coverage for the new field, its `BlockedPacket` shape, and
  the new ledger event class.

Phase 0.6 — the SKILL DRAFT SCAFFOLD (SKILL DRAFT SCAFFOLD region,
`.tess/bin/tessctl`, a sibling of AUDIT PACK, issue #131): demo-to-skill —
the "gets smarter from your work" pattern. `tessctl skill from-task <id>`
turns a completed task + its REAL ledger trail into a scaffolded, DRAFT,
human-reviewed reusable skill.

- **Inspection grounding.** `.claude/skills/*/SKILL.md` (mirrored core-
  managed at `.tess/core/skills/*/SKILL.md`) is a real skill format — YAML
  frontmatter (`name`/`description`, optionally `allowed-tools`/`source`/
  `triggers` — the shipped skills use a loose, non-schema'd superset) plus a
  progressive-disclosure markdown body, consumed NATIVELY by the Claude Code
  host's own skill loader. There is no in-repo loader/parser/curator for
  this format anywhere in `.tess/bin/tessctl` prior to this phase. This
  build generates INTO that existing real format — it does not invent a new
  one, and it does not build a curator or a loader (neither exists in-repo
  to build against; the host's own progressive disclosure IS the loader).
- **`tessctl skill from-task <id> --harness H [--out DIR] [--force]
  [--session S] [--persona P] [--json]`** — the full, real flag set; there
  is no `--slug` flag. Reads the task record (`.tess/state/tasks/<id>.json`)
  and every ledger event referencing it (`_skill_collect_task_events`,
  reusing the AUDIT PACK region's own `_audit_collect_events_by_shard` — no
  forked task-scoped ledger scan), then writes two files to
  `.tess/state/skills/drafts/<slug>/` by default — `<slug>` (here and in
  `--out`'s own help text) is a PLACEHOLDER for the auto-derived directory
  name, not a CLI parameter: the task title's kebab-slug plus the task id's
  OWN trailing 4-hex uniqueness suffix, deterministic and collision-safe,
  no invented second id, no operator input:
  - **`SKILL.md`** — real progressive-disclosure frontmatter/body,
    `status: draft`, a `## Step sequence` built ONLY from the REAL matched
    ledger events (event class, verbatim `summary`, actor, timestamp —
    never invented text), a `## Reusable instructions` section built ONLY
    from the task record's own `notes`/`evidence` (verbatim, both APPEND-
    ONLY human-authored channels per `task.schema.json`), and a
    `## Provenance` trailer pointing back at `provenance.json` plus the live
    `tessctl log view --task <id>` / `tessctl audit export --task <id>` for
    independent re-verification.
  - **`provenance.json`** — the full generator input verbatim (source-task
    snapshot + every matched ledger event), the SAME
    "manifest.json+SUMMARY.md, one generator, two serializations" precedent
    the AUDIT PACK region already established — traceable back to the
    ledger without a live re-query.
- **Honesty is the point, again.** `_skill_trail_completeness` classifies
  every generated draft as `empty` (no matched ledger events — in practice
  unreachable through the normal CLI, since `tasks new` itself always
  auto-logs one creation event, but a real defensive/tested case), `
  mechanical-only` (events exist, no task notes — the trail shows WHAT
  happened, not WHY), or `narrated` (at least one recorded note). A THIN
  trail (`empty`/`mechanical-only`) produces a THIN scaffold: no fabricated
  procedural prose, only explicit `gap_flags` naming exactly what a human
  must fill in before the draft is authoritative. A source task not marked
  `done` gets a prominent `SKILL.md` warning banner too.
- **Never auto-activated.** Writes to `.tess/state/skills/drafts/` — a
  FIFTH `.tess/state/**` subsystem, with the SAME four-layer coverage
  memory/tasks/ledger/locks already get — but only TWO of the four layers
  needed an actual edit for this subsystem: `never_touch`
  (`tess.manifest.json`) and publish-clean's own
  `_PUBLISH_CLEAN_PRIVATE_GLOBS` already list `.tess/state/**` recursively,
  so both AUTO-COVER `.tess/state/skills/**` via that existing glob, with
  zero new entries required. The `.gitignore` content-ignore entry and the
  `create-tess` scaffold-strip exclusion (`EXCLUDE_CONTENT_PREFIXES`) are
  the two that ARE per-subsystem and were NEWLY ADDED for `skills/` in this
  phase. Coverage across all four layers is complete and correct either
  way — the distinction is only which ones needed a code change.
  Deliberately NEVER `.claude/skills/` (the LIVE, core-managed, host-loaded
  skill set) — and as of issue #133, `tessctl skill from-task --out` itself
  refuses (`SkillError`, unconditionally, `--force` does not override it)
  any target that path-normalize-resolves under `.claude/skills/`, catching
  a `..` traversal or a pre-planted symlink the same way as the literal
  path (`_skill_reject_out_under_claude_skills`) — closing the one
  remaining operator-explicit path into the live skill set. **★ CRITICAL
  hardened (Cyra, live-reproduced on macOS, PR #140 re-review):** the
  refusal is INODE-IDENTITY based (`os.path.samefile`, reusing
  `_path_is_prefix`/`_paths_are_same_location` from `tessctl memory
  adopt`'s own PR #117 fix verbatim), never a case-sensitive string
  comparison — the first version compared `Path.resolve()` output with
  `Path.is_relative_to()`, which macOS APFS/Windows NTFS's case-
  insensitivity bypassed (`--out .CLAUDE/skills/evil-skill` resolved to a
  different STRING than the real, same-inode `.claude/skills`) while
  Linux CI's case-sensitive filesystem never exercised the path, letting
  it ship green. No promotion command, no curator, no autonomous loop
  exists in this phase; a human/curator reviews a draft and promotes it
  manually, entirely outside this region.
- **Accountability — one new ledger event class, the SAME append path.**
  `skill_generated` (logged by `tessctl skill from-task`) goes through the
  EXISTING `_ledger_auto_log` → `_log_append_event` hash-chain append path
  — no fork of the chain algorithm, same pattern `earmarked`/`handoff`/
  `blocked` already established. Generating a draft never mutates the
  source task record itself — no `_tasks_write_locked` call, read-only
  against the task store; the ledger line is the sole accountability
  artifact of the generation.
- `tests/test_skill_from_task.py` — a narrated (notes + evidence) task's
  scaffold surfaces the real notes/evidence verbatim and a step sequence
  matching the real ledger summaries exactly → a mechanical-only (no notes)
  task's scaffold flags the gap and fabricates nothing → an engine-level
  `empty`-trail case (a task record with zero matching ledger events)
  produces the explicit "no derivable step sequence" gap, not silently
  narrated content → frontmatter is valid YAML with `name`/`description`
  present (the loadable-format proxy check) → `--out`/`--force` conflict
  handling → an unknown task id is refused with a clear message → the
  `skill_generated` ledger line is written, schema-accepted, and shows up
  in a subsequent `tessctl audit export --task <id>` → generation never
  touches `.claude/skills/` (the auto-activation scope-boundary check) →
  (issue #133) an `--out` target under `.claude/skills/` is refused,
  including via a literal path, a `..` traversal, and a symlink whose
  resolved target lands there, and refusal is unconditional (`--force`
  does not clear it) → an FS-independent regression test of the
  INODE-IDENTITY comparison itself (a same-inode, differently-spelled
  pair constructed via symlink — holds on case-sensitive AND
  case-insensitive filesystems, never relying on which one the test
  runner happens to be) plus an opportunistic, runtime-gated test of the
  real macOS/Windows case-fold scenario end to end via the CLI whenever
  the runner's own filesystem actually supports it → the `skill_generated`
  ledger event recording the resolved `--out` target → a relative `--out`
  resolving against `root`, not the caller's cwd.

## What's deliberately NOT built yet

- **The orphan-sweeper** — a daemon/process that would scan
  `.tess/state/tasks/*.json`'s claim-leases and `.tess/state/ledger/**` for
  dead-PID claims and auto-resume/re-dispatch abandoned work. Phase 0.2
  builds ONLY the substrate such a sweeper would read (claim-lease +
  heartbeat fields, and `claim`/`heartbeat`/`reclaimed`/`crashed` ledger
  events) — never a process that acts on them autonomously. Whether/how an
  autonomous sweeper is allowed to act is a separate Xavier trust-boundary
  decision, not a technical one this store's existence resolves. Phase 0.5
  (below) does not change this: `tessctl tasks pull --status blocked`
  makes stuck work VISIBLE and `tasks claim` makes it RESUMABLE by any
  agent, but nothing in this repository watches for a stuck task and
  auto-dispatches an agent to pick it up — a human, or an explicitly
  invoked agent, always initiates the resume.
- **A Codex (or any other harness) process-spawner or daemon (Phase 0.4,
  issue #125).** `tessctl tasks handoff` PREPARES a handoff — it earmarks a
  task's lane, logs the accountability event, and prints the exact
  invocation text an operator hands to a fresh session of the target
  harness. It never starts, execs, or forks a process of that harness
  itself; there is no such runtime available inside `tessctl`'s own
  process, and building one is explicitly out of scope for the PR that
  built the lane mechanism. A live Codex session actually reading its
  earmarked lane end-to-end is a deferred follow-up (mirrors #121's own
  "mounted, not yet live-smoke-tested" framing).

Do not assume an orphan-sweeper — or a harness process-spawner — exists
because this directory does. Phase 0.1-0.5 built the fenced store, the task
store + accountability ledger, the memory link, the external-harness LANE +
handoff-preparation mechanism, and the structured stuck-packet, and the
guarantee that none of them can ever leak — nothing more.
