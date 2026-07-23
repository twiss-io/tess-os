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

// ★★ HIGH regression lock (Reid, PR #170 second security re-review) — the
// primitive-level assertion for the Default_Ignorable_Code_Point widening:
// a component composed ENTIRELY of a Hangul filler codepoint (U+115F, U+1160,
// U+3164 — general category `Lo`, NOT `Cf` and NOT `\p{M}`, so the #146 fix's
// `\p{Cf}`-only strip did NOT catch these) also collapses to the EMPTY
// STRING. Verified directly against the pre-this-fix module (git stash the
// `\p{Cf}` -> `\p{Default_Ignorable_Code_Point}` widening, rerun this exact
// assertion): all three returned the UN-stripped, non-empty component
// pre-fix — i.e. these vectors survive on the CURRENT (pre-#170-fix) PR-170
// branch, not just on unpatched `main`.
test('★★ HIGH regression lock (Reid, PR #170): a component composed entirely of Hangul-filler codepoints normalizes to the empty string', () => {
  assert.equal(normalizeComponent('ᅟ'), '', 'a lone HANGUL CHOSEONG FILLER (U+115F, Lo, Default_Ignorable) must normalize to empty');
  assert.equal(normalizeComponent('ᅠ'), '', 'a lone HANGUL JUNGSEONG FILLER (U+1160, Lo, Default_Ignorable) must normalize to empty');
  assert.equal(normalizeComponent('ㅤ'), '', 'a lone HANGUL FILLER (U+3164, Lo, Default_Ignorable) must normalize to empty');
  assert.equal(normalizeComponent('ᅟᅠ'), '', 'stacked Hangul fillers (no base) must normalize to empty');
});

// Embedded (not whole-component) Hangul-filler noise — same closure as the
// #146 embedded-Cf test above, extended to the widened codepoint set.
test('★ PR #170: a Hangul-filler codepoint embedded inside an otherwise-ordinary component is stripped, not just a whole-component match', () => {
  assert.equal(normalizeComponent('kᅟeys'), 'keys', 'an embedded HANGUL CHOSEONG FILLER inside "keys" must be stripped to reveal "keys"');
  assert.equal(normalizeComponent('verifㅤiers'), 'verifiers', 'an embedded HANGUL FILLER inside "verifiers" must be stripped to reveal "verifiers"');
});

// Negative control (PR #170 fix): re-confirm the café/日本支店-shaped negative
// control survives the WIDER Default_Ignorable_Code_Point strip, not just
// the narrower Cf-only strip #146 shipped with — the widening must not
// regress ordinary printable Unicode text of any script.
test('negative control (PR #170 fix): ordinary printable Unicode (no Default_Ignorable/combining-only content) remains unaffected by the widened strip', () => {
  assert.equal(normalizeComponent('café'), 'café');
  assert.equal(normalizeComponent('日本支店'), '日本支店');
});

// ---------------------------------------------------------------------------
// ★★★ HIGH regression lock (Cyra, PR #170 THIRD security re-review,
// RE-BLOCK at `d96cc7a`) — Part B: the category-agnostic "no visible base
// glyph survives" whole-component test (`GRAPHIC_RE`), which closes the
// Zs (space-separator) / Zl/Zp (line/paragraph separator) / Cc (control)
// sibling categories `Default_Ignorable_Code_Point` does not cover. Verified
// directly against `d96cc7a` (this exact PR branch, i.e. AFTER the Hangul-
// filler fix already landed) before writing this fix: every vector below
// returned the UN-stripped, non-empty component. Escaped via `\uXXXX` rather
// than literal bytes so this file's own source never embeds a raw control
// character.
// ---------------------------------------------------------------------------

test('★★★ HIGH regression lock (Cyra, PR #170 third re-review): a component composed entirely of Zs (space-separator) codepoints normalizes to the empty string', () => {
  const zsVectors = {
    'NBSP U+00A0': ' ',
    'EN QUAD U+2000': ' ',
    'EM SPACE U+2003': ' ',
    'THIN SPACE U+2009': ' ',
    'NARROW NO-BREAK SPACE U+202F': ' ',
    'MEDIUM MATHEMATICAL SPACE U+205F': ' ',
    'IDEOGRAPHIC SPACE U+3000': '　',
    'OGHAM SPACE MARK U+1680': ' ',
  };
  for (const [label, ch] of Object.entries(zsVectors)) {
    assert.equal(normalizeComponent(ch), '', `a lone ${label} (Zs) must normalize to empty`);
  }
});

test('★★★ HIGH regression lock (Cyra, PR #170 third re-review): a component composed entirely of Zl/Zp (line/paragraph separator) codepoints normalizes to the empty string', () => {
  assert.equal(normalizeComponent(' '), '', 'a lone LINE SEPARATOR (U+2028, Zl) must normalize to empty');
  assert.equal(normalizeComponent(' '), '', 'a lone PARAGRAPH SEPARATOR (U+2029, Zp) must normalize to empty');
});

test('★★★ HIGH regression lock (Cyra, PR #170 third re-review): a component composed entirely of Cc (control) codepoints normalizes to the empty string', () => {
  const ccVectors = {
    'SOH U+0001 (C0)': '',
    'US U+001F (C0)': '',
    'TAB U+0009 (C0)': '	',
    'PAD U+0080 (C1)': '',
    'NEL U+0085 (C1)': '',
  };
  for (const [label, ch] of Object.entries(ccVectors)) {
    assert.equal(normalizeComponent(ch), '', `a lone ${label} must normalize to empty — filesystem-legal on macOS/Linux`);
  }
});

