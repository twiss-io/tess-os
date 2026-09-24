// force-plan.test.js — unit coverage for the --force plan, backup and
// restore (src/force-plan.js, src/force-run.js). The end-to-end behaviour is
// in force-safety.test.js; this file pins the honesty rule: "clean" is never
// reported unless the restored tree matches the pre-run snapshot.
//
// Run: npm test   (or `node --test test/force-plan.test.js`)
import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import {
  mkdtempSync,
  rmSync,
  mkdirSync,
  writeFileSync,
  readFileSync,
  symlinkSync,
  existsSync,
} from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import {
  planForce,
  detectInstall,
  createBackup,
  snapshotTree,
  diffSnapshots,
} from '../src/force-plan.js';
import { rollback, verifyOnly } from '../src/force-run.js';

const tempDirs = [];
after(() => {
  for (const d of tempDirs) rmSync(d, { recursive: true, force: true });
});
function mkTemp(prefix) {
  const d = mkdtempSync(join(tmpdir(), prefix));
  tempDirs.push(d);
  return d;
}

function fixtureTarget() {
  const t = mkTemp('ct-plan-target-');
  writeFileSync(join(t, 'a.txt'), 'original a\n');
  mkdirSync(join(t, 'sub'));
  writeFileSync(join(t, 'sub', 'b.txt'), 'original b\n');
  return t;
}

