// secrets-nested-noise-dir-copy-filter.test.js — PERMANENT fs-level
// regression guard for Reid's HIGH finding (PR #170 second security
// re-review): a noise-component path (Cf/zero-width/soft-hyphen/
// combining-only, #146; Hangul-filler family, PR #170) must be excluded by
// the REAL scaffold-copy path, `makeCopyFilter` — not just the string-only
// `isExcludedRel` check every other test file in this directory exercises.
//
// WHY THIS FILE EXISTS, SEPARATELY FROM secrets-noise-component-bypass.test.js:
// that file is deliberately FS-independent (pure string input to
// `isExcludedRel`, see its own header comment). Reid's review showed that is
// not sufficient on its own: `isExcludedRel` returning `true` proves the
// STRING arm excludes a path, but says nothing about whether the SECOND,
// inode-based arm inside `makeCopyFilter` could ever independently rescue a
// leak the string arm missed (the "inode arm backstops it" claim issue #146
// and this PR's own original body made — see src/pathnorm.js's header
// comment for the full correction). Proving the fix actually closes the real
// scaffold-copy path requires calling `makeCopyFilter` itself against a
// GENUINE on-disk fixture (real directories, real inodes) — exactly Reid's
// own PoC methodology, reproduced here as a permanent, deterministic test
// rather than a one-off manual repro.
//
// THE BUG (empirically reproduced against this PR's OWN pre-this-fix code,
// i.e. AFTER #146's `\p{Cf}`-only fix already landed): a Hangul-filler noise
// directory (U+115F/U+1160/U+3164) interposed BEFORE a forbidden
// EXCLUDE_DIR_PREFIXES root is reached (e.g.
// `.tess/<U+115F>/keys/verifiers/cyra.asc`) was KEPT by `isExcludedRel` AND
// COPIED by `makeCopyFilter` — a real, unmitigated leak of a genuine
// verifier key through the actual scaffold-copy pipeline, not a theoretical
// string-only gap. The inode/stat arm did NOT catch it: `.tess/<noise>/keys/
// verifiers` is a genuinely different, separate, differently-inoded
// directory from `.tess/keys/verifiers` — the inode arm only defends against
// SAME-DIRECTORY case-fold/NFC-NFD aliasing (the CRITICAL bug PR #145 fixed),
// never a nested extra directory.
//
// THE FIX (src/pathnorm.js): widen `normalizeComponent`'s strip from
// `\p{Cf}` to `\p{Default_Ignorable_Code_Point}` (a strict superset covering
// the Hangul-filler family too) — see pathnorm.js's header comment for the
// full design.
//
// Run: npm test   (or `node --test`)
import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

import { isExcludedRel, makeCopyFilter } from '../src/ignore.js';

// Fixture content shaped like a real PGP key file (mirrors
// scaffold-key-guard.test.js's own convention) — never a real key, just
// enough to prove the FILE ITSELF, not merely an empty placeholder, would be
// copied or excluded.
const FIXTURE_KEY_CONTENT =
  '-----BEGIN PGP PUBLIC KEY BLOCK-----\nFIXTURE-NOT-A-REAL-KEY-test-only\n-----END PGP PUBLIC KEY BLOCK-----\n';

const tempDirs = [];
after(() => {
  for (const d of tempDirs) rmSync(d, { recursive: true, force: true });
});

// Build a real on-disk fixture rooted at a fresh tmpdir: writes a "key" file
// at `root/<relPath>` (creating every intermediate directory for real, on
// the real filesystem — genuine inodes, not a mock), and returns
// { root, abs, rel } for use against `isExcludedRel`/`makeCopyFilter`.
function buildFixture(relPath) {
  const root = mkdtempSync(join(tmpdir(), 'create-tess-nested-noise-'));
  tempDirs.push(root);
  const abs = join(root, ...relPath.split('/'));
  mkdirSync(join(abs, '..'), { recursive: true });
  writeFileSync(abs, FIXTURE_KEY_CONTENT);
  return { root, abs, rel: relPath };
}

// ---------------------------------------------------------------------------
// ★★ HIGH regression lock (Reid, PR #170) — the exact PoC structure Reid
// reproduced: a noise directory interposed BEFORE `.tess/keys/verifiers` is
// ever reached, proven via a REAL on-disk fixture through BOTH arms
// (`isExcludedRel` AND `makeCopyFilter`) — not just the string arm alone.
// ---------------------------------------------------------------------------

