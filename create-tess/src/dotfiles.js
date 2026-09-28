// dotfiles.js — ship the template's .gitignore files through npm intact.
//
// npm never packs a file named `.gitignore` (npm-packlist drops it at every
// depth), so a scaffold from the published tarball arrived with NO
// .gitignore at all: `.env`, `operator/profile.json` and client data were
// all one `git add -A` away from a commit. The bundled template therefore
// stores each one under SHIPPED_GITIGNORE ("gitignore", no dot), written by
// scripts/build-template.mjs, and the scaffold renames it back to
// `.gitignore` in staging before anything reaches the target.
import { existsSync, readdirSync, renameSync } from 'node:fs';
import { join, relative, sep } from 'node:path';

export const SHIPPED_GITIGNORE = 'gitignore';
export const REAL_GITIGNORE = '.gitignore';
const SKIP_DIRS = new Set(['.git', 'node_modules']);

function* walkDirs(dir) {
  yield dir;
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.isDirectory() && !SKIP_DIRS.has(entry.name)) yield* walkDirs(join(dir, entry.name));
  }
}

// Rename every `from` file under `root` to `to` in the same directory, unless
// a `to` sibling already exists (then the `from` file is left untouched, so a
// git-clone source that carries both names is never clobbered). Returns the
// renamed paths relative to root, '/'-separated.
function renameAll(root, from, to) {
  const done = [];
  for (const dir of walkDirs(root)) {
    const src = join(dir, from);
    const dst = join(dir, to);
    if (existsSync(src) && !existsSync(dst)) {
      renameSync(src, dst);
      done.push(relative(root, dst).split(sep).join('/'));
    }
  }
  return done.sort();
}

// Build time: `.gitignore` -> `gitignore` inside the bundled template.
export function packGitignores(templateDir) {
  return renameAll(templateDir, REAL_GITIGNORE, SHIPPED_GITIGNORE);
}

// Scaffold time: `gitignore` -> `.gitignore` inside the staged template.
export function restoreGitignores(stagingDir) {
  return renameAll(stagingDir, SHIPPED_GITIGNORE, REAL_GITIGNORE);
}