test('★★★ HIGH regression lock (Cyra, PR #170 third re-review): mixed noise components (Zs + Default_Ignorable, Zs + trailing dot) normalize to the empty string', () => {
  assert.equal(normalizeComponent(' ​'), '', 'NBSP + ZWSP (mixed Zs + Default_Ignorable) must normalize to empty');
  assert.equal(normalizeComponent(' .'), '', 'NBSP + trailing dot must normalize to empty');
});

// Negative control — PART B must not become an embedded strip: a real,
// visible-glyph CJK name that uses U+3000 IDEOGRAPHIC SPACE as an internal
// word separator (a legitimate use — not noise) must survive completely
// unaffected, RETAINING the embedded separator character itself, not merely
// "not excluded". Reid's constraint: `\p{Zs}` must never be stripped
// mid-component — only the whole-component graphic test may drop a
// component, and only when NO visible base glyph survives anywhere in it.
test('★ negative control (Cyra, PR #170 third re-review): a real CJK name using U+3000 as an internal word separator is NOT mangled by the whole-component test', () => {
  assert.equal(
    normalizeComponent('日本　支店'),
    '日本　支店',
    'an embedded ideographic space between two real glyphs must survive untouched (including the separator itself) — Part B only drops a component with NO visible base; this one has two',
  );
});

// Negative control: a lone punctuation character is itself a visible glyph
// (`\p{P}`, general category Pd) and must not be swept up by the
// noise-collapse.
test('negative control (Cyra, PR #170 third re-review): a lone hyphen (visible punctuation, not noise) is unaffected', () => {
  assert.equal(normalizeComponent('-'), '-');
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

// ★★ HIGH regression lock (Reid, PR #170), primitive level — the FIX itself
// at normalizePath's join surface: a Hangul-filler noise component
// interposed WITHIN a forbidden-prefix-shaped path must vanish from the
// joined path exactly like the #146 Cf vectors above, collapsing back to
// the canonical form so the (unchanged) downstream `startsWith` prefix
// match in ignore.js fires correctly. Empirically verified against the
// pre-#170-fix module (git stash the Default_Ignorable widening): all three
// vectors below normalized to a STRING CONTAINING the noise codepoint (not
// the canonical collapsed form) pre-fix — reproducing Reid's exact finding
// at the primitive level.
test('★★ HIGH regression lock (Reid, PR #170): normalizePath drops a Hangul-filler noise component interposed within a forbidden-prefix path', () => {
  assert.equal(
    normalizePath('.tess/ᅟ/keys/verifiers/cyra.asc'),
    '.tess/keys/verifiers/cyra.asc',
    'a lone HANGUL CHOSEONG FILLER (U+115F) directory component must vanish, not defeat the prefix match',
  );
  assert.equal(
    normalizePath('.tess/ᅠ/keys/verifiers/cyra.asc'),
    '.tess/keys/verifiers/cyra.asc',
    'a lone HANGUL JUNGSEONG FILLER (U+1160) directory component must vanish, not defeat the prefix match',
  );
  assert.equal(
    normalizePath('.tess/ㅤ/keys/verifiers/cyra.asc'),
    '.tess/keys/verifiers/cyra.asc',
    'a lone HANGUL FILLER (U+3164) directory component must vanish, not defeat the prefix match',
  );
});

// ★★★ HIGH regression lock (Cyra, PR #170 THIRD security re-review), at
// normalizePath's join surface — the FIX itself: a Zs/Zl/Zp/Cc noise
// component interposed WITHIN a forbidden-prefix-shaped path must vanish
// from the joined path exactly like every prior vector in this class,
// collapsing back to the canonical form so the (unchanged) downstream
// `startsWith` prefix match in ignore.js fires correctly. Empirically
// verified against `d96cc7a` (this PR branch, pre-this-fix): all four
// vectors below normalized to a STRING CONTAINING the noise codepoint (not
// the canonical collapsed form) pre-fix.
test('★★★ HIGH regression lock (Cyra, PR #170 third re-review): normalizePath drops a Zs/Zl/Zp/Cc noise component interposed within a forbidden-prefix path', () => {
  assert.equal(
    normalizePath('.tess/\u00A0/keys/verifiers/cyra.asc'),
    '.tess/keys/verifiers/cyra.asc',
    'a lone NBSP (U+00A0) directory component must vanish, not defeat the prefix match',
  );
  assert.equal(
    normalizePath('.tess/\u3000/keys/verifiers/cyra.asc'),
    '.tess/keys/verifiers/cyra.asc',
    'a lone IDEOGRAPHIC SPACE (U+3000) directory component must vanish, not defeat the prefix match',
  );
  assert.equal(
    normalizePath('.tess/\u2028/keys/verifiers/cyra.asc'),
    '.tess/keys/verifiers/cyra.asc',
    'a lone LINE SEPARATOR (U+2028) directory component must vanish, not defeat the prefix match',
  );
  assert.equal(
    normalizePath('.tess/\u0001/keys/verifiers/cyra.asc'),
    '.tess/keys/verifiers/cyra.asc',
    'a lone Cc control (U+0001) directory component must vanish, not defeat the prefix match',
  );
});

test('negative control: normalizePath does not collapse an ordinary path with no noise components', () => {
  assert.equal(normalizePath('docs/notes/README.md'), 'docs/notes/readme.md');
  assert.equal(normalizePath(''), '');
});

// Negative control: normalizePath must preserve a legitimate CJK path
// segment that uses U+3000 as an internal word separator, not merely "not
// exclude" it — the whole component (with its embedded separator intact)
// must appear unchanged in the joined path.
test('negative control (Cyra, PR #170 third re-review): normalizePath preserves a legitimate CJK path segment using U+3000 as an internal word separator', () => {
  assert.equal(normalizePath('docs/日本　支店/README.md'), 'docs/日本　支店/readme.md');
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
