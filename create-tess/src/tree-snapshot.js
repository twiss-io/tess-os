// tree-snapshot.js — a sorted, symlink-safe walk of a directory with a
// sha256 per file. force-plan.js takes one before a forced scaffold writes
// anything and compares against it after a restore: "clean" is only ever
// claimed when the two walks are identical.
import { lstatSync, readdirSync, readFileSync, readlinkSync } from 'node:fs';
import { join } from 'node:path';
import { createHash } from 'node:crypto';

// A forced run hashes the whole target twice. Past this size, refuse rather
// than spend minutes hashing a directory that is almost certainly the wrong
// target (a home directory, a monorepo root).
export const MAX_SNAPSHOT_ENTRIES = 200000;

export const absOf = (root, rel) => join(root, ...rel.split('/'));

export function lstatOrNull(p) {
  try {
    return lstatSync(p);
  } catch (err) {
    if (err.code === 'ENOENT' || err.code === 'ENOTDIR') return null;
    throw err;
  }
}

export function kindOf(st) {
  if (!st) return null;
  if (st.isSymbolicLink()) return 'symlink';
  if (st.isDirectory()) return 'dir';
  if (st.isFile()) return 'file';
  return 'other';
}

export function sha256File(p) {
  return createHash('sha256').update(readFileSync(p)).digest('hex');
}

// Sorted snapshot of everything under `root`, never following symlinks:
// rel -> "dir|<mode>" | "file|<mode>|<sha256>" | "symlink|<target>" | "other|<mode>".
// A missing root is an empty snapshot. A root that exists but is not a real
// directory (a symlink, a file) throws: its walk would be empty while writes
// through it land somewhere real, and an empty-vs-empty comparison would
// "verify" anything.
export function snapshotTree(root, { skipTop = () => false } = {}) {
  const rootKind = kindOf(lstatOrNull(root));
  if (rootKind !== null && rootKind !== 'dir') {
    throw new Error(`${root} is a ${rootKind}, not a directory; create-tess will not snapshot through it`);
  }
  const out = new Map();
  const visit = (dirAbs, relBase) => {
    for (const name of readdirSync(dirAbs).sort()) {
      if (!relBase && skipTop(name)) continue;
      const rel = relBase ? `${relBase}/${name}` : name;
      const p = join(dirAbs, name);
      const st = lstatSync(p);
      const mode = (st.mode & 0o7777).toString(8);
      if (st.isSymbolicLink()) out.set(rel, `symlink|${readlinkSync(p)}`);
      else if (st.isDirectory()) out.set(rel, `dir|${mode}`);
      else if (st.isFile()) out.set(rel, `file|${mode}|${sha256File(p)}`);
      else out.set(rel, `other|${mode}`);
      if (out.size > MAX_SNAPSHOT_ENTRIES) {
        throw new Error(
          `${root} holds more than ${MAX_SNAPSHOT_ENTRIES} entries; --force will not ` +
            'scaffold into a directory this large. Use a new directory.',
        );
      }
      if (st.isDirectory() && !st.isSymbolicLink()) visit(p, rel);
    }
  };
  if (rootKind === 'dir') visit(root, '');
  return out;
}

// Paths whose snapshot entry differs between `before` and `after`, sorted.
export function diffSnapshots(before, after) {
  const diffs = [];
  for (const [rel, v] of before) {
    if (!after.has(rel)) diffs.push(`removed  ${rel}`);
    else if (after.get(rel) !== v) diffs.push(`changed  ${rel}`);
  }
  for (const rel of after.keys()) if (!before.has(rel)) diffs.push(`added    ${rel}`);
  return diffs.sort((a, b) => a.slice(9).localeCompare(b.slice(9)));
}
