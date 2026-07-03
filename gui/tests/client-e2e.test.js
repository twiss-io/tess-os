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
  assert.equal(badge.textContent, '2 files had unreadable descriptions');
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

test('boot: a cost caveat icon sits next to the header session-cost figure, not just buried in the detail panel', () => {
  const group = document.getElementById('header-cost-group');
  const icon = group.querySelector('.caveat__icon');
  assert.ok(icon, 'a caveat icon must be rendered next to the header session-cost figure');
  const tooltip = document.getElementById('cost-caveat-tooltip-header');
  assert.equal(tooltip.textContent, mockModule.MOCK_COST_NOTE, 'header caveat must render the server-provided costNote verbatim');
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

test('SSE reconnect-replay: a completed mission closes its EventSource and does not double-count cost on the reconnect the mock now simulates', async () => {
  const mock = await import(path.join(clientDir, 'js/mock.js'));
  mock.resetMockState(); // clear the previous test's seeded fake-running missions

  const tiles = Array.from(document.querySelectorAll('#command-groups .tile'));
  const wakeTile = tiles.find((t) => t.querySelector('.tile__command')?.textContent === '/wake');
  wakeTile.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));

  await waitFor(() => document.getElementById('live-view').hidden === false);

  const runningMissions = mock.__test__.missions().filter((m) => m.status === 'running');
  assert.equal(runningMissions.length, 1, 'exactly one mission must be running after launch');
  const source = mock.__test__.activeSources().get(runningMissions[0].id);
  assert.ok(source, 'a MockEventSource must be tracked for the running mission');

  const costBefore = document.getElementById('header-session-cost').textContent;

  // Force-stop for a fast, deterministic completion (mock.js's forceStop
  // reports a fixed costUSD: 0.02) instead of waiting out the ~9s natural
  // script.
  document.getElementById('live-view-stop').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await waitFor(() => document.getElementById('live-view').dataset.state === 'stopped');

  const costAfterDone = document.getElementById('header-session-cost').textContent;
  assert.notEqual(costAfterDone, costBefore, 'the header cost figure must update once the mission completes');
  assert.equal(source.readyState, 2, "the 'done' handler must close the EventSource (readyState CLOSED) instead of leaving it open to auto-reconnect");

  // A real EventSource does NOT self-close when the server ends the HTTP
  // response right after 'done' (see server/routes/missions.js's res.end())
  // — it treats that as a dropped connection and auto-reconnects, at which
  // point the server replays the exact same status+done for the
  // now-finished mission. MockEventSource._endStream simulates that full
  // loop now (this is the regression coverage: before the fix, this replay
  // re-fired onDone and re-accumulated cost/duration on every reconnect).
  // Waiting comfortably past the (shortened, test-only) retry delay proves
  // no reconnect ever gets scheduled, because close() already ran
  // synchronously inside the 'done' handler.
  await new Promise((resolve) => setTimeout(resolve, mock.__test__.MockEventSource.RECONNECT_DELAY_MS * 5));

  assert.equal(
    document.getElementById('header-session-cost').textContent,
    costAfterDone,
    'cost must not accumulate again from a simulated reconnect replay',
  );
  assert.equal(source.readyState, 2, 'the source must remain closed, not have auto-reconnected');

  document.getElementById('live-view-back').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await waitFor(() => document.getElementById('launcher-view').hidden === false);
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
