// force-plan.js — what `--force` may do to a directory that already has
// content, decided BEFORE anything is written. The backup and the verified
// restore live in force-backup.js (re-exported here).
//
// planForce() is read-only. It refuses (returns `problems`) on
//   - a type conflict: the template needs a directory where the target has a
//     file or a symlink, or a file where the target has a directory or a
//     symlink. Writing through a symlink could land outside the target, so a
//     symlink on any path the scaffold writes is always a conflict;
//   - an existing entry whose stored name differs from the template's only in
//     letter case (or Unicode form): one path on a case-insensitive
//     filesystem, which the scaffold would silently overwrite;
//   - pre-existing content in a framework-managed path (MANAGED_PATHS) when
//     the target is not a real Tess OS install.
import { readdirSync, readFileSync, lstatSync } from 'node:fs';
import { join } from 'node:path';
import { isExcludedRel } from './ignore.js';
import { absOf, lstatOrNull, kindOf, snapshotTree } from './tree-snapshot.js';
import { CREATE_TESS_VERSION } from './version.js';

export { snapshotTree, diffSnapshots, MAX_SNAPSHOT_ENTRIES } from './tree-snapshot.js';
export {
  BACKUP_PREFIX,
  createBackup,
  verifyAgainst,
  restoreFromBackup,
} from './force-backup.js';

// Any one of these marks the directory as a Tess OS install for the
// "already an install" message.
export const INSTALL_MARKERS = ['.tess/tess.lock', 'tess.manifest.json', 'operator/profile.json'];

// Framework-managed paths a forced re-scaffold of a real install
// clean-replaces (moved into the backup, never merged), so stale managed files
// such as a renamed agent cannot survive.
export const MANAGED_PATHS = ['.claude/agents', '.claude/commands', 'conductor', '.tess/core', 'CLAUDE.md'];

// Written by the wizard itself (keystone.js writeProfile), not copied from the
// template, so the template walk alone would miss it.
export const EXTRA_WRITE_PATHS = ['operator/profile.json'];

// Which install markers exist, and whether this is a REAL install: a regular
// .tess/tess.lock with `framework:` and `files:` sections plus a
// tess.manifest.json that parses as a JSON object. Only a real install lets
// --force clean-replace its managed paths.
export function detectInstall(targetDir) {
  const markers = INSTALL_MARKERS.filter((rel) => lstatOrNull(absOf(targetDir, rel)) !== null);
  let real = false;
  const isFile = (rel) => kindOf(lstatOrNull(absOf(targetDir, rel))) === 'file';
  if (isFile('.tess/tess.lock') && isFile('tess.manifest.json')) {
    try {
      const lock = readFileSync(absOf(targetDir, '.tess/tess.lock'), 'utf8');
      const manifest = JSON.parse(readFileSync(absOf(targetDir, 'tess.manifest.json'), 'utf8'));
      real =
        /^framework:/m.test(lock) &&
        /^files:/m.test(lock) &&
        manifest !== null &&
        typeof manifest === 'object' &&
        !Array.isArray(manifest);
    } catch {
      real = false;
    }
  }
  return { markers, real };
}

// rel -> kind for every entry promote() will lay down from the staged
// template: the same isExcludedRel filter promote() applies, and an excluded
// directory hides its whole subtree (cpSync never descends into it).
export function templateEntries(stagingDir) {
  const out = new Map();
  const visit = (dirAbs, relBase) => {
    for (const name of readdirSync(dirAbs).sort()) {
      const rel = relBase ? `${relBase}/${name}` : name;
      if (isExcludedRel(rel)) continue;
      const st = lstatSync(join(dirAbs, name));
      const kind = kindOf(st);
      out.set(rel, kind === 'symlink' ? 'file' : kind);
      if (kind === 'dir') visit(join(dirAbs, name), rel);
    }
  };
  visit(stagingDir, '');
  return out;
}

// Leaf entries under a pre-existing managed path, for the refusal message.
function leavesUnder(targetDir, rel, kind) {
  if (kind !== 'dir') return [rel];
  const snap = snapshotTree(absOf(targetDir, rel));
  const leaves = [...snap.entries()].filter(([, v]) => !v.startsWith('dir|')).map(([r]) => `${rel}/${r}`);
  return leaves.length ? leaves : [`${rel}/`];
}

