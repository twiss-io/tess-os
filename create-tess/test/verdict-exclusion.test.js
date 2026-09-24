// verdict-exclusion.test.js — `reviews/verdicts/**` never enters a scaffold.
//
// Signed review verdicts (`tessctl verdict sign` writes the signature into the
// verdict file itself) are this repo's own governance records. If they were
// copied, every verdict commit would make the committed create-tess/template
// bundle stale and would ship the maintainer's verdicts to every adopter.
//
// Run: npm test   (or `node --test test/verdict-exclusion.test.js`)
import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import {
  mkdtempSync,
  rmSync,
  cpSync,
  mkdirSync,
  writeFileSync,
  readFileSync,
  readdirSync,
  existsSync,
} from 'node:fs';
import { join, resolve, dirname, relative, sep } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { isExcludedRel, EXCLUDE_DIR_PREFIXES } from '../src/ignore.js';

test('reviews/verdicts is a whole-subtree exclusion', () => {
  assert.equal(isExcludedRel('reviews/verdicts/x.cyra.verdict.md'), true);
  assert.equal(isExcludedRel('reviews/verdicts'), true);
  assert.equal(isExcludedRel('reviews/verdicts/nested/2026-09-24-x.cyra.verdict.md'), true);
  // Case-fold hardening applies like every other prefix.
  assert.equal(isExcludedRel('Reviews/Verdicts/x.cyra.verdict.md'), true);
  assert.ok(EXCLUDE_DIR_PREFIXES.includes('reviews/verdicts'));
});

test('the exclusion is scoped: siblings and look-alike prefixes still ship', () => {
  assert.equal(isExcludedRel('reviews/README.md'), false);
  assert.equal(isExcludedRel('reviews/verdicts-guide.md'), false);
  assert.equal(isExcludedRel('docs/reviews/verdicts.md'), false);
});

// Build-level proof: a tracked reviews/verdicts file must not change the
// built bundle. Rebuilds the template from a throwaway git index that holds
// exactly this repo's tracked files PLUS a dummy verdict, then compares the
// result with the committed create-tess/template byte for byte.
const TEST_DIR = dirname(fileURLToPath(import.meta.url));
const PKG_DIR = resolve(TEST_DIR, '..');
const REPO_ROOT = resolve(PKG_DIR, '..');
const tempDirs = [];
after(() => {
  for (const d of tempDirs) rmSync(d, { recursive: true, force: true });
});

function walkFiles(root) {
  const out = [];
  (function rec(dir) {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const p = join(dir, entry.name);
      if (entry.isDirectory()) rec(p);
      else out.push(relative(root, p).split(sep).join('/'));
    }
  })(root);
  return out.sort();
}

test('a tracked reviews/verdicts file leaves the built template unchanged', { timeout: 240000 }, () => {
  const snap = mkdtempSync(join(tmpdir(), 'ct-verdict-drift-'));
  tempDirs.push(snap);
  const skip = (rel) => {
    const parts = rel.split(sep);
    return parts[0] === '.git' || parts.includes('node_modules') || rel.startsWith(join('create-tess', 'template'));
  };
  cpSync(REPO_ROOT, snap, {
    recursive: true,
    dereference: false,
    filter: (src) => !skip(relative(REPO_ROOT, src)),
  });

  const ls = spawnSync('git', ['-C', REPO_ROOT, 'ls-files', '-z'], { maxBuffer: 64 * 1024 * 1024 });
  assert.equal(ls.status, 0, String(ls.stderr));
  const verdictRel = 'reviews/verdicts/2026-09-24-dummy.cyra.verdict.md';
  mkdirSync(join(snap, 'reviews', 'verdicts'), { recursive: true });
  writeFileSync(join(snap, ...verdictRel.split('/')), '---\nverdict: APPROVE\n---\nsigned body\n');
  const tracked = ls.stdout
    .toString('utf8')
    .split('\0')
    .filter((rel) => rel && existsSync(join(snap, ...rel.split('/'))));
  tracked.push(verdictRel);

  const init = spawnSync('git', ['init', '-q', snap], { encoding: 'utf8' });
  assert.equal(init.status, 0, init.stderr);
  const add = spawnSync('git', ['-C', snap, 'add', '--force', '--pathspec-from-file=-', '--pathspec-file-nul'], {
    input: tracked.join('\0'),
    encoding: 'utf8',
    maxBuffer: 64 * 1024 * 1024,
  });
  assert.equal(add.status, 0, add.stderr);

  const build = spawnSync(process.execPath, [join(snap, 'create-tess', 'scripts', 'build-template.mjs')], {
    cwd: snap,
    encoding: 'utf8',
  });
  assert.equal(build.status, 0, `build-template failed\n${build.stdout}\n${build.stderr}`);

  const committed = join(PKG_DIR, 'template');
  const fresh = join(snap, 'create-tess', 'template');
  const freshFiles = walkFiles(fresh);
  assert.ok(!freshFiles.some((f) => f.startsWith('reviews/')), 'no verdict may enter the bundle');
  assert.deepEqual(freshFiles, walkFiles(committed), 'the bundle file set must not change');
  const mismatched = freshFiles.filter(
    (rel) => !readFileSync(join(fresh, ...rel.split('/'))).equals(readFileSync(join(committed, ...rel.split('/')))),
  );
  assert.deepEqual(mismatched, [], 'the bundle bytes must not change');
});
