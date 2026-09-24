// force-edge.test.js — the edges of the "never claim clean unless it is"
// contract (v0.2.0 review, fix round 1): a --target that is a symlink, a target
// whose parents the run creates, a case-variant name on a case-insensitive
// filesystem, an unreadable file, and the backup dir itself leaking into a
// later scaffold. Every CLI test checks the tree with walkHash(), which is
// independent of the code under test.
//
// Run: npm test   (or `node --test test/force-edge.test.js`)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  mkdirSync,
  writeFileSync,
  symlinkSync,
  lstatSync,
  readlinkSync,
  readdirSync,
  existsSync,
  chmodSync,
} from 'node:fs';
import { join } from 'node:path';
import { isExcludedRel } from '../src/ignore.js';
import { fetchTemplate } from '../src/scaffold.js';
import { mkTemp, walkHash, runCli, show, FLAGS, brokenTemplate } from './force-helpers.js';

test('--force through a symlinked --target: a failed run restores the real directory and keeps the link', { timeout: 120000 }, () => {
  const base = mkTemp('ct-edge-link-');
  const real = join(base, 'real');
  mkdirSync(real);
  writeFileSync(join(real, 'notes.md'), 'user notes\n');
  const link = join(base, 'link');
  symlinkSync(real, link);

  const before = walkHash(real);
  const r = runCli([`--target=${link}`, '--force', `--template-source=${brokenTemplate()}`, ...FLAGS]);
  assert.equal(r.status, 1, show(r));
  assert.ok(lstatSync(link).isSymbolicLink(), 'the user symlink must survive');
  assert.equal(readlinkSync(link), real);
  assert.deepEqual(walkHash(real), before, `the real directory must be byte-identical${show(r)}`);
  // "left clean" is only allowed because the walk above is equal.
  assert.match(r.stdout, /left clean \(verified/, show(r));
});

test('no --force, symlink to an empty dir: a failed run empties the real dir and keeps both the dir and the link', { timeout: 120000 }, () => {
  const base = mkTemp('ct-edge-emptylink-');
  const real = join(base, 'real');
  mkdirSync(real);
  const link = join(base, 'link');
  symlinkSync(real, link);

  const r = runCli([`--target=${link}`, `--template-source=${brokenTemplate()}`, ...FLAGS]);
  assert.equal(r.status, 1, show(r));
  assert.ok(existsSync(link) && lstatSync(link).isSymbolicLink(), `the user symlink must survive${show(r)}`);
  assert.equal(readlinkSync(link), real);
  assert.deepEqual(readdirSync(real), [], 'the half-scaffolded files must be removed from the real dir');
  assert.match(r.stdout, /left clean/, show(r));
});

test('a failed run into a path whose parents did not exist removes every directory it created', { timeout: 120000 }, () => {
  const base = mkTemp('ct-edge-deep-');
  const target = join(base, 'a', 'b', 'c');
  const r = runCli([`--target=${target}`, `--template-source=${brokenTemplate()}`, ...FLAGS]);
  assert.equal(r.status, 1, show(r));
  assert.deepEqual(readdirSync(base), [], `the run created ${join(base, 'a')}, so rollback must remove it${show(r)}`);
  assert.match(r.stdout, /left clean/, show(r));
});

test('--force on a case-insensitive filesystem: readme.md vs the template README.md is a clear refusal', { timeout: 120000 }, (t) => {
  const target = mkTemp('ct-edge-case-');
  writeFileSync(join(target, 'readme.md'), 'my readme\n');
  writeFileSync(join(target, 'notes.md'), 'user notes\n');
  if (!existsSync(join(target, 'README.md'))) {
    t.skip('this filesystem is case-sensitive: readme.md and README.md are different paths');
    return;
  }
  const before = walkHash(target);
  const r = runCli([`--target=${target}`, '--force', ...FLAGS]);
  assert.equal(r.status, 1, show(r));
  assert.deepEqual(walkHash(target), before);
  assert.match(r.stderr, /readme\.md\b[^\n]*README\.md[^\n]*letter case/, show(r));
  assert.doesNotMatch(r.stderr, /does not match the pre-run snapshot/, show(r));
  assert.match(r.stdout, /left clean \(verified/, show(r));
});

test('--force over a target with an unreadable file refuses with guidance, not a raw fatal', { timeout: 120000 }, (t) => {
  if (typeof process.getuid === 'function' && process.getuid() === 0) {
    t.skip('root can read a mode-000 file');
    return;
  }
  const target = mkTemp('ct-edge-eacces-');
  writeFileSync(join(target, 'notes.md'), 'user notes\n');
  mkdirSync(join(target, 'private'));
  writeFileSync(join(target, 'private', 'locked.txt'), 'secret-ish\n');
  const before = walkHash(target);
  chmodSync(join(target, 'private', 'locked.txt'), 0o000);
  let r;
  try {
    r = runCli([`--target=${target}`, '--force', ...FLAGS]);
  } finally {
    chmodSync(join(target, 'private', 'locked.txt'), 0o644);
  }
  assert.equal(r.status, 1, show(r));
  assert.deepEqual(walkHash(target), before);
  assert.doesNotMatch(r.stderr, /fatal:/, show(r));
  assert.match(r.stderr, /--force needs to read every file in the target/, show(r));
  assert.ok(r.stderr.includes(join('private', 'locked.txt')), `the refusal must name the file${show(r)}`);
});

test('a .create-tess-backup-* dir is never copied out of a local --template-source', () => {
  for (const p of [
    '.create-tess-backup-20260924T063933Z',
    '.create-tess-backup-20260924T063933Z/files/operator/profile.json',
    '.create-tess-backup-20260924T063933Z-1/manifest.json',
  ]) {
    assert.equal(isExcludedRel(p), true, `${p} must be excluded`);
  }
  const src = mkTemp('ct-edge-src-');
  writeFileSync(join(src, 'README.md'), '# template\n');
  const bk = join(src, '.create-tess-backup-20260924T063933Z', 'files', 'operator');
  mkdirSync(bk, { recursive: true });
  writeFileSync(join(bk, 'profile.json'), '{"operator": "previous instance"}\n');
  const staging = mkTemp('ct-edge-staging-');
  fetchTemplate(src, staging);
  assert.deepEqual(readdirSync(staging), ['README.md']);
});
