// secrets-casefold-bypass.test.js — PERMANENT regression guard for the
// CRITICAL secrets-exclusion case-fold bypass (2026-07 security audit,
// live-reproduced on macOS).
//
// THE BUG: `create-tess/src/ignore.js`'s `isExcludedRel()`/`makeCopyFilter()`
// (the SINGLE shared filter both scaffold copy paths — `fetchTemplate`'s
// local-source branch and `promote()` — derive from) used plain JS string
// `===`/`.startsWith()`/`Set.has()` on path strings. macOS (APFS, default)
// and Windows (NTFS, default) — the two documented default DEPLOYMENT
// filesystems for `npm create tess` — are case-INSENSITIVE, so a secret dir
// spelled with non-canonical case, e.g. `.Claude/Tess-Secrets/`, is the SAME
// INODE as `.claude/tess-secrets/` on disk but a DIFFERENT STRING: every
// check in the filter silently returned false and the scaffolder COPIED the
// secret tree verbatim into every produced instance. Live-reproduced:
// `isExcludedRel('.Claude/Tess-Secrets/token.env')` returned `false` despite
// `.Claude/Tess-Secrets` being the identical inode as `.claude/tess-secrets`.
// Payload = LITERAL SECRETS: `vault.age`, `identity.age`, live
// `.claude/tess-secrets/*` tokens, the PRIVATE `.tess/keys/verifiers/**`/
// `signoffs/**` trust-anchor keys, and real `.tess/state/memory/**` operator
// data. Same bug CLASS as #117/#140 (fixed on the Python `tessctl` side with
// inode-identity — `_paths_are_same_location`/`_path_is_prefix`,
// `.tess/bin/tessctl`) landing again in the JS scaffolder — and it silently
// defeated the #108/0.1.2 npm-hazard scaffold-key-strip, since that strip
// only ever runs on paths this filter decided to actually look at.
//
// THE FIX (ignore.js): a case/NFC-normalized string fallback applied to
// EVERY comparison (`normalizeComponent`/`normalizePath`, mirroring
// tessctl's write-gate `.rstrip('. ').lower()` per-component normalization,
// extended with NFC), PLUS an inode-identity ground-truth layer
// (`sameFsLocation`, the JS analogue of tessctl's `_paths_are_same_location`
// / `os.path.samefile`) in `makeCopyFilter` for the DIR-prefix secret
// exclusions (EXCLUDE_DIR_PREFIXES) — the exclusion tier anchored to a
// single, fixed, resolvable path under the copy root.
//
// ★ CI-COVERAGE NOTE (mirrors the #140 fix's own note, `tests/
// test_skill_from_task.py`): a NATIVE case-fold (writing `.claude/x` and
// reading it back as `.CLAUDE/x`) can only be reproduced on an ACTUALLY
// case-insensitive filesystem — macOS APFS, Windows NTFS. This repo's Linux
// CI runners (ext4, case-SENSITIVE) cannot construct one natively, so a test
// that relies on real OS case-folding would silently never exercise the bug
// on CI — exactly how the original bug shipped green. Every test below is
// therefore split into:
//   (a) FS-INDEPENDENT primitive tests — exercise `isExcludedRel` directly
//       with a case-variant / NFC-vs-NFD STRING (no disk I/O at all), and a
//       `makeCopyFilter` inode-identity test using a SYMLINK alias (works
//       identically on ext4/APFS/NTFS — a symlink is not a case-fold, but it
//       is the same "two different path strings, one filesystem location"
//       shape, and is exactly the portable stand-in PR #140's own
//       FS-independent regression test used for the identical reason). These
//       run, and must pass, on EVERY CI runner including this repo's Linux
//       job.
//   (b) an OPPORTUNISTIC, runtime-gated (never hardcoded by platform name)
//       full-pipeline test using a REAL native case-fold, through the ACTUAL
//       `fetchTemplate` + `promote` copy paths a real `npm create tess` run
//       takes. Skipped (never silently "passed") when the test runner's own
//       filesystem is genuinely case-sensitive.
//
// Run: npm test   (or `node --test`)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  mkdtempSync,
  mkdirSync,
  writeFileSync,
  existsSync,
  rmSync,
  symlinkSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { isExcludedRel, makeCopyFilter, normalizeComponent } from '../src/ignore.js';
