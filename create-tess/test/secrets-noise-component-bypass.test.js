// secrets-noise-component-bypass.test.js — PERMANENT regression guard for
// issue #146: a Unicode Cf-category (format-control) / zero-width /
// soft-hyphen / combining-only path component defeating the string
// prefix-match in create-tess's secrets-exclusion filter.
//
// THE RESIDUAL: documented by Cyra during the security re-review of PR #145
// (the CRITICAL case-fold bypass fix) — pre-existing, identical in `cc38323`
// and `22b85a6`, not a regression opened by #145. `isExcludedRel`'s
// normalization (`normalizeComponent`/`normalizePath`, src/pathnorm.js)
// dropped a component that normalizes to the empty string (all-dots/
// all-space, PR #145's own HIGH fix), but a "noise" component composed of
// non-`[. ]` characters that nonetheless survive NFC/case-fold — a zero-width
// space (U+200B), a soft hyphen (U+00AD), or a combining-only component (a
// lone combining mark with no base character) — did NOT normalize to empty,
// so it was NOT dropped. Interposed WITHIN a forbidden prefix (e.g.
// `.tess/<U+200B>/keys/verifiers/cyra.asc`), such a component still defeated
// the string prefix-match: the interposed segment broke the contiguous
// prefix comparison while remaining, under the old rule, a "real",
// non-empty path segment — letting a scaffold-forbidden path (most
// concretely, `.tess/keys/verifiers/**` / `.tess/keys/signoffs/**`, the
// registered-verifier-key leak class `EXCLUDE_DIR_PREFIXES` exists to stop,
// see ignore.js's own header comment) slip past the filter as KEPT instead
// of EXCLUDED.
//
// THE FIX (src/pathnorm.js's `normalizeComponent`): strip every Unicode
// Cf-category codepoint from the ENTIRE component (not only a trailing
// run), and collapse a component that is, after that, ENTIRELY combining
// marks (no base character) to the empty string too — extending the SAME
// fail-safe drop-via-`.filter(Boolean)` machinery PR #145's HIGH fix already
// built for the all-dots/all-space case, to this wider input set. See
// pathnorm.js's header comment for the full design + the deliberately
// rejected broader alternative (force-excluding ANY non-ASCII component),
// and test/pathnorm.test.js for the primitive-level regression lock.
//
// THIS FILE locks the fix at ignore.js's public `isExcludedRel` surface —
// the same scope/shape as test/secrets-casefold-bypass.test.js's own HIGH
// regression lock for the closely-related all-dots/all-space vector, kept in
// its own file (rather than appended to that already-420-line file) since
// #146 is its own tracked, numbered issue with its own named vectors.
//
// ★★ PR #170 second security re-review (Reid HIGH) — WIDENED beyond #146's
// original Cf-only scope. `\p{Cf}` is exhaustive over Unicode's
// format-control block but NOT over the full Default_Ignorable_Code_Point
// derived property: the Hangul filler family (U+115F HANGUL CHOSEONG
// FILLER, U+1160 HANGUL JUNGSEONG FILLER, U+3164 HANGUL FILLER — general
// category `Lo`, not `Cf`, not `\p{M}`) survived the #146 fix untouched and
// defeated exclusion on this PR's own post-#146-fix code, reproduced live
// through the REAL `makeCopyFilter` scaffold-copy path — see
// src/pathnorm.js's header comment for the full risk-language correction
// (the "inode arm backstops it, not an active leak" framing in issue #146
// and this PR's original body was empirically disproved) and
// test/secrets-nested-noise-dir-copy-filter.test.js for the fs-level
// `makeCopyFilter` proof. `src/pathnorm.js`'s `normalizeComponent` now strips
// `\p{Default_Ignorable_Code_Point}` (a strict superset of `\p{Cf}`) instead
// of `\p{Cf}` alone; every test below tagged "PR #170" locks that widening at
// this file's `isExcludedRel` surface, alongside the pre-existing #146 locks.
//
// Every assertion below is FS-independent — pure string input to
// `isExcludedRel`, no disk I/O, so it runs identically on every CI runner
// (this repo's Linux ext4 runner included) with no platform gating needed,
// unlike the opportunistic native-case-fold tests in
// secrets-casefold-bypass.test.js.
//
// Run: npm test   (or `node --test`)
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { isExcludedRel } from '../src/ignore.js';

