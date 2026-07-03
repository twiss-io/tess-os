// tess-gui client tests — end-to-end: real index.html + real app.js booted
// against ?mock=1, exactly the self-verification method used before (and
// the one that caught real bugs then) — reused here, not reimplemented.
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss
import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { JSDOM } from 'jsdom';

import { waitFor } from './helpers/wait-for.js';

const clientDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../client');
const indexPath = path.join(clientDir, 'index.html');

const dom = await JSDOM.fromFile(indexPath, {
  url: 'http://localhost/index.html?mock=1&token=test-token-do-not-use',
  pretendToBeVisual: true,
});
const { window } = dom;
globalThis.window = window;
globalThis.document = window.document;
globalThis.EventTarget = window.EventTarget;
globalThis.Event = window.Event;
globalThis.MessageEvent = window.MessageEvent;
globalThis.CustomEvent = window.CustomEvent;
globalThis.MouseEvent = window.MouseEvent;
globalThis.HTMLElement = window.HTMLElement;
globalThis.history = window.history;
globalThis.location = window.location;

// app.js runs its boot() automatically at import time, exactly as a real
// page load would — not re-invoked here, just awaited-for via DOM polling
// since boot()'s promise isn't exported (matching how a real page works).
await import(path.join(clientDir, 'app.js'));
const mockModule = await import(path.join(clientDir, 'js/mock-data.js'));

await waitFor(() => document.querySelectorAll('#command-groups .tile').length > 0);

test('boot: token is stripped from the address bar', () => {
  assert.ok(!window.location.href.includes('test-token-do-not-use'));
  assert.ok(window.location.href.includes('mock=1'), 'other query params must survive the strip');
});

test('boot: CLI status dot reflects a compatible, connected mock health check', () => {
  const dot = document.getElementById('cli-status-dot');
  assert.equal(dot.dataset.state, 'ok');
  assert.equal(document.querySelector('[data-banner-id="cli-incompatible"]'), null);
});

test('boot: all 26 mock commands render, grouped, with the skipped-files badge visible', () => {
  const tiles = document.querySelectorAll('#command-groups .tile');
  assert.equal(tiles.length, 26);
  const badge = document.getElementById('commands-skipped-badge');
  assert.equal(badge.hidden, false);
  assert.equal(badge.textContent, '2 files skipped (malformed)');
});

test('boot: seeded saved-mission tiles render in "Your Missions"', () => {
  const savedSection = document.getElementById('saved-missions-section');
  assert.equal(savedSection.hidden, false);
  assert.equal(document.querySelectorAll('#saved-missions-grid .tile--saved').length, 2);
});

test('boot: timeline renders the 3 seeded entries', () => {
  assert.equal(document.querySelectorAll('#timeline-list .timeline__entry').length, 3);
});

test('boot: 7-day detail panel — byModel fix holds end-to-end (no [object Object]/NaN, synthetic filtered, caveat/cost note visible)', () => {
  const toggle = document.querySelector('.metrics-band__toggle');
  toggle.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  const detail = document.getElementById('metrics-detail');
  assert.equal(detail.hidden, false);

  const text = detail.textContent;
  assert.ok(!text.includes('[object Object]'));
  assert.ok(!text.includes('NaN'));
  assert.ok(!text.includes('<synthetic>'));
  assert.ok(text.includes('claude-sonnet-5'));
  assert.ok(text.includes(mockModule.MOCK_TOKENS_CAVEAT));
  assert.ok(text.includes(mockModule.MOCK_COST_NOTE));

  toggle.dispatchEvent(new window.MouseEvent('click', { bubbles: true })); // leave it collapsed for later tests
});

test('mission launch + live log streaming: real SSE events render every msg kind with no [object Object]/NaN', async () => {
  const tiles = Array.from(document.querySelectorAll('#command-groups .tile'));
  const wakeTile = tiles.find((t) => t.querySelector('.tile__command')?.textContent === '/wake');
  assert.ok(wakeTile, 'the /wake command tile must exist');

  wakeTile.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));

  await waitFor(() => document.getElementById('live-view').hidden === false);
  assert.equal(document.getElementById('launcher-view').hidden, true, 'launcher must fully swap out, not just overlay');
  assert.equal(document.getElementById('live-view').dataset.state, 'running');

  // Enough real time for system-init, two assistant-text lines, two
  // tool_use chips, and the stderr line to have played back (~6.4s per the
  // canned script) — proves every SSE msg-event kind renders correctly.
  await waitFor(() => document.querySelectorAll('#live-view-log .log-line').length >= 6, { timeout: 8000 });

  const logText = document.getElementById('live-view-log').textContent;
  assert.ok(!logText.includes('[object Object]'));
  assert.ok(!logText.includes('NaN'));
  assert.ok(logText.includes('session initialized'), 'system event renders as a dim init line');
  assert.ok(logText.includes('⚙ Read'), 'tool_use renders as a mono chip');
  assert.ok(logText.includes('⚙ Bash'), 'tool_use renders as a mono chip');
  assert.ok(logText.includes('detached HEAD state'), 'stderr event renders');

  const stderrLine = document.querySelector('.log-line--stderr');
  assert.ok(stderrLine, 'stderr must use the dedicated dim-red style hook');

  // Cancel the still-running mock playback (rather than waiting the full
  // ~9s for its natural 'done') by navigating back — this also proves the
  // "◀ missions" control tears down its SSE subscription cleanly.
  document.getElementById('live-view-back').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await waitFor(() => document.getElementById('launcher-view').hidden === false);
});

test('concurrency cap: a 4th mission attempt while 3 are already running shows a polite banner, not a native alert', async () => {
  const mock = await import(path.join(clientDir, 'js/mock.js'));
  mock.resetMockState();
  const running = mock.__test__.missions();
  running.push(
    { id: 'seed-running-1', label: 'a', prompt: 'a', status: 'running', startedAt: new Date().toISOString(), endedAt: null, costUSD: null, usage: null },
    { id: 'seed-running-2', label: 'b', prompt: 'b', status: 'running', startedAt: new Date().toISOString(), endedAt: null, costUSD: null, usage: null },
    { id: 'seed-running-3', label: 'c', prompt: 'c', status: 'running', startedAt: new Date().toISOString(), endedAt: null, costUSD: null, usage: null },
  );

  const input = document.getElementById('mission-input');
  input.value = 'one mission too many';
  input.dispatchEvent(new window.Event('input', { bubbles: true }));
  document.getElementById('mission-launch-btn').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));

  await waitFor(() => document.querySelector('[data-banner-id="mission-limit"]') != null);
  const banner = document.querySelector('[data-banner-id="mission-limit"]');
  assert.match(banner.textContent, /mission limit reached/i);
  assert.ok(banner.querySelector('.banner__dismiss'), 'concurrency-cap banner must be dismissable (unlike the persistent CLI/connection banners)');
});

// app.js's boot() intentionally starts a health-poll interval that runs
// forever (correct for a real, always-open browser tab), and jsdom's
// pretendToBeVisual re-schedules its own animation-frame timer indefinitely
// — unref() alone doesn't catch timers rescheduled after this hook runs, so
// the process never drains on its own. A bare process.exit() here would
// race ahead of node:test's own result reporting for the last test (it did,
// in an earlier version of this file — the last test's passing result was
// silently dropped from the report even though it ran and passed). The
// short setTimeout gives the reporter a tick to flush before the hard exit.
after(() => {
  for (const handle of process._getActiveHandles()) {
    if (typeof handle.unref === 'function') handle.unref();
  }
  setTimeout(() => process.exit(0), 50).unref();
});