test('restore puts overwritten files back, deletes added paths, and only then says clean', () => {
  const t = fixtureTarget();
  const before = snapshotTree(t);
  const state = { before, backup: createBackup(t, { overwrite: ['a.txt'], move: [] }, before) };
  writeFileSync(join(t, 'a.txt'), 'scaffold wrote this\n');
  mkdirSync(join(t, 'added', 'deep'), { recursive: true });
  writeFileSync(join(t, 'added', 'deep', 'x.md'), 'new\n');

  const r = rollback(t, state);
  assert.equal(r.clean, true, r.stdout);
  assert.match(r.stdout, /left clean \(verified/);
  assert.deepEqual(diffSnapshots(before, snapshotTree(t)), []);
  assert.ok(!existsSync(state.backup.dir), 'a verified restore removes the backup');
});

test('restore that cannot verify says NOT clean, never "left clean", and keeps the backup', () => {
  const t = fixtureTarget();
  const before = snapshotTree(t);
  const state = { before, backup: createBackup(t, { overwrite: ['a.txt', 'sub/b.txt'], move: [] }, before) };
  writeFileSync(join(t, 'a.txt'), 'scaffold wrote this\n');
  // Simulate a lost backup copy: a.txt cannot be restored.
  rmSync(join(state.backup.dir, 'files', 'a.txt'));

  const r = rollback(t, state);
  assert.equal(r.clean, false);
  assert.doesNotMatch(r.stdout, /left clean/);
  assert.match(r.stdout, /NOT clean/);
  assert.match(r.stdout, /a\.txt/);
  assert.ok(existsSync(state.backup.dir), 'an unverified restore keeps the backup');
  assert.equal(readFileSync(join(t, 'sub', 'b.txt'), 'utf8'), 'original b\n');
});

test('createBackup refuses a copy that does not match the snapshot and undoes its moves', () => {
  const t = fixtureTarget();
  const before = snapshotTree(t);
  writeFileSync(join(t, 'a.txt'), 'changed after the snapshot\n');
  assert.throws(
    () => createBackup(t, { overwrite: ['a.txt'], move: ['sub'] }, before),
    /does not match the pre-run snapshot/,
  );
  assert.ok(existsSync(join(t, 'sub', 'b.txt')), 'moved paths are put back');
  const leftovers = snapshotTree(t);
  assert.ok(![...leftovers.keys()].some((k) => k.startsWith('.create-tess-backup-')));
});

test('planForce: type conflicts and symlinks are problems; a plain overwrite is not', () => {
  const staging = mkTemp('ct-plan-staging-');
  mkdirSync(join(staging, 'x'));
  writeFileSync(join(staging, 'x', 'inner.md'), 'x\n');
  writeFileSync(join(staging, 'y.md'), 'y\n');
  writeFileSync(join(staging, 'z.md'), 'z\n');
  mkdirSync(join(staging, 'd'));
  writeFileSync(join(staging, 'd', 'f.md'), 'f\n');

  const t = mkTemp('ct-plan-conflict-');
  writeFileSync(join(t, 'x'), 'a file where the template has a dir\n');
  symlinkSync(join(t, 'x'), join(t, 'y.md'));
  writeFileSync(join(t, 'z.md'), 'user z\n');
  mkdirSync(join(t, 'real'));
  symlinkSync(join(t, 'real'), join(t, 'd'));

  const plan = planForce(staging, t);
  assert.ok(plan.problems.includes('x is a file, but the template needs a directory there'), plan.problems.join('\n'));
  assert.ok(plan.problems.includes('y.md is a symlink, but the template writes a file there'));
  assert.ok(plan.problems.includes('d is a symlink, but the template needs a directory there'));
  assert.ok(plan.overwrite.includes('z.md'));
  assert.ok(!plan.overwrite.includes('y.md'));
});

test('detectInstall: markers alone are not a real install; lock + manifest are', () => {
  const t = mkTemp('ct-detect-unit-');
  mkdirSync(join(t, 'operator'));
  writeFileSync(join(t, 'operator', 'profile.json'), '{}\n');
  assert.deepEqual(detectInstall(t), { markers: ['operator/profile.json'], real: false });

  mkdirSync(join(t, '.tess'));
  writeFileSync(join(t, '.tess', 'tess.lock'), 'schema: 1\nframework:\n  version: 0.2.0\nfiles:\n');
  writeFileSync(join(t, 'tess.manifest.json'), '[]\n');
  assert.equal(detectInstall(t).real, false, 'a manifest that is not an object is not an install');
  writeFileSync(join(t, 'tess.manifest.json'), '{"schema": 1}\n');
  assert.equal(detectInstall(t).real, true);
});

test('an empty plan creates no backup, and rollback still deletes what the run added', () => {
  const t = fixtureTarget();
  const before = snapshotTree(t);
  const backup = createBackup(t, { overwrite: [], move: [] }, before);
  assert.equal(backup, null);
  mkdirSync(join(t, 'added'));
  writeFileSync(join(t, 'added', 'x.md'), 'new\n');
  writeFileSync(join(t, 'top.md'), 'new\n');
  const r = rollback(t, { before, backup });
  assert.equal(r.clean, true, r.stdout);
  assert.deepEqual(diffSnapshots(before, snapshotTree(t)), []);
});

test('snapshotTree refuses a root that is a symlink or a file instead of walking it as empty', () => {
  const t = fixtureTarget();
  const base = mkTemp('ct-plan-linkroot-');
  const link = join(base, 'link');
  symlinkSync(t, link);
  assert.throws(() => snapshotTree(link), /is a symlink, not a directory/);
  assert.throws(() => snapshotTree(join(t, 'a.txt')), /is a file, not a directory/);
  assert.equal(snapshotTree(join(base, 'missing')).size, 0, 'a missing root is an empty snapshot');
});

test('rollback never says clean, and deletes nothing, when a target that had content has an empty snapshot', () => {
  const t = fixtureTarget();
  writeFileSync(join(t, 'added-by-run.md'), 'x\n');
  const r = rollback(t, { before: new Map(), backup: null, hadContent: true });
  assert.equal(r.clean, false);
  assert.doesNotMatch(r.stdout, /left clean/);
  assert.match(r.stdout, /NOT attempted/);
  assert.ok(existsSync(join(t, 'a.txt')) && existsSync(join(t, 'added-by-run.md')), 'nothing may be deleted');
  assert.doesNotMatch(verifyOnly(t, { before: new Map(), hadContent: true }), /left clean/);
});

test('rollback of a target that existed empty empties it again and keeps the directory', () => {
  const t = mkTemp('ct-plan-empty-');
  const before = snapshotTree(t);
  mkdirSync(join(t, '.tess', 'bin'), { recursive: true });
  writeFileSync(join(t, 'NEWFILE.md'), 'x\n');
  const r = rollback(t, { before, backup: null, hadContent: false });
  assert.equal(r.clean, true, r.stdout);
  assert.match(r.stdout, /empty again/);
  assert.ok(existsSync(t));
  assert.equal(snapshotTree(t).size, 0);
});

test('planForce: a case-variant name on a case-insensitive filesystem is a clear problem', (t) => {
  const staging = mkTemp('ct-plan-case-staging-');
  writeFileSync(join(staging, 'README.md'), 'template\n');
  mkdirSync(join(staging, 'kb'));
  writeFileSync(join(staging, 'kb', 'x.md'), 'x\n');
  const target = mkTemp('ct-plan-case-target-');
  writeFileSync(join(target, 'readme.md'), 'mine\n');
  mkdirSync(join(target, 'KB'));
  writeFileSync(join(target, 'KB', 'x.md'), 'mine\n');
  if (!existsSync(join(target, 'README.md'))) {
    t.skip('case-sensitive filesystem');
    return;
  }
  const plan = planForce(staging, target);
  const text = plan.problems.join('\n');
  assert.match(text, /readme\.md in the target differs from the template's README\.md only in letter case/);
  assert.match(text, /KB in the target differs from the template's kb only in letter case/);
});

test('messages name the running create-tess version, not a hard-coded release', () => {
  const pkg = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8'));
  const staging = mkTemp('ct-plan-ver-staging-');
  mkdirSync(join(staging, 'conductor'));
  writeFileSync(join(staging, 'conductor', 'x.md'), 'x\n');
  const target = mkTemp('ct-plan-ver-target-');
  mkdirSync(join(target, 'conductor'));
  writeFileSync(join(target, 'conductor', 'mine.md'), 'mine\n');
  const plan = planForce(staging, target);
  assert.ok(plan.problems[0].endsWith(`not supported in create-tess ${pkg.version}`), plan.problems[0]);
});
