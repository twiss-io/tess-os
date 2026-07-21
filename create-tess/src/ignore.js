// ignore.js — the SINGLE shared source of truth for what the scaffolder must
// never copy into a produced Tess OS instance.
//
// Why this file exists (Quinn MEDIUM — local-scaffold contamination): the old
// scaffold kept a tiny parallel EXCLUDE set (.git / create-tess / node_modules /
// caches) that drifted from the repo's .gitignore / .npmignore. A local
// `--template-source` copies the template AUTHOR'S working tree verbatim, so that
// short list dragged the author's secret + operator-state material into every
// produced instance: `.claude/vault/vault.age`, `vault.recipients`, `identity.age`,
// `.tess/snapshots/**`, `.tess/staging/**`, `.env*`, `*.pem`, `*.key`,
// `.claude/tess-secrets`, `.claude/channels`, and Python caches — cross-operator
// contamination plus a recipients-lockout.
//
// Both copy paths (fetchTemplate + promote) derive their filter from this one
// module — there is no second list to keep in sync. The patterns intentionally
// MIRROR the secret/runtime block of the repo .gitignore / .npmignore (the
// content-structure ignores like kb/raw/* or clients/* are deliberately NOT here:
// the scaffolder ships the template structure, it only strips secrets + runtime
// state). The mirrored secret block also covers: bare `secrets/` /
// `tess-secrets/` / `channels/` dirs (not only `.claude/`-anchored), the
// `.claude/settings.local.json` local override, `*.env.json` files (e.g.
// prod.env.json), `operator/secrets` + `operator/*.secret`, and any file under a
// `clients/*/.vault/` subtree. Keep this in lockstep with that block when it changes.
import { sep, relative, resolve, join } from 'node:path';
import { statSync } from 'node:fs';
import { normalizeComponent, normalizePath, basenameMatchesGlob } from './pathnorm.js';

// Re-exported for backward compat — was this module's own export before the
// pathnorm.js extraction (PR #145 LOW item); test/secrets-casefold-bypass.test.js
// still imports it from here.
export { normalizeComponent };

// Basenames that are ALWAYS kept even when a broader pattern would drop them.
// `.env.example` is a committed template; `.gitkeep` preserves shipped empty dirs
// (e.g. .tess/snapshots/.gitkeep) whose CONTENT is otherwise stripped.
export const KEEP_BASENAMES = new Set(['.env.example', '.gitkeep']);

// Excluded if the name appears as ANY path component (dirs or files).
export const EXCLUDE_NAMES = new Set([
  // structural / build / cache
  '.git',
  'create-tess',
  'node_modules',
  '__pycache__',
  '.pytest_cache',
  '.venv',
  '.DS_Store',
  // secret / vault material (filenames)
  'vault.age',
  'identity.age',
  'vault.recipients',
  // bare secret / runtime dirs that .gitignore matches at ANY depth
  // (`secrets/`, `tess-secrets/`, `channels/`) — not only the `.claude/`-anchored
  // ones already covered by EXCLUDE_DIR_PREFIXES. Also `operator/secrets`.
  'secrets',
  'tess-secrets',
  'channels',
  // any `clients/*/.vault/` subtree — the dir itself + everything under it
  // (the basenames vault.age/identity.age/vault.recipients only caught those
  // three files; arbitrary blobs under a `.vault/` were leaking).
  '.vault',
  // Claude Code local override (`.claude/settings.local.json`)
  'settings.local.json',
  // `.npmignore` leak (PR #160 revision-2, Cyra MEDIUM): this repo's own
  // root `.npmignore` (+ any nested one, e.g. `tests/.npmignore`) is a
  // tracked file build-template.mjs otherwise copies verbatim into
  // `create-tess/template/.npmignore`. `npm pack` HONORS a nested
  // `.npmignore` it finds inside a `files`-listed directory — and this
  // repo's own root `.npmignore`'s rules for `kb/raw/`, `kb/lint/`,
  // `kb/wiki/{concepts,missions,people,synthesis}/`, `.tess/snapshots/`,
  // `.tess/staging/` are WHOLE-DIRECTORY excludes with NO `.gitkeep`
  // re-inclusion (unlike `.gitignore`'s carefully negated
  // `kb/wiki/concepts/*` + `!kb/wiki/concepts/.gitkeep` pattern) — so the
  // REAL npm tarball silently dropped those directories ENTIRELY, `.gitkeep`
  // and all, even though the committed `create-tess/template/` source tree
  // (and every prior test, which only ever inspected the pre-pack source
  // tree or secret-shaped paths) looked correct. `.npmignore` serves no
  // purpose in a scaffolded end-user instance — it is never itself
  // npm-published — so it is dropped here at BOTH build time
  // (build-template.mjs never copies it into the committed bundle) and
  // scaffold time (the git-clone opt-in path's promote() step, same
  // defense-in-depth as every other EXCLUDE_NAMES entry).
  '.npmignore',
]);

