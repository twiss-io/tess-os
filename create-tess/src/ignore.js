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
export const EXCLUDE_REL_PATHS = new Set([
  '.github/workflows/ci.yml',
  '.github/workflows/release.yml',
  '.github/workflows/publish-npm.yml',
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
export const EXCLUDE_CONTENT_PREFIXES = [
  '.tess/snapshots',
  '.tess/staging',
  '.tess/state/memory',
  '.tess/state/tasks',
  '.tess/state/ledger',
  '.tess/state/locks',
  '.tess/state/skills',
  '.tess/state/receipts',
];

// Basename suffix globs (the `*.<suffix>` shape — `endsWith` match).
// `*.env.json` mirrors the .gitignore `*.env.json` (e.g. prod.env.json); the
// plain `.env` / `.env.*` handling below does NOT catch a `foo.env.json` name.
// `*.secret` mirrors `operator/*.secret`.
export const EXCLUDE_BASENAME_GLOBS = ['*.pem', '*.key', '*.pyc', '*.env.json', '*.secret'];

function basenameMatchesGlob(base, glob) {
  return glob.startsWith('*') ? base.endsWith(glob.slice(1)) : base === glob;
}

// ---------------------------------------------------------------------------
// Case/Unicode-robust normalization (CRITICAL, secrets-exclusion case-fold
// bypass — 2026-07 security audit, live-reproduced on macOS). Every string
// comparison below used to be a plain JS `===`/`.startsWith()`/`Set.has()`
// against the path exactly as written. macOS (APFS, default) and Windows
// (NTFS, default) — the two documented default deployment filesystems — are
// case-INSENSITIVE, so a secret dir under non-canonical case, e.g.
// `.Claude/Tess-Secrets/`, is the SAME INODE as `.claude/tess-secrets/` but a
// DIFFERENT STRING: every check here silently returned false and the
// scaffolder COPIED the secret tree verbatim into produced instances —
// `vault.age`, `identity.age`, live `.claude/tess-secrets/*` tokens, the
// PRIVATE `.tess/keys/verifiers/**`/`signoffs/**` trust-anchor keys, and real
// `.tess/state/memory/**` operator data. Reproduced: `isExcludedRel` returned
// `false` for `.Claude/Tess-Secrets/token.env` despite it being the same
// inode as `.claude/tess-secrets/token.env`. This is the SAME bug CLASS as
// #117/#140 (fixed on the Python `tessctl` side with inode-identity —
// `_paths_are_same_location`/`_path_is_prefix`, `.tess/bin/tessctl`) landing
// again in the JS scaffolder — and it silently defeats the #108/0.1.2
// npm-hazard scaffold-key-strip, since that strip only ever runs on paths
// this filter decided to actually look at.
//
// Fix, mirroring tessctl's OWN two-layer pattern rather than reinventing it:
//
//   1. `normalizeComponent` — the string-level fallback, always available
//      even when the candidate path does not (yet) exist on disk. NFC-
//      normalizes (so an NFD-decomposed component compares equal to its
//      NFC-composed form — both encode "the same grapheme" as different
//      UTF-8 byte sequences), THEN casefolds via `toLowerCase()`, THEN strips
//      trailing dots/spaces — mirrors tessctl's write-gate per-component
//      normalization (`check_manifest_write_gate`'s `.rstrip('. ').lower()`,
//      `.tess/bin/tessctl`), extended with NFC since this filter, unlike
//      that Python gate, also has to cope with a case-insensitive
//      filesystem's Unicode-equivalence edge cases. Applied to every path
//      component compared against EXCLUDE_NAMES/EXCLUDE_DIR_PREFIXES/
//      EXCLUDE_CONTENT_PREFIXES/EXCLUDE_REL_PATHS/the basename globs/the
//      `.env` check below.
//
//   2. `sameFsLocation` (used by `makeCopyFilter`, below) — the JS analogue
//      of tessctl's `_paths_are_same_location` (`os.path.samefile` /
//      `(st_dev, st_ino)` inode identity): when BOTH paths exist, ask the
//      filesystem itself whether they are the SAME inode — correct
//      regardless of case-folding AND NFC/NFD, because inode identity is a
//      filesystem-resolution property, not a string property this module
//      would otherwise have to reimplement. Reserved for the DIR-prefix
//      secret exclusions (EXCLUDE_DIR_PREFIXES) — the only exclusion tier
//      anchored to a single, fixed, resolvable path under the copy root
//      (EXCLUDE_NAMES matches a bare component at ANY depth, with no single
//      fixed root to stat against).
//
// ★ This is a DENYLIST (default-allow): any case/normalization ambiguity —
// a stat failure, a partial match, anything the fallback can't resolve
// cleanly — must resolve to EXCLUDE, never to "copy it anyway". Every helper
// below is written fail-closed: the risky branch always returns `true`
// (excluded)/`false` (not-a-safe-match), never the reverse.
//
// Exported (like scaffold.js's buildCloneArgs/resolveTemplateRef) as a pure,
// dependency-free primitive so the NFC-then-casefold ordering is directly
// unit-testable: lower-casing an NFD-decomposed grapheme (e.g. "e" plus a
// COMBINING ACUTE ACCENT codepoint, U+0065 U+0301) WITHOUT normalizing
// first does NOT converge with the lower-cased form of its NFC-precomposed
// counterpart (U+00C9 lower-cases to U+00E9, a single codepoint) -- the two
// stay different byte sequences. Only NFC-normalizing FIRST makes them
// compare equal, so that step is load-bearing, not redundant with
// casefolding alone. See test/secrets-casefold-bypass.test.js for the
// regression lock (deliberately avoids a literal accented character in
// this comment itself, so the source file's own bytes can't silently drift
// between NFC/NFD depending on the editor that touched it last).
export function normalizeComponent(c) {
  return c.normalize('NFC').toLowerCase().replace(/[. ]+$/, '');
}

function normalizePath(relForward) {
  return relForward.split('/').filter(Boolean).map(normalizeComponent).join('/');
}

const EXCLUDE_NAMES_NORM = new Set([...EXCLUDE_NAMES].map(normalizeComponent));
const EXCLUDE_DIR_PREFIXES_NORM = EXCLUDE_DIR_PREFIXES.map(normalizePath);
const EXCLUDE_CONTENT_PREFIXES_NORM = EXCLUDE_CONTENT_PREFIXES.map(normalizePath);
const EXCLUDE_REL_PATHS_NORM = new Set([...EXCLUDE_REL_PATHS].map(normalizePath));
const EXCLUDE_BASENAME_GLOBS_NORM = EXCLUDE_BASENAME_GLOBS.map(normalizeComponent);

// True if `a` and `b` refer to the SAME filesystem location, by INODE
// IDENTITY (`fs.statSync` -> compare `dev`+`ino`) — the JS analogue of
// tessctl's `_paths_are_same_location` (`os.path.samefile`). Fails CLOSED
// (returns false — "not proven to be the same location by this arm") on any
// stat error: either path not (yet) existing, a permission error, or a race.
// This is the supplementary GROUND-TRUTH layer, not the sole line of
// defense — the case/NFC string fallback in `isExcludedRel` above already
// covers the "doesn't exist yet" case, so this helper never needs to guess;
// an inconclusive stat here simply means this arm didn't fire, never that
// the path is safe.
function sameFsLocation(a, b) {
  try {
    const sa = statSync(a);
    const sb = statSync(b);
    return sa.dev === sb.dev && sa.ino === sb.ino;
  } catch {
    return false;
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
  // layers an inode-identity check on top of this for candidates that
  // actually exist on disk — see sameFsLocation above).
  if (EXCLUDE_DIR_PREFIXES_NORM.some((p) => normFold === p || normFold.startsWith(p + '/'))) return true;

  // Content under snapshot/staging dirs (dir + its .gitkeep kept above).
  if (EXCLUDE_CONTENT_PREFIXES_NORM.some((p) => normFold.startsWith(p + '/'))) return true;

  return false;
}

// Build a cpSync filter bound to a source root. The filter receives ABSOLUTE
// source paths; we resolve them back to a root-relative path so multi-component
// and glob patterns work (the old component-only filter could not).
//
// Layers TWO checks (both must pass for a path to be copied):
//   1. `isExcludedRel` — the case/NFC-normalized string fallback (above),
//      correct even for a candidate that doesn't exist on disk under the
//      forbidden root's OWN spelling.
//   2. Inode-identity (`sameFsLocation`) against every resolved
//      EXCLUDE_DIR_PREFIXES root — the ground-truth arm for the CRITICAL
//      secrets-exclusion case-fold bypass: even if a future edge case (an
//      exotic Unicode equivalence, an OS-specific folding rule) slipped past
//      the string fallback, this asks the filesystem itself whether `src`
//      IS, or resolves under, one of the fixed secret-dir roots — the JS
//      analogue of tessctl's `_path_is_prefix`/`_paths_are_same_location`.
//      Walks `src`'s own ancestors up to the root (not just a direct-equality
//      check) so a secret reached via a case-divergent PARENT alias is also
//      caught, mirroring `_path_is_prefix`'s ancestor walk — belt-and-
//      suspenders on top of `fs.cpSync`'s own documented subtree pruning
//      (once a directory's filter returns false, its descendants are never
//      visited at all), so this still holds even if that pruning behavior
//      ever changes.
export function makeCopyFilter(srcRoot) {
  const rootAbs = resolve(srcRoot);

  // Resolve every EXCLUDE_DIR_PREFIXES entry ONCE, up front, to its absolute
  // path under THIS root. A prefix that doesn't exist under this particular
  // source (the common case — most template sources ship no secret dirs at
  // all) simply never matches on this arm; `isExcludedRel`'s string fallback
  // still covers it regardless.
  const forbiddenDirRoots = EXCLUDE_DIR_PREFIXES.map((p) => resolve(rootAbs, p));

  return (src) => {
    const rel = relative(rootAbs, src);
    // The root itself (rel === "") and anything outside the root is copied.
    if (!rel || rel.startsWith('..')) return true;
    if (isExcludedRel(rel)) return false;
    if (forbiddenDirRoots.length === 0) return true;

    const segments = rel.split(sep).filter(Boolean);
    for (let i = segments.length; i >= 1; i--) {
      const ancestorAbs = join(rootAbs, ...segments.slice(0, i));
      for (const forbidden of forbiddenDirRoots) {
        if (sameFsLocation(forbidden, ancestorAbs)) return false;
      }
    }
    return true;
  };
}