import { fetchTemplate, promote } from '../src/scaffold.js';

// ---------------------------------------------------------------------------
// (a) FS-INDEPENDENT primitives — no disk I/O, run identically on every OS.
// ---------------------------------------------------------------------------

// The EXACT live-reproduced bug: a case-variant spelling of every secret
// pattern class this filter is supposed to catch must be excluded, IDENTICAL
// to the canonical-case verdict.
test('CRITICAL case-fold bypass: a case-variant spelling of every secret pattern class is excluded, same as canonical case', () => {
  const pairs = [
    // The literal live repro.
    ['.claude/tess-secrets/token.env', '.Claude/Tess-Secrets/token.env'],
    ['.claude/tess-secrets/token.env', '.CLAUDE/TESS-SECRETS/TOKEN.ENV'],
    // EXCLUDE_DIR_PREFIXES — the other three whole-subtree secret roots.
    ['.claude/channels/access.json', '.Claude/Channels/access.json'],
    ['.tess/keys/verifiers/cyra.asc', '.Tess/Keys/Verifiers/cyra.asc'],
    ['.tess/keys/signoffs/xavier.asc', '.TESS/KEYS/SIGNOFFS/xavier.asc'],
    // EXCLUDE_NAMES — bare-name component match (any depth).
    ['.git/config', '.GIT/config'],
    ['.claude/vault/vault.age', '.CLAUDE/VAULT/VAULT.AGE'],
    ['.claude/vault/identity.age', '.Claude/Vault/Identity.Age'],
    ['secrets/api-key.txt', 'SECRETS/api-key.txt'],
    ['tess-secrets/token.json', 'Tess-Secrets/token.json'],
    ['nested/dir/secrets/leaked.txt', 'nested/Dir/SECRETS/leaked.txt'],
    // ★ LOW fix (Reid, PR #145 review): the leaf filename must ALSO vary
    // case here, not just the parent dir — `vault.age` is already an EXACT
    // EXCLUDE_NAMES match independent of `.vault`/`.VAULT` casing, so a row
    // that leaves the leaf untouched provides no discriminating power (it
    // "passes" even against a pre-fix module, proving nothing about the
    // `.vault` directory-name case-fold this row is meant to exercise).
    // Verified directly: all 24 original pairs run against the pre-fix
    // module — 23/24 genuinely failed pre-fix/passed post-fix; this row was
    // the one exception. Varying the leaf too makes it discriminate.
    ['clients/Acme/.vault/vault.age', 'clients/Acme/.VAULT/Vault.AGE'],
    ['node_modules/x/index.js', 'NODE_MODULES/x/index.js'],
    // Basename suffix globs.
    ['server.pem', 'SERVER.PEM'],
    ['deploy.key', 'Deploy.KEY'],
    ['prod.env.json', 'PROD.ENV.JSON'],
    ['operator/db.secret', 'operator/DB.SECRET'],
    // .env handling.
    ['.env', '.ENV'],
    ['.env.local', '.Env.Local'],
    // .claude/settings.local.json local override.
    ['.claude/settings.local.json', '.Claude/Settings.Local.JSON'],
    // .tess/state/** content prefixes.
    ['.tess/state/memory/real.json', '.Tess/State/Memory/real.json'],
    ['.tess/state/receipts/chain.jsonl', '.TESS/STATE/RECEIPTS/chain.jsonl'],
    // EXCLUDE_REL_PATHS exact-path excludes.
    ['.github/workflows/ci.yml', '.GitHub/Workflows/CI.yml'],
    ['.github/workflows/publish-npm.yml', '.github/Workflows/Publish-NPM.yml'],
  ];
  for (const [canonical, variant] of pairs) {
    assert.equal(isExcludedRel(canonical), true, `sanity: canonical-case ${canonical} must be excluded`);
    assert.equal(
      isExcludedRel(variant),
      true,
      `CRITICAL: case-variant ${variant} must be excluded identically to ${canonical} — ` +
        `same inode on a case-insensitive filesystem (macOS APFS / Windows NTFS, the documented ` +
        `default deployment targets), a plain string comparison misses it`,
    );
  }
});