// Excluded as a WHOLE subtree (the dir itself and everything under it).
//
// `.tess/keys/verifiers` / `.tess/keys/signoffs` (P0 G-01, npm scaffold
// key-leak audit, 2026-07): each verifier's/sign-off's bundled PUBLIC PGP key
// (e.g. `.tess/keys/verifiers/cyra.asc`, registered by THIS repo's own
// `chore/register-verifier-cyra-phase1`, PR #91, to govern THIS repo's own
// development) is exactly the same category of "this repo's own trust
// anchor" material that policy-reset.js already resets out of
// `policy.verifier_keys`/`policy.signoff_keys` — but until this fix, the
// RAW KEY FILE itself was never covered by that reset (policy-reset.js only
// rewrites the two YAML maps) NOR by any ignore-filter exclusion, so
// `promote()` copied it into every scaffold verbatim regardless. Concretely:
// the published `create-tess` 0.1.0 (npm, 2026-06-28) clones unpinned `main`
// HEAD, and every `main` commit since #91 carries `cyra.asc` — so every
// `npm create tess` run was shipping a scaffold that would trust the Twiss
// maintainer's own verifier key as if it were the scaffolded project's own
// trust root, the exact inversion policy-reset.js exists to prevent for the
// YAML registration. Whole-subtree exclusion (not content-only, unlike
// `.tess/snapshots`/`.tess/staging` below) — a scaffolded project has
// registered no verifier/sign-off of its own yet, so it needs no directory,
// let alone any key file, to preserve; the operator creates both when they
// run their own `tessctl verdict keygen`-equivalent ceremony. Guarded by a
// permanent regression test: test/scaffold-key-guard.test.js.
// `.tess/keys/twiss-release-key.asc` (this repo's OWN release-signing PUBLIC
// key, used to verify a `tessctl update` upstream fetch) is a DIFFERENT
// category — a fixed, intentionally-bundled verification key, not a
// per-project trust anchor a scaffold should ever discard — and is
// deliberately NOT listed here.
export const EXCLUDE_DIR_PREFIXES = [
  '.claude/tess-secrets',
  '.claude/channels',
  '.tess/keys/verifiers',
  '.tess/keys/signoffs',
];

// B3 (gap-loop R2) — exact relative-path excludes. `.github/workflows/` is
// otherwise copied verbatim, so a scaffolded instance was inheriting THIS
// repo's own framework-internal CI: `ci.yml` (tess-os's own pytest/doctor/
// verify suite), `release.yml` (this repo's release-cut pipeline), and
// `publish-npm.yml` (this repo's npm-publish pipeline) — none of which apply
// to, or are runnable in, a user's produced instance. Only `tess-gate.yml`
// (the doctrine ship-gate's CI entrypoint) is user-relevant and must ship.
//
// `operator/profile.json` (PR #160 gap-loop fix, Reid HIGH): this repo's own
// ROOT operator/profile.json is `writeProfile()`'s target — every real
// scaffold run (bundled default AND the git-clone opt-in) overwrites it
// unconditionally after a successful bake (see keystone.js), so shipping the
// SOURCE repo's own copy verbatim serves no purpose and is pure drift/leak
// risk: the moment this repo's own dogfooded operator/profile.json carries
// real values (today it is still the placeholder default), the next
// `prepack`/git-clone would ship it. Excluding it here is a no-op for a
// real scaffold (writeProfile() always wins) and closes the gap for good.
export const EXCLUDE_REL_PATHS = new Set([
  '.github/workflows/ci.yml',
  '.github/workflows/release.yml',
  '.github/workflows/publish-npm.yml',
  'operator/profile.json',
]);

