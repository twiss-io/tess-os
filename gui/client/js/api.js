// Tess OS Mission Control — API transport.
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss
//
// Every /api/* request carries the per-launch token as an Authorization
// header (fetch) or ?token= query param (EventSource, which cannot set
// headers) — see server/index.js extractToken(). setToken() is called once
// at boot from the URL; the token is never written back to the address bar.

let currentToken = null;

export function setToken(token) {
  currentToken = token || null;
}

function authHeaders() {
  return currentToken ? { Authorization: `Bearer ${currentToken}` } : {};
}

class ApiError extends Error {
  constructor(status, body) {
    super(`tess-gui API request failed: ${status}`);
    this.status = status;
    this.body = body;
  }
}

async function request(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: { ...authHeaders(), ...(opts.headers || {}) },
  });
  if (!res.ok) {
    let body = null;
    try {
      body = await res.json();
    } catch {
      /* no JSON body */
    }
    throw new ApiError(res.status, body);
  }
  if (res.status === 204) return null;
  return res.json();
}

function jsonBody(payload) {
  return {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  };
}

export const api = {
  getHealth: () => request('/api/health'),
  getCommands: () => request('/api/commands'),
  getRoster: () => request('/api/roster'),
  getMetricsSummary: (days = 7) => request(`/api/metrics/summary?days=${encodeURIComponent(days)}`),
  getMetricsCommands: (days = 30) => request(`/api/metrics/commands?days=${encodeURIComponent(days)}`),
  getTimeline: () => request('/api/timeline'),
  getMissions: () => request('/api/missions'),
  createMission: (prompt, label) => request('/api/missions', jsonBody(label ? { prompt, label } : { prompt })),
  stopMission: (id) => request(`/api/missions/${encodeURIComponent(id)}/stop`, { method: 'POST' }),
  getSavedMissions: () => request('/api/saved-missions'),
  createSavedMission: (label, prompt) => request('/api/saved-missions', jsonBody({ label, prompt })),
  deleteSavedMission: (id) => request(`/api/saved-missions/${encodeURIComponent(id)}`, { method: 'DELETE' }),
};

export function createMissionEventSource(missionId) {
  const url = `/api/missions/${encodeURIComponent(missionId)}/events?token=${encodeURIComponent(currentToken || '')}`;
  return new EventSource(url);
}

export { ApiError };
