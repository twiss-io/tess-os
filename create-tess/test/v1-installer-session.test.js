// v1-installer-session.test.js — v1.0 integration pass 4.
//
// Since round 3, `tessctl lock --regen` refuses inside a Claude Code or Codex
// session (CLAUDECODE, CLAUDE_CODE_ENTRYPOINT, CODEX_THREAD_ID, CODEX_SANDBOX,
// CODEX_SANDBOX_NETWORK_DISABLED), even with --yes. The wizard's own setup
// re-pins the one policy file it resets with `lock --regen --yes --only`, so
// `npm create tess` started inside an assistant session failed and rolled the
// new folder back. The installer's own setup step now runs without the
// markers; the operator confirmation steps of tessctl are unchanged.
import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import './anchor-cleanup.js';

const TEST_DIR = dirname(fileURLToPath(import.meta.url));
const PKG_DIR = resolve(TEST_DIR, '..');
const ENTRY = join(PKG_DIR, 'bin', 'create-tess.mjs');
const TEMPLATE_SOURCE = process.env.TESS_TEMPLATE_SOURCE || resolve(PKG_DIR, '..');
const MARKERS = {
  CLAUDECODE: '1', CLAUDE_CODE_ENTRYPOINT: 'cli', CODEX_THREAD_ID: 'thread-1',
  CODEX_SANDBOX: 'seatbelt', CODEX_SANDBOX_NETWORK_DISABLED: '1',
};
const dirs = [];
after(() => { for (const d of dirs) rmSync(d, { recursive: true, force: true }); });

test('npm create tess works when started inside an assistant session', () => {
  const base = mkdtempSync(join(tmpdir(), 'ct-session-'));
  dirs.push(base);
  const target = join(base, 'inst');
  const r = spawnSync(process.execPath, [ENTRY, '--yes', '--operator=Alex', '--vibe=command',
    '--path=founders', '--pathway=operator', `--template-source=${TEMPLATE_SOURCE}`,
    `--target=${target}`], { cwd: PKG_DIR, encoding: 'utf8', env: { ...process.env, ...MARKERS } });
  assert.equal(r.status, 0, `wizard failed inside a session\nSTDOUT:\n${r.stdout}\nSTDERR:\n${r.stderr}`);
  // An operator confirmation step is still refused in the same session.
  const regen = spawnSync('python3', [join(target, '.tess', 'bin', 'tessctl'), 'lock', '--regen',
    '--yes', '--only', '.tess/core/policy/policy.yaml'],
  { cwd: target, encoding: 'utf8', env: { ...process.env, ...MARKERS, TESS_ROOT: target } });
  assert.notEqual(regen.status, 0);
  assert.match(regen.stdout + regen.stderr, /REFUSED/);
});
