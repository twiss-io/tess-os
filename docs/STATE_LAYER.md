# The state layer: one canonical store, every harness mounts it

> **Status: Phase 0.1 — the fenced store only.** This page describes the
> plan; most of it is not built yet. See "What's built today" vs. "What's
> Phase 0.2+" below before assuming any of this is live.

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
three-part fence those paths already get, before anything writes to it for
real:

1. **`tess.manifest.json`'s `never_touch`** — `.tess/state/**` is listed
   there, so the framework updater/renderer (`tessctl update` / `render` /
   `restore`) can never read, write, or publish it. There is no
   `.tess/core/state/**` mirror; nothing here is compiled from core.
2. **The publish-clean gate** — `.tess/state/**` is in
   `_PUBLISH_CLEAN_PRIVATE_GLOBS` (`.tess/bin/tessctl`), the commit-side
   control from issue #92/#93. `tessctl doctor --publish-clean` (installed as
   a pre-commit hook by `tessctl gate install-hooks`) refuses a commit that
   stages anything under `.tess/state/**`, regardless of `.gitignore` state
   — private memory/tasks/ledger data can never reach a public commit.
3. **The public scaffold ships it EMPTY** — `create-tess` copies the
   template's `.tess/state/{memory,tasks,ledger,locks}/` directories (each
   holding only a `.gitkeep`) but strips any content underneath
   (`EXCLUDE_CONTENT_PREFIXES` in `create-tess/src/ignore.js`), the same
   scaffold-strip treatment `.tess/snapshots`/`.tess/staging` already get.
   Adopters inherit the canonical structure; they never inherit another
   instance's actual memory, tasks, or ledger entries.

`.gitignore` additionally ignores `.tess/state/locks/*` outright (keeping
only `.gitkeep`) — locks are pure ephemeral runtime coordination state, the
same rationale as `.tess/update.lock`. `memory/`, `tasks/`, and `ledger/` are
not separately gitignored in Phase 0.1: their actual content-tracking policy
(what gets committed, if anything, and how) is a Phase 0.2+ design decision;
until then they rely on the publish-clean gate alone, which already covers
the whole `.tess/state/**` tree regardless of `.gitignore`.

## What's built today (Phase 0.1)

- The four empty, fenced directories above.
- The never_touch / publish-clean / scaffold-strip / gitignore protections
  described above.
- `test_state_never_publishable` (`tests/test_publish_clean_gate.py`) +
  companion coverage in `tests/test_write_gate.py` and
  `create-tess/test/units.test.js` — proves the write-gate denies tessctl
  writes into `.tess/state/**`, the publish-clean gate blocks a commit that
  stages anything under it, and a local-source scaffold never copies real
  content into a produced instance's `.tess/state/**`.

## What's deliberately NOT built yet (Phase 0.2+)

- **Memory adopt** — the mechanism by which a harness-private memory file
  (e.g. a Claude Code memory artifact) gets adopted into
  `.tess/state/memory/` as the canonical copy, rather than living only in
  that harness's home directory.
- **Tasks CLI** — `tessctl task ...` reading/writing the shared task graph
  in `.tess/state/tasks/`.
- **Ledger** — the harness-neutral form of the mission/retry ledger
  (`tests/test_mission_ledger.py` is the existing per-project pattern this
  will generalize) landing in `.tess/state/ledger/`.

Do not assume any of the above exists because this directory does. Phase 0.1
is the fenced, empty store and the guarantee that it can never leak — nothing
more.