// ---------------------------------------------------------------------------
// The three named #146 vectors, each interposed within EXCLUDE_DIR_PREFIXES'
// `.tess/keys/verifiers` — the registered-verifier-key leak class this
// prefix specifically exists to stop (see ignore.js's header comment).
// Verified directly against the pre-fix module (`git stash` the fix, run
// this exact assertion, confirm it fails) before writing the fix: all three
// returned `false` (KEPT — the bug) pre-fix.
// ---------------------------------------------------------------------------

test('★★ #146 regression lock: a zero-width-space (U+200B) noise component interposed within .tess/keys/verifiers does not defeat exclusion', () => {
  assert.equal(
    isExcludedRel('.tess/​/keys/verifiers/cyra.asc'),
    true,
    'a zero-width-space directory component interposed within the forbidden .tess/keys/verifiers prefix must not defeat exclusion',
  );
});

test('★★ #146 regression lock: a soft-hyphen (U+00AD) noise component interposed within .tess/keys/verifiers does not defeat exclusion', () => {
  assert.equal(
    isExcludedRel('.tess/­/keys/verifiers/cyra.asc'),
    true,
    'a soft-hyphen directory component interposed within the forbidden .tess/keys/verifiers prefix must not defeat exclusion',
  );
});

test('★★ #146 regression lock: a combining-only (lone combining mark, no base) noise component interposed within .tess/keys/verifiers does not defeat exclusion', () => {
  assert.equal(
    isExcludedRel('.tess/́/keys/verifiers/cyra.asc'),
    true,
    'a combining-only directory component interposed within the forbidden .tess/keys/verifiers prefix must not defeat exclusion',
  );
});

// ★★ HIGH regression lock (Reid, PR #170 second security re-review) —
// `isExcludedRel`-surface: the Hangul-filler family (U+115F/U+1160/U+3164 —
// general category `Lo`, part of Unicode's Default_Ignorable_Code_Point
// derived property but NOT `\p{Cf}` and NOT `\p{M}`) interposed within
// `.tess/keys/verifiers` must not defeat exclusion, exactly like the three
// #146 vectors above. Verified directly against the CURRENT (pre-this-fix)
// PR-170 branch — i.e. AFTER the #146 `\p{Cf}`-only fix already landed —
// before writing this fix: all three returned `false` (KEPT — the bug).
// Reid additionally proved this exact vector defeats the REAL scaffold-copy
// path (`makeCopyFilter`, not just this string-only `isExcludedRel` check)
// with a live on-disk fixture — see
// test/secrets-nested-noise-dir-copy-filter.test.js for that fs-level lock.
test('★★ HIGH regression lock (Reid, PR #170): a Hangul-filler (U+115F HANGUL CHOSEONG FILLER) noise component interposed within .tess/keys/verifiers does not defeat exclusion', () => {
  assert.equal(
    isExcludedRel('.tess/ᅟ/keys/verifiers/cyra.asc'),
    true,
    'a HANGUL CHOSEONG FILLER (U+115F) directory component interposed within the forbidden .tess/keys/verifiers prefix must not defeat exclusion',
  );
});

test('★★ HIGH regression lock (Reid, PR #170): a Hangul-filler (U+1160 HANGUL JUNGSEONG FILLER) noise component interposed within .tess/keys/verifiers does not defeat exclusion', () => {
  assert.equal(
    isExcludedRel('.tess/ᅠ/keys/verifiers/cyra.asc'),
    true,
    'a HANGUL JUNGSEONG FILLER (U+1160) directory component interposed within the forbidden .tess/keys/verifiers prefix must not defeat exclusion',
  );
});

