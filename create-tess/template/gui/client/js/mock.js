// Tess OS Mission Control — ?mock=1 fetch/EventSource shim.
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss
//
// installMock() replaces window.fetch and window.EventSource with
// fixture-backed fakes that speak the exact same URL/shape contract as the
// real server (see gui/server/routes/*.js) — app.js and api.js run
// unmodified in mock mode, only the transport differs.
import {
  MOCK_HEALTH,
  MOCK_COMMANDS,
  MOCK_ROSTER,
  MOCK_TIMELINE,
  MOCK_METRICS_SUMMARY,
  MOCK_METRICS_COMMANDS,
  MOCK_SAVED_MISSIONS_SEED,
  MISSION_SCRIPT_TEMPLATE,
} from './mock-data.js';

const MAX_CONCURRENT = 3;

let missions = [];
let savedMissions = [];
let nextId = 1;
const activeSources = new Map(); // missionId -> MockEventSource

export function resetMockState() {
  missions = [];
  savedMissions = MOCK_SAVED_MISSIONS_SEED.map((m) => ({ ...m }));
  nextId = 1;
  activeSources.clear();
}
resetMockState();

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
}

function countRunning() {
  return missions.filter((m) => m.status === 'running').length;
}

function createMockMission(body) {
  let payload;
  try {
    payload = JSON.parse(body || '{}');
  } catch {
    return jsonResponse({ error: 'invalid request body' }, 400);
  }
  const prompt = typeof payload.prompt === 'string' ? payload.prompt.trim() : '';
  if (!prompt) return jsonResponse({ error: 'prompt is required' }, 400);
  if (countRunning() >= MAX_CONCURRENT) {
    return jsonResponse({ error: 'maximum concurrent missions reached' }, 409);
  }

  const label = typeof payload.label === 'string' && payload.label.trim() ? payload.label.trim() : prompt.slice(0, 80);
  const id = `mock-${nextId++}`;
  const mission = {
    id,
    label,
    prompt,
    status: 'running',
    startedAt: new Date().toISOString(),
    endedAt: null,
    costUSD: null,
    usage: null,
  };
  missions.push(mission);
  return jsonResponse({ id }, 201);
}

function stopMockMission(id) {
  const mission = missions.find((m) => m.id === id);
  if (!mission) return jsonResponse({ error: 'mission not found' }, 404);
  const source = activeSources.get(id);
  if (mission.status === 'running' && source) source.forceStop();
  return jsonResponse({ ok: true });
}

function listSavedMissions() {
  return jsonResponse({ missions: savedMissions });
}

function createSavedMission(body) {
  let payload;
  try {
    payload = JSON.parse(body || '{}');
  } catch {
    return jsonResponse({ error: 'invalid request body' }, 400);
  }
  const label = typeof payload.label === 'string' ? payload.label.trim() : '';
  const prompt = typeof payload.prompt === 'string' ? payload.prompt.trim() : '';
  if (!label || !prompt) return jsonResponse({ error: 'label and prompt are required' }, 400);
  const entry = { id: `saved-mock-${nextId++}`, label, prompt, createdAt: new Date().toISOString() };
  savedMissions.push(entry);
  return jsonResponse(entry, 201);
}

function deleteSavedMission(id) {
  const before = savedMissions.length;
  savedMissions = savedMissions.filter((m) => m.id !== id);
  if (savedMissions.length === before) return jsonResponse({ error: 'saved mission not found' }, 404);
  return jsonResponse({ ok: true });
}

function route(pathname, method, searchParams, body) {
  if (pathname === '/api/health' && method === 'GET') return jsonResponse(MOCK_HEALTH);
  if (pathname === '/api/commands' && method === 'GET') return jsonResponse(MOCK_COMMANDS);
  if (pathname === '/api/roster' && method === 'GET') return jsonResponse(MOCK_ROSTER);
  if (pathname === '/api/timeline' && method === 'GET') return jsonResponse(MOCK_TIMELINE);
  if (pathname === '/api/metrics/summary' && method === 'GET') return jsonResponse(MOCK_METRICS_SUMMARY);
  if (pathname === '/api/metrics/commands' && method === 'GET') return jsonResponse(MOCK_METRICS_COMMANDS);
  if (pathname === '/api/missions' && method === 'GET') return jsonResponse({ missions });
  if (pathname === '/api/missions' && method === 'POST') return createMockMission(body);
  if (pathname === '/api/saved-missions' && method === 'GET') return listSavedMissions();
  if (pathname === '/api/saved-missions' && method === 'POST') return createSavedMission(body);

  const stopMatch = /^\/api\/missions\/([^/]+)\/stop$/.exec(pathname);
  if (stopMatch && method === 'POST') return stopMockMission(decodeURIComponent(stopMatch[1]));

  const deleteSavedMatch = /^\/api\/saved-missions\/([^/]+)$/.exec(pathname);
  if (deleteSavedMatch && method === 'DELETE') return deleteSavedMission(decodeURIComponent(deleteSavedMatch[1]));

  return jsonResponse({ error: 'not found' }, 404);
}

