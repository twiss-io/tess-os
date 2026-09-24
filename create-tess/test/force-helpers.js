// force-helpers.js — shared helpers for the CLI-level --force tests
// (force-safety.test.js, force-edge.test.js). Not a test file itself: `npm
// test` only runs test/*.test.js.
//
// walkHash() is deliberately independent of src/tree-snapshot.js, so a bug in
// the code under test cannot hide itself.
import { after } from 'node:test';
import { spawnSync } from 'node:child_process';
import {
  mkdtempSync,
  rmSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  writeFileSync,
  copyFileSync,
  lstatSync,
  readlinkSync,
} from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { tmpdir } from 'node:os';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';

const TEST_DIR = dirname(fileURLToPath(import.meta.url));
export const PKG_DIR = resolve(TEST_DIR, '..');
export const ENTRY = join(PKG_DIR, 'bin', 'create-tess.mjs');
export const BUNDLED = join(PKG_DIR, 'template');
export const PKG_VERSION = JSON.parse(readFileSync(join(PKG_DIR, 'package.json'), 'utf8')).version;
export const FLAGS = ['--yes', '--no-git-init', '--no-gate-hooks'];

const tempDirs = [];
after(() => {
  for (const d of tempDirs) rmSync(d, { recursive: true, force: true });
});
export function mkTemp(prefix) {
  const d = mkdtempSync(join(tmpdir(), prefix));
  tempDirs.push(d);
  return d;
}

// Sorted walk, never following symlinks: "<rel> <kind> <sha256|link target>".
export function walkHash(root) {
  const out = [];
  (function rec(dir, base) {
    for (const name of readdirSync(dir).sort()) {
      const p = join(dir, name);
      const rel = base ? `${base}/${name}` : name;
      const st = lstatSync(p);
      if (st.isSymbolicLink()) out.push(`${rel} symlink ${readlinkSync(p)}`);
      else if (st.isDirectory()) {
        out.push(`${rel} dir`);
        rec(p, rel);
      } else {
        out.push(`${rel} file ${createHash('sha256').update(readFileSync(p)).digest('hex')}`);
      }
    }
  })(root, '');
  return out;
}

export function runCli(args) {
  return spawnSync(process.execPath, [ENTRY, ...args], { cwd: PKG_DIR, encoding: 'utf8' });
}

export const show = (r) => `\nSTDOUT:\n${r.stdout}\nSTDERR:\n${r.stderr}`;

export function tessctl(target, ...sub) {
  return spawnSync('python3', [join(target, '.tess', 'bin', 'tessctl'), ...sub], {
    cwd: target,
    env: { ...process.env, TESS_ROOT: target },
    encoding: 'utf8',
  });
}

export function backupDirs(target) {
  return readdirSync(target).filter((n) => n.startsWith('.create-tess-backup-'));
}

// A template whose tessctl fails every verb: promote succeeds, bake fails.
// Lays down .tess/bin/tessctl, .tess/core/roster-paths.json and NEWFILE.md.
export function brokenTemplate() {
  const broken = mkTemp('ct-force-broken-');
  mkdirSync(join(broken, '.tess', 'core'), { recursive: true });
  mkdirSync(join(broken, '.tess', 'bin'), { recursive: true });
  copyFileSync(join(BUNDLED, '.tess', 'core', 'roster-paths.json'), join(broken, '.tess', 'core', 'roster-paths.json'));
  writeFileSync(
    join(broken, '.tess', 'bin', 'tessctl'),
    '#!/usr/bin/env python3\nimport sys\nsys.stderr.write("simulated bake failure\\n")\nsys.exit(1)\n',
  );
  writeFileSync(join(broken, 'NEWFILE.md'), 'added by the broken template\n');
  return broken;
}
