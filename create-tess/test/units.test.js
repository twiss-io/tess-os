// units.test.js — fast, in-process unit coverage for the M3-remediation fixes
// that aren't observable through a non-interactive end-to-end run (taste copy in
// vibes/sigils, plus the arg-parser / name-validator guards).
//
// Run: npm test   (or `node --test`)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, existsSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { VIBES, VIBE_ORDER, VIBE_HONESTY } from '../src/content/vibes.js';
import { SIGILS, NEUTRAL } from '../src/content/sigils.js';
import { parseArgs } from '../src/args.js';
import { validateName } from '../src/validate.js';
import { isExcludedRel } from '../src/ignore.js';
import { fetchTemplate, promote } from '../src/scaffold.js';

// L3 / Lysandra #5 + #4 — the "language, not the power" honesty line is LIFTED
// off each vibe's cinematic `engaged` beat onto a DIMMED follow-line (rendered in
// journey.js S1 for every vibe), so it stays honest without crowding the moment.
// The shared copy must remain intact, no vibe may re-inline it, and Studio's
// engaged must reach parity with RPG/Command by carrying an in-world hook verb
// (an action) rather than a bare path label.
test('L3/#5/#4: honesty split to a dimmed follow-line; every vibe engaged is an in-world hook', () => {
  assert.ok(
    /language/i.test(VIBE_HONESTY) && /power/i.test(VIBE_HONESTY),
    'VIBE_HONESTY must keep the language-not-power honesty copy',
  );
  for (const k of VIBE_ORDER) {
    const eng = VIBES[k].engaged;
    assert.ok(eng && eng.trim().length > 0, `${k}.engaged must be a non-empty beat`);
    assert.ok(
      !eng.includes(VIBE_HONESTY),
      `${k}.engaged must NOT inline the honesty line (it rides as a dimmed follow-line)`,
    );
  }
  // #4 — every vibe's engaged is an action hook; Studio is no longer the bare label.
  assert.match(VIBES.rpg.engaged, /engaged/i);
  assert.match(VIBES.command.engaged, /engaged/i);
  assert.match(VIBES.studio.engaged, /unlocked/i);
  assert.notEqual(VIBES.studio.engaged.trim(), 'The Studio Path.');
});

// L1 — per-vibe bake-climax copy keyed to the five real keystone operations.
test('L1: every vibe defines bake-step copy for all five operations', () => {
  const OPS = ['roster', 'setOperator', 'rename', 'pathway', 'render'];
  for (const k of VIBE_ORDER) {
    const steps = VIBES[k].bakeSteps;
    assert.ok(steps, `${k} must define bakeSteps`);
    for (const op of OPS) {
      const v = steps[op];
      assert.ok(
        typeof v === 'string' || typeof v === 'function',
        `${k}.bakeSteps.${op} must be a string or function`,
      );
    }
  }
  // The climax must be per-vibe, not one shared label set: the three vibes'
  // roster labels differ.
  const rosters = VIBE_ORDER.map((k) => VIBES[k].bakeSteps.roster);
  assert.equal(new Set(rosters).size, rosters.length, 'roster labels must differ per vibe');
});

// L1 — a function-valued step resolves the conductor/operator name into the copy
// (proves the climax is genuinely personalised, e.g. the Command "Designating
// command intelligence as <name>" beat).
test('L1: function bake-step copy interpolates the chosen names', () => {
  const ctx = {
    operator: 'Alex',
    conductor: 'Atlas',
    operatorTerm: VIBES.command.operatorTerm,
    squadNoun: VIBES.command.squadNoun,
    pathwayLabel: 'Operator',
  };
  const renameLabel = VIBES.command.bakeSteps.rename(ctx);
  assert.match(renameLabel, /Atlas/, 'command rename step must name the conductor');
  const studioRename = VIBES.studio.bakeSteps.rename(ctx);
  assert.match(studioRename, /Atlas/, 'studio rename step must name the conductor');
});

// L2 — Studio gets a bespoke sigil (no longer byte-identical to the neutral mark).
test('L2: the Studio sigil is bespoke, not the neutral wordmark', () => {
  assert.notEqual(SIGILS.studio.fancy, NEUTRAL.fancy, 'studio.fancy must differ from neutral');
  assert.notEqual(SIGILS.studio.plain, NEUTRAL.plain, 'studio.plain must differ from neutral');
});

// LOW — a value flag must not swallow the next flag as its value.
test('LOW: a value flag rejects a following flag as its value', () => {
  assert.throws(
    () => parseArgs(['--operator', '--vibe=studio']),
    /requires a value/,
    'a following --flag must not be eaten as the operator value',
  );
  // A single-dash value (a negative Telegram channel id) is still accepted.
  assert.equal(parseArgs(['--telegram', '-1001234']).telegram, '-1001234');
  // The '=' form is unaffected.
  assert.equal(parseArgs(['--operator=Alex']).operator, 'Alex');
});