function mockFetch(input, init = {}) {
  const raw = typeof input === 'string' ? input : input.url;
  const url = new URL(raw, window.location.origin);
  const method = (init.method || 'GET').toUpperCase();
  return new Promise((resolve) => {
    setTimeout(() => resolve(route(url.pathname, method, url.searchParams, init.body)), 120);
  });
}

class MockEventSource extends EventTarget {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 2;

  // Real browsers default to ~3s between reconnect attempts; shortened here
  // so tests exercising the reconnect-replay path don't block on real time.
  static RECONNECT_DELAY_MS = 30;

  constructor(url) {
    super();
    this.url = url;
    this.readyState = 0;
    this._timers = [];
    this._reconnectTimer = null;
    this._startedAt = Date.now();
    const match = /\/api\/missions\/([^/]+)\/events/.exec(new URL(url, window.location.origin).pathname);
    this._missionId = match ? decodeURIComponent(match[1]) : null;
    if (this._missionId) activeSources.set(this._missionId, this);
    queueMicrotask(() => this._start());
  }

  _start() {
    this.readyState = 1;
    this.dispatchEvent(new Event('open'));
    const mission = missions.find((m) => m.id === this._missionId);
    if (!mission || mission.status !== 'running') {
      // Reconnecting to an already-finished mission — the real server
      // replays status+done immediately then ends the response (see
      // handleMissionEvents). A real EventSource does NOT self-close on
      // that: it auto-reconnects after the retry delay and gets the exact
      // same replay again, forever, until the client calls .close(). That
      // full loop is simulated below (_endStream) rather than closing here,
      // so non-idempotent 'done' handlers get caught by tests instead of
      // hidden by the mock — this is exactly the gap that hid the
      // reconnect double-count bug last time.
      this._emit({ event: 'status', data: { status: mission ? mission.status : 'error' } });
      this._emit({ event: 'done', data: { status: mission ? mission.status : 'error', costUSD: mission?.costUSD ?? null, durationMs: null } });
      return;
    }
    let elapsed = 0;
    for (const step of MISSION_SCRIPT_TEMPLATE) {
      elapsed += step.delay;
      this._timers.push(setTimeout(() => this._emit(step), elapsed));
    }
  }

  _emit(step) {
    if (this.readyState === 2) return;
    this.dispatchEvent(new MessageEvent(step.event, { data: JSON.stringify(step.data) }));
    if (step.event === 'done') {
      const mission = missions.find((m) => m.id === this._missionId);
      if (mission) {
        mission.status = step.data.status;
        mission.endedAt = new Date().toISOString();
        mission.costUSD = step.data.costUSD;
      }
      this._endStream();
    }
  }

  // Mirrors the server ending the HTTP response right after 'done': a real
  // EventSource fires 'error', drops to CONNECTING, and retries later —
  // it does not transition to CLOSED on its own. If the consumer already
  // called close() synchronously from within its 'done' handler (readyState
  // is CLOSED by the time we get here), this is correctly a no-op.
  _endStream() {
    if (this.readyState === 2) return;
    this._timers.forEach(clearTimeout);
    this._timers = [];
    this.readyState = 0;
    this.dispatchEvent(new Event('error'));
    this._reconnectTimer = setTimeout(() => {
      if (this.readyState !== 2) this._start();
    }, MockEventSource.RECONNECT_DELAY_MS);
  }

  forceStop() {
    this._timers.forEach(clearTimeout);
    this._timers = [];
    const elapsed = Date.now() - this._startedAt;
    this._emit({ event: 'status', data: { status: 'stopped' } });
    this._emit({ event: 'done', data: { status: 'stopped', costUSD: 0.02, durationMs: elapsed } });
  }

  close() {
    this._timers.forEach(clearTimeout);
    this._timers = [];
    if (this._reconnectTimer) clearTimeout(this._reconnectTimer);
    this._reconnectTimer = null;
    this.readyState = 2;
    if (this._missionId && activeSources.get(this._missionId) === this) activeSources.delete(this._missionId);
  }
}

export function installMock() {
  globalThis.fetch = mockFetch;
  globalThis.EventSource = MockEventSource;
}

export const __test__ = {
  MockEventSource,
  missions: () => missions,
  savedMissions: () => savedMissions,
  activeSources: () => activeSources,
};
