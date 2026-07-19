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
import { sep, relative, resolve } from 'node:path';

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
export const EXCLUDE_CONTENT_PREFIXES = [
  '.tess/snapshots',
  '.tess/staging',
  '.tess/state/memory',
  '.tess/state/tasks',
  '.tess/state/ledger',
  '.tess/state/locks',
];

// Basename suffix globs (the `*.<suffix>` shape — `endsWith` match).
// `*.env.json` mirrors the .gitignore `*.env.json` (e.g. prod.env.json); the
// plain `.env` / `.env.*` handling below does NOT catch a `foo.env.json` name.
// `*.secret` mirrors `operator/*.secret`.
export const EXCLUDE_BASENAME_GLOBS = ['*.pem', '*.key', '*.pyc', '*.env.json', '*.secret'];

function basenameMatchesGlob(base, glob) {
  return glob.startsWith('*') ? base.endsWith(glob.slice(1)) : base === glob;
}

// Decide whether a path RELATIVE to the copy root must be excluded.
export function isExcludedRel(rel) {
  if (!rel || rel === '.') return false;
  const norm = rel.split(sep).join('/');
  const parts = norm.split('/').filter(Boolean);
  if (parts.length === 0) return false;
  const base = parts[parts.length - 1];

  // Explicit keeps win over every exclude pattern.
  if (KEEP_BASENAMES.has(base)) return false;

  // Exact relative-path excludes (framework-internal files under an
  // otherwise-kept directory — see EXCLUDE_REL_PATHS above).
  if (EXCLUDE_REL_PATHS.has(norm)) return true;

  // Name/component excludes (anywhere in the path).
  if (parts.some((p) => EXCLUDE_NAMES.has(p))) return true;

  // Basename suffix globs.
  if (EXCLUDE_BASENAME_GLOBS.some((g) => basenameMatchesGlob(base, g))) return true;

  // .env and any .env.<suffix> (`.env.example` already kept above).
  if (base === '.env' || base.startsWith('.env.')) return true;

  // Whole-subtree dir prefixes.
  if (EXCLUDE_DIR_PREFIXES.some((p) => norm === p || norm.startsWith(p + '/'))) return true;

  // Content under snapshot/staging dirs (dir + its .gitkeep kept above).
  if (EXCLUDE_CONTENT_PREFIXES.some((p) => norm.startsWith(p + '/'))) return true;

  return false;
}

// Build a cpSync filter bound to a source root. The filter receives ABSOLUTE
// source paths; we resolve them back to a root-relative path so multi-component
// and glob patterns work (the old component-only filter could not).
export function makeCopyFilter(srcRoot) {
  const rootAbs = resolve(srcRoot);
  return (src) => {
    const rel = relative(rootAbs, src);
    // The root itself (rel === "") and anything outside the root is copied.
    if (!rel || rel.startsWith('..')) return true;
    return !isExcludedRel(rel);
  };
}
