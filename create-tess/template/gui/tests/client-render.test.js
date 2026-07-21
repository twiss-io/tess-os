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

test('renderMetricsBand: caveat icons sit next to both the cost and tokens headline numbers, not buried', () => {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const detailEl = document.createElement('div');
  detailEl.id = 'metrics-detail';
  detailEl.hidden = true;
  document.body.appendChild(detailEl);

  renderMetricsBand(container, SERVER_SHAPED_SUMMARY, { sessionCostUSD: 4.62, activeMissions: 1, avgDurationMs: 9100 });

  const caveatIcons = container.querySelectorAll('.caveat__icon');
  assert.equal(caveatIcons.length, 2, 'both the session-cost and tokens metric cells must carry a caveat icon');

  const tokensTooltip = container.querySelector('#tokens-caveat-tooltip');
  assert.equal(tokensTooltip.textContent, SERVER_SHAPED_SUMMARY.tokensCaveat);

  const costTooltip = container.querySelector('#cost-caveat-tooltip-band');
  assert.equal(costTooltip.textContent, SERVER_SHAPED_SUMMARY.costNote, 'cost caveat must render the server-provided costNote verbatim');
});

test('renderMetricsBand: re-rendering disposes the previous caveat icons\' outside-click listeners (no leak)', () => {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const detailEl = document.createElement('div');
  detailEl.id = 'metrics-detail';
  detailEl.hidden = true;
  document.body.appendChild(detailEl);

  const liveState = { sessionCostUSD: 4.62, activeMissions: 1, avgDurationMs: 9100 };

  // Prime once, unobserved, so any caveat icons left pending by earlier
  // tests in this file (renderMetricsBand's disposal tracking is
  // module-scoped, not reset between tests) are flushed before the spy
  // starts counting — otherwise this assertion would be order-dependent.
  renderMetricsBand(container, SERVER_SHAPED_SUMMARY, liveState);

  const removeSpy = [];
  const originalRemove = document.removeEventListener.bind(document);
  document.removeEventListener = (...args) => {
    if (args[0] === 'click') removeSpy.push(args);
    return originalRemove(...args);
  };
  try {
    renderMetricsBand(container, SERVER_SHAPED_SUMMARY, liveState);
  } finally {
    document.removeEventListener = originalRemove;
  }
  assert.equal(removeSpy.length, 2, 'the priming render\'s two caveat icons (cost + tokens) must have their document click listeners removed before this render');
});

test('renderMetricsBand: metric cells get an incrementing animation-delay on first render; re-rendering the same container does not restagger', () => {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const detailEl = document.createElement('div');
  detailEl.id = 'metrics-detail';
  detailEl.hidden = true;
  document.body.appendChild(detailEl);

  const liveState = { sessionCostUSD: 4.62, activeMissions: 1, avgDurationMs: 9100 };
  renderMetricsBand(container, SERVER_SHAPED_SUMMARY, liveState);

  const cells = Array.from(container.querySelectorAll('.metric-cell'));
  assert.equal(cells.length, 5, 'cost, tokens, active missions, sessions, avg duration');
  assert.deepEqual(
    cells.map((c) => c.style.animationDelay),
    ['0ms', '90ms', '180ms', '270ms', '360ms'],
    'cells must stagger in the order they are appended (cost, tokens, active, sessions, duration)',
  );

  renderMetricsBand(container, SERVER_SHAPED_SUMMARY, liveState);
  const rerendered = Array.from(container.querySelectorAll('.metric-cell'));
  assert.deepEqual(
    rerendered.map((c) => c.style.animationDelay),
    ['', '', '', '', ''],
    'a metrics-band rebuild (mission launch/finish) must not replay the staggered cascade',
  );
});