// ★★ HIGH regression lock (Reid, PR #145 review) — empty-normalized-component
// join corruption. `normalizeComponent` strips a component that is ENTIRELY
// dots/spaces (a literal `...` directory — legal `mkdir`, no special
// filesystem meaning; a leading `.` from a `./`-prefixed relative path; or a
// whitespace-only component) down to `''`. Pre-fix, joining that empty
// string back into the path (rather than dropping it) corrupted the string
// used for prefix matching — either a double `//` or a leading `/` — and
// NEITHER `startsWith` its intended EXCLUDE_DIR_PREFIXES/
// EXCLUDE_CONTENT_PREFIXES entry anymore, so a secret nested under a noise
// component silently slipped through as KEPT instead of EXCLUDED. This
// directly violates the fix's own stated invariant ("any case/normalization
// ambiguity … must resolve to EXCLUDE, never to copy it anyway … fail-closed
// … never the reverse") — the exact same DIRECTION of failure (a leak) as
// the CRITICAL bug this file otherwise guards, just via a narrower vector.
//
// Empirically verified (not by reasoning alone) against the actual pre-fix
// PR-branch blob before writing the fix: all three vectors below returned
// `false` (BUG) pre-fix and `true` (correct) post-fix.
//
// ★ Reid's own suggested one-liner (`stripped || norm` — fall back to the
// UN-stripped, casefolded component instead of collapsing to empty) and
// Cyra's independently-flagged LOW-1 finding on the SAME root cause
// (suggesting "re-filter empties *after* normalization") diverge in
// behavior: Reid's fallback merely PRESERVES the noise component literally
// in the joined path (avoiding the corrupting empty-string artifact) but
// does NOT remove it — so `.tess/.../keys/verifiers/cyra.asc` normalizes to
// `.tess/.../keys/verifiers/cyra.asc` (unchanged) and still does not
// `startsWith('.tess/keys/verifiers/')`, i.e. it does NOT actually restore
// exclusion (verified directly, in isolation, against his exact snippet).
// Cyra's direction — DROP the empty component entirely, so the noise
// component vanishes from the matched path and the secret's canonical
// prefix lines back up — is the one implemented here (ignore.js's
// `normalizePath`: a second `.filter(Boolean)` after the `.map`). This is
// the deliberate, fail-safe DENYLIST choice: over-EXCLUDING an ordinary path
// that happens to collapse onto a forbidden prefix this way is acceptable;
// under-excluding a secret is not.
test('★★ HIGH regression lock: an empty-after-normalization noise component (all-dots, leading ./, all-space) does not defeat prefix-based exclusion', () => {
  const vectors = [
    ['.tess/.../keys/verifiers/cyra.asc', 'a literal "..." directory component (legal mkdir, no special FS meaning)'],
    ['./.tess/keys/verifiers/cyra.asc', 'a leading "./" producing a leading empty component (Cyra LOW-1)'],
    ['.tess/.  /keys/verifiers/cyra.asc', 'a whitespace-only component (". ", two trailing spaces)'],
    // EXCLUDE_CONTENT_PREFIXES is affected by the identical root cause, not
    // just EXCLUDE_DIR_PREFIXES — Reid's second reproduction.
    ['.tess/state/.../memory/real.json', 'the same noise-component bug against EXCLUDE_CONTENT_PREFIXES, not just EXCLUDE_DIR_PREFIXES'],
  ];
  for (const [p, label] of vectors) {
    assert.equal(isExcludedRel(p), true, `HIGH: ${label} must not defeat exclusion — isExcludedRel(${JSON.stringify(p)})`);
  }
  // Sanity: the canonical (noise-free) forms are excluded too, as a baseline.
  assert.equal(isExcludedRel('.tess/keys/verifiers/cyra.asc'), true, 'sanity: canonical form must be excluded');
  assert.equal(isExcludedRel('.tess/state/memory/real.json'), true, 'sanity: canonical form must be excluded');
});

// Negative control for the HIGH fix: an ORDINARY (non-secret) path that
// happens to contain a noise component must still be handled — the fix's
// over-exclusion direction is acceptable (per the denylist fail-safe
// design) but should not be mistaken for "the fix breaks all paths with
// dots in them"; a ordinary all-dots component that does NOT collapse onto
// any forbidden prefix stays kept, same as before the fix.
test('negative control (HIGH fix): a noise component NOT adjacent to any forbidden prefix does not spuriously exclude an ordinary file', () => {
  assert.equal(isExcludedRel('docs/.../notes/README.md'), false, 'an ordinary nested path with a noise component must still be kept');
  assert.equal(isExcludedRel('./README.md'), false, 'an ordinary leading-./ path must still be kept');
});

