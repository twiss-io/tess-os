// units.test.js — fast, in-process unit coverage for the M3-remediation fixes
// that aren't observable through a non-interactive end-to-end run (taste copy in
// vibes/sigils, plus the arg-parser / name-validator guards).
//
// Run: npm test   (or `node --test`)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, existsSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

import { VIBES, VIBE_ORDER, VIBE_HONESTY } from '../src/content/vibes.js';
import { SIGILS, NEUTRAL } from '../src/content/sigils.js';
import { parseArgs } from '../src/args.js';
import { validateName } from '../src/validate.js';
import { isExcludedRel } from '../src/ignore.js';
import { fetchTemplate, promote } from '../src/scaffold.js';
import { resetKeyToEmptyInline, resetPolicyKeyRegistries } from '../src/policy-reset.js';

// Repo root (create-tess/ lives one level inside it) — used below to read
// the REAL core/policy/policy.yaml so the comment-heavy fixture is the
// file's actual shape, not a synthetic stand-in that could drift from it.
const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');

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
    '.github/workflows/tess-gate.yml',
  ]) {
    assert.equal(isExcludedRel(p), false, `${p} must be kept`);
  }
});

// B3 (gap-loop R2) — the scaffold copies `.github/workflows/` verbatim, so
// without an exact-path exclude a produced instance inherited this repo's OWN
// framework-internal CI (its pytest/doctor/verify suite, its release-cut
// pipeline, its npm-publish pipeline) alongside the one workflow a user
// instance actually needs: the doctrine ship-gate's CI entrypoint.
test('B3: framework-internal workflows are excluded, tess-gate.yml is kept', () => {
  for (const p of [
    '.github/workflows/ci.yml',
    '.github/workflows/release.yml',
    '.github/workflows/publish-npm.yml',
  ]) {
    assert.equal(isExcludedRel(p), true, `${p} must be excluded from the scaffold`);
  }
  assert.equal(
    isExcludedRel('.github/workflows/tess-gate.yml'),
    false,
    'tess-gate.yml (the user-relevant ship-gate CI) must be kept',
  );
});

