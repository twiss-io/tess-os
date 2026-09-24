// force-safety.test.js — `--force` must never destroy an existing directory
// while claiming it is clean, and the install-detection message must only
// name tessctl verbs that exist.
//
// Every test drives the real CLI (bin/create-tess.mjs) and checks the target
// with its OWN sorted walk + sha256, independent of src/tree-snapshot.js, so a
// bug in the code under test cannot hide itself.
//
// Run: npm test   (or `node --test test/force-safety.test.js`)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import {
  mkdirSync,
  readdirSync,
  readFileSync,
  writeFileSync,
  copyFileSync,
  symlinkSync,
  existsSync,
} from 'node:fs';
import { join } from 'node:path';
import {
  BUNDLED,
  FLAGS,
  PKG_VERSION,
  mkTemp,
  walkHash,
  runCli,
  show,
  tessctl,
  backupDirs,
  brokenTemplate,
} from './force-helpers.js';

const NOT_SUPPORTED = `not supported in create-tess ${PKG_VERSION}`;

test('--force over user content in managed paths plus a symlinked skill: exit 1, tree unchanged, "left clean" only because it is', { timeout: 120000 }, () => {
  const target = mkTemp('ct-force-collide-');
  const outside = mkTemp('ct-force-outside-');
  writeFileSync(join(outside, 'keep.txt'), 'outside the target\n');
  writeFileSync(join(target, 'CLAUDE.md'), '# my own CLAUDE.md\n');
  mkdirSync(join(target, 'conductor'));
  writeFileSync(join(target, 'conductor', 'mine.md'), 'mine\n');
  mkdirSync(join(target, '.claude', 'agents'), { recursive: true });
  writeFileSync(join(target, '.claude', 'agents', 'custom.md'), 'custom agent\n');
  mkdirSync(join(target, '.claude', 'skills'), { recursive: true });
  const skill = readdirSync(join(BUNDLED, '.claude', 'skills')).sort()[0];
  symlinkSync(outside, join(target, '.claude', 'skills', skill));
  writeFileSync(join(target, 'notes.md'), 'user notes\n');

  const before = walkHash(target);
  const outsideBefore = walkHash(outside);
  const r = runCli([`--target=${target}`, '--force', ...FLAGS]);

  assert.equal(r.status, 1, `--force must refuse${show(r)}`);
  const afterWalk = walkHash(target);
  assert.deepEqual(afterWalk, before, 'the target must be byte-identical after a refused --force');
  assert.deepEqual(walkHash(outside), outsideBefore, 'nothing may be written through the symlink');
  // "left clean" may only appear when the walks are equal (asserted above).
  assert.match(r.stdout, /left clean/, `a verified refusal says so${show(r)}`);
  for (const p of ['CLAUDE.md', 'conductor/mine.md', '.claude/agents/custom.md', `.claude/skills/${skill}`]) {
    assert.ok(r.stderr.includes(p), `the refusal must name ${p}${show(r)}`);
  }
  assert.ok(r.stderr.includes(NOT_SUPPORTED), show(r));
});

test('--force refuses a type conflict (a file where the template needs a directory) and writes nothing', { timeout: 120000 }, () => {
  const target = mkTemp('ct-force-type-');
  writeFileSync(join(target, 'kb'), 'a file named kb\n');
  writeFileSync(join(target, 'notes.md'), 'user notes\n');
  const before = walkHash(target);
  const r = runCli([`--target=${target}`, '--force', ...FLAGS]);
  assert.equal(r.status, 1, show(r));
  assert.deepEqual(walkHash(target), before);
  assert.match(r.stderr, /kb is a file, but the template needs a directory there/, show(r));
});

test('--force refuses a symlink on a template file path and never writes through it', { timeout: 120000 }, () => {
  const target = mkTemp('ct-force-link-');
  const outside = mkTemp('ct-force-victim-');
  writeFileSync(join(outside, 'victim.md'), 'must not be overwritten\n');
  symlinkSync(join(outside, 'victim.md'), join(target, 'README.md'));
  const before = walkHash(target);
  const outsideBefore = walkHash(outside);
  const r = runCli([`--target=${target}`, '--force', ...FLAGS]);
  assert.equal(r.status, 1, show(r));
  assert.deepEqual(walkHash(target), before);
  assert.deepEqual(walkHash(outside), outsideBefore);
  assert.match(r.stderr, /README\.md is a symlink, but the template writes a file there/, show(r));
});

