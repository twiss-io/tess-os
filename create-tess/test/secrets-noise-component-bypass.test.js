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
// mirrors secrets-casefold-bypass.test.js's own convention.
test('sanity: canonical (noise-free) forms of every #146 vector path are excluded', () => {
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
// Negative controls — the #146 fix must not become an overbroad hammer.
// ---------------------------------------------------------------------------

// A noise component NOT adjacent to any forbidden prefix — mirrors
// secrets-casefold-bypass.test.js's identical negative control for the
// all-dots/all-space vector.
test('negative control (#146 fix): a noise component NOT within any forbidden prefix does not spuriously exclude an ordinary file', () => {
  assert.equal(isExcludedRel('docs/​/notes/README.md'), false, 'an ordinary nested path with a zero-width-space noise component must still be kept');
  assert.equal(isExcludedRel('docs/­/notes/README.md'), false, 'an ordinary nested path with a soft-hyphen noise component must still be kept');
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
test('negative control: ordinary ASCII files are unaffected by the #146 fix', () => {
  for (const p of ['README.md', 'CLAUDE.md', 'src/index.js', 'agents/leah/README.md', 'package.json']) {
    assert.equal(isExcludedRel(p), false, `${p} must be kept`);
  }
});
