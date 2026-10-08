// Opt-in integration check: fresh registry resolution in an isolated fixture,
// never execution of the shell generator or any E2E/kill-port script.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';

test('fresh generated dependency graph audits clean and builds Tailwind CSS', {
  skip: process.env.TESS_TEST_GENERATED_DEPS !== '1', timeout: 180000,
}, async () => {
  const script = readFileSync(new URL('../../starter/scripts/scaffold-default.sh', import.meta.url), 'utf8');
  const dir = mkdtempSync(join(tmpdir(), 'tess-generated-deps-'));
  // Retain on request so the independent reviewer can read primary evidence.
  try {
    const files = [
      'package.json', 'postcss.config.mjs', 'src/app/globals.css',
      'src/app/page.tsx', 'src/app/layout.tsx', 'src/app/api/v1/health/route.ts',
      'vitest.config.ts', 'tests/unit/example.test.ts', 'tsconfig.json', 'next.config.ts',
    ];
    const entries = [...script.matchAll(/cat > "\$PROJECT_PATH\/([^"\n]+)" << '?([A-Z_]+)'?\n([\s\S]*?)\n\2\n/g)];
    for (const path of files) {
      const entry = entries.find((m) => m[1] === path);
      assert.ok(entry, `missing generator heredoc for ${path}`);
      const dest = join(dir, path);
      mkdirSync(dirname(dest), { recursive: true });
      writeFileSync(dest, entry[3].replaceAll('$PROJECT_NAME', 'generated-dependency-check') + '\n');
    }
    console.log(`Generated fixture: ${dir} (literal source heredocs; generator never executed)`);
    function run(args, json = false) {
      const p = spawnSync('pnpm', args, { cwd: dir, encoding: 'utf8', timeout: 120000,
        env: { ...process.env, CI: '1', NEXT_TELEMETRY_DISABLED: '1' }, maxBuffer: 16 * 1024 * 1024 });
      writeFileSync(join(dir, `${args.join('_').replaceAll('/', '_')}.log`), p.stdout + p.stderr);
      assert.equal(p.status, 0, `${args.join(' ')}\n${p.stdout}\n${p.stderr}`);
      return json ? JSON.parse(p.stdout) : p.stdout;
    }
    run(['install', '--ignore-scripts']);
    run(['install', '--frozen-lockfile', '--ignore-scripts']);
    const audit = run(['audit', '--json'], true);
    assert.deepEqual(audit.advisories, {});
    const graph = run(['list', '--depth', 'Infinity', '--json'], true);
    let postcssCount = 0;
    function walk(node) {
      if (!node || typeof node !== 'object') return;
      for (const kind of ['dependencies', 'devDependencies', 'optionalDependencies']) {
        for (const [name, dep] of Object.entries(node[kind] || {})) {
          assert.notEqual(name, 'braces', 'unpatched braces chain must not return');
          assert.notEqual(name, 'postcss-selector-parser', 'legacy selector-parser chain must not return');
          if (name === 'postcss') {
            postcssCount++;
            assert.match(dep.version, /^8\.5\.(?:2[89]|[3-9]\d|\d{3,})$/);
          }
          walk(dep);
        }
      }
    }
    graph.forEach(walk);
    assert.ok(postcssCount >= 2, 'inspect both direct and nested PostCSS');
    const require = createRequire(join(dir, 'package.json'));
    const css = await require('postcss')([require('@tailwindcss/postcss')()]).process(
      readFileSync(join(dir, 'src/app/globals.css'), 'utf8'),
      { from: join(dir, 'src/app/globals.css') },
    );
    writeFileSync(join(dir, 'compiled.css'), css.css);
    for (const selector of ['.flex', '.min-h-screen', '.p-8', '.text-4xl', '.text-gray-600']) {
      assert.ok(css.css.includes(selector), `missing generated utility ${selector}`);
    }
    run(['exec', 'vitest', 'run', 'tests/unit', '--coverage']);
    run(['exec', 'next', 'build']);
  } finally {
    if (process.env.TESS_KEEP_GENERATED_FIXTURE !== '1') rmSync(dir, { recursive: true, force: true });
  }
});