test('★★ HIGH regression lock (Reid, PR #170): a Hangul-filler (U+3164 HANGUL FILLER) noise component interposed within .tess/keys/verifiers does not defeat exclusion', () => {
  assert.equal(
    isExcludedRel('.tess/ㅤ/keys/verifiers/cyra.asc'),
    true,
    'a HANGUL FILLER (U+3164) directory component interposed within the forbidden .tess/keys/verifiers prefix must not defeat exclusion',
  );
});

// Sweep across every EXCLUDE_DIR_PREFIXES / EXCLUDE_CONTENT_PREFIXES root —
// the noise component is interposed WITHIN each prefix (breaking its own
// contiguous string match, the actual vulnerable position — mirroring the
// exact structural position of the `.tess/<noise>/keys/verifiers` vectors
// above), NOT merely nested underneath an already-matched prefix (that
// shape is already safe by construction — whole-subtree `startsWith`
// matching does not care what is nested further down — see the "already-safe
// shape" sanity test in test/secrets-nested-noise-dir-copy-filter.test.js).
// Verified directly against the CURRENT (pre-this-fix) PR-170 branch: all
// four returned `false` (KEPT — the bug) pre-fix.
test('★ PR #170: the Hangul-filler noise-component vector is closed against every EXCLUDE_DIR_PREFIXES / EXCLUDE_CONTENT_PREFIXES root, not just one', () => {
  const vectors = [
    ['.claude/ᅟ/tess-secrets/token.env', 'EXCLUDE_DIR_PREFIXES: .claude/tess-secrets'],
    ['.claude/ᅠ/channels/access.json', 'EXCLUDE_DIR_PREFIXES: .claude/channels'],
    ['.tess/ㅤ/keys/signoffs/xavier.asc', 'EXCLUDE_DIR_PREFIXES: .tess/keys/signoffs'],
    ['.tess/ᅟ/state/memory/real.json', 'EXCLUDE_CONTENT_PREFIXES: .tess/state/memory'],
  ];
  for (const [p, label] of vectors) {
    assert.equal(isExcludedRel(p), true, `${label}: Hangul-filler noise component interposed within the prefix must not defeat exclusion — isExcludedRel(${JSON.stringify(p)})`);
  }
});

// Every other EXCLUDE_DIR_PREFIXES / EXCLUDE_CONTENT_PREFIXES root is subject
// to the identical root cause, not just `.tess/keys/verifiers` — the same
// breadth Reid's HIGH fix (PR #145) itself proved against a second root.
test('★ #146: the noise-component vector is closed against every EXCLUDE_DIR_PREFIXES / EXCLUDE_CONTENT_PREFIXES root, not just one', () => {
  const vectors = [
    ['.claude/tess-secrets/​/token.env', 'EXCLUDE_DIR_PREFIXES: .claude/tess-secrets'],
    ['.claude/channels/­/access.json', 'EXCLUDE_DIR_PREFIXES: .claude/channels'],
    ['.tess/keys/signoffs/​/xavier.asc', 'EXCLUDE_DIR_PREFIXES: .tess/keys/signoffs'],
    ['.tess/state/memory/­/real.json', 'EXCLUDE_CONTENT_PREFIXES: .tess/state/memory'],
    ['.tess/state/receipts/​/chain.jsonl', 'EXCLUDE_CONTENT_PREFIXES: .tess/state/receipts'],
    ['.tess/snapshots/́/x.json', 'EXCLUDE_CONTENT_PREFIXES: .tess/snapshots'],
  ];
  for (const [p, label] of vectors) {
    assert.equal(isExcludedRel(p), true, `${label}: noise component must not defeat exclusion — isExcludedRel(${JSON.stringify(p)})`);
  }
});

