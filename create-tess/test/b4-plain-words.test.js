// b4-plain-words.test.js — the v1.0 "B4" first-run findings: a person with no
// technical background must see accurate numbers, plain words, one clear next
// step, and a clean refusal (nothing written) when git is missing.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, writeFileSync, chmodSync, rmSync, existsSync, readFileSync, readdirSync } from 'node:fs';
import { join, dirname, resolve, delimiter } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';

import { checkGit, missingGitMessage, gitPreflight } from '../src/git-check.js';
import { missingPythonMessage, oldPythonMessage } from '../src/python.js';
import { parseArgs } from '../src/args.js';
import { NEUTRAL, SIGILS } from '../src/content/sigils.js';
import { VIBES } from '../src/content/vibes.js';
import { buildArrival, crewTip } from '../src/content/pathways.js';

const PKG_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const ENTRY = join(PKG_DIR, 'bin', 'create-tess.mjs');
const PKG_VERSION = JSON.parse(readFileSync(join(PKG_DIR, 'package.json'), 'utf8')).version;
const STALE = [/~\s?1[45]0/, /hundred and fifty/i, /orchestrators (loaded|on call)/, /\bv0\.1\b/, /ten roles/i, /Commander/];

function copyText() {
  const parts = [NEUTRAL.fancy, NEUTRAL.plain];
  for (const s of Object.values(SIGILS)) parts.push(s.fancy, s.plain);
  for (const v of Object.values(VIBES)) {
    for (const val of Object.values(v)) {
      if (typeof val === 'string') parts.push(val);
      if (typeof val === 'function') parts.push(String(val('Alex')));
    }
    for (const step of Object.values(v.bakeSteps)) {
      parts.push(typeof step === 'function' ? step({ operator: 'Alex', operatorTerm: v.operatorTerm, conductor: 'Tess', pathwayLabel: 'Guide' }) : step);
    }
  }
  return parts.join('\n');
}

test('B4: banner and vibe copy carry no stale counts or rank jargon', () => {
  const text = copyText();
  for (const re of STALE) assert.doesNotMatch(text, re, `wizard copy must not contain ${re}`);
  assert.match(NEUTRAL.plain, /a crew of 9 specialists plus your assistant/);
});

test('B4: the arrival greeting has no "Commander", no slash command, and counts the crew', () => {
  const ctx = { operator: 'Alex', conductor: 'Tess', vibeKey: 'rpg', squadNoun: 'squad', squadNames: ['Ada', 'Reid'], orchNames: [] };
  for (const pathway of ['chief-of-staff', 'co-founder', 'strategist', 'guide', 'operator']) {
    const out = buildArrival(pathway, ctx);
    assert.doesNotMatch(out, /Commander|▶|\/add-mission/, `${pathway}: ${out}`);
    assert.doesNotMatch(out, /\n\n/, `${pathway}: no blank gap when there are no orchestrators`);
    assert.match(out, /Alex/);
  }
  assert.equal(crewTip(9), 'Tip: you have a crew of 9 specialists plus your assistant. Ask your assistant any time to add expertise.');
});

test('B4: missing git and missing Python messages give a link and say nothing was installed', () => {
  for (const platform of ['darwin', 'linux', 'win32']) {
    const g = missingGitMessage(platform);
    assert.match(g, /https:\/\/git-scm\.com\/downloads/);
    assert.match(g, /Nothing was installed\./);
    const p = missingPythonMessage(platform);
    assert.match(p, /Python 3\.9 or newer/);
    assert.match(p, /https:\/\/www\.python\.org\/downloads\//);
    assert.match(p, /Nothing was installed\./);
  }
  assert.match(missingGitMessage('darwin'), /xcode-select --install/);
  assert.match(oldPythonMessage('3.8'), /this computer has Python 3\.8/);
  assert.equal(checkGit({ cmd: join(tmpdir(), 'definitely-not-git-' + process.pid) }).ok, false);
  assert.equal(checkGit().ok, true, 'the machine running the tests has git');
});

test('B4: gitPreflight needs git unless the run opts out of git on the bundled template', () => {
  const missing = () => ({ ok: false, message: 'no git' });
  assert.equal(gitPreflight({}, true, missing), 'no git');
  assert.equal(gitPreflight({ noOnboarding: true }, true, missing), 'no git');
  assert.equal(gitPreflight({ noGitInit: true }, false, missing), 'no git', 'a git template source always needs git');
  assert.equal(gitPreflight({ noGitInit: true }, true, missing), null);
  assert.equal(gitPreflight({}, true, () => ({ ok: true })), null);
});

test('B4: create-tess --version and -v print the package version and exit 0', () => {
  assert.equal(parseArgs(['--version']).version, true);
  for (const flag of ['--version', '-v']) {
    const r = spawnSync(process.execPath, [ENTRY, flag], { encoding: 'utf8' });
    assert.equal(r.status, 0, r.stderr);
    assert.equal(r.stdout.trim(), `create-tess ${PKG_VERSION}`);
  }
  const help = spawnSync(process.execPath, [ENTRY, '--help'], { encoding: 'utf8' });
  assert.match(help.stdout, /--version, -v/);
});

test('B4: missing git fails cleanly before anything is written (no half-install)', () => {
  const bin = mkdtempSync(join(tmpdir(), 'ct-nogit-bin-'));
  const parent = mkdtempSync(join(tmpdir(), 'ct-nogit-target-'));
  const target = join(parent, 'my-os');
  try {
    const gitShim = join(bin, 'git');
    writeFileSync(gitShim, '#!/bin/sh\necho "git: command not found" >&2\nexit 127\n');
    chmodSync(gitShim, 0o755);
    const env = { ...process.env, PATH: `${bin}${delimiter}${process.env.PATH}` };
    const r = spawnSync(process.execPath, [ENTRY, target, '--yes', '--operator=Alex'], { env, encoding: 'utf8' });
    assert.equal(r.status, 1, `must exit 1\n${r.stdout}\n${r.stderr}`);
    assert.match(r.stderr, /Tess OS needs git/);
    assert.match(r.stderr, /https:\/\/git-scm\.com\/downloads/);
    assert.match(r.stderr, /Nothing was installed\./);
    assert.ok(!existsSync(target), 'the target folder must not be created');
    assert.deepEqual(readdirSync(parent), [], 'nothing may be written next to it either');
  } finally {
    rmSync(bin, { recursive: true, force: true });
    rmSync(parent, { recursive: true, force: true });
  }
});