// Quinn MEDIUM (drift) — the EXCLUDE_* set had drifted from the secret block of
// the repo .gitignore / .npmignore. These patterns are present in BOTH ignore
// files but were NOT being excluded, so a local-source scaffold copied real
// secrets into the produced instance. Each must now classify as excluded, while
// ordinary kept files (README, normal source) stay NON-excluded.
test('Quinn-MED: drifted secret patterns are now excluded (lockstep with .gitignore/.npmignore)', () => {
  // Newly-covered secret/runtime material — must DROP.
  for (const p of [
    // `.claude/settings.local.json` local override
    '.claude/settings.local.json',
    // bare secret/runtime dirs at any depth (not only `.claude/`-anchored)
    'secrets/api-key.txt',
    'tess-secrets/token.json',
    'channels/telegram.json',
    'nested/dir/secrets/leaked.txt',
    // `*.env.json` files (only `.env` / `.env.*` were handled before)
    'prod.env.json',
    'config/staging.env.json',
    // operator/ secret material
    'operator/secrets',
    'operator/db.secret',
    // any file under a `clients/*/.vault/` subtree (not just the 3 basenames)
    'clients/Acme/.vault/vault.age',
    'clients/Acme/.vault/notes.txt',
    'clients/Acme/.vault/sub/blob.bin',
  ]) {
    assert.equal(isExcludedRel(p), true, `${p} must be excluded`);
  }
  // Ordinary kept files (incl. operator/ + clients/ template structure) — must KEEP.
  for (const p of [
    'README.md',
    'src/index.js',
    'operator/README.md',
    'clients/_template/CLAUDE.md',
    'config/settings.json',
    'package.json',
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

// ── Scaffold reset: verifier_keys/signoff_keys never inherited from source ──
// A repo's registered verifier/sign-off keys are ITS OWN trust anchor (e.g.
// twiss-io/tess-os registering Cyra via chore/register-verifier-cyra-phase1,
// PR #91, to govern its OWN development). Without a reset, promote() would
// copy core/policy/policy.yaml (and its .tess/core mirror) verbatim — a
// scaffolded USER project would silently inherit the maintainer's key as its
// own trust anchor. See create-tess/src/policy-reset.js.

test('policy-reset: resetKeyToEmptyInline collapses a populated block to {}, preserving every other line', () => {
  const text =
    'policy:\n' +
    '  rules: []\n' +
    '\n' +
    '  verifier_keys:\n' +
    '    Cyra:\n' +
    '      fingerprint: "AAAA"\n' +
    '      public_key_file: .tess/keys/verifiers/cyra.asc\n' +
    '\n' +
    '  # signoff_keys comment\n' +
    '  signoff_keys: {}\n';
  const { text: out, changed } = resetKeyToEmptyInline(text, 'verifier_keys');
  assert.equal(changed, true);
  assert.equal(
    out,
    'policy:\n' +
      '  rules: []\n' +
      '\n' +
      '  verifier_keys: {}\n' +
      '\n' +
      '  # signoff_keys comment\n' +
      '  signoff_keys: {}\n',
    'every other line (including the trailing blank line before the next key) must survive byte-for-byte',
  );
});

test('policy-reset: already-empty registries are a no-op (changed:false, byte-identical)', () => {
  const text = 'policy:\n  verifier_keys: {}\n  signoff_keys: {}\n';
  const { text: out, changed } = resetPolicyKeyRegistries(text);
  assert.equal(changed, false);
  assert.equal(out, text);
});

test('policy-reset: a commented-out example block is never mistaken for the real key', () => {
  const text =
    'policy:\n' +
    '  # Example shape (commented out — replace with a REAL registered key):\n' +
    '  #   verifier_keys:\n' +
    '  #     Reid:\n' +
    '  #       fingerprint: "AAAA0000AAAA0000AAAA0000AAAA0000AAAA0000"\n' +
    '  verifier_keys:\n' +
    '    Cyra:\n' +
    '      fingerprint: "AAAA"\n' +
    '      public_key_file: .tess/keys/verifiers/cyra.asc\n' +
    '  signoff_keys: {}\n';
  const { text: out, changed } = resetPolicyKeyRegistries(text);
  assert.equal(changed, true);
  assert.ok(
    out.includes('#   verifier_keys:\n  #     Reid:'),
    'the commented-out example block must survive untouched',
  );
  assert.ok(out.includes('  verifier_keys: {}\n'), 'the REAL (uncommented) key must be reset');
});

test('policy-reset: resetKeyToEmptyInline throws when the key is entirely absent (fail loud, never silent)', () => {
  assert.throws(
    () => resetKeyToEmptyInline('policy:\n  rules: []\n', 'verifier_keys'),
    /no `verifier_keys:` key found/,
  );
});

// ── Realistic fixture: the REAL, comment-heavy policy.yaml, with a second
// registered entry added under an interior annotation comment ──────────────
// Reads THIS repo's actual core/policy/policy.yaml (not a hand-typed
// stand-in — its extensive header/walkthrough prose is real, load-bearing
// documentation, and drifts over time) and registers TWO entries under
// EACH of verifier_keys/signoff_keys: the first mirrors PR #91's real,
// merged Cyra registration (real name, real fingerprint, real
// public_key_file path); the second is preceded by an interior comment
// written at the PARENT key's indent (2 spaces) rather than the child
// entry's own indent (4 spaces) — noting when/why that second key was
// added. This is an entirely ordinary way a second contributor annotates a
// growing map (this very file's own header comments are written this way
// throughout), and it is the exact shape that broke resetKeyToEmptyInline:
// a comment at header-indent used to be treated, unconditionally, as "the
// next sibling key" — stopping block removal one entry too early and
// leaving the second entry's fingerprint (and the rest of the file after
// it) spliced in right after the supposedly-reset `{}`, corrupting the YAML.
const CYRA_FINGERPRINT = 'F9321F92B4E2DF36304CB6BAA53B9C5A1F5876E8'; // real — PR #91
const REID_FINGERPRINT = '1234ABCD1234ABCD1234ABCD1234ABCD1234ABCD'; // fixture-only
const XAVIER_FINGERPRINT = 'DEADBEEFDEADBEEFDEADBEEFDEADBEEFDEADBEEF'; // fixture-only
const PRIYA_FINGERPRINT = 'FEEDFACEFEEDFACEFEEDFACEFEEDFACEFEEDFACE'; // fixture-only

function realisticMultiEntryPolicyText() {
  const real = readFileSync(join(REPO_ROOT, 'core', 'policy', 'policy.yaml'), 'utf8');

  const vkBefore = '  verifier_keys: {}\n';
  const vkAfter =
    '  verifier_keys:\n' +
    '    Cyra:\n' +
    `      fingerprint: "${CYRA_FINGERPRINT}"\n` +
    '      public_key_file: .tess/keys/verifiers/cyra.asc\n' +
    '\n' +
    '  # Reid — registered 2026-07-20 via `tessctl verdict keygen --verifier Reid`\n' +
    '    Reid:\n' +
    `      fingerprint: "${REID_FINGERPRINT}"\n` +
    '      public_key_file: .tess/keys/verifiers/reid.asc\n';
  assert.equal(
    real.split(vkBefore).length - 1, 1,
    'fixture assumption: core/policy/policy.yaml ships exactly one `verifier_keys: {}` line to inject into',
  );

  const skBefore = '  signoff_keys: {}\n';
  const skAfter =
    '  signoff_keys:\n' +
    '    Xavier:\n' +
    `      fingerprint: "${XAVIER_FINGERPRINT}"\n` +
    '      public_key_file: .tess/keys/signoffs/xavier.asc\n' +
    '\n' +
    '  # Priya — registered 2026-07-20 via `tessctl gate signoff sign`\n' +
    '    Priya:\n' +
    `      fingerprint: "${PRIYA_FINGERPRINT}"\n` +
    '      public_key_file: .tess/keys/signoffs/priya.asc\n';
  assert.equal(
    real.split(skBefore).length - 1, 1,
    'fixture assumption: core/policy/policy.yaml ships exactly one `signoff_keys: {}` line to inject into',
  );

  return real.split(vkBefore).join(vkAfter).split(skBefore).join(skAfter);
}

// THE REGRESSION LOCK, function-level: resetPolicyKeyRegistries against the
// REAL, comment-heavy, multi-entry shape above must ship BOTH registries
// truly empty — no fingerprint of either entry surviving, valid YAML (no
// value-line-fused-onto-comment corruption), and idempotent on a second pass.
// This test FAILS on the pre-fix resetKeyToEmptyInline (it leaks Reid's/
// Priya's fingerprint and produces unparsable YAML) and PASSES once the
// walk-forward block-end detection stops trusting a comment's own indent.
test('policy-reset: a REAL comment-heavy multi-entry block (interior annotation comment) collapses cleanly — no leak, no fusion, valid YAML', () => {
  const text = realisticMultiEntryPolicyText();
  const { text: out, changed } = resetPolicyKeyRegistries(text);
  assert.equal(changed, true);
  assert.match(out, /verifier_keys: \{\}/);
  assert.match(out, /signoff_keys: \{\}/);
  for (const fp of [CYRA_FINGERPRINT, REID_FINGERPRINT, XAVIER_FINGERPRINT, PRIYA_FINGERPRINT]) {
    assert.doesNotMatch(out, new RegExp(fp), `registered fingerprint ${fp} must not survive the reset`);
  }
  assert.ok(out.endsWith('\n'), 'file must still end with a trailing newline (no dropped line ending)');

  // Valid YAML, and both maps parse as genuinely empty (not silently
  // dropped, not merged into a sibling by a corrupted indent).
  const check = spawnSync('python3', [
    '-c',
    'import sys, yaml\n' +
      'd = yaml.safe_load(sys.stdin.read())\n' +
      'assert d["policy"]["verifier_keys"] == {}, d["policy"]["verifier_keys"]\n' +
      'assert d["policy"]["signoff_keys"] == {}, d["policy"]["signoff_keys"]\n',
  ], { input: out, encoding: 'utf8' });
  assert.equal(
    check.status, 0,
    `reset output must be valid YAML with both registries empty\nSTDOUT:\n${check.stdout}\nSTDERR:\n${check.stderr}`,
  );

  // Idempotent: resetting the already-clean output is a true no-op.
  const second = resetPolicyKeyRegistries(out);
  assert.equal(second.changed, false);
  assert.equal(second.text, out);
});

// THE REGRESSION LOCK, full pipeline (task spec): a scaffold produced from a
// source repo whose policy HAS verifier_keys/signoff_keys registered
// (simulating the state twiss-io/tess-os itself is in once PR #91 merges —
// built here from the REAL, comment-heavy policy.yaml, not a simplified
// synthetic) must ship with EMPTY registries in BOTH the live policy and its
// .tess/core mirror — never inheriting the source repo's trust anchor.
test('scaffold reset: a source with a REAL comment-heavy multi-entry registration scaffolds with empty registries in both copies', () => {
  const base = mkdtempSync(join(tmpdir(), 'tess-policy-reset-test-'));
  const src = join(base, 'source');
  const staging = join(base, 'staging');
  const target = join(base, 'instance');

  const REALISTIC_POLICY = realisticMultiEntryPolicyText();

  const w = (rel, body) => {
    const fp = join(src, rel);
    mkdirSync(join(fp, '..'), { recursive: true });
    writeFileSync(fp, body);
  };
  w('core/policy/policy.yaml', REALISTIC_POLICY);
  w('.tess/core/policy/policy.yaml', REALISTIC_POLICY);

  try {
    fetchTemplate(src, staging);
    const { policyReset } = promote(staging, target);

    assert.equal(policyReset.changed, true, 'promote() must report that the reset ran');
    assert.deepEqual(
      [...policyReset.files].sort(),
      ['.tess/core/policy/policy.yaml', 'core/policy/policy.yaml'].sort(),
      'both the live policy and its .tess/core mirror must be reported as reset',
    );

    for (const rel of ['core/policy/policy.yaml', join('.tess', 'core', 'policy', 'policy.yaml')]) {
      const out = readFileSync(join(target, rel), 'utf8');
      assert.match(out, /verifier_keys: \{\}/, `${rel} must ship empty verifier_keys`);
      assert.match(out, /signoff_keys: \{\}/, `${rel} must ship empty signoff_keys`);
      // NOTE: the shipped policy.yaml legitimately mentions "Cyra"/"Reid"/
      // "Xavier" as bare names in its own commented-out walkthrough even in
      // its pristine, nothing-registered state — asserting against the bare
      // names would false-fail on the file's own documentation. Assert
      // against the actual registered FINGERPRINTS instead: cryptographic
      // material that can only be present if a real registered entry
      // survived the reset — a precise, unambiguous proof of leakage.
      for (const fp of [CYRA_FINGERPRINT, REID_FINGERPRINT, XAVIER_FINGERPRINT, PRIYA_FINGERPRINT]) {
        assert.doesNotMatch(out, new RegExp(fp), `${rel} must NOT carry the source repo's registered fingerprint ${fp}`);
      }
      // Every other line (the file's real header/rule documentation) must survive.
      assert.match(out, /policy:\n\s*version: 1/, `${rel} must keep unrelated policy content intact`);
    }

    // The SOURCE itself must be untouched — promote() must never write back
    // into staging/source, only into the target.
    assert.match(readFileSync(join(src, 'core', 'policy', 'policy.yaml'), 'utf8'), new RegExp(CYRA_FINGERPRINT));
  } finally {
    rmSync(base, { recursive: true, force: true });
  }
});
