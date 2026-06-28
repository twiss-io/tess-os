// wizard.test.js — end-to-end coverage for the create-tess wizard.
//
// Runs the wizard NON-INTERACTIVELY (--yes + flags) for three distinct
// vibe×path×pathway×conductor combos against a local --template-source, into
// throwaway temp dirs, and asserts the produced Tess OS instance for each:
//   (a) correct starter squad + universal base installed, the rest staged
//   (b) rendered CLAUDE.md addresses the operator by name
//   (c) the conductor name applied (or the 'Tess' default)
//   (d) personality.md carries the chosen pathway's persona
//   (e) `tessctl doctor` AND `tessctl verify` exit 0 in the produced instance
//   (f) create-tess/ and .git are NOT scaffolded into the target
//
// Run: npm test   (or `node --test`)
import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import {
  mkdtempSync,
  rmSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  writeFileSync,
  copyFileSync,
  existsSync,
} from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';

const TEST_DIR = dirname(fileURLToPath(import.meta.url));
const PKG_DIR = resolve(TEST_DIR, '..'); // create-tess/
const ENTRY = join(PKG_DIR, 'bin', 'create-tess.mjs');

// Template source: the Tess OS repo that contains this package (create-tess/ lives
// one level inside it). Overridable so the suite is portable / CI-friendly.
const TEMPLATE_SOURCE =
  process.env.TESS_TEMPLATE_SOURCE || resolve(PKG_DIR, '..');

// System of record: derive expected install sets straight from the template's
// roster-paths.json rather than hardcoding — same source the wizard reads.
const ROSTER = JSON.parse(
  readFileSync(
    join(TEMPLATE_SOURCE, '.tess', 'core', 'roster-paths.json'),
    'utf8',
  ),
);

// Pathway key → persona label rendered into personality.md
// (mirrors src/content/pathways.js PATHWAY_LABEL).
const PATHWAY_LABEL = {
  'chief-of-staff': 'Chief of Staff',
  'co-founder': 'Co-founder',
  strategist: 'Strategist',
  guide: 'Guide',
  operator: 'Operator',
};

const COMBOS = [
  {
    title: 'rpg + builders + co-founder — operator Pixel, conductor Atlas',
    operator: 'Pixel',
    vibe: 'rpg',
    path: 'builders',
    pathway: 'co-founder',
    conductor: 'Atlas',
    expectConductor: 'Atlas',
  },
  {
    title: 'command + founders + operator — operator Atlas, default conductor',
    operator: 'Atlas',
    vibe: 'command',
    path: 'founders',
    pathway: 'operator',
    conductor: null, // exercises the 'Tess' default (rename skipped)
    expectConductor: 'Tess',
  },
  {
    title: 'studio + operators + guide — operator Margo, conductor Sage',
    operator: 'Margo',
    vibe: 'studio',
    path: 'operators',
    pathway: 'guide',
    conductor: 'Sage',
    expectConductor: 'Sage',
  },
];

const tempDirs = [];

after(() => {
  for (const d of tempDirs) rmSync(d, { recursive: true, force: true });
});

function expectedInstallSet(pathName) {
  const def = ROSTER.paths[pathName];
  return [
    ...ROSTER.universal_base,
    ...def.squad,
    ...(def.orchestrators || []),
  ].sort();
}

function runWizard(combo, target) {
  const args = [
    ENTRY,
    '--yes',
    `--operator=${combo.operator}`,
    `--vibe=${combo.vibe}`,
    `--path=${combo.path}`,
    `--pathway=${combo.pathway}`,
    `--template-source=${TEMPLATE_SOURCE}`,
    `--target=${target}`,
  ];
  if (combo.conductor) args.push(`--conductor=${combo.conductor}`);
  return spawnSync(process.execPath, args, {
    cwd: PKG_DIR,
    encoding: 'utf8',
  });
}

// Shell the produced keystone the same way keystone.js does (python3 + TESS_ROOT).
function tessctl(target, ...sub) {
  return spawnSync('python3', [join(target, '.tess', 'bin', 'tessctl'), ...sub], {
    cwd: target,
    env: { ...process.env, TESS_ROOT: target },
    encoding: 'utf8',
  });
}