// Embedded (not whole-segment) noise, spliced INTO an otherwise-canonical
// segment name rather than used as its own segment — the same closure as
// the primitive-level test in pathnorm.test.js, exercised here at the
// isExcludedRel surface.
test('★ #146: a Cf codepoint spliced inside a forbidden segment name (not a separate segment) does not defeat exclusion', () => {
  assert.equal(
    isExcludedRel('.tess/k​eys/verifiers/cyra.asc'),
    true,
    'a zero-width space embedded inside the "keys" segment itself must still resolve to the canonical .tess/keys/verifiers prefix',
  );
  assert.equal(
    isExcludedRel('secre­ts/api-key.txt'),
    true,
    'a soft hyphen embedded inside the "secrets" segment itself must still match the bare EXCLUDE_NAMES "secrets" entry',
  );
});

// Multiple stacked noise components/codepoints — the fix must not merely
// handle a single lone occurrence.
test('★ #146: multiple noise components/codepoints in the same path do not defeat exclusion', () => {
  assert.equal(isExcludedRel('.tess/​/­/keys/verifiers/cyra.asc'), true, 'two consecutive noise components (ZWSP then soft hyphen) must both vanish');
  assert.equal(isExcludedRel('.tess/keys/verifiers/́̀/cyra.asc'), true, 'multiple stacked combining marks (no base) as their own component must vanish');
});

// Sanity: the canonical (noise-free) forms are excluded too, as a baseline —
// mirrors secrets-casefold-bypass.test.js's own convention. Include the
// Hangul-filler vectors' canonical forms too (same paths as above, minus the
// noise component) so this sanity check isn't scoped only to the original
// #146 vectors.
test('sanity: canonical (noise-free) forms of every #146/PR-170 vector path are excluded', () => {
  for (const p of [
    '.tess/keys/verifiers/cyra.asc',
    '.claude/tess-secrets/token.env',
    '.claude/channels/access.json',
    '.tess/keys/signoffs/xavier.asc',
    '.tess/state/memory/real.json',
    'secrets/api-key.txt',
  ]) {
    assert.equal(isExcludedRel(p), true, `sanity: canonical form ${p} must be excluded`);
  }
});

// ---------------------------------------------------------------------------
// ★★★ HIGH regression lock (Cyra, PR #170 THIRD security re-review,
// RE-BLOCK at `d96cc7a`) — `isExcludedRel`-surface: a whole path component
// composed entirely of Unicode Zs (space separator) / Zl / Zp (line /
// paragraph separator) / Cc (control) codepoints, interposed within
// `.tess/keys/verifiers`, must not defeat exclusion — the same closure as
// the #146 Cf and PR #170 Hangul-filler vectors above, extended to the
// categories `Default_Ignorable_Code_Point` does not cover. Verified
// directly against `d96cc7a` (this PR branch, AFTER the Hangul-filler fix
// already landed) before writing this fix: every vector below returned
// `false` (KEPT — the bug) pre-fix. Codepoints given as \\uXXXX escapes
// (unambiguous ASCII in the source) rather than literal bytes.
// ---------------------------------------------------------------------------

test('★★★ HIGH regression lock (Cyra, PR #170 third re-review): a whole-component Zs (space-separator) noise directory interposed within .tess/keys/verifiers does not defeat exclusion', () => {
  const vectors = {
    'NBSP U+00A0': '.tess/\u00A0/keys/verifiers/cyra.asc',
    'EN QUAD U+2000': '.tess/\u2000/keys/verifiers/cyra.asc',
    'EM SPACE U+2003': '.tess/\u2003/keys/verifiers/cyra.asc',
    'THIN SPACE U+2009': '.tess/\u2009/keys/verifiers/cyra.asc',
    'NARROW NO-BREAK SPACE U+202F': '.tess/\u202F/keys/verifiers/cyra.asc',
    'MEDIUM MATHEMATICAL SPACE U+205F': '.tess/\u205F/keys/verifiers/cyra.asc',
    'IDEOGRAPHIC SPACE U+3000': '.tess/\u3000/keys/verifiers/cyra.asc',
    'OGHAM SPACE MARK U+1680': '.tess/\u1680/keys/verifiers/cyra.asc',
  };
  for (const [label, p] of Object.entries(vectors)) {
    assert.equal(isExcludedRel(p), true, `a ${label} directory component interposed within the forbidden .tess/keys/verifiers prefix must not defeat exclusion`);
  }
});

