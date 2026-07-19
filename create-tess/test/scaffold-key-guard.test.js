// scaffold-key-guard.test.js — PERMANENT regression guard for P0 G-01 (the npm
// scaffold key-leak audit, 2026-07).
//
// THE INCIDENT: the published `create-tess` 0.1.0 (npm, 2026-06-28) clones
// unpinned `main` HEAD; every `main` commit since PR #91 (which registers this
// repo's own verifier, Cyra, so THIS repo's gate can accept her verdicts on
// ITS OWN doctrine changes) carries the real bundled PUBLIC key file
// `.tess/keys/verifiers/cyra.asc`. Nothing in the scaffold copy filter
// (create-tess/src/ignore.js) or the policy reset (create-tess/src/
// policy-reset.js — which only rewrites the two `policy.yaml` YAML maps, not
// any raw key FILE) ever stripped that file, so every `npm create tess` run
// shipped a scaffolded project trusting the Twiss maintainer's own verifier
// key as if it were the scaffolded project's OWN trust root — the exact
// inversion policy-reset.js exists to prevent for the YAML registration side.
//
// THIS TEST is the permanent guard against that class of regression ever
// recurring, in EITHER direction the leak could reappear:
//   (a) broad, blast-radius-agnostic: scan the ENTIRE produced scaffold for
//       ANY PGP key-block marker or the specific known Cyra fingerprint,
//       wherever it might turn up — not just the two paths known today. A
//       future contributor adding a new key file somewhere else entirely
//       still fails this test.
//   (b) precise: `.tess/keys/verifiers/**` and `.tess/keys/signoffs/**` must
//       not exist in a scaffold AT ALL (whole-subtree exclusion, see
//       ignore.js EXCLUDE_DIR_PREFIXES), while the intentionally-bundled,
//       unrelated release-verification key (`.tess/keys/twiss-release-key.asc`)
//       must still ship — proving the fix is not an overbroad
//       "never copy anything under .tess/keys/" hammer that would also break
//       the legitimate `tessctl update` trust-verification flow.
//
// Runs a REAL, non-interactive, end-to-end scaffold (same --template-source
// pattern as wizard.test.js) rather than a synthetic fixture, so it exercises
// the actual promote()/makeCopyFilter() pipeline a real `npm create tess` run
// takes. Wired into the same `create-tess` CI job (node 18/24, `npm test` —
// Node's test runner auto-discovers any `*.test.js` under test/) as every
// other file in this directory — no separate CI wiring needed.
//
// Run: npm test   (or `node --test`)
import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, rmSync, readdirSync, readFileSync, existsSync, statSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';

const TEST_DIR = dirname(fileURLToPath(import.meta.url));
const PKG_DIR = resolve(TEST_DIR, '..'); // create-tess/
const ENTRY = join(PKG_DIR, 'bin', 'create-tess.mjs');

// Same portability override wizard.test.js/units.test.js use: the Tess OS
// repo that contains this package, one level up from create-tess/.
const TEMPLATE_SOURCE = process.env.TESS_TEMPLATE_SOURCE || resolve(PKG_DIR, '..');

// The exact fingerprint PR #91 registered for Cyra (real, not a fixture
// stand-in) — precise proof that no fingerprint-bearing artifact leaked,
// distinct from (and in addition to) the broad PGP-block scan below.
const CYRA_FINGERPRINT = 'F9321F92B4E2DF36304CB6BAA53B9C5A1F5876E8';

// Any ASCII-armored PGP key block — public OR private — anywhere in the
// scaffold is an automatic failure. This is intentionally broader than "the
// two known paths": it catches a leak wherever it recurs, including a future
// key file added somewhere this test's authors never anticipated.
const PGP_BLOCK_RE = /-----BEGIN PGP (PUBLIC|PRIVATE) KEY BLOCK-----/;

const tempDirs = [];
after(() => {
  for (const d of tempDirs) rmSync(d, { recursive: true, force: true });
});

// Recursively collect every regular file under `dir` (relative paths,
// forward-slash normalized), skipping nothing — this guard must see the
// WHOLE scaffold, not a curated subset.
function walkFiles(dir, base = dir, out = []) {
  for (const entry of readdirSync(dir)) {
    const abs = join(dir, entry);
    const st = statSync(abs);
    if (st.isDirectory()) {
      walkFiles(abs, base, out);
    } else if (st.isFile()) {
      out.push(abs);
    }
  }
  return out;
}