// On a case-insensitive filesystem (the macOS default) lstat('README.md')
// succeeds for a file stored as readme.md, and the scaffold would overwrite
// it under the template's spelling. Returns a refusal line when the entry at
// `rel` is stored under a different spelling, else null.
function spellingProblem(listing, rel) {
  const i = rel.lastIndexOf('/');
  const parent = i < 0 ? '' : rel.slice(0, i);
  const name = rel.slice(i + 1);
  const names = listing(parent);
  if (!names || names.includes(name)) return null;
  const fold = (n) => n.normalize('NFC').toLowerCase();
  const actual = names.find((n) => fold(n) === fold(name));
  const shown = actual ? `${parent ? `${parent}/` : ''}${actual}` : `an entry named like ${rel}`;
  return (
    `${shown} in the target differs from the template's ${rel} only in letter case ` +
    '(or Unicode form); this filesystem treats them as one path, so the scaffold ' +
    'would overwrite it. Rename it'
  );
}

// Read-only, cached view of the target: kindAt(rel) is the lstat kind (or
// null), and adds a problem when the entry is stored under another spelling;
// ancestorProblem(rel) says why a proper ancestor cannot hold the template.
function makeProbe(targetDir, problems) {
  const kinds = new Map();
  const listings = new Map();
  const listing = (parentRel) => {
    if (!listings.has(parentRel)) {
      let names = null;
      try {
        names = readdirSync(parentRel ? absOf(targetDir, parentRel) : targetDir);
      } catch {
        names = null;
      }
      listings.set(parentRel, names);
    }
    return listings.get(parentRel);
  };
  const kindAt = (rel) => {
    if (kinds.has(rel)) return kinds.get(rel);
    const k = kindOf(lstatOrNull(absOf(targetDir, rel)));
    kinds.set(rel, k);
    const sp = k === null ? null : spellingProblem(listing, rel);
    if (sp) problems.add(sp);
    return k;
  };
  const ancestorProblem = (rel) => {
    const parts = rel.split('/');
    for (let i = 1; i < parts.length; i++) {
      const a = parts.slice(0, i).join('/');
      const k = kindAt(a);
      if (k === null) return null;
      if (k !== 'dir') return `${a} is a ${k}, but the template needs a directory there`;
    }
    return null;
  };
  return { kindAt, ancestorProblem };
}

// Managed paths: a real install moves them into the backup; anything else
// holding content there is a collision.
function planManaged(targetDir, install, probe, problems) {
  const move = [];
  const collisions = [];
  for (const m of MANAGED_PATHS) {
    const k = probe.kindAt(m);
    if (k === null) continue;
    const ap = probe.ancestorProblem(m);
    if (ap) problems.add(ap);
    else if (!install.real) collisions.push(...leavesUnder(targetDir, m, k));
    else move.push(m);
  }
  return { move, collisions };
}

// Every other path the scaffold writes: type conflicts are problems, an
// existing regular file is overwritten (and backed up first).
function planWrites(stagingDir, move, probe, problems) {
  const overwrite = [];
  const underMoved = (rel) => move.some((m) => rel === m || rel.startsWith(`${m}/`));
  const wanted = templateEntries(stagingDir);
  for (const rel of EXTRA_WRITE_PATHS) if (!wanted.has(rel)) wanted.set(rel, 'file');
  for (const [rel, want] of wanted) {
    if (underMoved(rel)) continue;
    const ap = probe.ancestorProblem(rel);
    if (ap) {
      problems.add(ap);
      continue;
    }
    const have = probe.kindAt(rel);
    if (have === null) continue;
    if (want === 'dir') {
      if (have !== 'dir') problems.add(`${rel} is a ${have}, but the template needs a directory there`);
    } else if (have !== 'file') {
      problems.add(`${rel} is a ${have}, but the template writes a file there`);
    } else {
      overwrite.push(rel);
    }
  }
  return overwrite;
}

function collisionMessage(collisions) {
  const shown = collisions.slice(0, 10).join(', ');
  const more = collisions.length > 10 ? ` (+${collisions.length - 10} more)` : '';
  return (
    `framework-managed paths already hold content: ${shown}${more}. This directory is ` +
    'not a complete Tess OS install (.tess/tess.lock plus tess.manifest.json), and ' +
    '--force only clean-replaces managed paths in one. Adopting an existing ' +
    `directory or instance is not supported in create-tess ${CREATE_TESS_VERSION}`
  );
}

// Read-only preflight. Returns { install, move, overwrite, problems }.
export function planForce(stagingDir, targetDir) {
  const install = detectInstall(targetDir);
  const problems = new Set();
  const probe = makeProbe(targetDir, problems);
  const { move, collisions } = planManaged(targetDir, install, probe, problems);
  const overwrite = planWrites(stagingDir, move, probe, problems);
  const list = [...problems];
  if (collisions.length) list.unshift(collisionMessage(collisions));
  return { install, move, overwrite, problems: list };
}
