// force-backup.js — the backup and the verified restore that make a failed
// forced run leave the directory exactly as it was (split out of
// force-plan.js, which decides WHAT a forced run may do).
//
// Contract:
//   - createBackup() copies every file the scaffold will overwrite, then
//     moves the managed paths, into <target>/.create-tess-backup-<ts>/files/,
//     and writes a manifest.json. Each copy is hash-checked against the
//     pre-run snapshot.
//   - restoreFromBackup() puts everything back, deletes every path the run
//     added, and walks the tree again. It reports `clean` ONLY when that walk
//     (type, mode, sha256, link target) equals the pre-run snapshot.
import {
  mkdirSync,
  renameSync,
  copyFileSync,
  rmSync,
  writeFileSync,
  existsSync,
} from 'node:fs';
import { join, dirname } from 'node:path';
import { BACKUP_DIR_PREFIX } from './ignore.js';
import { absOf, sha256File, snapshotTree, diffSnapshots } from './tree-snapshot.js';

export const BACKUP_PREFIX = BACKUP_DIR_PREFIX;

function uniqueBackupName(targetDir) {
  const ts = new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d+Z$/, 'Z');
  let name = `${BACKUP_PREFIX}${ts}`;
  for (let i = 1; existsSync(join(targetDir, name)); i++) name = `${BACKUP_PREFIX}${ts}-${i}`;
  return name;
}

// Copy each file the scaffold will overwrite; every copy must hash to the
// pre-run snapshot's value.
function copyOverwrites(targetDir, filesRoot, rels, before) {
  const out = [];
  for (const rel of rels) {
    const dest = absOf(filesRoot, rel);
    mkdirSync(dirname(dest), { recursive: true });
    copyFileSync(absOf(targetDir, rel), dest);
    const expected = before.get(rel);
    const sha = sha256File(dest);
    if (!expected || !expected.endsWith(`|${sha}`)) {
      throw new Error(`backup copy of ${rel} does not match the pre-run snapshot`);
    }
    out.push({ path: rel, sha256: sha });
  }
  return out;
}

function writeManifest(dir, moved, overwritten) {
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
}

// Put moved paths back after a failed backup. Returns the ones that could not
// be put back (their only copy is still in the backup).
function undoMoves(targetDir, filesRoot, moved) {
  const stuck = [];
  for (const rel of [...moved].reverse()) {
    try {
      renameSync(absOf(filesRoot, rel), absOf(targetDir, rel));
    } catch {
      stuck.push(rel);
    }
  }
  return stuck;
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
  let overwritten = [];
  mkdirSync(filesRoot, { recursive: true });
  // Self-ignoring: git never picks up the backup, even with no root .gitignore.
  writeFileSync(join(dir, '.gitignore'), '*\n');
  try {
    overwritten = copyOverwrites(targetDir, filesRoot, plan.overwrite, before);
    for (const rel of plan.move) {
      const dest = absOf(filesRoot, rel);
      mkdirSync(dirname(dest), { recursive: true });
      renameSync(absOf(targetDir, rel), dest);
      moved.push(rel);
    }
    writeManifest(dir, moved, overwritten);
  } catch (err) {
    const stuck = undoMoves(targetDir, filesRoot, moved);
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

// Put the backup's moved and overwritten paths back.
function putBack(targetDir, backup, attempt) {
  const filesRoot = join(backup.dir, 'files');
  for (const rel of backup.moved) {
    attempt(rel, () => {
      rmSync(absOf(targetDir, rel), { recursive: true, force: true });
      mkdirSync(dirname(absOf(targetDir, rel)), { recursive: true });
      renameSync(absOf(filesRoot, rel), absOf(targetDir, rel));
    });
  }
  for (const rel of backup.overwritten) {
    attempt(rel, () => {
      rmSync(absOf(targetDir, rel), { recursive: true, force: true });
      copyFileSync(absOf(filesRoot, rel), absOf(targetDir, rel));
    });
  }
}

// Undo a failed run. `backup` is null when the plan replaced nothing (the run
// only added paths). Returns { clean, diffs, errors, entries, backupKept }.
export function restoreFromBackup(targetDir, backup, before) {
  const errors = [];
  const skipName = backup ? backup.name : null;
  const attempt = (rel, fn) => {
    try {
      fn();
    } catch (err) {
      errors.push(`${rel}: ${err.message}`);
    }
  };
  if (backup) putBack(targetDir, backup, attempt);
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
