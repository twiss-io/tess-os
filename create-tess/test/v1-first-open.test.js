// v1-first-open.test.js — v1.0.0: the final screen tells a Claude Code and a
// Codex user the one question their app asks the first time (trust the
// folder; in Codex also approve Tess's hooks in /hooks), and the wizard hands
// the install the bundled release proof only for the bundled template.
import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync, writeFileSync, readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

import { printFinalScreen, FIRST_OPEN_CLAUDE, FIRST_OPEN_CODEX } from '../src/brain.js';
import { installReleaseProof, INSTALLED_RELEASE_PROOF } from '../src/release-proof.js';

const temps = [];
after(() => temps.forEach((d) => rmSync(d, { recursive: true, force: true })));
const mkTemp = () => { const d = mkdtempSync(join(tmpdir(), 'ct-v1-')); temps.push(d); return d; };

function capture(fn) {
  const orig = process.stdout.write.bind(process.stdout);
  let out = '';
  process.stdout.write = (s) => { out += s; return true; };
  try { fn(); } finally { process.stdout.write = orig; }
  return out;
}

test('final screen: one plain line each for Claude Code and Codex, after the next step', () => {
  const out = capture(() => printFinalScreen('/tmp/my-os', {
    mode: 'personal', brain: { status: 'done', commit: 'abc1234' }, checks: { doctor: true, verify: true },
  }));
  assert.equal(FIRST_OPEN_CODEX, "  In Codex: trust this folder and approve Tess's hooks when asked (/hooks).");
  assert.match(FIRST_OPEN_CLAUDE, /In Claude Code: .*trust this folder/);
  const next = out.indexOf('What to do next:');
  assert.ok(next >= 0, out);
  assert.ok(out.indexOf(FIRST_OPEN_CLAUDE + '\n') > next, out);
  assert.ok(out.indexOf(FIRST_OPEN_CODEX + '\n') > out.indexOf(FIRST_OPEN_CLAUDE), out);
});

test('release proof: written for the bundled template, never for another source', () => {
  const src = join(mkTemp(), 'release-proof.json');
  writeFileSync(src, '{"format":"tess-release-proof/1"}\n');
  const a = mkTemp();
  assert.equal(installReleaseProof(a, { bundled: false, source: src }), false);
  assert.equal(existsSync(join(a, INSTALLED_RELEASE_PROOF)), false);
  const b = mkTemp();
  assert.equal(installReleaseProof(b, { bundled: true, source: join(b, 'missing.json') }), false);
  assert.equal(installReleaseProof(b, { bundled: true, source: src }), true);
  assert.equal(readFileSync(join(b, INSTALLED_RELEASE_PROOF), 'utf8'), readFileSync(src, 'utf8'));
});
