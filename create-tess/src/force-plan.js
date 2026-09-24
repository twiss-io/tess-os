// force-plan.js — what `--force` may do to a directory that already has
// content, decided BEFORE anything is written, plus the backup and the
// verified restore that make a failed forced run leave the directory exactly
// as it was.
//
// Contract:
//   1. planForce() is read-only. It refuses (returns `problems`) on
//      - a type conflict: the template needs a directory where the target has
//        a file or a symlink, or a file where the target has a directory or a
//        symlink. Writing through a symlink could land outside the target, so
//        a symlink on any path the scaffold writes is always a conflict;
//      - pre-existing content in a framework-managed path (MANAGED_PATHS)
//        when the target is not a real Tess OS install.
//   2. createBackup() copies every file the scaffold will overwrite, then
//      moves the managed paths, into <target>/.create-tess-backup-<ts>/files/,
//      and writes a manifest.json. Each copy is hash-checked against the
//      pre-run snapshot.
//   3. restoreFromBackup() puts everything back, deletes every path the run
//      added, and walks the tree again. It reports `clean` ONLY when that walk
//      (type, mode, sha256, link target) equals the pre-run snapshot.
import {
  lstatSync,
  readdirSync,
  readFileSync,
  mkdirSync,
  renameSync,
  copyFileSync,
  rmSync,
  writeFileSync,
  existsSync,
} from 'node:fs';
import { join, dirname } from 'node:path';
import { isExcludedRel } from './ignore.js';
import {
  absOf,
  lstatOrNull,
  kindOf,
  sha256File,
  snapshotTree,
  diffSnapshots,
} from './tree-snapshot.js';

export { snapshotTree, diffSnapshots, MAX_SNAPSHOT_ENTRIES } from './tree-snapshot.js';

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

export const BACKUP_PREFIX = '.create-tess-backup-';

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

// Read-only preflight. Returns { install, move, overwrite, problems }.
export function planForce(stagingDir, targetDir) {
  const install = detectInstall(targetDir);
  const problems = new Set();
  const move = [];
  const overwrite = [];
  const collisions = [];

  const cache = new Map();
  const kindAt = (rel) => {
    if (!cache.has(rel)) cache.set(rel, kindOf(lstatOrNull(absOf(targetDir, rel))));
    return cache.get(rel);
  };
  // Every proper ancestor must be absent or a real directory.
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
  const underMoved = (rel) => move.some((m) => rel === m || rel.startsWith(`${m}/`));

  for (const m of MANAGED_PATHS) {
    const k = kindAt(m);
    if (k === null) continue;
    const ap = ancestorProblem(m);
    if (ap) problems.add(ap);
    else if (!install.real) collisions.push(...leavesUnder(targetDir, m, k));
    else move.push(m);
  }

  const wanted = templateEntries(stagingDir);
  for (const rel of EXTRA_WRITE_PATHS) if (!wanted.has(rel)) wanted.set(rel, 'file');
  for (const [rel, want] of wanted) {
    if (underMoved(rel)) continue;
    const ap = ancestorProblem(rel);
    if (ap) {
      problems.add(ap);
      continue;
    }
    const have = kindAt(rel);
    if (have === null) continue;
    if (want === 'dir') {
      if (have !== 'dir') problems.add(`${rel} is a ${have}, but the template needs a directory there`);
    } else if (have !== 'file') {
      problems.add(`${rel} is a ${have}, but the template writes a file there`);
    } else {
      overwrite.push(rel);
    }
  }

  const list = [...problems];
  if (collisions.length) {
    const shown = collisions.slice(0, 10).join(', ');
    const more = collisions.length > 10 ? ` (+${collisions.length - 10} more)` : '';
    list.unshift(
      `framework-managed paths already hold content: ${shown}${more}. This directory is ` +
        'not a complete Tess OS install (.tess/tess.lock plus tess.manifest.json), and ' +
        '--force only clean-replaces managed paths in one. Adopting an existing ' +
        'directory or instance is not supported in create-tess 0.2.0',
    );
  }
  return { install, move, overwrite, problems: list };
}

function uniqueBackupName(targetDir) {
  const ts = new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d+Z$/, 'Z');
  let name = `${BACKUP_PREFIX}${ts}`;
  for (let i = 1; existsSync(join(targetDir, name)); i++) name = `${BACKUP_PREFIX}${ts}-${i}`;
  return name;
}