// The denylist's fail-safe direction, made explicit: a case ambiguity must
// resolve to EXCLUDE, never to a loosened KEEP. `.env.example` is exempted
// ONLY at its exact, canonical case — a differently-cased spelling is NOT
// granted the exemption, and instead falls through to the (normalized)
// `.env` exclusion below it and is excluded. Over-excluding a template file
// is the acceptable failure mode; under-excluding a secret is not.
test('★ denylist fail-safe: a case-variant of a KEEP_BASENAMES exemption is EXCLUDED, never loosely kept', () => {
  assert.equal(isExcludedRel('.env.example'), false, 'the exact, canonical-case exemption must still be kept');
  assert.equal(isExcludedRel('starter/.env.example'), false, 'the exact, canonical-case exemption must still be kept (nested)');
  assert.equal(
    isExcludedRel('.ENV.EXAMPLE'),
    true,
    'a case-variant spelling of the .env.example exemption must NOT be granted the keep — ' +
      'ambiguity resolves to exclude, per the fail-safe denylist design',
  );
  // Same property via the .gitkeep exemption: the canonical-case placeholder
  // under a content-stripped dir is kept, but a case-variant of it is NOT
  // granted the exemption — it falls through to the (normalized)
  // EXCLUDE_CONTENT_PREFIXES strip and is excluded.
  assert.equal(isExcludedRel('.tess/snapshots/.gitkeep'), false, 'the exact, canonical-case .gitkeep exemption must still be kept');
  assert.equal(
    isExcludedRel('.tess/snapshots/.GITKEEP'),
    true,
    'a case-variant spelling of the .gitkeep exemption must NOT be granted the keep',
  );
});

// Negative control: ordinary, non-secret files with unrelated case are still
// kept — proving the fix is not an overbroad hammer that excludes everything.
test('negative control: ordinary files are unaffected by the case/NFC normalization', () => {
  for (const p of ['README.md', 'CLAUDE.md', 'src/index.js', 'agents/leah/README.md', 'package.json']) {
    assert.equal(isExcludedRel(p), false, `${p} must be kept`);
  }
});

// ★ The LOAD-BEARING NFC regression lock (mirrors the exported
// buildCloneArgs/resolveTemplateRef pattern in scaffold.js — a pure,
// dependency-free primitive exported specifically so this is directly
// unit-testable, no filesystem or full-path plumbing required): none of
// today's secret-pattern names contain an accented character, so an
// isExcludedRel()-level assertion using an accented filename ends up
// passing/failing on the (unrelated) prefix or casefold match alone and
// never actually exercises the NFC step in isolation. This test isolates
// the primitive directly and PROVES the NFC-normalize-BEFORE-casefold
// ordering is load-bearing, not redundant with `.toLowerCase()` alone:
// lower-casing an NFD-decomposed grapheme ("E" + COMBINING ACUTE ACCENT, two
// codepoints) does NOT, on its own, converge with the lower-cased form of
// its NFC-precomposed counterpart (a single codepoint) — only normalizing
// to NFC FIRST makes the two forms compare equal. Fails on a version of
// `normalizeComponent` that casefolds without normalizing first (i.e. would
// have failed against the original bug's naive `.toLowerCase()`-only shape
// had it also lacked NFC handling).
test('★ NFC/NFD regression lock: normalizeComponent converges NFC-composed and NFD-decomposed forms of the identical grapheme', () => {
  const composed = 'É'; // U+00C9 — single precomposed codepoint
  const decomposed = 'É'.normalize('NFD'); // U+0045 U+0301 — "E" + COMBINING ACUTE ACCENT
  assert.notEqual(composed, decomposed, 'sanity: NFC and NFD must be different byte sequences for the same grapheme');
  // The bug this guards against: casefolding WITHOUT normalizing to NFC
  // first leaves the two forms divergent.
  assert.notEqual(
    composed.toLowerCase(), decomposed.toLowerCase(),
    'sanity: casefolding alone (no NFC step) does NOT converge NFC/NFD — proves the NFC step is necessary, not redundant',
  );
  // The fix: normalizeComponent converges both to the identical string.
  assert.equal(normalizeComponent(composed), normalizeComponent(decomposed));
  assert.equal(normalizeComponent(composed), 'é');
});