for (const [label, noise] of [
  ['U+115F HANGUL CHOSEONG FILLER', 'ᅟ'],
  ['U+1160 HANGUL JUNGSEONG FILLER', 'ᅠ'],
  ['U+3164 HANGUL FILLER', 'ㅤ'],
]) {
  test(`★★ HIGH regression lock (Reid, PR #170): a genuine verifier key nested under a ${label} noise directory is excluded by makeCopyFilter (fs-level PoC)`, () => {
    const { root, abs, rel } = buildFixture(`.tess/${noise}/keys/verifiers/cyra.asc`);

    assert.equal(isExcludedRel(rel), true, `isExcludedRel must exclude the ${label}-nested path`);

    const filter = makeCopyFilter(root);
    assert.equal(
      filter(abs),
      false,
      `makeCopyFilter must refuse to copy a real verifier key nested under a ${label} noise directory — ` +
        'this is the real scaffold-copy path, not just the string-only isExcludedRel check',
    );
  });
}

// Re-confirm the ORIGINAL #146 vector (ZWSP) at this same fs-level surface —
// belt-and-suspenders proof that the "inode arm backstops it" mischaracterization
// was already false for #146's own named vectors too, not only the
// Hangul-filler addition.
test('★★ regression lock (#146, fs-level): a genuine verifier key nested under a zero-width-space noise directory is excluded by makeCopyFilter', () => {
  const { root, abs, rel } = buildFixture('.tess/​/keys/verifiers/cyra.asc');

  assert.equal(isExcludedRel(rel), true);

  const filter = makeCopyFilter(root);
  assert.equal(
    filter(abs),
    false,
    'makeCopyFilter must refuse to copy a real verifier key nested under a zero-width-space noise directory',
  );
});

// ---------------------------------------------------------------------------
// ★★★ HIGH regression lock (Cyra, PR #170 THIRD security re-review,
// RE-BLOCK at `d96cc7a`) — the exact PoC structure Cyra reproduced: a WHOLE
// noise directory composed entirely of Zs (space-separator) / Zl / Zp
// (line/paragraph separator) / Cc (control) codepoints, interposed BEFORE
// `.tess/keys/verifiers` is ever reached, proven via a REAL on-disk fixture
// through BOTH arms (`isExcludedRel` AND `makeCopyFilter`) — not just the
// string arm alone. Verified directly against `d96cc7a` (this PR branch,
// AFTER the Hangul-filler fix already landed) before writing this fix: every
// vector below returned `copied = true` (LEAK) pre-fix, through the REAL
// scaffold-copy path, exactly mirroring the Hangul-filler PoC above.
// Codepoints given as \\uXXXX escapes (unambiguous ASCII in the source)
// rather than literal bytes.
// ---------------------------------------------------------------------------

for (const [label, noise] of [
  ['NBSP U+00A0', '\u00A0'],
  ['EN QUAD U+2000', '\u2000'],
  ['EM SPACE U+2003', '\u2003'],
  ['THIN SPACE U+2009', '\u2009'],
  ['NARROW NO-BREAK SPACE U+202F', '\u202F'],
  ['MEDIUM MATHEMATICAL SPACE U+205F', '\u205F'],
  ['IDEOGRAPHIC SPACE U+3000', '\u3000'],
  ['OGHAM SPACE MARK U+1680', '\u1680'],
  ['LINE SEPARATOR U+2028', '\u2028'],
  ['PARAGRAPH SEPARATOR U+2029', '\u2029'],
  ['Cc SOH U+0001 (C0)', '\u0001'],
  ['Cc US U+001F (C0)', '\u001F'],
  ['Cc TAB U+0009 (C0)', '\u0009'],
  ['Cc PAD U+0080 (C1)', '\u0080'],
  ['Cc NEL U+0085 (C1)', '\u0085'],
  ['combining-only U+0301 (no base)', '\u0301'],
  ['mixed NBSP+ZWSP', '\u00A0\u200B'],
  ['mixed NBSP+trailing-dot', '\u00A0.'],
]) {
  test(`★★★ HIGH regression lock (Cyra, PR #170 third re-review): a genuine verifier key nested under a ${label} whole-noise directory is excluded by makeCopyFilter (fs-level PoC)`, () => {
    const { root, abs, rel } = buildFixture(`.tess/${noise}/keys/verifiers/cyra.asc`);

    assert.equal(isExcludedRel(rel), true, `isExcludedRel must exclude the ${label}-nested path`);

    const filter = makeCopyFilter(root);
    assert.equal(
      filter(abs),
      false,
      `makeCopyFilter must refuse to copy a real verifier key nested under a ${label} whole-noise directory — ` +
        'this is the real scaffold-copy path, not just the string-only isExcludedRel check',
    );
  });
}