// Excluded CONTENT under these dirs, while the dir itself and its `.gitkeep`
// placeholder are preserved (so the produced instance keeps the empty structure
// but never inherits the author's actual snapshots / staging state).
//
// Phase 0.1 (cross-harness shared brain, docs/STATE_LAYER.md): the four
// .tess/state/** subdirs get the SAME treatment for the SAME reason —
// adopters inherit the canonical memory/tasks/ledger/locks STRUCTURE, never
// a source instance's actual runtime data. tess.manifest.json's never_touch
// + the publish-clean deny set already stop this repo's own git history from
// ever capturing real content there; this closes the THIRD path (a local
// `--template-source` copying the author's working tree verbatim, same gap
// Quinn's MEDIUM finding closed for .tess/snapshots/.tess/staging above).
// Phase 0.6 (issue #131, SKILL DRAFT SCAFFOLD): .tess/state/skills gets the
// SAME treatment for the SAME reason — adopters inherit the empty
// drafts/ STRUCTURE, never a source instance's actual generated skill
// drafts.
//
// PR-2 (Agent Receipt EMIT wiring, tools/receipt-emit/): .tess/state/receipts
// gets the SAME treatment for the SAME reason. This is the #132/#105/#111
// leak-class applied to a SIXTH `.tess/state/**` subsystem: the ship-gate's
// auto-emitted Agent Receipt chain (.tess/state/receipts/chain.jsonl) is
// real, per-instance governance/audit data the moment the gate appends its
// first receipt (actor, policy_decision, the embedded signed verdict/
// sign-off) — a `--template-source` local copy must inherit the empty
// STRUCTURE only, never the template author's own real receipt chain,
// exactly like every other `.tess/state/**` subdir above.
//
// `kb/wiki` (PR #160 gap-loop fix, Reid HIGH, create-tess bundle-template
// audit): the SAME leak class, applied at repo ROOT rather than under
// `.tess/state/`. Root `kb/wiki/index.md` + `kb/wiki/log.md` are THIS
// repo's own live, Tess-maintained internal wiki/mission-log — CLAUDE.md
// calls the whole `kb/wiki/` tree "Tess-maintained... READ-ONLY to humans."
// Content is placeholder-benign today ("No missions logged yet"), but there
// is no test/CI guard stopping a future real log entry from silently
// shipping to every `npm create tess` user on the next bundle regen — the
// exact drift Reid's review caught by diffing a fresh `build-template.mjs`
// run against the committed bundle. `kb/wiki/{concepts,missions,people,
// synthesis}/.gitkeep` (the STRUCTURE a scaffolded instance's own wiki
// needs) are unaffected — `.gitkeep` is exempted via KEEP_BASENAMES before
// this prefix list is ever consulted, same as every `.tess/state/**` entry
// above. Deliberately scoped to the REPO ROOT `kb/wiki/` only (this list is
// a plain string-prefix match against the path from the copy root, not a
// component match) — `clients/_template/kb/wiki/**` and any future
// `clients/*/kb/wiki/**` are legitimate generic starter content (their own
// `index.md`/`log.md` already ship with genericized `[Client Name]`
// placeholders, not live data) and must keep shipping untouched.
export const EXCLUDE_CONTENT_PREFIXES = [
  '.tess/snapshots',
  '.tess/staging',
  '.tess/state/memory',
  '.tess/state/tasks',
  '.tess/state/ledger',
  '.tess/state/locks',
  '.tess/state/skills',
  '.tess/state/receipts',
  'kb/wiki',
];

// Basename suffix globs (the `*.<suffix>` shape — `endsWith` match).
// `*.env.json` mirrors the .gitignore `*.env.json` (e.g. prod.env.json); the
// plain `.env` / `.env.*` handling below does NOT catch a `foo.env.json` name.
// `*.secret` mirrors `operator/*.secret`.
export const EXCLUDE_BASENAME_GLOBS = ['*.pem', '*.key', '*.pyc', '*.env.json', '*.secret'];

