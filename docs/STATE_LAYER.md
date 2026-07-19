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
- `tests/test_gitignore_reconciliation.py` — proves the `.gitignore`
  content-level layer itself, independent of the publish-clean hook: a
  fresh file under any of `.tess/state/{memory,tasks,ledger,locks}/` is
  `git check-ignore`d and never appears in `git add -A` staging, while each
  subdir's `.gitkeep` stays trackable (issue #110).

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
