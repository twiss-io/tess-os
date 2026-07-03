// tess-gui client tests — format.js (no DOM required).
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  formatTokenCount,
  formatModelLine,
  formatCurrency,
  formatDuration,
  formatShortDate,
  realModelEntries,
  SYNTHETIC_MODEL_KEY,
} from '../client/js/format.js';

test('formatTokenCount abbreviates large counts', () => {
  assert.equal(formatTokenCount(842), '842');
  assert.equal(formatTokenCount(1234), '1.2k');
  assert.equal(formatTokenCount(15000), '15k');
  assert.equal(formatTokenCount(1_250_000), '1.3M');
  assert.equal(formatTokenCount(0), '0');
});

test('formatTokenCount never returns NaN for malformed input', () => {
  assert.equal(formatTokenCount(undefined), '0');
  assert.equal(formatTokenCount(null), '0');
  assert.equal(formatTokenCount('not a number'), '0');
  assert.equal(formatTokenCount({}), '0');
});

// THE regression test for Reid's HIGH finding: byModel[model] is a
// {input, output} token-sum object, never a bare integer count. The
// previous build did `${model} ×${count}` treating the object as a number,
// which rendered "[object Object]" to every real user.
test('formatModelLine destructures {input,output} and never renders [object Object] or NaN', () => {
  const line = formatModelLine('claude-opus-4-8', { input: 12400, output: 3100 });
  assert.equal(line, 'claude-opus-4-8 · 12.4k in / 3.1k out');
  assert.ok(!line.includes('[object Object]'));
  assert.ok(!line.includes('NaN'));
});

test('formatModelLine is defensive against malformed usage objects', () => {
  const line = formatModelLine('weird-model', { input: undefined, output: 'garbage' });
  assert.ok(!line.includes('[object Object]'));
  assert.ok(!line.includes('NaN'));
  assert.equal(line, 'weird-model · 0 in / 0 out');
});

test('formatModelLine handles byModel passed as a bare number (the old bug shape) without throwing or emitting NaN', () => {
  // Simulates a server regression back to the old (wrong) shape — the fix
  // must degrade gracefully (0/0), not crash or print NaN/[object Object].
  const line = formatModelLine('claude-sonnet-5', 42);
  assert.ok(!line.includes('[object Object]'));
  assert.ok(!line.includes('NaN'));
});

test('realModelEntries filters the synthetic sentinel and sorts by token volume desc', () => {
  const byModel = {
    'claude-sonnet-5': { input: 150000, output: 31000 },
    'claude-opus-4-8': { input: 73700, output: 16500 },
    [SYNTHETIC_MODEL_KEY]: { input: 300, output: 100 },
  };
  const entries = realModelEntries(byModel);
  assert.equal(entries.length, 2);
  assert.ok(entries.every(([model]) => model !== SYNTHETIC_MODEL_KEY));
  assert.equal(entries[0][0], 'claude-sonnet-5'); // higher total volume sorts first
});

test('formatCurrency treats null/undefined as unavailable, not zero (Number(null) === 0 trap)', () => {
  assert.equal(formatCurrency(4.6), '$4.60');
  assert.equal(formatCurrency(0), '$0.00');
  assert.equal(formatCurrency(null), '—');
  assert.equal(formatCurrency(undefined), '—');
});

test('formatDuration treats null/undefined as unavailable, not zero', () => {
  assert.equal(formatDuration(500), '500ms');
  assert.equal(formatDuration(9100), '9s');
  assert.equal(formatDuration(65000), '1m 5s');
  assert.equal(formatDuration(3700000), '1h 1m');
  assert.equal(formatDuration(null), '—');
  assert.equal(formatDuration(undefined), '—');
});

test('formatShortDate parses YYYY-MM-DD as UTC midnight (no local-timezone day drift)', () => {
  assert.equal(formatShortDate('2026-07-01'), 'Jul 1');
});