test('renderCommandGroups: shows the skipped-files badge only when skippedCount > 0', () => {
  const container = document.createElement('div');
  const badge = document.createElement('span');
  renderCommandGroups(container, badge, { commands: [{ name: 'wake', description: 'Session start checklist' }], skippedCount: 2 }, {
    onLaunchImmediate: () => {},
    onLaunchWithArg: () => {},
  });
  assert.equal(badge.hidden, false);
  assert.equal(badge.textContent, '2 files had unreadable descriptions');

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

test('renderCommandGroups: tiles get an incrementing animation-delay in reading order on first render; re-rendering the same container does not restagger', () => {
  const container = document.createElement('div');
  const badge = document.createElement('span');
  const handlers = { onLaunchImmediate: () => {}, onLaunchWithArg: () => {} };
  // All three sit in the "Mission Lifecycle" group; passed out of order to
  // confirm tile order follows the group's declared reading order, not
  // input order — wake, close, summary in that sequence.
  const commands = [
    { name: 'summary', description: '' },
    { name: 'wake', description: '' },
    { name: 'close', description: '' },
  ];

  renderCommandGroups(container, badge, { commands, skippedCount: 0 }, handlers);
  const tiles = Array.from(container.querySelectorAll('.tile'));
  assert.deepEqual(
    tiles.map((t) => t.querySelector('.tile__command').textContent),
    ['/wake', '/close', '/summary'],
  );
  assert.deepEqual(
    tiles.map((t) => t.style.animationDelay),
    ['0ms', '90ms', '180ms'],
  );

  renderCommandGroups(container, badge, { commands, skippedCount: 0 }, handlers);
  const rerendered = Array.from(container.querySelectorAll('.tile'));
  assert.deepEqual(
    rerendered.map((t) => t.style.animationDelay),
    ['', '', ''],
    'a rebuild of the same container must not replay the staggered cascade',
  );
});

test('renderSavedMissions: saved tiles get an incrementing animation-delay on the inner .tile button on first render', () => {
  const sectionEl = document.createElement('div');
  const gridEl = document.createElement('div');
  const missions = [
    { id: 'a', label: 'First', prompt: '/wake' },
    { id: 'b', label: 'Second', prompt: '/close' },
  ];

  renderSavedMissions(sectionEl, gridEl, missions, { onLaunch: () => {}, onRemove: () => {} });

  const tiles = Array.from(gridEl.querySelectorAll('.tile'));
  assert.deepEqual(
    tiles.map((t) => t.style.animationDelay),
    ['0ms', '90ms'],
  );
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

test('renderSavedMissions: the saved tile has no interactive control nested inside another (valid ARIA), and clicking launches', () => {
  const sectionEl = document.createElement('div');
  const gridEl = document.createElement('div');
  const launched = [];
  const missions = [{ id: 'a', label: 'Weekly ops check', prompt: '/ops-mode review fleet uptime' }];

  renderSavedMissions(sectionEl, gridEl, missions, {
    onLaunch: (m) => launched.push(m.id),
    onRemove: () => {},
  });

  const wrapper = gridEl.querySelector('.tile-wrapper');
  assert.ok(wrapper, 'saved tile must have a non-interactive wrapper');
  assert.equal(wrapper.getAttribute('role'), null, 'the wrapper must not carry role="button" — the launch tile is a real button now');
  assert.equal(wrapper.getAttribute('tabindex'), null, 'the wrapper must not be independently focusable');

  const launchBtn = wrapper.querySelector('button.tile--saved');
  assert.ok(launchBtn, 'the launch surface must be a real <button>');
  assert.equal(launchBtn.tagName, 'BUTTON');

  const removeBtn = wrapper.querySelector('.tile__remove');
  assert.ok(removeBtn, 'remove control must exist');
  assert.ok(!launchBtn.contains(removeBtn), 'the remove button must be a sibling of the launch button, not nested inside it');

  launchBtn.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  assert.deepEqual(launched, ['a']);
});

test('renderSavedMissions: hides the section entirely when there are no saved missions', () => {
  const sectionEl = document.createElement('div');
  const gridEl = document.createElement('div');
  renderSavedMissions(sectionEl, gridEl, [], { onLaunch: () => {}, onRemove: () => {} });
  assert.equal(sectionEl.hidden, true);
});
