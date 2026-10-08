// v1.0 e2e round 2: the wizard summary shows the plain preset name, never the
// preset id ("(solo-consultant)").
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { BRAIN_PRESETS, PRESET_LABELS, presetLabel } from '../src/brain.js';

test('every preset has a plain label and the summary uses it', () => {
  for (const id of Object.values(BRAIN_PRESETS)) {
    assert.ok(PRESET_LABELS[id], `no plain label for ${id}`);
    assert.doesNotMatch(presetLabel(id), /-/);
  }
  assert.equal(presetLabel('solo-consultant'), 'working on your own');
  assert.equal(presetLabel('startup'), 'a small startup');
  const journey = readFileSync(new URL('../src/journey.js', import.meta.url), 'utf8');
  assert.doesNotMatch(journey, /\(\$\{(c\.)?preset\}\)/);
  assert.equal((journey.match(/presetLabel\(/g) || []).length, 2);
});