test('--force over a real install: user-only files survive, replaced paths are backed up, doctor + verify pass', { timeout: 240000 }, () => {
  const target = mkTemp('ct-force-reinstall-');
  const first = runCli([`--target=${target}`, ...FLAGS]);
  assert.equal(first.status, 0, `first scaffold failed${show(first)}`);

  mkdirSync(join(target, 'notes'));
  writeFileSync(join(target, 'notes', 'mine.md'), 'user-only file\n');
  writeFileSync(join(target, '.claude', 'agents', 'zzz-custom.md'), '# custom agent\n');
  const userReadme = '# my edited README\n';
  writeFileSync(join(target, 'README.md'), userReadme);

  const second = runCli([`--target=${target}`, '--force', ...FLAGS]);
  assert.equal(second.status, 0, `forced re-scaffold failed${show(second)}`);

  assert.equal(readFileSync(join(target, 'notes', 'mine.md'), 'utf8'), 'user-only file\n');
  assert.ok(!existsSync(join(target, '.claude', 'agents', 'zzz-custom.md')), 'managed paths are clean-replaced');
  assert.equal(
    readFileSync(join(target, 'README.md'), 'utf8'),
    readFileSync(join(BUNDLED, 'README.md'), 'utf8'),
  );

  const backups = backupDirs(target);
  assert.equal(backups.length, 1, `exactly one backup dir expected, got ${backups}`);
  const b = join(target, backups[0]);
  assert.equal(readFileSync(join(b, '.gitignore'), 'utf8'), '*\n');
  assert.equal(readFileSync(join(b, 'files', 'README.md'), 'utf8'), userReadme);
  assert.equal(readFileSync(join(b, 'files', '.claude', 'agents', 'zzz-custom.md'), 'utf8'), '# custom agent\n');
  const manifest = JSON.parse(readFileSync(join(b, 'manifest.json'), 'utf8'));
  assert.ok(manifest.moved.includes('.claude/agents'), JSON.stringify(manifest.moved));
  assert.ok(manifest.overwritten.some((o) => o.path === 'README.md'));
  assert.ok(manifest.overwritten.some((o) => o.path === 'operator/profile.json'));
  assert.match(second.stdout, /backed up in \.create-tess-backup-/);
  assert.match(second.stdout, /doctor and verify passed/);

  // The backup is still there after doctor and verify ran, and does not
  // disturb them.
  const doctor = tessctl(target, 'doctor');
  assert.equal(doctor.status, 0, `doctor after --force failed\n${doctor.stdout}\n${doctor.stderr}`);
  const verify = tessctl(target, 'verify');
  assert.equal(verify.status, 0, `verify after --force failed\n${verify.stdout}\n${verify.stderr}`);
  assert.ok(existsSync(b));
});

test('a forced run that fails mid-bake restores the install byte-for-byte and verifies it', { timeout: 240000 }, () => {
  const target = mkTemp('ct-force-restore-');
  const first = runCli([`--target=${target}`, ...FLAGS]);
  assert.equal(first.status, 0, `first scaffold failed${show(first)}`);
  mkdirSync(join(target, 'notes'));
  writeFileSync(join(target, 'notes', 'mine.md'), 'user-only file\n');

  // A template whose tessctl fails every verb: promote succeeds, bake fails.
  const broken = brokenTemplate();

  const before = walkHash(target);
  const r = runCli([`--target=${target}`, '--force', `--template-source=${broken}`, ...FLAGS]);
  assert.equal(r.status, 1, show(r));
  assert.deepEqual(walkHash(target), before, 'a failed forced run must restore the exact pre-run tree');
  assert.match(r.stdout, /left clean \(verified/, show(r));
  assert.deepEqual(backupDirs(target), [], 'a verified restore removes its backup');
});

test('install detection: a dir holding only .tess/tess.lock is "already a Tess OS install", naming only real tessctl verbs', { timeout: 60000 }, () => {
  const target = mkTemp('ct-detect-');
  mkdirSync(join(target, '.tess'));
  copyFileSync(join(BUNDLED, '.tess', 'tess.lock'), join(target, '.tess', 'tess.lock'));
  const r = runCli([`--target=${target}`, ...FLAGS]);
  assert.equal(r.status, 1, show(r));
  assert.match(r.stderr, /already a Tess OS install/, show(r));

  const help = spawnSync('python3', [join(BUNDLED, '.tess', 'bin', 'tessctl'), '--help'], { encoding: 'utf8' });
  assert.equal(help.status, 0, help.stderr);
  const realVerbs = new Set([...help.stdout.matchAll(/^ {4}([a-z][a-z-]*)\s/gm)].map((m) => m[1]));
  assert.ok(realVerbs.has('doctor') && realVerbs.has('update'), `unexpected --help shape:\n${help.stdout}`);
  const named = [...r.stderr.matchAll(/tessctl ([a-z][a-z-]*)/g)].map((m) => m[1]);
  assert.ok(named.length > 0, 'the message should point at a tessctl verb');
  for (const verb of named) assert.ok(realVerbs.has(verb), `message names non-existent verb: tessctl ${verb}`);
  assert.doesNotMatch(r.stderr, /adopt |reconfigure/);
});

test('a non-empty, non-Tess dir without --force says adoption is not supported in this version', { timeout: 60000 }, () => {
  const target = mkTemp('ct-nonempty-');
  writeFileSync(join(target, 'notes.md'), 'hello\n');
  const r = runCli([`--target=${target}`, ...FLAGS]);
  assert.equal(r.status, 1, show(r));
  assert.ok(r.stderr.includes(NOT_SUPPORTED), show(r));
  assert.doesNotMatch(r.stderr, /tessctl (adopt|reconfigure)/);
  assert.equal(readFileSync(join(target, 'notes.md'), 'utf8'), 'hello\n');
});
