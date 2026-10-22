// v1-nontech.test.js — v1.0 non-technical end-to-end review (S3, S4, S7):
// the default setup speaks plain words, records what the person chose on
// screen as their answer, and ends with the literal commands to type.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { DEFAULTS, VIBES as VIBE_KEYS, HELP } from '../src/args.js';
import { VIBES, VIBE_ORDER, DEFAULT_VIBE } from '../src/content/vibes.js';
import { PATH_FRAMING } from '../src/content/squads.js';
import { NEUTRAL } from '../src/content/sigils.js';
import { buildArrival } from '../src/content/pathways.js';
import { onScreenAnswers, printFinalScreen } from '../src/brain.js';
import { checkConductorName } from '../src/validate.js';

const JARGON = /conductor|gates|forging|doctrine|lens|guild|squad|orchestrator|operator\b/i;

function plainCopy() {
  const v = VIBES.plain;
  const parts = [];
  for (const val of Object.values(v)) {
    if (typeof val === 'string') parts.push(val);
    if (typeof val === 'function') parts.push(String(val('Alex')));
  }
  for (const step of Object.values(v.bakeSteps)) {
    parts.push(typeof step === 'function' ? step({ operator: 'Alex', conductor: 'Tess' }) : step);
  }
  for (const f of Object.values(PATH_FRAMING.plain)) parts.push(f.label, f.hint);
  return parts.join('\n');
}

test('S4: plain is the default skin for new installs; the themes are opt-in', () => {
  assert.equal(DEFAULTS.vibe, 'plain');
  assert.equal(DEFAULT_VIBE, 'plain');
  assert.equal(VIBE_ORDER[0], 'plain');
  assert.deepEqual(VIBE_KEYS, ['plain', 'rpg', 'command', 'studio']);
  assert.match(HELP, /--vibe <plain\|rpg\|command\|studio>/);
  assert.match(HELP, /default: plain/);
});

test('S4: the default path has no game words, no "conductor", no lens lists', () => {
  const text = plainCopy();
  assert.doesNotMatch(text, JARGON, text);
  assert.doesNotMatch(text, /Open the gates/);
  assert.doesNotMatch(NEUTRAL.plain + NEUTRAL.fancy, /conductor/i);
  assert.match(VIBES.plain.namePrompt, /there is no default/);
  const arrival = buildArrival('chief-of-staff', {
    operator: 'Alex', conductor: 'Tess', vibeKey: 'plain', squadNoun: 'team',
    squadNames: ['Ada', 'Reid', 'Quinn'], orchNames: ["Founder's Office"],
  });
  assert.doesNotMatch(arrival, /Ada|Reid|Founder's Office|conductor/);
  assert.match(arrival, /Hi Alex\. Your team of 3 specialists/);
  const clash = checkConductorName('Ada', 'Alex', new Set(['ada']));
  assert.equal(clash.block, true);
  assert.doesNotMatch(clash.reason, /conductor|squad|dispatch/);
});

test('S3: on-screen answers are quoted as chosen; a kept default is not a quote', () => {
  const data = onScreenAnswers({
    mode: 'personal', preset: null, operator: 'Rowan', conductor: 'Tess',
    said: { mode: 'Just me', preset: null, operator: 'Rowan', conductor: null },
  });
  assert.equal(data.runtime, 'setup-wizard');
  const by = Object.fromEntries(data.answers.map((a) => [a.field, a]));
  assert.equal(by.mode.quote, 'Just me');
  assert.equal(by.operator_name.quote, 'Rowan');
  assert.equal(by.preset, undefined, 'no preset question was asked, so no preset answer');
  assert.deepEqual([by.assistant_name.quote, by.assistant_name.runtime], ['', 'default']);
  for (const a of data.answers) assert.ok(!String(a.quote).startsWith('--'), a.quote);
  const typed = onScreenAnswers({
    mode: 'organisation', preset: 'startup', operator: 'Rowan', conductor: 'Atlas',
    said: { mode: 'A team or company', preset: 'Yes', operator: 'Rowan', conductor: 'Atlas' },
  });
  const t = Object.fromEntries(typed.answers.map((a) => [a.field, a]));
  assert.deepEqual([t.preset.value, t.preset.quote], ['startup', 'Yes']);
  assert.equal(t.assistant_name.quote, 'Atlas');
});

test('S7: the final screen gives the literal lines to type', () => {
  const out = [];
  const orig = process.stdout.write.bind(process.stdout);
  process.stdout.write = (s) => { out.push(String(s)); return true; };
  try {
    printFinalScreen(`${process.cwd()}/my-os`, {
      mode: 'personal', brain: { status: 'done', commit: 'abc1234' }, checks: { doctor: true, verify: true },
    });
  } finally {
    process.stdout.write = orig;
  }
  const text = out.join('');
  assert.match(text, /In this terminal, type these two lines, pressing Return after each:\n {6}cd my-os\n {6}claude {12}\(or: codex, if you use Codex\)\n/);
  assert.match(text, /Then say hi\. Tess, your assistant, will take it from there\./);
  assert.match(text, /in Claude Code or Codex and say hi/);
});