// End-to-end consistency, through the public isExcludedRel/makeCopyFilter
// surface a real scaffold run actually calls: macOS APFS/HFS+ is documented
// to normalize filenames to NFD form on disk (and on readdir()) even when a
// tool wrote them as NFC-composed bytes — so the SAME semantic path can
// arrive at this filter as either encoding depending on which layer
// produced it. Both encodings of the identical semantic path must produce
// the IDENTICAL verdict — a normalization divergence must never let one
// spelling slip past while the other is caught (kept OR excluded).
test('NFC/NFD variant: both Unicode encodings of the identical semantic path produce the identical isExcludedRel verdict', () => {
  const secretNfc = '.claude/tess-secrets/café-token.env'.normalize('NFC');
  const secretNfd = '.claude/tess-secrets/café-token.env'.normalize('NFD');
  assert.notEqual(secretNfc, secretNfd, 'sanity: NFC-composed and NFD-decomposed must be different byte sequences for the same semantic filename');
  assert.equal(isExcludedRel(secretNfc), true, 'the NFC-composed secret path must be excluded');
  assert.equal(isExcludedRel(secretNfd), true, 'the NFD-decomposed secret path must be excluded identically');

  // Positive control: a legitimate, non-secret file that happens to carry
  // accented characters is kept in EITHER encoding — the fix must not
  // become an overbroad hammer against ordinary unicode filenames.
  const legitNfc = 'agents/café-notes/README.md'.normalize('NFC');
  const legitNfd = 'agents/café-notes/README.md'.normalize('NFD');
  assert.notEqual(legitNfc, legitNfd, 'sanity: NFC and NFD must differ as byte sequences');
  assert.equal(isExcludedRel(legitNfc), false, 'a legitimate NFC-composed filename must be kept');
  assert.equal(isExcludedRel(legitNfd), false, 'a legitimate NFD-decomposed filename must be kept identically');
});

// The inode-identity GROUND-TRUTH arm, proven FS-INDEPENDENTLY (works
// identically on Linux ext4, macOS APFS, any POSIX filesystem — no reliance
// on native case-folding at all). A symlink is the portable stand-in PR
// #140's own FS-independent regression test used for the identical
// reason: two DIFFERENT path strings that the filesystem resolves to the
// SAME inode. `decoy/alias` bears zero string resemblance to
// `.claude/tess-secrets` — the case/NFC string fallback alone would NOT
// flag it — so this proves the inode arm in `makeCopyFilter` does real,
// non-redundant work, not just a belt-and-suspenders no-op.
test('CRITICAL (FS-independent): makeCopyFilter catches a same-inode alias of a secret dir via a symlink, on ANY filesystem', () => {
  const base = mkdtempSync(join(tmpdir(), 'tess-inode-arm-test-'));
  try {
    const src = join(base, 'source');
    mkdirSync(join(src, '.claude', 'tess-secrets'), { recursive: true });
    writeFileSync(join(src, '.claude', 'tess-secrets', 'token.env'), 'GITHUB_TOKEN=ghp_x\n');
    mkdirSync(join(src, 'decoy'));
    symlinkSync(join(src, '.claude', 'tess-secrets'), join(src, 'decoy', 'alias'));

    const filter = makeCopyFilter(src);

    // Sanity: the alias STRING alone (no inode check) would not be excluded
    // by any string/casefold/NFC pattern — isolates that the inode arm, not
    // the string fallback, is what makes this pass.
    assert.equal(
      isExcludedRel('decoy/alias'),
      false,
      'sanity: "decoy/alias" as a bare string matches no secret pattern — proves the string ' +
        'fallback alone could not have caught this',
    );

    // The inode arm catches it anyway.
    assert.equal(filter(join(src, 'decoy', 'alias')), false, 'a same-inode alias of a secret dir must be excluded');
    // Negative control — an unrelated symlink to a non-secret dir is unaffected.
    mkdirSync(join(src, 'public-docs'));
    writeFileSync(join(src, 'public-docs', 'README.md'), 'hi\n');
    symlinkSync(join(src, 'public-docs'), join(src, 'decoy', 'fine-alias'));
    assert.equal(filter(join(src, 'decoy', 'fine-alias')), true, 'an alias of a NON-secret dir must still be copied');
  } finally {
    rmSync(base, { recursive: true, force: true });
  }
});

