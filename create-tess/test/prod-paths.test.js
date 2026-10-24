// prod-paths.test.js — the wizard can name the adopter's production code.
//
// The shipped policy's production rule points at `__REPLACE_ME__/prod/**`,
// so a fresh install's `tessctl doctor` warns that the ship gate reviews none
// of the app's code. `--prod-paths` (or the skippable prompt) writes the real
// folders into that rule, in both policy copies, and re-pins the lock entry,
// so doctor and verify stay clean and the warning goes away. Skipping leaves
// the placeholder (and the warning) exactly as before.
import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, rmSync, readFileSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import './anchor-cleanup.js';

import { parseArgs } from '../src/args.js';
import { parseProdPaths, applyProdPaths, PROD_PLACEHOLDER_LINE, PROD_PATHS_MAX } from '../src/prod-paths.js';
import { PROD_PATHS_PROMPT, PROD_PATHS_SKIP_HINT, prodPathsLine } from '../src/journey.js';

const PKG_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const REPO = resolve(PKG_DIR, '..');
const ENTRY = join(PKG_DIR, 'bin', 'create-tess.mjs');
const POLICY = readFileSync(join(REPO, 'core', 'policy', 'policy.yaml'), 'utf8');
const WARNING = /still points at __REPLACE_ME__/;
const temps = [];
after(() => temps.forEach((d) => rmSync(d, { recursive: true, force: true })));

test('parseProdPaths: folders become folder/**, patterns stay, duplicates collapse', () => {
  assert.deepEqual(parseProdPaths('src, api/**, ./apps/web/, src').value, ['src/**', 'api/**', 'apps/web/**']);
  assert.deepEqual(parseProdPaths('infra/prod/*.tf').value, ['infra/prod/*.tf']);
});

test('parseProdPaths: empty, whitespace or "skip" means skip (no change)', () => {
  for (const raw of [undefined, null, '', '   ', 'skip', 'SKIP', ' , ']) {
    const r = parseProdPaths(raw);
    assert.equal(r.ok, true, String(raw));
    assert.deepEqual(r.value, [], String(raw));
  }
});

test('parseProdPaths: refuses absolute, "..", match-everything, quotes, spaces, colons', () => {
  for (const raw of ['/etc', '../x', 'a/../b', '**', '*', '**/*', 'a"b', 'my app', 'a:b',
    'a#b', 'a\\b', '-x', 'a//b', '__REPLACE_ME__ x', '__REPLACE_ME__/prod/**']) {
    const r = parseProdPaths(raw);
    assert.equal(r.ok, false, raw);
    assert.ok(r.error.length > 10, raw);
  }
  const many = Array.from({ length: PROD_PATHS_MAX + 1 }, (_, i) => `d${i}`).join(',');
  assert.equal(parseProdPaths(many).ok, false);
});

test('applyProdPaths replaces only the placeholder line; no globs = unchanged', () => {
  assert.equal(POLICY.split(PROD_PLACEHOLDER_LINE).length, 2, 'placeholder is in the shipped policy once');
  const { text, changed } = applyProdPaths(POLICY, ['src/**', 'api/**']);
  assert.equal(changed, true);
  assert.ok(!text.includes(PROD_PLACEHOLDER_LINE));
  assert.ok(text.includes('        - "src/**"\n        - "api/**"\n'));
  assert.equal(text.replace('        - "src/**"\n        - "api/**"\n', PROD_PLACEHOLDER_LINE), POLICY);
  assert.deepEqual(applyProdPaths(POLICY, []), { text: POLICY, changed: false });
  assert.throws(() => applyProdPaths('policy: {}\n', ['src/**']), /not found exactly once/);
});

test('--prod-paths parses as a value flag; the prompt says how to skip', () => {
  assert.equal(parseArgs(['--prod-paths', 'src,api']).prodPaths, 'src,api');
  assert.equal(parseArgs(['--prod-paths=src']).prodPaths, 'src');
  assert.throws(() => parseArgs(['--prod-paths', '--yes']), /requires a value/);
  assert.match(PROD_PATHS_SKIP_HINT, /Enter to skip/);
  assert.match(PROD_PATHS_PROMPT, /review before they ship/);
  assert.equal(prodPathsLine(['src/**']), 'src/**');
  assert.match(prodPathsLine([]), /not set yet/);
});

function wizard(extra) {
  const target = mkdtempSync(join(tmpdir(), 'create-tess-prod-'));
  temps.push(target);
  const r = spawnSync(process.execPath, [ENTRY, '--yes', '--operator=Alex', `--template-source=${REPO}`,
    '--no-onboarding', `--target=${target}`, ...extra], { cwd: PKG_DIR, encoding: 'utf8' });
  return { target, r };
}

function doctor(target) {
  return spawnSync('python3', [join(target, '.tess', 'bin', 'tessctl'), 'doctor'], {
    cwd: target, env: { ...process.env, TESS_ROOT: target }, encoding: 'utf8',
  });
}

test('wizard --prod-paths: both policy copies carry the paths; doctor/verify clean, no warning', { timeout: 240000 }, () => {
  const { target, r } = wizard(['--prod-paths', 'src, api/**']);
  assert.equal(r.status, 0, r.stdout + r.stderr);
  for (const rel of ['core/policy/policy.yaml', '.tess/core/policy/policy.yaml']) {
    const text = readFileSync(join(target, rel), 'utf8');
    assert.ok(text.includes('        - "src/**"\n        - "api/**"\n'), rel);
    assert.ok(!text.includes(PROD_PLACEHOLDER_LINE), rel);
  }
  const d = doctor(target);
  assert.equal(d.status, 0, d.stdout + d.stderr);
  assert.doesNotMatch(d.stdout, WARNING);
  const v = spawnSync('python3', [join(target, '.tess', 'bin', 'tessctl'), 'verify'], {
    cwd: target, env: { ...process.env, TESS_ROOT: target }, encoding: 'utf8' });
  assert.equal(v.status, 0, v.stdout + v.stderr);
});

test('wizard without --prod-paths keeps the placeholder and the doctor warning', { timeout: 240000 }, () => {
  const { target, r } = wizard([]);
  assert.equal(r.status, 0, r.stdout + r.stderr);
  assert.ok(readFileSync(join(target, 'core/policy/policy.yaml'), 'utf8').includes(PROD_PLACEHOLDER_LINE));
  const d = doctor(target);
  assert.equal(d.status, 0, d.stdout + d.stderr);
  assert.match(d.stdout, WARNING);
});

test('wizard refuses a bad --prod-paths before writing anything', () => {
  const { target, r } = wizard(['--prod-paths', '../outside']);
  assert.notEqual(r.status, 0);
  assert.match(r.stderr, /--prod-paths/);
  assert.equal(spawnSync('ls', ['-A', target], { encoding: 'utf8' }).stdout.trim(), '');
});
