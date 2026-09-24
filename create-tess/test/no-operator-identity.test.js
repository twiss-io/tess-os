// no-operator-identity.test.js — keeps maintainer identity out of what
// `npm create tess` ships.
//
// Everything under create-tess/template/ is copied into every scaffold, and
// create-tess/src/ is the wizard itself. Neither may contain the maintainer's
// name or handle, a client name, or a maintainer machine path: the five
// strings of the release identity grep. On commit 5c2d698 (before v0.2.0),
// 68 template files and 2 wizard source files did.
//
// This repository is public, so the strings are not written out here.
// IDENTITY_NEEDLES holds each string's first three characters, its length
// and its SHA-256; the scan hashes each same-length window that starts with
// that prefix. To add a string, append
//   { prefix, length, sha256 } with
//   sha256 = node -e "console.log(require('crypto').createHash('sha256').update(process.argv[1]).digest('hex'))" '<string>'
//
// A hit is allowed only when test/identity-allowlist.txt lists its path with
// a reason. The allowlist is a plain `grep -f` pattern file, so the release
// check can run the same rule from the repository root:
//
//   git grep -lI -e <each of the five strings> \
//     -- create-tess/template create-tess/src \
//     | grep -v -f create-tess/test/identity-allowlist.txt
//
// which must print nothing. This test is the offline equivalent: it walks
// the files on disk (no git needed), skips binary files the way `git grep
// -I` does (a NUL byte in the first 8000 bytes), and checks symlink targets
// as text.
//
// The allowlist itself is checked too, so it cannot quietly grow:
//   * every pattern has a reason on the comment line directly above it;
//   * every pattern is anchored to create-tess/template/ or create-tess/src/
//     and uses only a small regex subset that means the same thing in
//     `grep -f` (POSIX basic regex) and in JavaScript;
//   * a permanent pattern that no longer matches any hit is stale and must
//     be deleted;
//   * a PENDING pattern marks a hit another v0.2.0 change removes. PENDING
//     entries are allowed only while create-tess/package.json is still 0.1.x,
//     so the 0.2.0 version bump fails until they are gone.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, readFileSync, lstatSync, readlinkSync, openSync, readSync, closeSync } from 'node:fs';
import { join, resolve, dirname, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';

const TEST_DIR = dirname(fileURLToPath(import.meta.url));
const PKG_DIR = resolve(TEST_DIR, '..'); // create-tess/
const REPO_ROOT = resolve(PKG_DIR, '..'); // repository root
const ALLOWLIST_PATH = join(TEST_DIR, 'identity-allowlist.txt');
const SCAN_ROOTS = ['create-tess/template', 'create-tess/src'];

// The same five strings as the release check's `git grep -e ...` list, in
// the same order: the maintainer's name, the maintainer's handle (the name
// plus a suffix, kept so the two lists match), a client name, and two
// maintainer home-directory prefixes. Matching is case-sensitive, as in
// `git grep`.
const IDENTITY_NEEDLES = [
  { prefix: 'Xav', length: 6, sha256: 'a350091b19d64b70d486e50c1e4b4cacce1b1efc701a255eeba0cd9639301cb5' },
  { prefix: 'Xav', length: 9, sha256: '2bfaee8ca55dbef137f4d2c61e47d3b5c806aa87e5b3a9afba8a223301b736c9' },
  { prefix: 'Sup', length: 9, sha256: '28070439ee9b5f98e0f6d6531d98814ea16c28902b05d175f46c17dceadb3b93' },
  { prefix: '/Us', length: 12, sha256: '6fb06a732c7c69f3b63a333f6d9e91745adc916a55d6823b3f9887d841fb6374' },
  { prefix: '/Us', length: 13, sha256: '4a9db63c58759adf2d69b6c00e32c5dbc311a42bcff2883e222624639d64b931' },
];

// Pattern subset shared by POSIX BRE and JS RegExp: a leading ^,
// then literal path characters, `\.` (literal dot) or `.*`, optional
// trailing $. Anything else (brackets, groups, +, ?, |, other escapes) is
// refused, because it would mean different things to grep and to this test.
const SAFE_PATTERN = /^\^(?:[A-Za-z0-9_\/-]|\\\.|\.\*)+\$?$/;
const REQUIRED_PREFIXES = ['^create-tess/template/', '^create-tess/src/'];

function toPosix(p) {
  return p.split(sep).join('/');
}

function isBinary(absPath) {
  const fd = openSync(absPath, 'r');
  try {
    const buf = Buffer.alloc(8000);
    const n = readSync(fd, buf, 0, buf.length, 0);
    return buf.subarray(0, n).includes(0);
  } finally {
    closeSync(fd);
  }
}

function sha256(text) {
  return createHash('sha256').update(text, 'utf8').digest('hex');
}

function containsNeedle(text, { prefix, length, sha256: digest }) {
  for (let i = text.indexOf(prefix); i !== -1; i = text.indexOf(prefix, i + 1)) {
    if (i + length <= text.length && sha256(text.slice(i, i + length)) === digest) return true;
  }
  return false;
}

function containsIdentity(text) {
  return IDENTITY_NEEDLES.some((needle) => containsNeedle(text, needle));
}

function walk(absDir, out) {
  for (const entry of readdirSync(absDir, { withFileTypes: true })) {
    const abs = join(absDir, entry.name);
    const st = lstatSync(abs);
    if (st.isSymbolicLink()) {
      out.push({ abs, symlink: true });
    } else if (st.isDirectory()) {
      walk(abs, out);
    } else if (st.isFile()) {
      out.push({ abs, symlink: false });
    }
  }
  return out;
}

// Repository-relative, POSIX-separated paths of every scanned file that
// contains an identity string.
function identityHits() {
  const hits = [];
  for (const root of SCAN_ROOTS) {
    for (const { abs, symlink } of walk(join(REPO_ROOT, ...root.split('/')), [])) {
      const rel = toPosix(relative(REPO_ROOT, abs));
      if (symlink) {
        if (containsIdentity(readlinkSync(abs))) hits.push(rel);
        continue;
      }
      if (isBinary(abs)) continue;
      if (containsIdentity(readFileSync(abs, 'utf8'))) hits.push(rel);
    }
  }
  return hits.sort();
}

function parseAllowlist() {
  const lines = readFileSync(ALLOWLIST_PATH, 'utf8').split('\n');
  if (lines[lines.length - 1] === '') lines.pop(); // trailing newline only
  const entries = [];
  const problems = [];
  lines.forEach((line, i) => {
    const lineNo = i + 1;
    if (line.trim() === '') {
      problems.push(`line ${lineNo}: blank line (as a grep -f pattern it would match every path)`);
      return;
    }
    if (line.startsWith('#')) {
      if (!line.startsWith('# ')) problems.push(`line ${lineNo}: a comment must start with "# "`);
      if (/[\[\]\\{}]/.test(line)) {
        problems.push(`line ${lineNo}: comments must not contain brackets, braces or backslashes (grep -f reads them as patterns)`);
      }
      return;
    }
    const reasonLine = i > 0 ? lines[i - 1] : '';
    const reason = reasonLine.startsWith('# ') ? reasonLine.slice(2).trim() : '';
    if (!reason) problems.push(`line ${lineNo}: pattern ${JSON.stringify(line)} has no reason on the line above`);
    if (!SAFE_PATTERN.test(line)) {
      problems.push(`line ${lineNo}: pattern ${JSON.stringify(line)} uses syntax outside the shared grep/JS subset`);
    }
    if (!REQUIRED_PREFIXES.some((prefix) => line.startsWith(prefix))) {
      problems.push(`line ${lineNo}: pattern ${JSON.stringify(line)} must start with ${REQUIRED_PREFIXES.join(' or ')}`);
    }
    entries.push({ lineNo, pattern: line, reason, pending: reason.startsWith('PENDING'), regex: new RegExp(line) });
  });
  return { entries, problems };
}

test('identity-allowlist.txt is well formed: one reason per anchored, grep-compatible pattern', () => {
  const { entries, problems } = parseAllowlist();
  assert.deepEqual(problems, [], `identity-allowlist.txt problems:\n  ${problems.join('\n  ')}`);
  assert.ok(entries.length > 0, 'the allowlist should list at least the permanent fixture entries');
  const seen = new Set();
  for (const e of entries) {
    assert.ok(!seen.has(e.pattern), `duplicate allowlist pattern ${e.pattern}`);
    seen.add(e.pattern);
  }
});

test('create-tess/template and create-tess/src carry no maintainer identity outside the allowlist', () => {
  const { entries } = parseAllowlist();
  const hits = identityHits();
  // Sanity: the scan really reads the bundle (a broken walk would pass vacuously).
  const scannedTemplate = walk(join(REPO_ROOT, 'create-tess', 'template'), []).length;
  assert.ok(scannedTemplate > 100, `expected to scan the bundled template, found only ${scannedTemplate} files`);
  // A '#' in a path could collide with the allowlist's comment lines under grep -f.
  assert.deepEqual(hits.filter((h) => h.includes('#')), [], 'no scanned path may contain "#"');

  const unexplained = hits.filter((h) => !entries.some((e) => e.regex.test(h)));
  assert.deepEqual(
    unexplained,
    [],
    'maintainer identity (one of the five release-grep strings) found in shipped files.\n' +
      'De-identify these files (then regenerate the template with `npm run build-template`), or add an\n' +
      'anchored entry with a one-line reason to create-tess/test/identity-allowlist.txt:\n  ' +
      unexplained.join('\n  '),
  );
});

test('permanent allowlist entries are not stale', () => {
  const { entries } = parseAllowlist();
  const hits = identityHits();
  const stale = entries.filter((e) => !e.pending && !hits.some((h) => e.regex.test(h))).map((e) => `line ${e.lineNo}: ${e.pattern}`);
  assert.deepEqual(stale, [], `these allowlist entries no longer match any hit; delete them:\n  ${stale.join('\n  ')}`);
});

test('PENDING allowlist entries cannot survive the 0.2.0 version bump', () => {
  const { entries } = parseAllowlist();
  const version = JSON.parse(readFileSync(join(PKG_DIR, 'package.json'), 'utf8')).version;
  const pending = entries.filter((e) => e.pending).map((e) => `line ${e.lineNo}: ${e.pattern}`);
  if (version.startsWith('0.1.')) return; // pre-release train: PENDING entries are allowed
  assert.deepEqual(
    pending,
    [],
    `create-tess is ${version}; delete every PENDING entry from identity-allowlist.txt (and fix any hit it still hides):\n  ${pending.join('\n  ')}`,
  );
});