// HIGH-2(b) — names must start with an alphanumeric (no leading hyphen), so a
// flag-shaped name can never be injected into tessctl.
test('HIGH-2b: validateName forbids leading-hyphen (flag-shaped) names', () => {
  assert.equal(validateName('--help', 'operator').ok, false);
  assert.equal(validateName('-foo', 'operator').ok, false);
  assert.equal(validateName('Alex', 'operator').ok, true);
  assert.equal(validateName("O'Brien", 'operator').ok, true);
  assert.equal(validateName('Anne-Marie', 'operator').ok, true);
});

// Quinn MEDIUM — local-scaffold contamination. The shared ignore source must
// classify secret/runtime material as excluded while keeping legit template
// files (incl. the .env.example template and shipped .gitkeep placeholders).
test('Quinn-MED: isExcludedRel drops secrets/runtime, keeps template files', () => {
  // Must DROP — secret + operator-state material.
  for (const p of [
    '.claude/vault/vault.age',
    '.claude/vault/vault.recipients',
    '.claude/vault/identity.age',
    '.claude/tess-secrets/secrets.env.json',
    '.claude/channels/access.json',
    '.tess/snapshots/2026-01-01/snap.json',
    '.tess/staging/incoming.md',
    '.env',
    '.env.local',
    'server.pem',
    'deploy.key',
    '__pycache__/mod.cpython-311.pyc',
    'pkg/util.pyc',
    '.git/config',
    'node_modules/x/index.js',
    'create-tess/src/index.js',
  ]) {
    assert.equal(isExcludedRel(p), true, `${p} must be excluded`);
  }
  // Must KEEP — legit template structure.
  for (const p of [
    'README.md',
    'CLAUDE.md',
    '.env.example',
    'starter/.env.example',
    '.claude/vault/.gitkeep',
    '.claude/vault/vault.registry.json',
    '.tess/snapshots',
    '.tess/snapshots/.gitkeep',
    '.tess/staging/.gitkeep',
    'agents/leah/README.md',
    '.gitignore',
    '.github/workflows/ci.yml',
  ]) {
    assert.equal(isExcludedRel(p), false, `${p} must be kept`);
  }
});

// Quinn MEDIUM (end-to-end) — a produced instance from a LOCAL --template-source
// must NOT contain the author's vault.age / vault.recipients / snapshots / .env /
// keys, while the legit template files survive.
test('Quinn-MED: produced instance from a local source is contamination-free', () => {
  const base = mkdtempSync(join(tmpdir(), 'tess-scaffold-test-'));
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
  w('CLAUDE.md');
  w('.env.example', 'KEY=__PLACEHOLDER__\n');
  w('.claude/vault/.gitkeep', '');
  w('.claude/vault/vault.registry.json', '{"services":{}}\n');
  w('.tess/snapshots/.gitkeep', '');
  w('.tess/staging/.gitkeep', '');
  w('agents/leah/README.md');

  // The author's secret + operator-state material (must NOT leak).
  w('.claude/vault/vault.age', 'CIPHERTEXT\n');
  w('.claude/vault/vault.recipients', 'age1authorpubkey\n');
  w('.claude/vault/identity.age', 'CIPHERTEXT\n');
  w('.claude/tess-secrets/secrets.env.json', '{"GITHUB_TOKEN":"ghp_x"}\n');
  w('.claude/channels/access.json', '{"allow":["x"]}\n');
  w('.tess/snapshots/2026-01-01/snap.json', '{"author":"state"}\n');
  w('.tess/staging/incoming.md', 'author staging\n');
  w('.env', 'SECRET=real\n');
  w('server.pem', '-----BEGIN PRIVATE KEY-----\n');
  w('deploy.key', 'KEYMATERIAL\n');
  w('__pycache__/mod.pyc', 'bytecode\n');
  w('.git/config', '[core]\n');
  w('node_modules/dep/index.js', 'module.exports={}\n');

  try {
    fetchTemplate(src, staging);
    promote(staging, target);

    const gone = (rel) => assert.equal(existsSync(join(target, rel)), false, `${rel} leaked into produced instance`);
    const kept = (rel) => assert.equal(existsSync(join(target, rel)), true, `${rel} missing from produced instance`);

    // No contamination.
    gone('.claude/vault/vault.age');
    gone('.claude/vault/vault.recipients');
    gone('.claude/vault/identity.age');
    gone('.claude/tess-secrets');
    gone('.claude/channels');
    gone('.tess/snapshots/2026-01-01');
    gone('.tess/staging/incoming.md');
    gone('.env');
    gone('server.pem');
    gone('deploy.key');
    gone('__pycache__');
    gone('.git');
    gone('node_modules');

    // Legit structure preserved.
    kept('README.md');
    kept('CLAUDE.md');
    kept('.env.example');
    kept('.claude/vault/.gitkeep');
    kept('.claude/vault/vault.registry.json');
    kept('.tess/snapshots/.gitkeep');
    kept('.tess/staging/.gitkeep');
    kept('agents/leah/README.md');
  } finally {
    rmSync(base, { recursive: true, force: true });
  }
});
