// pathnorm.test.js — dedicated unit coverage for create-tess/src/pathnorm.js
// (LOW item, PR #145 review: the normalization primitives were extracted out
// of ignore.js into their own module so they get their own focused tests,
// independent of ignore.js's EXCLUDE_* config / fs-touching makeCopyFilter).
//
// This file tests the PRIMITIVES directly (`normalizeComponent`,
// `normalizePath`, `basenameMatchesGlob`), at a lower level than
// test/secrets-casefold-bypass.test.js, which locks the same fixes at
// ignore.js's `isExcludedRel` surface. Also addresses Cyra's LOW-4 finding
// (PR #145 review): a *full* revert of ignore.js/pathnorm.js used to make
// the test file fail to LOAD (missing export) rather than fail a behavioral
// assertion — splitting the pure-primitive tests into their own file means a
// logic regression here can never be masked by an unrelated import error in
// a bigger, fs-touching test file.
//
// Run: npm test   (or `node --test`)
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { normalizeComponent, normalizePath, basenameMatchesGlob } from '../src/pathnorm.js';

// ---------------------------------------------------------------------------
// normalizeComponent
// ---------------------------------------------------------------------------

test('normalizeComponent: casefolds an ordinary component', () => {
  assert.equal(normalizeComponent('Tess-Secrets'), 'tess-secrets');
  assert.equal(normalizeComponent('VAULT.AGE'), 'vault.age');
});

test('normalizeComponent: strips trailing dots/spaces from a real name (Windows-illegal trailing-dot legacy handling)', () => {
  assert.equal(normalizeComponent('foo.'), 'foo');
  assert.equal(normalizeComponent('foo '), 'foo');
  assert.equal(normalizeComponent('foo. . '), 'foo');
});

// ★★ HIGH regression lock (Reid, PR #145 review) — the primitive-level
// assertion: a component that is ENTIRELY dots/spaces collapses to the
// EMPTY STRING, not back to itself. This is deliberate and load-bearing —
// `normalizePath`'s OWN second `.filter(Boolean)` (below) depends on this
// exact return value to know which components to drop. A version of
// `normalizeComponent` that falls back to the un-stripped component instead
// (e.g. Reid's own suggested one-liner, `return stripped || norm;`) would
// break that contract: `normalizePath` would then have nothing to filter,
// and the noise component would survive LITERALLY in the joined path,
// which — verified directly, see the vectors below — does NOT restore the
// prefix match either (the two suggested mechanisms genuinely diverge; only
// dropping the empty component, not preserving it, restores exclusion).
test('★★ HIGH regression lock: an all-dots/all-spaces component normalizes to the empty string', () => {
  assert.equal(normalizeComponent('...'), '', 'a literal "..." directory component must normalize to empty');
  assert.equal(normalizeComponent('.'), '', 'a single "." component (e.g. from a leading "./") must normalize to empty');
  assert.equal(normalizeComponent('.  '), '', 'a whitespace-only component (dot + spaces) must normalize to empty');
  assert.equal(normalizeComponent('   '), '', 'a pure-space component must normalize to empty');
});

test('★ NFC/NFD regression lock: normalizeComponent converges NFC-composed and NFD-decomposed forms of the identical grapheme', () => {
  const composed = 'É'; // U+00C9 — single precomposed codepoint
  const decomposed = 'É'.normalize('NFD'); // U+0045 U+0301 — "E" + COMBINING ACUTE ACCENT
  assert.notEqual(composed, decomposed, 'sanity: NFC and NFD must be different byte sequences for the same grapheme');
  assert.notEqual(
    composed.toLowerCase(), decomposed.toLowerCase(),
    'sanity: casefolding alone (no NFC step) does NOT converge NFC/NFD — proves the NFC step is necessary, not redundant',
  );
  assert.equal(normalizeComponent(composed), normalizeComponent(decomposed));
  assert.equal(normalizeComponent(composed), 'é');
});

// ---------------------------------------------------------------------------
// normalizePath
// ---------------------------------------------------------------------------

test('normalizePath: joins ordinary components, casefolded, unaffected by noise-free paths', () => {
  assert.equal(normalizePath('.tess/Keys/Verifiers/cyra.asc'), '.tess/keys/verifiers/cyra.asc');
  assert.equal(normalizePath('a/b/c'), 'a/b/c');
});

// ★★ HIGH regression lock (Reid, PR #145 review), primitive level — the FIX
// itself: an empty-after-normalization component must be DROPPED from the
// joined path, not joined back in (which corrupts the string with a `//` or
// a leading `/` and defeats every downstream `startsWith` prefix match in
// ignore.js). Empirically verified against the actual pre-fix PR-branch
// blob before writing this fix: `.tess/.../keys/verifiers/cyra.asc`
// normalized to `.tess//keys/verifiers/cyra.asc` pre-fix (corrupted double
// slash) and to `.tess/keys/verifiers/cyra.asc` post-fix (matches the
// canonical form exactly).
test('★★ HIGH regression lock: normalizePath drops an empty-after-normalization component instead of corrupting the join', () => {
  assert.equal(
    normalizePath('.tess/.../keys/verifiers/cyra.asc'),
    '.tess/keys/verifiers/cyra.asc',
    'a literal "..." directory component must vanish from the normalized path, not corrupt it into "tess//keys/..."',
  );
  assert.equal(
    normalizePath('./.tess/keys/verifiers/cyra.asc'),
    '.tess/keys/verifiers/cyra.asc',
    'a leading "./" must not corrupt the normalized path into a leading "/"',
  );
  assert.equal(
    normalizePath('.tess/.  /keys/verifiers/cyra.asc'),
    '.tess/keys/verifiers/cyra.asc',
    'a whitespace-only component must vanish from the normalized path',
  );
  // Multiple noise components, and a noise component at the very end.
  assert.equal(normalizePath('.tess/.../.../keys/verifiers/cyra.asc'), '.tess/keys/verifiers/cyra.asc');
  assert.equal(normalizePath('.tess/keys/verifiers/...'), '.tess/keys/verifiers');
});

test('negative control: normalizePath does not collapse an ordinary path with no noise components', () => {
  assert.equal(normalizePath('docs/notes/README.md'), 'docs/notes/readme.md');
  assert.equal(normalizePath(''), '');
});

// ---------------------------------------------------------------------------
// basenameMatchesGlob
// ---------------------------------------------------------------------------

test('basenameMatchesGlob: suffix-glob match (the `*.<suffix>` shape)', () => {
  assert.equal(basenameMatchesGlob('server.pem', '*.pem'), true);
  assert.equal(basenameMatchesGlob('server.pem.bak', '*.pem'), false);
  assert.equal(basenameMatchesGlob('deploy.key', '*.key'), true);
});

test('basenameMatchesGlob: exact (non-glob) match', () => {
  assert.equal(basenameMatchesGlob('.gitkeep', '.gitkeep'), true);
  assert.equal(basenameMatchesGlob('.gitkeep2', '.gitkeep'), false);
});