// Copy every overwritten file, then move every managed path, into the backup.
// Returns null when the plan replaces nothing. Any failure puts the moved
// paths back and removes the backup before rethrowing, so the caller's
// verification sees the original tree; if a moved path cannot be put back,
// the backup is KEPT (it holds the only copy) and the error names it.
export function createBackup(targetDir, plan, before) {
  if (plan.overwrite.length === 0 && plan.move.length === 0) return null;
  const name = uniqueBackupName(targetDir);
  const dir = join(targetDir, name);
  const filesRoot = join(dir, 'files');
  const moved = [];
  const overwritten = [];
  mkdirSync(filesRoot, { recursive: true });
  // Self-ignoring: git never picks up the backup, even with no root .gitignore.
  writeFileSync(join(dir, '.gitignore'), '*\n');
  try {
    for (const rel of plan.overwrite) {
      const dest = absOf(filesRoot, rel);
      mkdirSync(dirname(dest), { recursive: true });
      copyFileSync(absOf(targetDir, rel), dest);
      const expected = before.get(rel);
      const sha = sha256File(dest);
      if (!expected || !expected.endsWith(`|${sha}`)) {
        throw new Error(`backup copy of ${rel} does not match the pre-run snapshot`);
      }
      overwritten.push({ path: rel, sha256: sha });
    }
    for (const rel of plan.move) {
      const dest = absOf(filesRoot, rel);
      mkdirSync(dirname(dest), { recursive: true });
      renameSync(absOf(targetDir, rel), dest);
      moved.push(rel);
    }
    const manifest = {
      created: new Date().toISOString(),
      tool: 'create-tess --force',
      note:
        'Files create-tess replaced. "moved" paths were moved here whole; ' +
        '"overwritten" files were copied here before being replaced. To undo by hand, ' +
        'copy files/<path> back to <path>.',
      moved,
      overwritten,
    };
    writeFileSync(join(dir, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
  } catch (err) {
    const stuck = [];
    for (const rel of [...moved].reverse()) {
      try {
        renameSync(absOf(filesRoot, rel), absOf(targetDir, rel));
      } catch {
        stuck.push(rel);
      }
    }
    if (stuck.length === 0) rmSync(dir, { recursive: true, force: true });
    else err.message += ` (could not put back ${stuck.join(', ')}; the originals are in ${name}/files)`;
    throw err;
  }
  return { name, dir, moved, overwritten: overwritten.map((o) => o.path) };
}

// Compare the target (minus any backup dir) against `before`.
export function verifyAgainst(targetDir, before, skipName = null) {
  const after = snapshotTree(targetDir, { skipTop: (n) => n === skipName });
  const diffs = diffSnapshots(before, after);
  return { clean: diffs.length === 0, diffs, entries: before.size };
}

// Undo a failed forced run. `backup` is null when the plan replaced nothing
// (the run only added paths). Returns { clean, diffs, errors, entries, backupKept }.
export function restoreFromBackup(targetDir, backup, before) {
  const errors = [];
  const skipName = backup ? backup.name : null;
  const filesRoot = backup ? join(backup.dir, 'files') : null;
  const attempt = (rel, fn) => {
    try {
      fn();
    } catch (err) {
      errors.push(`${rel}: ${err.message}`);
    }
  };
  for (const rel of backup ? backup.moved : []) {
    attempt(rel, () => {
      rmSync(absOf(targetDir, rel), { recursive: true, force: true });
      mkdirSync(dirname(absOf(targetDir, rel)), { recursive: true });
      renameSync(absOf(filesRoot, rel), absOf(targetDir, rel));
    });
  }
  for (const rel of backup ? backup.overwritten : []) {
    attempt(rel, () => {
      rmSync(absOf(targetDir, rel), { recursive: true, force: true });
      copyFileSync(absOf(filesRoot, rel), absOf(targetDir, rel));
    });
  }
  // Delete everything the run added (shallowest first; a removed directory
  // takes its subtree with it).
  const now = snapshotTree(targetDir, { skipTop: (n) => n === skipName });
  const removed = [];
  for (const rel of now.keys()) {
    if (before.has(rel)) continue;
    if (removed.some((r) => rel.startsWith(`${r}/`))) continue;
    attempt(rel, () => rmSync(absOf(targetDir, rel), { recursive: true, force: true }));
    removed.push(rel);
  }
  let result = verifyAgainst(targetDir, before, skipName);
  let backupKept = Boolean(backup);
  if (backup && result.clean && errors.length === 0) {
    rmSync(backup.dir, { recursive: true, force: true });
    result = verifyAgainst(targetDir, before);
    backupKept = existsSync(backup.dir);
  }
  return { ...result, clean: result.clean && errors.length === 0, errors, backupKept };
}
