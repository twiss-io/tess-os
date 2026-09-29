// packed-tarball-install.test.js — v0.2.1: install from the REAL `npm pack`
// tarball on a Python with no PyYAML, and check what a stock Mac user gets.
//
// Before v0.2.1 three things broke here: npm dropped every .gitignore from the
// tarball (so .env and operator/profile.json were not ignored), tessctl exited
// with "requires pyyaml" on /usr/bin/python3, and nobody ran onboarding. This
// test packs the package, installs from the extracted tarball with --mode
// agency, and asserts the .gitignore files are back, private paths are
// ignored, the brain has a real first commit, and doctor/verify pass.
//
// Python: by default a shim runs the local python3 with -S -E -s (no
// site-packages, so no PyYAML). TESS_TEST_PYTHON=/usr/bin/python3 (the macOS
// CI leg) uses that interpreter as-is. `npm pack --ignore-scripts` packs the
// committed template/ (template-drift-guard.test.js keeps it equal to a fresh
// build), so this test never rewrites the working tree.
import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync, chmodSync, existsSync, symlinkSync, readdirSync } from 'node:fs';
import { join, resolve, dirname, delimiter } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';

const PKG_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const temps = [];
after(() => temps.forEach((d) => rmSync(d, { recursive: true, force: true })));
const mkTemp = (p) => { const d = mkdtempSync(join(tmpdir(), p)); temps.push(d); return d; };
const sh = (cmd, args, opts = {}) => spawnSync(cmd, args, { encoding: 'utf8', maxBuffer: 1 << 28, ...opts });

function pythonShimDir() {
  const dir = mkTemp('ct-python-');
  const real = process.env.TESS_TEST_PYTHON;
  const script = real
    ? `#!/bin/sh\nexec "${real}" "$@"\n`
    : `#!/bin/sh\nexec "${sh('sh', ['-c', 'command -v python3']).stdout.trim()}" -S -E -s "$@"\n`;
  writeFileSync(join(dir, 'python3'), script);
  chmodSync(join(dir, 'python3'), 0o755);
  return dir;
}

test('v0.2.1: npm-packed tarball installs on a Python without PyYAML, restores .gitignore, commits the brain', { timeout: 900000 }, () => {
  const packDest = mkTemp('ct-pack-');
  const pack = sh('npm', ['pack', '--ignore-scripts', '--pack-destination', packDest], { cwd: PKG_DIR });
  assert.equal(pack.status, 0, pack.stderr);
  const tgz = readdirSync(packDest).find((f) => f.endsWith('.tgz'));
  const listing = sh('tar', ['-tzf', join(packDest, tgz)]).stdout.split('\n');
  assert.ok(listing.includes('package/template/gitignore'), 'tarball must carry template/gitignore');

  const unpacked = mkTemp('ct-unpacked-');
  assert.equal(sh('tar', ['-xzf', join(packDest, tgz), '-C', unpacked]).status, 0);
  const pkg = join(unpacked, 'package');
  symlinkSync(join(PKG_DIR, 'node_modules'), join(pkg, 'node_modules'), 'dir');

  const shim = pythonShimDir();
  const noYaml = sh(join(shim, 'python3'), ['-c', 'import yaml']);
  assert.notEqual(noYaml.status, 0, 'the test Python must NOT have PyYAML, or this proves nothing');

  const home = mkTemp('ct-home-');
  const target = join(mkTemp('ct-target-'), 'my-tess');
  const env = { ...process.env, HOME: home, PATH: shim + delimiter + process.env.PATH, GIT_CONFIG_NOSYSTEM: '1' };
  for (const k of ['GIT_AUTHOR_NAME', 'GIT_AUTHOR_EMAIL', 'GIT_COMMITTER_NAME', 'GIT_COMMITTER_EMAIL']) delete env[k];
  const run = sh('node', [join(pkg, 'bin', 'create-tess.mjs'), target, '--yes', '--mode', 'agency',
    '--operator', 'Probe', '--conductor', 'Tess', '--vibe', 'command'], { env, cwd: home });
  assert.equal(run.status, 0, `STDOUT:\n${run.stdout.slice(-4000)}\nSTDERR:\n${run.stderr.slice(-4000)}`);

  for (const rel of ['.gitignore', 'starter/.gitignore', 'gui/.gitignore', 'spec-engine/.gitignore']) {
    assert.ok(existsSync(join(target, rel)), `${rel} must be restored`);
    assert.ok(!existsSync(join(target, rel.replace('.gitignore', 'gitignore'))), `no stray ${rel} twin`);
  }
  const git = (...a) => sh('git', ['-C', target, ...a], { env });
  for (const p of ['.env', '.env.local', 'operator/profile.json', 'clients/acme/notes.md', 'brain/agency/.private/x.md']) {
    assert.equal(git('check-ignore', '-q', p).status, 0, `${p} must be gitignored`);
  }
  assert.equal(git('log', '--format=%s').stdout.trim(), 'tess: seed instance + second brain (onboarding)');
  const tracked = new Set(git('ls-files').stdout.split('\n'));
  assert.ok(tracked.has('brain/brain.json') && tracked.has('.gitignore'), 'brain and .gitignore are committed');
  assert.ok(!tracked.has('operator/profile.json'), 'operator/profile.json must never be committed');
  assert.equal(git('status', '--porcelain').stdout, '', 'nothing left uncommitted');
  assert.match(run.stdout, /Checked every Tess OS file: all in place \(tessctl doctor OK\)/);
  assert.match(run.stdout, /Checked the install matches the release \(tessctl verify OK\)/);
  const folder = target.split(/[\\/]/).pop();
  assert.ok(
    run.stdout.includes('What to do next:\n  In this terminal, type these two lines, pressing Return after each:\n      cd ') &&
      run.stdout.includes(`\n      claude            (or: codex, if you use Codex)\n`) &&
      run.stdout.includes(`(Or open the folder "${folder}" in Claude Code or Codex and say hi.)`),
    'the final screen must name the folder and the one next step',
  );
});
