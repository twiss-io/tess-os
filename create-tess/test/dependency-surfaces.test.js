// Static extraction only: never execute scaffold-default.sh (it installs
// packages and emits E2E commands that can kill occupied development ports).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const root = new URL('../../', import.meta.url);
const read = (path) => readFileSync(new URL(path, root), 'utf8');
const starter = JSON.parse(read('starter/package.json'));
const generator = read('starter/scripts/scaffold-default.sh');
const body = generator.match(/cat > "\$PROJECT_PATH\/package\.json" << PKGJSON_EOF\n([\s\S]*?)\nPKGJSON_EOF/);
assert.ok(body, 'the generator must contain its package.json heredoc');
const generated = JSON.parse(body[1]);

function checkTestDependencies(manifest) {
  assert.equal(manifest.devDependencies.vitest, '4.1.11');
  assert.equal(manifest.devDependencies['@vitest/coverage-v8'], manifest.devDependencies.vitest);
  assert.equal(manifest.engines.node, '^20.19.0 || ^22.12.0 || >=24.0.0');
  assert.equal(manifest.pnpm.overrides['source-map-js'], '>=1.2.2');
  assert.equal(manifest.pnpm.overrides.vite, '>=6.4.3 <8');
}

test('starter and extracted generator use patched matching test/coverage dependencies', () => {
  checkTestDependencies(starter);
  checkTestDependencies(generated);
});

function checkGeneratedCSS(manifest, script) {
  assert.equal(manifest.pnpm.overrides.postcss, '^8.5.28');
  assert.equal(manifest.devDependencies.tailwindcss, '4.3.3');
  assert.equal(manifest.devDependencies['@tailwindcss/postcss'], '4.3.3');
  assert.match(script, /@import "tailwindcss";/);
  assert.match(script, /'@tailwindcss\/postcss': \{\}/);
  assert.doesNotMatch(script, /@tailwind (base|components|utilities);/);
}

test('generator patches nested PostCSS and uses the matching Tailwind 4 pipeline', () => {
  checkGeneratedCSS(generated, generator);
});

test('generator contract rejects loss of nested patch or reintroduction of Tailwind 3', () => {
  for (const mutate of [
    (p) => { delete p.pnpm.overrides.postcss; },
    (p) => { p.devDependencies.tailwindcss = '^3.4.0'; },
    (p) => { delete p.devDependencies['@tailwindcss/postcss']; },
  ]) {
    const bad = structuredClone(generated);
    mutate(bad);
    assert.throws(() => checkGeneratedCSS(bad, generator));
  }
  assert.throws(() => checkGeneratedCSS(generated, generator.replace('@import "tailwindcss";', '@tailwind utilities;')));
});

test('dependency contract rejects vulnerable Vitest, mismatched coverage, and unsupported Node floors', () => {
  for (const mutate of [
    (p) => { p.devDependencies.vitest = '^2.0.0'; },
    (p) => { p.devDependencies['@vitest/coverage-v8'] = '3.2.6'; },
    (p) => { p.engines.node = '>=18'; },
    (p) => { p.pnpm.overrides['source-map-js'] = '1.2.1'; },
  ]) {
    const bad = structuredClone(generated);
    mutate(bad);
    assert.throws(() => checkTestDependencies(bad));
  }
});

test('GUI declares the installed jsdom Node floor and locks patched source-map-js', () => {
  const gui = JSON.parse(read('gui/package.json'));
  const lock = JSON.parse(read('gui/package-lock.json'));
  assert.equal(gui.engines.node, '^20.19.0 || ^22.13.0 || >=24.0.0');
  assert.equal(lock.packages[''].engines.node, gui.engines.node);
  assert.equal(lock.packages['node_modules/source-map-js'].version, '1.2.2');
});

test('all refreshed dependency surfaces match the shipped bundle byte-for-byte', () => {
  for (const path of [
    'gui/package.json', 'gui/package-lock.json', 'gui/README.md', 'starter/package.json',
    'starter/pnpm-lock.yaml', 'starter/scripts/scaffold-default.sh',
  ]) {
    assert.equal(read(`create-tess/template/${path}`), read(path), fileURLToPath(new URL(path, root)));
  }
});