for (const combo of COMBOS) {
  test(combo.title, { timeout: 180000 }, () => {
    const target = mkdtempSync(join(tmpdir(), 'create-tess-test-'));
    tempDirs.push(target);

    const run = runWizard(combo, target);
    assert.equal(
      run.status,
      0,
      `wizard exited non-zero\nSTDOUT:\n${run.stdout}\nSTDERR:\n${run.stderr}`,
    );

    // (a) starter squad + universal base installed; everything else staged.
    const agentsDir = join(target, '.claude', 'agents');
    const installed = readdirSync(agentsDir)
      .filter((f) => f.endsWith('.md'))
      .map((f) => f.slice(0, -3))
      .sort();
    assert.deepEqual(
      installed,
      expectedInstallSet(combo.path),
      `.claude/agents/ does not match the ${combo.path} install set`,
    );
    const rl = tessctl(target, 'roster', 'list');
    assert.equal(rl.status, 0, `roster list failed:\n${rl.stderr}`);
    const staged = rl.stdout.match(/staged \/ benched \((\d+)\)/);
    assert.ok(
      staged && Number(staged[1]) > 0,
      `expected the rest of the roster to be staged; got:\n${rl.stdout}`,
    );

    // (b) rendered CLAUDE.md addresses the operator by name.
    const claudeMd = readFileSync(join(target, 'CLAUDE.md'), 'utf8');
    assert.match(
      claudeMd,
      new RegExp(`Operator this instance serves:\\*\\*\\s+${combo.operator}\\b`),
      'CLAUDE.md does not address the operator by name',
    );

    // (c) conductor name applied (or the 'Tess' default).
    assert.match(
      claudeMd,
      new RegExp(`^#\\s+${combo.expectConductor} — AI Overseer & Conductor`, 'm'),
      'CLAUDE.md title does not carry the conductor name',
    );
    const profile = JSON.parse(
      readFileSync(join(target, 'operator', 'profile.json'), 'utf8'),
    );
    assert.equal(profile.operator_name, combo.operator);
    assert.equal(profile.assistant_name, combo.expectConductor);
    assert.equal(profile.vibe, combo.vibe);
    assert.equal(profile.starter_path, combo.path);
    assert.equal(profile.pathway, combo.pathway);

    // (d) personality.md carries the chosen pathway's persona.
    const personality = readFileSync(
      join(target, 'conductor', 'personality.md'),
      'utf8',
    );
    assert.match(
      personality,
      new RegExp(`Active Pathway — ${PATHWAY_LABEL[combo.pathway]}\\b`),
      'personality.md does not carry the chosen pathway persona',
    );

    // (e) doctor AND verify exit 0 in the produced instance.
    const doctor = tessctl(target, 'doctor');
    assert.equal(
      doctor.status,
      0,
      `tessctl doctor non-zero\nSTDOUT:\n${doctor.stdout}\nSTDERR:\n${doctor.stderr}`,
    );
    const verify = tessctl(target, 'verify');
    assert.equal(
      verify.status,
      0,
      `tessctl verify non-zero\nSTDOUT:\n${verify.stdout}\nSTDERR:\n${verify.stderr}`,
    );

    // (f) create-tess/ and .git must NOT be scaffolded into the target.
    assert.ok(
      !existsSync(join(target, 'create-tess')),
      'create-tess/ leaked into the scaffolded instance',
    );
    assert.ok(
      !existsSync(join(target, '.git')),
      '.git leaked into the scaffolded instance',
    );
  });
}

// ── HIGH-2 — argument-injection guards ──────────────────────────────────────
test('arg-injection: --operator=--help and --template-source=-x are rejected', () => {
  // (a) a flag-shaped operator name is rejected (leading hyphen forbidden), and
  //     the target is never created.
  const t1 = join(tmpdir(), `create-tess-inj-op-${Date.now()}`);
  tempDirs.push(t1);
  const r1 = spawnSync(
    process.execPath,
    [
      ENTRY,
      '--yes',
      '--operator=--help',
      `--template-source=${TEMPLATE_SOURCE}`,
      `--target=${t1}`,
    ],
    { cwd: PKG_DIR, encoding: 'utf8' },
  );
  assert.notEqual(r1.status, 0, 'wizard must reject --operator=--help');
  assert.ok(!existsSync(t1), 'no target may be created on a rejected operator name');

  // (b) a flag-shaped template source is rejected before any git invocation.
  const t2 = join(tmpdir(), `create-tess-inj-src-${Date.now()}`);
  tempDirs.push(t2);
  const r2 = spawnSync(
    process.execPath,
    [ENTRY, '--yes', '--operator=Alex', '--template-source=-x', `--target=${t2}`],
    { cwd: PKG_DIR, encoding: 'utf8' },
  );
  assert.notEqual(r2.status, 0, 'wizard must reject --template-source=-x');
  assert.match(r2.stderr, /template-source/i, 'error must name the bad template source');
  assert.ok(!existsSync(t2), 'no target may be created on a rejected template source');
});