// Case/Unicode-robust normalization primitives (`normalizeComponent`,
// `normalizePath`, `basenameMatchesGlob`) — the CRITICAL case-fold-bypass
// fix plus the HIGH empty-component fix (PR #145) — live in ./pathnorm.js
// (LOW item, PR #145: extracted cleanly, this file was over the 300-line
// gate). See pathnorm.js's header + test/pathnorm.test.js for the details.

const EXCLUDE_NAMES_NORM = new Set([...EXCLUDE_NAMES].map(normalizeComponent));
const EXCLUDE_DIR_PREFIXES_NORM = EXCLUDE_DIR_PREFIXES.map(normalizePath);
const EXCLUDE_CONTENT_PREFIXES_NORM = EXCLUDE_CONTENT_PREFIXES.map(normalizePath);
const EXCLUDE_REL_PATHS_NORM = new Set([...EXCLUDE_REL_PATHS].map(normalizePath));
const EXCLUDE_BASENAME_GLOBS_NORM = EXCLUDE_BASENAME_GLOBS.map(normalizeComponent);

// `statSync`, returning `null` (fail-closed — "not proven to exist by this
// arm", never "safe") on any stat error, instead of throwing. Split out of
// the earlier two-argument `sameFsLocation(a, b)` shape so `makeCopyFilter`'s
// memoized ancestor walk (below) can cache each SIDE's stat independently,
// with the `dev`/`ino` INODE IDENTITY comparison (tessctl's
// `_paths_are_same_location` / `os.path.samefile`, JS analogue) done inline
// against the two cached results.
function statOrNull(p) {
  try {
    return statSync(p);
  } catch {
    return null;
  }
}

// Decide whether a path RELATIVE to the copy root must be excluded.
export function isExcludedRel(rel) {
  if (!rel || rel === '.') return false;
  const norm = rel.split(sep).join('/');
  const parts = norm.split('/').filter(Boolean);
  if (parts.length === 0) return false;
  const base = parts[parts.length - 1];

  // Explicit keeps win over every exclude pattern — checked against the RAW
  // (not case/NFC-normalized) basename, deliberately. This is an ALLOWLIST
  // punched through a denylist scanner, so it must never be loosened by
  // normalization: a mis-cased `.ENV.EXAMPLE` does NOT get the exemption —
  // it falls through to the (normalized) `.env` exclusion below and is
  // excluded. That is the correct, fail-safe direction (over-exclusion of a
  // template file, never under-exclusion of a secret).
  if (KEEP_BASENAMES.has(base)) return false;

  const normFold = normalizePath(norm);
  const partsFold = normFold.split('/').filter(Boolean);
  const baseFold = partsFold.length > 0 ? partsFold[partsFold.length - 1] : '';

  // Exact relative-path excludes (framework-internal files under an
  // otherwise-kept directory — see EXCLUDE_REL_PATHS above).
  if (EXCLUDE_REL_PATHS_NORM.has(normFold)) return true;

  // Name/component excludes (anywhere in the path).
  if (partsFold.some((p) => EXCLUDE_NAMES_NORM.has(p))) return true;

  // Basename suffix globs.
  if (EXCLUDE_BASENAME_GLOBS_NORM.some((g) => basenameMatchesGlob(baseFold, g))) return true;

  // .env and any .env.<suffix> (`.env.example` already kept above).
  if (baseFold === '.env' || baseFold.startsWith('.env.')) return true;

  // Whole-subtree dir prefixes (string/casefold/NFC fallback; makeCopyFilter
  // layers a memoized inode-identity check on top of this for candidates
  // that actually exist on disk — see `statOrNull` and `makeCopyFilter` below).
  if (EXCLUDE_DIR_PREFIXES_NORM.some((p) => normFold === p || normFold.startsWith(p + '/'))) return true;

  // Content under snapshot/staging dirs (dir + its .gitkeep kept above).
  if (EXCLUDE_CONTENT_PREFIXES_NORM.some((p) => normFold.startsWith(p + '/'))) return true;

  return false;
}

