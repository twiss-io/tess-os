// v021-units.test.js — plain-English Python preflight and the --mode/--preset flags.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, chmodSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { checkPython } from '../src/python.js';
import { resolveBrainFlags } from '../src/brain.js';
import { parseArgs } from '../src/args.js';

function fakePython(body) {
  const dir = mkdtempSync(join(tmpdir(), 'ct-fakepy-'));
  writeFileSync(join(dir, 'python3'), `#!/bin/sh\n${body}\n`);
  chmodSync(join(dir, 'python3'), 0o755);
  return dir;
}

test('checkPython: missing Python gives the exact next step on a Mac', () => {
  const r = checkPython({ cmd: 'python3-definitely-not-installed', platform: 'darwin' });
  assert.equal(r.ok, false);
  assert.match(r.message, /needs Python 3\.9 or newer, and this computer does not have it yet/);
  assert.match(r.message, /xcode-select --install/);
});

test('checkPython: the macOS stub that exits non-zero counts as missing', () => {
  const dir = fakePython('echo "xcode-select: note: No developer tools were found" >&2; exit 1');
  const r = checkPython({ cmd: join(dir, 'python3'), platform: 'darwin' });
  rmSync(dir, { recursive: true, force: true });
  assert.equal(r.ok, false);
  assert.match(r.message, /does not have it yet/);
});

test('checkPython: too-old Python names the version found and where to get a new one', () => {
  const dir = fakePython('echo 3.8');
  const r = checkPython({ cmd: join(dir, 'python3') });
  rmSync(dir, { recursive: true, force: true });
  assert.equal(r.ok, false);
  assert.match(r.message, /this computer has Python 3\.8/);
  assert.match(r.message, /python\.org\/downloads/);
});

test('checkPython: 3.9 is enough (no PyYAML needed)', () => {
  const dir = fakePython('echo 3.9');
  const r = checkPython({ cmd: join(dir, 'python3') });
  rmSync(dir, { recursive: true, force: true });
  assert.deepEqual([r.ok, r.version], [true, '3.9']);
});

test('--mode / --preset / --no-onboarding parse and validate', () => {
  const o = parseArgs(['x', '--yes', '--mode', 'agency', '--preset=solo-consultant', '--no-onboarding']);
  assert.deepEqual([o.mode, o.preset, o.noOnboarding], ['agency', 'solo-consultant', true]);
  assert.deepEqual(resolveBrainFlags(o), { mode: 'agency', preset: 'solo-consultant' });
  assert.deepEqual(resolveBrainFlags({}), { mode: 'personal', preset: null });
  assert.deepEqual(resolveBrainFlags({ mode: 'organisation', preset: 'none' }), { mode: 'organisation', preset: null });
  assert.match(resolveBrainFlags({ mode: 'family' }).error, /--mode must be one of personal, agency, organisation/);
  assert.match(resolveBrainFlags({ mode: 'personal', preset: 'startup' }).error, /must be none/);
});
