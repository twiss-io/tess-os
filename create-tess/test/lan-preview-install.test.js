// Exercise the actual packed default template, with synthetic public files only.
// No signing fixtures, credential ceremony, network package fetch or publishing.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, existsSync,
  rmSync, realpathSync, readdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { promote } from '../src/scaffold.js';

const pkg = resolve(dirname(fileURLToPath(import.meta.url)), '..');

test('source and bundled preview instructions have exact generated-output cache hashes', () => {
  for (const root of [resolve(pkg, '..'), join(pkg, 'template')]) {
    const records = readFileSync(join(root, '.tess', 'tess.lock'), 'utf8').split('\nrender_outputs:\n')[1];
    assert.ok(records, 'generated render-output cache must exist');
    for (const name of ['CLAUDE.md', 'AGENTS.md']) {
      const record = records.split(`  ${name}:\n`)[1]?.split(/\n  (?=\S)/)[0];
      const recorded = record?.match(/rendered_sha: sha256:([a-f0-9]{64})/)?.[1];
      const actual = createHash('sha256').update(readFileSync(join(root, name))).digest('hex');
      assert.equal(recorded, actual, `${root}: ${name} cache must match shipped bytes; stale metadata breaks forced re-scaffold`);
    }
  }
});

test('packed installer ships inert portable launcher, renders rules, and serves only selections', () => {
  const scratch = realpathSync(mkdtempSync(join(tmpdir(), 'tess-lan-preview-install-')));
  let launcher;
  try {
    const output = execFileSync('npm', ['pack', '--json', '--ignore-scripts', '--pack-destination', scratch],
      { cwd: pkg, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });
    const [packed] = JSON.parse(output);
    const paths = packed.files.map(f => f.path);
    for (const file of ['tesspreview.py', 'content.py', 'lifecycle.py', 'server.py', 'readiness.py']) {
      assert.ok(paths.includes(`template/scripts/preview/${file}`), file);
    }
    assert.ok(paths.includes('template/docs/LAN_PREVIEWS.md'));
    assert.ok(!paths.includes('template/.github/workflows/lan-preview.yml'),
      'framework platform CI must not be activated in adopter projects');
    execFileSync('tar', ['-xzf', join(scratch, packed.filename), '-C', scratch]);
    const installed = join(scratch, 'instance');
    promote(join(scratch, 'package', 'template'), installed);
    launcher = join(installed, 'scripts', 'preview', 'tesspreview.py');
    const call = (...args) => spawnSync('python3', [launcher, ...args], { encoding: 'utf8' });
    assert.equal(call('--help').status, 0);
    assert.equal(existsSync(join(installed, '.tess', 'state', 'previews')), false,
      'install/help must not create listener lifecycle state');
    for (const target of ['claude-code', 'codex', 'generic', 'gemini']) {
      execFileSync('python3', [join(installed, '.tess', 'bin', 'tessctl'), 'render', '--target', target],
        { cwd: installed, stdio: 'pipe', env: { ...process.env, TESS_ROOT: installed } });
    }
    for (const file of ['CLAUDE.md', 'AGENTS.md']) {
      const text = readFileSync(join(installed, file), 'utf8');
      assert.match(text, /scripts\/preview\/tesspreview\.py/);
      assert.match(text, /Other computers on the same LAN/);
      assert.match(text, /localhost-only/);
      assert.match(text, /explicit restart/);
    }
    assert.match(readFileSync(join(installed, 'GEMINI.md'), 'utf8'), /@\.\/AGENTS\.md/);
    assert.equal(existsSync(join(installed, '.tess', 'state', 'previews')), false,
      'render must not start any preview');
    const publicDir = join(scratch, 'public');
    mkdirSync(join(publicDir, 'assets'), { recursive: true });
    writeFileSync(join(publicDir, 'index.html'), '<base href="/dev/packed-demo/"><script src="assets/app.js"></script>PUBLIC');
    writeFileSync(join(publicDir, 'assets', 'app.js'), 'console.log("PUBLIC")');
    writeFileSync(join(publicDir, 'private.html'), 'NOT-SELECTED');
    const started = call('--json', 'start', 'packed-demo', '--public-dir', publicDir,
      '--file', 'index.html', '--file', 'assets/app.js', '--localhost-only', '--spa');
    assert.equal(started.status, 0, started.stderr);
    const handoff = JSON.parse(started.stdout);
    assert.match(handoff.localhost_url, /^http:\/\/127\.0\.0\.1:\d+\/dev\/packed-demo$/);
    assert.equal(handoff.lan_url, null);
    assert.equal(handoff.bind, '127.0.0.1');
    assert.equal(handoff.second_device_tested, false);
    const checked = call('--json', 'verify', 'packed-demo');
    assert.equal(checked.status, 0, checked.stderr);
    assert.deepEqual(JSON.parse(checked.stdout).host_verified_addresses, ['127.0.0.1']);
    assert.ok(readdirSync(join(installed, '.tess', 'state', 'previews')).includes('packed-demo.log'));
  } finally {
    if (launcher) spawnSync('python3', [launcher, 'stop', 'packed-demo'], { stdio: 'ignore' });
    rmSync(scratch, { recursive: true, force: true });
  }
});