// Build a cpSync filter bound to a source root. The filter receives ABSOLUTE
// source paths; we resolve them back to a root-relative path so multi-component
// and glob patterns work (the old component-only filter could not).
//
// Layers TWO checks (both must pass for a path to be copied): (1)
// `isExcludedRel` — the case/NFC-normalized string fallback (above), correct
// even for a candidate that doesn't exist on disk under the forbidden root's
// OWN spelling; (2) inode-identity (memoized `dev`/`ino` comparison, below)
// against every resolved EXCLUDE_DIR_PREFIXES root — the ground-truth arm
// for the CRITICAL secrets-exclusion case-fold bypass: even if a future edge
// case slipped past the string fallback, this asks the filesystem itself
// whether `src` IS, or resolves under, a fixed secret-dir root (tessctl's
// `_path_is_prefix`/`_paths_are_same_location`, JS analogue). Walks `src`'s
// own ancestors up to the root (not just direct equality) so a secret
// reached via a case-divergent PARENT alias is also caught — belt-and-
// suspenders on top of `fs.cpSync`'s own subtree-pruning behavior.
//
// ★ MEDIUM (Reid, PR #145 perf review) — memoize the ancestor walk. Pre-fix,
// every ancestor level of every candidate re-`statSync`'d each of the 4
// fixed forbidden roots from scratch AND re-`statSync`'d the SAME shared
// ancestor directory once per sibling underneath it — Reid measured 56,690
// statSync calls / +55% wall-clock (504ms -> ~780ms) on a 2,669-file repo;
// this repo's benchmark fixture (2,548 entries) reproduced the shape:
// 54,684 stat attempts pre-fix, ~751ms average. Fix, scoped to THIS
// `makeCopyFilter(srcRoot)` call (one CLI copy pass — a fresh call gets a
// fresh cache, never shared across copies): (1) stat the 4 forbidden roots
// ONCE, up front — a source with no secret dirs (the common case) now skips
// the whole ancestor-walk loop below, since `forbiddenStats` is empty; (2)
// memoize each ancestor path's own stat on first encounter
// (`ancestorStatCache`) — many files share parents, collapsing a fresh
// `statSync` per sibling into one per unique ancestor.
export function makeCopyFilter(srcRoot) {
  const rootAbs = resolve(srcRoot);

  // Resolve + stat every EXCLUDE_DIR_PREFIXES entry ONCE, up front (not once
  // per ancestor level per candidate). A prefix that doesn't exist under
  // this source (the common case) is dropped here rather than re-attempted
  // per file; `isExcludedRel`'s string fallback still covers it regardless.
  const forbiddenStats = EXCLUDE_DIR_PREFIXES.map((p) => resolve(rootAbs, p))
    .map(statOrNull)
    .filter(Boolean);

  // Per-copy-pass memo of ancestor-path stats.
  const ancestorStatCache = new Map();
  const statCached = (p) => {
    if (ancestorStatCache.has(p)) return ancestorStatCache.get(p);
    const s = statOrNull(p);
    ancestorStatCache.set(p, s);
    return s;
  };

  return (src) => {
    const rel = relative(rootAbs, src);
    // The root itself (rel === "") and anything outside the root is copied.
    if (!rel || rel.startsWith('..')) return true;
    if (isExcludedRel(rel)) return false;
    // No forbidden root exists under this source at all (the common case) —
    // no ancestor of any candidate can possibly match one, so skip the walk.
    if (forbiddenStats.length === 0) return true;

    const segments = rel.split(sep).filter(Boolean);
    for (let i = segments.length; i >= 1; i--) {
      const ancestorAbs = join(rootAbs, ...segments.slice(0, i));
      const ancestorStat = statCached(ancestorAbs);
      if (!ancestorStat) continue;
      for (const forbiddenStat of forbiddenStats) {
        if (ancestorStat.dev === forbiddenStat.dev && ancestorStat.ino === forbiddenStat.ino) return false;
      }
    }
    return true;
  };
}
