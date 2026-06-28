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
// state). Keep this in lockstep with that block when it changes.
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
]);

// Excluded as a WHOLE subtree (the dir itself and everything under it).
export const EXCLUDE_DIR_PREFIXES = [
  '.claude/tess-secrets',
  '.claude/channels',
];

// Excluded CONTENT under these dirs, while the dir itself and its `.gitkeep`
// placeholder are preserved (so the produced instance keeps the empty structure
// but never inherits the author's actual snapshots / staging state).
export const EXCLUDE_CONTENT_PREFIXES = [
  '.tess/snapshots',
  '.tess/staging',
];

// Basename suffix globs (only the `*.<ext>` shape is used here).
export const EXCLUDE_BASENAME_GLOBS = ['*.pem', '*.key', '*.pyc'];

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
