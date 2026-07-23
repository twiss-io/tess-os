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

// ★★ Issue #146 regression lock (Cyra, PR #145 re-review) — the primitive-
// level assertion: a component built ENTIRELY from Unicode format-control
// (Cf) codepoints, or ENTIRELY from a lone combining mark with no base
// character, also collapses to the EMPTY STRING — the SAME contract as the
// all-dots/all-spaces case above, extended to the three vectors named in
// #146. Verified directly against the pre-fix module (git stash) before
// writing this fix: all three returned the UN-stripped, non-empty component.
test('★★ #146 regression lock: a component composed entirely of Cf/zero-width/soft-hyphen/combining-only codepoints normalizes to the empty string', () => {
  assert.equal(normalizeComponent('​'), '', 'a lone zero-width space (U+200B, Cf) must normalize to empty');
  assert.equal(normalizeComponent('­'), '', 'a lone soft hyphen (U+00AD, Cf) must normalize to empty');
  assert.equal(normalizeComponent('́'), '', 'a lone combining acute accent (U+0301, no base) must normalize to empty');
  assert.equal(normalizeComponent('‌‍'), '', 'ZWNJ+ZWJ (both Cf) must normalize to empty');
  assert.equal(normalizeComponent('﻿'), '', 'a lone BOM/ZWNBSP (U+FEFF, Cf) must normalize to empty');
  assert.equal(
    normalizeComponent('́̀'),
    '',
    'multiple stacked combining marks with no base (U+0301 + U+0300) must normalize to empty',
  );
});

// Embedded (not whole-component) noise: Cf codepoints stripped from
// ANYWHERE in the component, not only when they make up the whole thing —
// closes the same vector when the attacker splices the invisible codepoint
// INTO an otherwise-ordinary segment name rather than using it as its own
// segment.
test('★ #146: a Cf codepoint embedded inside an otherwise-ordinary component is stripped, not just a whole-component match', () => {
  assert.equal(normalizeComponent('k​eys'), 'keys', 'an embedded ZWSP inside "keys" must be stripped to reveal "keys"');
  assert.equal(normalizeComponent('secre­ts'), 'secrets', 'an embedded soft hyphen inside "secrets" must be stripped to reveal "secrets"');
});

// Negative control (issue #146 fix): this fix must NOT become the overbroad
// hammer an earlier draft considered and rejected (see pathnorm.js's header
// comment) — real, printable, identity-bearing Unicode text (an ordinary
// accented word, no Cf/lone-combining-mark content) is left exactly as NFC +
// casefold already handled it.
test('negative control (#146 fix): an ordinary accented component (no Cf/combining-only content) is unaffected', () => {
  assert.equal(normalizeComponent('café'), 'café');
  assert.equal(normalizeComponent('CAFÉ'), 'café');
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

// ★★ Issue #146 regression lock, primitive level — the FIX itself, at
// normalizePath's join surface: a Cf/zero-width/soft-hyphen/combining-only
// component interposed WITHIN a forbidden-prefix-shaped path must vanish
// from the joined path exactly like the all-dots/all-space vector above,
// collapsing back to the canonical form so the (unchanged) downstream
// `startsWith` prefix match in ignore.js fires correctly. Empirically
// verified against the pre-#146-fix module (git stash) before writing this
// fix: all four vectors below normalized to a STRING CONTAINING the noise
// codepoint (not the canonical collapsed form) pre-fix.
test('★★ #146 regression lock: normalizePath drops a Cf/zero-width/soft-hyphen/combining-only noise component interposed within a forbidden-prefix path', () => {
  assert.equal(
    normalizePath('.tess/​/keys/verifiers/cyra.asc'),
    '.tess/keys/verifiers/cyra.asc',
    'a lone zero-width space (U+200B) directory component must vanish, not defeat the prefix match',
  );
  assert.equal(
    normalizePath('.tess/­/keys/verifiers/cyra.asc'),
    '.tess/keys/verifiers/cyra.asc',
    'a lone soft hyphen (U+00AD) directory component must vanish, not defeat the prefix match',
  );
  assert.equal(
    normalizePath('.tess/́/keys/verifiers/cyra.asc'),
    '.tess/keys/verifiers/cyra.asc',
    'a lone combining-only (U+0301, no base) directory component must vanish, not defeat the prefix match',
  );
  // EXCLUDE_CONTENT_PREFIXES is affected by the identical root cause, not
  // just EXCLUDE_DIR_PREFIXES (mirrors the HIGH fix's own second
  // reproduction above).
  assert.equal(
    normalizePath('.tess/state/​/memory/real.json'),
    '.tess/state/memory/real.json',
    'the same #146 noise-component vector against EXCLUDE_CONTENT_PREFIXES, not just EXCLUDE_DIR_PREFIXES',
  );
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
