// tess-gui client tests — real renderers (metrics.js, launcher.js) run
// against a jsdom document, not reimplemented.
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { installDomEnv } from './helpers/dom-env.js';

installDomEnv();

const { renderMetricsDetail, renderMetricsBand } = await import('../client/js/metrics.js');
const { renderCommandGroups, renderSavedMissions, ARG_COMMANDS } = await import('../client/js/launcher.js');

// Server-shaped fixture: byModel is {model: {input, output}} per day,
// including the synthetic sentinel on one day — exactly Ada's real
// aggregateSessions contract, and exactly what hid the bug last time.
const SERVER_SHAPED_SUMMARY = {
  days: [
    {
      date: '2026-07-01',
      sessions: 14,
      tokens: { input: 224000, output: 47600, cacheRead: 601000, cacheCreation: 9400 },
      byModel: {
        'claude-sonnet-5': { input: 150000, output: 31000 },
        'claude-opus-4-8': { input: 73700, output: 16500 },
        '<synthetic>': { input: 300, output: 100 },
      },
    },
  ],
  totals: { sessions: 14, tokens: { input: 224000, output: 47600, cacheRead: 601000, cacheCreation: 9400 } },
  missionCostUSD: 4.62,
  costNote: 'missionCostUSD reflects exact costs reported by the Claude Code CLI for missions launched from this dashboard only.',
  tokensCaveat: 'input_tokens may undercount actual usage — treat as directional only, not exact.',
};

test('renderMetricsDetail: byModel fix — real model rows render, no [object Object], no NaN, synthetic filtered out', () => {
  const container = document.createElement('div');
  document.body.appendChild(container);

  renderMetricsDetail(container, SERVER_SHAPED_SUMMARY, []);

  const text = container.textContent;
  assert.ok(!text.includes('[object Object]'), 'must never render [object Object]');
  assert.ok(!text.includes('NaN'), 'must never render NaN');
  assert.ok(!text.includes('<synthetic>'), 'synthetic sentinel model must be filtered out of the breakdown');
  assert.ok(text.includes('claude-sonnet-5'), 'real model must be rendered');
  assert.ok(text.includes('claude-opus-4-8'), 'real model must be rendered');
  assert.ok(text.includes('150k') || text.includes('150.0k'), 'token sums must be present, formatted');
  assert.ok(text.includes(SERVER_SHAPED_SUMMARY.tokensCaveat), 'tokensCaveat must be visible, not buried');
  assert.ok(text.includes(SERVER_SHAPED_SUMMARY.costNote), 'costNote must be visible');
});

test('renderMetricsBand: tokens caveat icon is present next to the headline number, not buried', () => {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const detailEl = document.createElement('div');
  detailEl.id = 'metrics-detail';
  detailEl.hidden = true;
  document.body.appendChild(detailEl);

  renderMetricsBand(container, SERVER_SHAPED_SUMMARY, { sessionCostUSD: 4.62, activeMissions: 1, avgDurationMs: 9100 });

  const caveatIcon = container.querySelector('.caveat__icon');
  assert.ok(caveatIcon, 'caveat icon must be rendered inside the tokens metric cell');
  const tooltip = container.querySelector('.caveat__tooltip');
  assert.equal(tooltip.textContent, SERVER_SHAPED_SUMMARY.tokensCaveat);
});

test('renderCommandGroups: shows the skipped-files badge only when skippedCount > 0', () => {
  const container = document.createElement('div');
  const badge = document.createElement('span');
  renderCommandGroups(container, badge, { commands: [{ name: 'wake', description: 'Session start checklist' }], skippedCount: 2 }, {
    onLaunchImmediate: () => {},
    onLaunchWithArg: () => {},
  });
  assert.equal(badge.hidden, false);
  assert.equal(badge.textContent, '2 files skipped (malformed)');

  renderCommandGroups(container, badge, { commands: [{ name: 'wake', description: '' }], skippedCount: 0 }, {
    onLaunchImmediate: () => {},
    onLaunchWithArg: () => {},
  });
  assert.equal(badge.hidden, true);
});

test('renderCommandGroups: arg-requiring commands route through onLaunchWithArg, others through onLaunchImmediate', () => {
  const container = document.createElement('div');
  const badge = document.createElement('span');
  const calls = { immediate: [], withArg: [] };
  renderCommandGroups(
    container,
    badge,
    { commands: [{ name: 'wake', description: '' }, { name: 'add-mission', description: '' }], skippedCount: 0 },
    { onLaunchImmediate: (name) => calls.immediate.push(name), onLaunchWithArg: (name) => calls.withArg.push(name) },
  );

  const tiles = container.querySelectorAll('.tile');
  for (const tile of tiles) tile.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));

  assert.deepEqual(calls.immediate, ['wake']);
  assert.deepEqual(calls.withArg, ['add-mission']);
  assert.ok(ARG_COMMANDS.has('add-mission'));
});

test('renderSavedMissions: remove control is keyboard-operable (Enter and Space), and does not also trigger launch', () => {
  const sectionEl = document.createElement('div');
  const gridEl = document.createElement('div');
  const removed = [];
  const launched = [];
  const missions = [{ id: 'a', label: 'Weekly ops check', prompt: '/ops-mode review fleet uptime' }];

  renderSavedMissions(sectionEl, gridEl, missions, {
    onLaunch: (m) => launched.push(m.id),
    onRemove: (id) => removed.push(id),
  });

  assert.equal(sectionEl.hidden, false);
  const removeBtn = gridEl.querySelector('.tile__remove');
  assert.ok(removeBtn, 'remove control must exist');

  removeBtn.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
  assert.deepEqual(removed, ['a']);
  assert.deepEqual(launched, [], 'keyboard-removing must not also launch the mission');

  removeBtn.dispatchEvent(new window.KeyboardEvent('keydown', { key: ' ', bubbles: true }));
  assert.deepEqual(removed, ['a', 'a']);
});

test('renderSavedMissions: hides the section entirely when there are no saved missions', () => {
  const sectionEl = document.createElement('div');
  const gridEl = document.createElement('div');
  renderSavedMissions(sectionEl, gridEl, [], { onLaunch: () => {}, onRemove: () => {} });
  assert.equal(sectionEl.hidden, true);
});