// ---------------------------------------------------------------------------
// ★ PART A regression lock (embedded strip, unaffected by this fix) —
// proves the ORIGINAL embedded-invisible-codepoint mechanism (Default_Ignorable
// stripped from ANYWHERE in a component, not only a whole noise component)
// still works at the fs-level makeCopyFilter surface: an invisible codepoint
// spliced INTO an otherwise-real `keys` segment must still resolve to the
// canonical `.tess/keys/verifiers` prefix and be excluded/refused.
// ---------------------------------------------------------------------------

for (const [label, noise] of [
  ['ZWSP U+200B', '\u200B'],
  ['HANGUL CHOSEONG FILLER U+115F', '\u115F'],
]) {
  test(`★ Part A regression lock (embedded invisible in a real prefix component): a genuine verifier key under .tess/keys<${label}>/verifiers is excluded by makeCopyFilter (fs-level PoC)`, () => {
    const { root, abs, rel } = buildFixture(`.tess/keys${noise}/verifiers/cyra.asc`);

    assert.equal(isExcludedRel(rel), true, `isExcludedRel must exclude the path with ${label} embedded inside the "keys" segment`);

    const filter = makeCopyFilter(root);
    assert.equal(
      filter(abs),
      false,
      `makeCopyFilter must refuse to copy a real verifier key when ${label} is embedded inside the "keys" segment — ` +
        'proves the embedded-strip mechanism (Part A) still works, not just the whole-component drop (Part B)',
    );
  });
}

// Negative control (fs-level, Cyra PR #170 third re-review): a legitimate
// CJK directory name using U+3000 as an internal word separator (has visible
// glyphs either side of the separator) must stay KEPT — the whole-component
// test must not become an embedded strip against real names.
test('negative control (fs-level, Cyra PR #170 third re-review): a real CJK directory name using U+3000 as an internal word separator is still copied, not excluded', () => {
  const { root, abs } = buildFixture('docs/\u65E5\u672C\u3000\u652F\u5E97/notes/README.md');

  const filter = makeCopyFilter(root);
  assert.equal(
    filter(abs),
    true,
    'a legitimate CJK directory name with an embedded ideographic-space word separator, outside any forbidden prefix, must still be copied (kept)',
  );
});

// ---------------------------------------------------------------------------
// Literal "noise directory nested under verifiers" shape — a noise
// component AFTER the forbidden root has already been reached
// (`.tess/keys/verifiers/<noise>/key.asc`). Unlike the vectors above, this
// shape was ALREADY safe before this fix (and before #146's fix): the
// EXCLUDE_DIR_PREFIXES whole-subtree match (`normFold.startsWith(p + '/')`)
// fires the moment the path starts with `.tess/keys/verifiers/`, regardless
// of what is nested underneath — so no noise-stripping is even needed for
// this ordering. Included for completeness (it exercises the real
// makeCopyFilter path end-to-end, same as the tests above) and to make that
// "already safe, different reason" distinction explicit and tested, not
// merely asserted.
// ---------------------------------------------------------------------------

test('sanity (already-safe shape, both pre- and post-#170): a genuine verifier key under .tess/keys/verifiers/<noise-dir>/key.asc is excluded by makeCopyFilter', () => {
  const { root, abs, rel } = buildFixture('.tess/keys/verifiers/ᅟ/key.asc');

  assert.equal(isExcludedRel(rel), true);

  const filter = makeCopyFilter(root);
  assert.equal(
    filter(abs),
    false,
    'a key nested UNDER an already-forbidden .tess/keys/verifiers root must be excluded regardless of any noise component further down the path — ' +
      'whole-subtree prefix matching already covers this shape',
  );
});

// ---------------------------------------------------------------------------
// Negative controls — the fix must not become an overbroad hammer at the
// makeCopyFilter fs-level surface either.
// ---------------------------------------------------------------------------

test('negative control (fs-level): an ordinary file nested under a noise directory NOT within any forbidden prefix is still copied', () => {
  const { root, abs } = buildFixture('docs/ᅟ/notes/README.md');

  const filter = makeCopyFilter(root);
  assert.equal(
    filter(abs),
    true,
    'an ordinary file under a noise-named directory outside any forbidden prefix must still be copied (kept)',
  );
});

test('negative control (fs-level): the canonical, noise-free forbidden path is still excluded by makeCopyFilter (baseline)', () => {
  const { root, abs, rel } = buildFixture('.tess/keys/verifiers/cyra.asc');

  assert.equal(isExcludedRel(rel), true);

  const filter = makeCopyFilter(root);
  assert.equal(filter(abs), false, 'the canonical, noise-free .tess/keys/verifiers path must remain excluded');
});