test('★★★ HIGH regression lock (Cyra, PR #170 third re-review): a whole-component Zl/Zp (line/paragraph separator) noise directory interposed within .tess/keys/verifiers does not defeat exclusion', () => {
  assert.equal(isExcludedRel('.tess/\u2028/keys/verifiers/cyra.asc'), true, 'a LINE SEPARATOR (U+2028) directory component must not defeat exclusion');
  assert.equal(isExcludedRel('.tess/\u2029/keys/verifiers/cyra.asc'), true, 'a PARAGRAPH SEPARATOR (U+2029) directory component must not defeat exclusion');
});

test('★★★ HIGH regression lock (Cyra, PR #170 third re-review): a whole-component Cc (control) noise directory interposed within .tess/keys/verifiers does not defeat exclusion', () => {
  const vectors = {
    'SOH U+0001 (C0)': '.tess/\u0001/keys/verifiers/cyra.asc',
    'US U+001F (C0)': '.tess/\u001F/keys/verifiers/cyra.asc',
    'TAB U+0009 (C0)': '.tess/\u0009/keys/verifiers/cyra.asc',
    'PAD U+0080 (C1)': '.tess/\u0080/keys/verifiers/cyra.asc',
    'NEL U+0085 (C1)': '.tess/\u0085/keys/verifiers/cyra.asc',
  };
  for (const [label, p] of Object.entries(vectors)) {
    assert.equal(isExcludedRel(p), true, `a ${label} directory component interposed within the forbidden .tess/keys/verifiers prefix must not defeat exclusion`);
  }
});

test('★★★ HIGH regression lock (Cyra, PR #170 third re-review): mixed noise components (NBSP+ZWSP, NBSP+trailing-dot) interposed within .tess/keys/verifiers do not defeat exclusion', () => {
  assert.equal(isExcludedRel('.tess/\u00A0\u200B/keys/verifiers/cyra.asc'), true, 'NBSP + ZWSP mixed noise component must not defeat exclusion');
  assert.equal(isExcludedRel('.tess/\u00A0./keys/verifiers/cyra.asc'), true, 'NBSP + trailing dot mixed noise component must not defeat exclusion');
});

// Sweep across every EXCLUDE_DIR_PREFIXES / EXCLUDE_CONTENT_PREFIXES root —
// mirrors the identical sweep already done above for the Hangul-filler
// vectors, extended to the Zs/Cc widening.
test('★ PR #170 third re-review: the Zs/Cc noise-component vector is closed against every EXCLUDE_DIR_PREFIXES / EXCLUDE_CONTENT_PREFIXES root, not just one', () => {
  const vectors = [
    ['.claude/\u00A0/tess-secrets/token.env', 'EXCLUDE_DIR_PREFIXES: .claude/tess-secrets (NBSP)'],
    ['.claude/\u3000/channels/access.json', 'EXCLUDE_DIR_PREFIXES: .claude/channels (IDEOGRAPHIC SPACE)'],
    ['.tess/\u0001/keys/signoffs/xavier.asc', 'EXCLUDE_DIR_PREFIXES: .tess/keys/signoffs (Cc control)'],
    ['.tess/\u2028/state/memory/real.json', 'EXCLUDE_CONTENT_PREFIXES: .tess/state/memory (LINE SEPARATOR)'],
  ];
  for (const [p, label] of vectors) {
    assert.equal(isExcludedRel(p), true, `${label}: Zs/Cc noise component interposed within the prefix must not defeat exclusion — isExcludedRel(${JSON.stringify(p)})`);
  }
});

// ---------------------------------------------------------------------------
// Negative controls — the #146 fix must not become an overbroad hammer.
// ---------------------------------------------------------------------------