// ---------------------------------------------------------------------------
// (b) Opportunistic, runtime-gated full pipeline — real native case-fold,
// through BOTH actual copy paths (fetchTemplate-local + promote). Mirrors
// the exact gating pattern PR #140's Python regression suite uses
// (`_fs_is_case_insensitive` / `pytest.skip`, `tests/test_skill_from_task.py`):
// runtime-detected, never hardcoded by platform name; cleanly SKIPPED (never
// silently "passed") on a genuinely case-sensitive runner.
// ---------------------------------------------------------------------------

// Runtime detection of whether the ACTUAL filesystem backing `dir` folds
// case — macOS APFS and Windows NTFS do by default; Linux ext4 (this repo's
// CI runner) does not.
function fsIsCaseInsensitive(dir) {
  writeFileSync(join(dir, `CaseProbeFile_${process.pid}`), 'x');
  return existsSync(join(dir, `caseprobefile_${process.pid}`));
}

test('CRITICAL (opportunistic, real case-fold): both copy paths (fetchTemplate-local + promote) exclude a case-variant secret dir', (t) => {
  const base = mkdtempSync(join(tmpdir(), 'tess-casefold-pipeline-test-'));
  try {
    if (!fsIsCaseInsensitive(base)) {
      t.skip(
        'this filesystem is case-sensitive (no native case-fold to reproduce here) — see the ' +
          'FS-independent inode-identity + string-fallback tests above for the guarantee that ' +
          'holds regardless of the runner filesystem',
      );
      return;
    }

    const src = join(base, 'source');
    const staging = join(base, 'staging');
    const target = join(base, 'instance');

    const w = (rel, body = 'x\n') => {
      const fp = join(src, rel);
      mkdirSync(join(fp, '..'), { recursive: true });
      writeFileSync(fp, body);
    };

    // Legit template files (must survive).
    w('README.md');
    w('.env.example', 'KEY=__PLACEHOLDER__\n');

    // The secret material, written under the CASE-VARIANT spelling — the
    // live-reproduced bug: a maintainer's checkout, an editor, or a prior
    // case-insensitive-aware tool can leave the on-disk directory spelled
    // this way; the scaffolder must exclude it regardless of which spelling
    // is actually on disk.
    w('.Claude/Tess-Secrets/token.env', '{"GITHUB_TOKEN":"ghp_x"}\n');
    w('.Tess/Keys/Verifiers/cyra.asc', '-----BEGIN PGP PUBLIC KEY BLOCK-----\n');

    fetchTemplate(src, staging);
    // Both spellings alias the SAME inode on this (confirmed case-insensitive)
    // filesystem — assert the canonical-case path is absent from staging,
    // proving fetchTemplate's local-source branch excluded it.
    assert.equal(
      existsSync(join(staging, '.claude', 'tess-secrets')),
      false,
      'fetchTemplate (local-source branch) must exclude the case-variant secret dir',
    );
    assert.equal(
      existsSync(join(staging, '.tess', 'keys', 'verifiers')),
      false,
      'fetchTemplate (local-source branch) must exclude the case-variant verifier-key dir',
    );
    assert.equal(existsSync(join(staging, 'README.md')), true, 'legit files must still stage');

    promote(staging, target);
    assert.equal(
      existsSync(join(target, '.claude', 'tess-secrets')),
      false,
      'promote() must exclude the case-variant secret dir from the produced instance',
    );
    assert.equal(
      existsSync(join(target, '.tess', 'keys', 'verifiers')),
      false,
      'promote() must exclude the case-variant verifier-key dir from the produced instance',
    );
    assert.equal(existsSync(join(target, 'README.md')), true, 'legit files must still land in the produced instance');
    assert.equal(existsSync(join(target, '.env.example')), true, 'the .env.example exemption must still land');
  } finally {
    rmSync(base, { recursive: true, force: true });
  }
});
