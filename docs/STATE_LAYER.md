# The state layer: one canonical store, every harness mounts it

> **Status: Phase 0.2 — the fenced store PLUS the task store + accountability
> ledger.** Phase 0.1 built the four empty, fenced directories and their
> leak-proofing. Phase 0.2 (this page's own next section) lands the first two
> real subsystems on top of that store: `tessctl tasks` (the shared task
> graph, `.tess/state/tasks/`) and `tessctl log` (the hash-chained
> accountability ledger, `.tess/state/ledger/`). Memory-adopt
> (`.tess/state/memory/`) and any orphan-sweeper daemon remain NOT built —
> see "What's deliberately NOT built yet" below, now scoped to just those
> two.

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
├── memory/     ← cross-harness memory (adopted, not duplicated — Phase 0.2)
├── tasks/      ← the shared task graph (Phase 0.2 CLI)
├── ledger/     ← mission/retry ledger, harness-neutral form (Phase 0.2+)
└── locks/      ← coordination locks between concurrent harness sessions
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

## What's built today (Phase 0.1 + Phase 0.2)

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

## What's deliberately NOT built yet (Phase 0.3+)

- **Memory adopt** — the mechanism by which a harness-private memory file
  (e.g. a Claude Code memory artifact) gets adopted into
  `.tess/state/memory/` as the canonical copy, rather than living only in
  that harness's home directory. A separate, later PR.
- **The orphan-sweeper** — a daemon/process that would scan
  `.tess/state/tasks/*.json`'s claim-leases and `.tess/state/ledger/**` for
  dead-PID claims and auto-resume/re-dispatch abandoned work. Phase 0.2
  builds ONLY the substrate such a sweeper would read (claim-lease +
  heartbeat fields, and `claim`/`heartbeat`/`reclaimed`/`crashed` ledger
  events) — never a process that acts on them autonomously. Whether/how an
  autonomous sweeper is allowed to act is a separate Xavier trust-boundary
  decision, not a technical one this store's existence resolves.

Do not assume the memory-adopt mechanism or an orphan-sweeper exists because
this directory does. Phase 0.2 is the task store + accountability ledger
substrate and the guarantee that neither can ever leak — nothing more.