// A noise component NOT adjacent to any forbidden prefix — mirrors
// secrets-casefold-bypass.test.js's identical negative control for the
// all-dots/all-space vector.
test('negative control (#146 fix): a noise component NOT within any forbidden prefix does not spuriously exclude an ordinary file', () => {
  assert.equal(isExcludedRel('docs/​/notes/README.md'), false, 'an ordinary nested path with a zero-width-space noise component must still be kept');
  assert.equal(isExcludedRel('docs/­/notes/README.md'), false, 'an ordinary nested path with a soft-hyphen noise component must still be kept');
});

// Same negative control, PR #170 widening: a Hangul-filler noise component
// NOT within any forbidden prefix must not spuriously exclude an ordinary
// file either.
test('negative control (PR #170 fix): a Hangul-filler noise component NOT within any forbidden prefix does not spuriously exclude an ordinary file', () => {
  assert.equal(isExcludedRel('docs/ᅟ/notes/README.md'), false, 'an ordinary nested path with a HANGUL CHOSEONG FILLER noise component must still be kept');
  assert.equal(isExcludedRel('docs/ㅤ/notes/README.md'), false, 'an ordinary nested path with a HANGUL FILLER noise component must still be kept');
});

// ★ The DELIBERATELY REJECTED broader interpretation, made explicit: this
// fix collapses only the two provably-noise categories (Cf format-control
// codepoints; lone combining marks with no base). It does NOT force-exclude
// every component containing any non-`[A-Za-z0-9._-]` character — that
// broader reading was evaluated and rejected because it directly conflicts
// with secrets-casefold-bypass.test.js's own existing negative control
// (`agents/café-notes/README.md` must be KEPT, not excluded — "the fix must
// not become an overbroad hammer against ordinary unicode filenames"). This
// test locks that scoping decision so a future "helpful" broadening cannot
// silently regress it.
test('negative control (#146 fix, scoping): ordinary non-ASCII (non-Cf, non-combining-only) content anywhere in the path is still kept', () => {
  assert.equal(isExcludedRel('agents/café-notes/README.md'), false, 'an ordinary accented directory name must still be kept — not every non-ASCII path is "ambiguous"');
  assert.equal(isExcludedRel('clients/日本支店/kb/wiki/index.md'), false, 'ordinary non-Latin-script content must still be kept — not every non-ASCII path is "ambiguous"');
});

// Ordinary files, completely unaffected — proves the fix is not an overbroad
// hammer in the plain-ASCII case either (mirrors secrets-casefold-bypass's
// own convention).
// Negative control (Cyra, PR #170 third re-review): the whole-component
// "no visible base" test (Part B) must NOT become an embedded strip — a real
// CJK directory name that uses U+3000 IDEOGRAPHIC SPACE as an internal word
// separator (a legitimate, identity-bearing use, not noise) must stay KEPT.
test('negative control (Cyra, PR #170 third re-review): a real CJK path segment using U+3000 as an internal word separator stays kept, not excluded', () => {
  assert.equal(isExcludedRel('clients/\u65E5\u672C\u3000\u652F\u5E97/kb/wiki/index.md'), false, 'a legitimate CJK directory name with an embedded ideographic-space word separator must stay kept');
});

// Negative control (Cyra, PR #170 third re-review): a lone visible
// punctuation character (Pd category, not noise) must not be swept up by
// the whole-component collapse.
test('negative control (Cyra, PR #170 third re-review): a lone hyphen path component is kept, not excluded', () => {
  assert.equal(isExcludedRel('docs/-/README.md'), false, 'a lone hyphen directory component is visible punctuation, not noise, and must stay kept');
});

test('negative control: ordinary ASCII files are unaffected by the #146 fix', () => {
  for (const p of ['README.md', 'CLAUDE.md', 'src/index.js', 'agents/leah/README.md', 'package.json']) {
    assert.equal(isExcludedRel(p), false, `${p} must be kept`);
  }
});
