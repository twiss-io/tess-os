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
//   (f) create-tess/ is NOT scaffolded into the target, and the template's
//       OWN .git (history) never leaks in — but a FRESH, history-less .git
//       now exists (gate activation, see (g))
//   (g) gate activation: `git init` ran (branch `main`, zero commits — never
//       the template's history) and `tessctl gate install-hooks` installed
//       live pre-commit/pre-push hooks + the CI workflow
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

    // (f) create-tess/ must NOT be scaffolded into the target.
    assert.ok(
      !existsSync(join(target, 'create-tess')),
      'create-tess/ leaked into the scaffolded instance',
    );

    // (g) gate activation: git init ran (fresh repo, zero commits — proves
    // this is NOT the template's own .git leaking in) and
    // `tessctl gate install-hooks` installed live hooks + the CI workflow.
    assert.ok(
      existsSync(join(target, '.git')),
      '.git must exist — the wizard must `git init` a fresh repo (gate activation)',
    );
    const branch = spawnSync('git', ['branch', '--show-current'], {
      cwd: target,
      encoding: 'utf8',
    });
    assert.equal(branch.stdout.trim(), 'main', 'git init must set the initial branch to main');
    const log = spawnSync('git', ['log', '--oneline'], { cwd: target, encoding: 'utf8' });
    assert.notEqual(
      log.status,
      0,
      'the fresh repo must have ZERO commits — the template\'s own history must never leak in',
    );

    for (const hook of ['pre-commit', 'pre-push']) {
      const hookPath = join(target, '.git', 'hooks', hook);
      assert.ok(existsSync(hookPath), `${hook} hook must be installed by gate activation`);
      const body = readFileSync(hookPath, 'utf8');
      assert.match(body, /tess-gate-guard v1/, `${hook} hook must carry the gate-guard marker`);
    }
    assert.ok(
      existsSync(join(target, '.github', 'workflows', 'tess-gate.yml')),
      'the gate CI workflow must be installed by install-hooks',
    );

    // A successful local scaffold must not be presented as production-ready.
    // It must disclose the expected fail-closed result and hand custody back
    // to Xavier without suggesting a bypass or self-bootstrap path.
    assert.match(
      run.stdout,
      /Local scaffold ready; protected production work remains blocked/,
      'success path must distinguish local setup from production protection',
    );
    assert.match(
      run.stdout,
      /no covering APPROVE verdict\s+found/,
      'success path must disclose the expected fail-closed result',
    );
    assert.match(run.stdout, /escalate to Xavier/, 'must return custody to Xavier');
    for (const unsafeGuidance of ['git push --no-verify', 'onboard a real verifier', 'verdict keygen']) {
      assert.doesNotMatch(run.stdout, new RegExp(unsafeGuidance));
    }

    // B3 (gap-loop R2) — the produced instance must NOT inherit this repo's
    // OWN framework-internal CI (its pytest suite, its release-cut pipeline,
    // its npm-publish pipeline); only the ship-gate CI is user-relevant.
    for (const wf of ['ci.yml', 'release.yml', 'publish-npm.yml']) {
      assert.ok(
        !existsSync(join(target, '.github', 'workflows', wf)),
        `.github/workflows/${wf} must NOT be scaffolded into a produced instance`,
      );
    }

    // The gate must actually work post-activation, not just look installed.
    const gatePreCommit = tessctl(target, 'gate', 'pre-commit');
    assert.equal(
      gatePreCommit.status,
      0,
      `tessctl gate pre-commit must pass on a clean repo\n${gatePreCommit.stdout}\n${gatePreCommit.stderr}`,
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

// ── Gate activation — opt-out flags + fallback next-steps ───────────────────
test('gate activation: --no-git-init/--no-gate-hooks skip activation and print manual next-steps', () => {
  const target = mkdtempSync(join(tmpdir(), 'create-tess-noflags-'));
  tempDirs.push(target);
  const combo = COMBOS[0];
  const run = spawnSync(
    process.execPath,
    [
      ENTRY,
      '--yes',
      `--operator=${combo.operator}`,
      `--vibe=${combo.vibe}`,
      `--path=${combo.path}`,
      `--pathway=${combo.pathway}`,
      `--conductor=${combo.conductor}`,
      `--template-source=${TEMPLATE_SOURCE}`,
      `--target=${target}`,
      '--no-git-init',
      '--no-gate-hooks',
    ],
    { cwd: PKG_DIR, encoding: 'utf8' },
  );
  assert.equal(run.status, 0, `wizard exited non-zero\nSTDOUT:\n${run.stdout}\nSTDERR:\n${run.stderr}`);
  assert.ok(!existsSync(join(target, '.git')), '--no-git-init must skip git init');
  assert.match(
    run.stdout,
    /ship-gate is NOT fully enforcing yet/,
    'must surface the fallback warning when activation is skipped',
  );
  assert.match(run.stdout, /1\. cd /, 'fallback must include a numbered cd step');
  assert.match(run.stdout, /git init/, 'fallback must include the git init next-step');
  assert.match(
    run.stdout,
    /tessctl gate install-hooks/,
    'fallback must include the install-hooks next-step',
  );
  // Still a good instance — gate activation being skipped must not fail the run.
  const doctor = tessctl(target, 'doctor');
  assert.equal(doctor.status, 0, `doctor must still pass\n${doctor.stderr}`);
});

// ── Gate activation — target nested in an existing git repo is left alone ───
test('gate activation: an already-git target is detected and left untouched (hooks still installed)', () => {
  const target = mkdtempSync(join(tmpdir(), 'create-tess-alreadygit-'));
  tempDirs.push(target);
  const initExisting = spawnSync('git', ['init', '--quiet', '-b', 'trunk'], {
    cwd: target,
    encoding: 'utf8',
  });
  assert.equal(initExisting.status, 0, `pre-seeding an existing repo failed\n${initExisting.stderr}`);

  const combo = COMBOS[0];
  const run = spawnSync(
    process.execPath,
    [
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
    ],
    { cwd: PKG_DIR, encoding: 'utf8' },
  );
  assert.equal(run.status, 0, `wizard exited non-zero\nSTDOUT:\n${run.stdout}\nSTDERR:\n${run.stderr}`);

  // The pre-existing branch name must survive — the wizard must NOT re-init.
  const branch = spawnSync('git', ['branch', '--show-current'], { cwd: target, encoding: 'utf8' });
  assert.equal(
    branch.stdout.trim(),
    'trunk',
    'an existing git repo must be left untouched (branch name preserved)',
  );
  assert.match(
    run.stdout,
    /git repository — already present/,
    'must report that the existing repo was detected and left alone',
  );
  // Hooks still get installed into the existing .git/hooks.
  assert.ok(
    existsSync(join(target, '.git', 'hooks', 'pre-commit')),
    'hooks must still be installed into a pre-existing repo',
  );
});