test('P0 G-01 permanent guard: a fresh scaffold carries NO verifier/sign-off key material anywhere', { timeout: 180000 }, () => {
  const target = mkdtempSync(join(tmpdir(), 'create-tess-key-guard-'));
  tempDirs.push(target);

  const run = spawnSync(
    process.execPath,
    [
      ENTRY,
      '--yes',
      '--operator=Vega',
      '--vibe=command',
      '--path=founders',
      '--pathway=operator',
      `--template-source=${TEMPLATE_SOURCE}`,
      `--target=${target}`,
      '--no-git-init',
      '--no-gate-hooks',
    ],
    { cwd: PKG_DIR, encoding: 'utf8' },
  );
  assert.equal(
    run.status,
    0,
    `wizard exited non-zero\nSTDOUT:\n${run.stdout}\nSTDERR:\n${run.stderr}`,
  );

  // ── (a) broad scan: no PGP key block, no Cyra fingerprint, ANYWHERE ──────
  const files = walkFiles(target);
  assert.ok(files.length > 50, `sanity check: expected a real scaffold tree, only found ${files.length} files`);

  // The ONE legitimate, intentionally-bundled exception: this repo's own
  // release-verification public key, which every scaffold is SUPPOSED to
  // ship (used by `tessctl update` to verify an upstream fetch — see
  // conductor/release-process.md). Everything else in the tree is a
  // per-project trust-anchor artifact that must never appear.
  const ALLOWED_KEY_FILE = join(target, '.tess', 'keys', 'twiss-release-key.asc');

  const offendersBlock = [];
  const offendersFingerprint = [];
  for (const abs of files) {
    if (abs === ALLOWED_KEY_FILE) continue;
    // Read as latin1 (byte-preserving) rather than utf8 — the search tokens
    // are pure ASCII, so this avoids a thrown UTF-8 decode error on any
    // non-text file in the tree without needing to guess/skip by extension.
    const text = readFileSync(abs, 'latin1');
    if (PGP_BLOCK_RE.test(text)) offendersBlock.push(abs);
    if (text.includes(CYRA_FINGERPRINT)) offendersFingerprint.push(abs);
  }
  assert.deepEqual(
    offendersBlock, [],
    `a scaffolded instance must NEVER contain a PGP key block; found in:\n${offendersBlock.join('\n')}`,
  );
  assert.deepEqual(
    offendersFingerprint, [],
    `a scaffolded instance must NEVER carry the registered Cyra fingerprint; found in:\n${offendersFingerprint.join('\n')}`,
  );

  // ── (b) precise: the two governance-key subtrees must not exist at all ──
  assert.equal(
    existsSync(join(target, '.tess', 'keys', 'verifiers')),
    false,
    '.tess/keys/verifiers must not exist in a scaffolded instance',
  );
  assert.equal(
    existsSync(join(target, '.tess', 'keys', 'signoffs')),
    false,
    '.tess/keys/signoffs must not exist in a scaffolded instance',
  );

  // ── positive control: the fix must not be an overbroad hammer — the
  // intentionally-bundled, unrelated release-verification key still ships,
  // and it is the ONLY thing under .tess/keys/ in a produced instance. ──────
  const keysDir = join(target, '.tess', 'keys');
  assert.ok(existsSync(keysDir), '.tess/keys/ must still exist (it ships the release-verification key)');
  const keysEntries = readdirSync(keysDir).sort();
  assert.deepEqual(
    keysEntries,
    ['twiss-release-key.asc'],
    `.tess/keys/ must contain ONLY the release-verification key, got: ${keysEntries.join(', ')}`,
  );
  assert.match(
    readFileSync(join(keysDir, 'twiss-release-key.asc'), 'utf8'),
    /-----BEGIN PGP PUBLIC KEY BLOCK-----/,
    'the release-verification key itself must still be a valid, intact PGP public key block',
  );

  // A leak-free scaffold must still be a genuinely working instance.
  const tessctl = (...sub) =>
    spawnSync('python3', [join(target, '.tess', 'bin', 'tessctl'), ...sub], {
      cwd: target,
      env: { ...process.env, TESS_ROOT: target },
      encoding: 'utf8',
    });
  const doctor = tessctl('doctor');
  assert.equal(doctor.status, 0, `tessctl doctor must pass\nSTDOUT:\n${doctor.stdout}\nSTDERR:\n${doctor.stderr}`);
  const verify = tessctl('verify');
  assert.equal(verify.status, 0, `tessctl verify must pass\nSTDOUT:\n${verify.stdout}\nSTDERR:\n${verify.stderr}`);
});