// ── HIGH-1 — rollback on bake failure: no partial target, re-runnable ────────
test('rollback: a failed bake removes the partial target and leaves it re-runnable', { timeout: 180000 }, () => {
  // A minimal BROKEN template: the real roster map (so loadRoster + flag
  // resolution succeed and the wizard reaches the bake), but a tessctl that
  // exits non-zero on every verb (so the bake fails AFTER promote()).
  const broken = mkdtempSync(join(tmpdir(), 'create-tess-broken-'));
  tempDirs.push(broken);
  mkdirSync(join(broken, '.tess', 'core'), { recursive: true });
  mkdirSync(join(broken, '.tess', 'bin'), { recursive: true });
  copyFileSync(
    join(TEMPLATE_SOURCE, '.tess', 'core', 'roster-paths.json'),
    join(broken, '.tess', 'core', 'roster-paths.json'),
  );
  writeFileSync(
    join(broken, '.tess', 'bin', 'tessctl'),
    '#!/usr/bin/env python3\n' +
      'import sys\n' +
      'sys.stderr.write("broken tessctl: simulated bake failure\\n")\n' +
      'sys.exit(1)\n',
  );

  const target = mkdtempSync(join(tmpdir(), 'create-tess-rb-'));
  tempDirs.push(target);
  const bad = spawnSync(
    process.execPath,
    [
      ENTRY,
      '--yes',
      '--operator=Alex',
      '--vibe=rpg',
      '--path=founders',
      '--pathway=chief-of-staff',
      `--template-source=${broken}`,
      `--target=${target}`,
    ],
    { cwd: PKG_DIR, encoding: 'utf8' },
  );
  assert.notEqual(
    bad.status,
    0,
    `broken bake must exit non-zero\nSTDOUT:\n${bad.stdout}\nSTDERR:\n${bad.stderr}`,
  );
  assert.ok(
    !existsSync(target),
    'a failed bake must leave NO partial target (rolled back)',
  );

  // Re-runnable: the SAME path now scaffolds cleanly with the real template,
  // proving no poisoning profile.json / tess.lock survived to trip clobberReason.
  const good = spawnSync(
    process.execPath,
    [
      ENTRY,
      '--yes',
      '--operator=Alex',
      '--vibe=rpg',
      '--path=founders',
      '--pathway=chief-of-staff',
      `--template-source=${TEMPLATE_SOURCE}`,
      `--target=${target}`,
    ],
    { cwd: PKG_DIR, encoding: 'utf8' },
  );
  assert.equal(
    good.status,
    0,
    `re-run must succeed (dir left re-runnable)\nSTDOUT:\n${good.stdout}\nSTDERR:\n${good.stderr}`,
  );
  assert.ok(
    existsSync(join(target, 'operator', 'profile.json')),
    're-run must produce operator/profile.json',
  );
  const doctor = tessctl(target, 'doctor');
  assert.equal(doctor.status, 0, `re-run doctor must pass\n${doctor.stdout}\n${doctor.stderr}`);
});

// ── M2 — --force clean-replaces managed dirs (no stale files survive) ─────────
test('M2: --force clean-replaces managed dirs, no stale files survive', { timeout: 180000 }, () => {
  const target = mkdtempSync(join(tmpdir(), 'create-tess-force-'));
  tempDirs.push(target);
  const combo = COMBOS[0];
  const first = runWizard(combo, target);
  assert.equal(first.status, 0, `first scaffold failed\nSTDERR:\n${first.stderr}`);

  // Inject a stale managed file the template does NOT ship.
  const stale = join(target, '.claude', 'agents', 'zzz-stale-agent.md');
  writeFileSync(stale, '# stale agent left over from a prior version\n');
  assert.ok(existsSync(stale));

  // Re-scaffold with --force → managed dirs are clean-replaced, not merged.
  const args = [
    ENTRY,
    '--yes',
    `--operator=${combo.operator}`,
    `--vibe=${combo.vibe}`,
    `--path=${combo.path}`,
    `--pathway=${combo.pathway}`,
    `--conductor=${combo.conductor}`,
    `--template-source=${TEMPLATE_SOURCE}`,
    `--target=${target}`,
    '--force',
  ];
  const second = spawnSync(process.execPath, args, { cwd: PKG_DIR, encoding: 'utf8' });
  assert.equal(
    second.status,
    0,
    `forced re-scaffold failed\nSTDOUT:\n${second.stdout}\nSTDERR:\n${second.stderr}`,
  );
  assert.ok(
    !existsSync(stale),
    '--force must clear stale managed files (clean-replace, not merge)',
  );
  const doctor = tessctl(target, 'doctor');
  assert.equal(doctor.status, 0, `doctor after --force failed\n${doctor.stderr}`);
});
