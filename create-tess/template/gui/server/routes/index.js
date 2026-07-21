// tess-gui routes — router table and dispatch.
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss
import { handleHealth } from './health.js';
import { handleCommands } from './commands.js';
import { handleRoster } from './roster.js';
import { handleMetricsSummary, handleMetricsCommands } from './metrics.js';
import { handleTimeline } from './timeline.js';
import {
  handleListMissions,
  handleCreateMission,
  handleStopMission,
  handleMissionEvents,
} from './missions.js';
import { handleListSaved, handleCreateSaved, handleDeleteSaved } from './saved-missions.js';
import { sendJson } from './util.js';

function compilePattern(pattern) {
  const paramNames = [];
  const regexSource = pattern
    .split('/')
    .map((segment) => {
      if (segment.startsWith(':')) {
        paramNames.push(segment.slice(1));
        return '([^/]+)';
      }
      return segment.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    })
    .join('/');
  return { regex: new RegExp(`^${regexSource}$`), paramNames };
}

const ROUTE_DEFS = [
  { method: 'GET', pattern: '/api/health', handler: handleHealth },
  { method: 'GET', pattern: '/api/commands', handler: handleCommands },
  { method: 'GET', pattern: '/api/roster', handler: handleRoster },
  { method: 'GET', pattern: '/api/metrics/summary', handler: handleMetricsSummary },
  { method: 'GET', pattern: '/api/metrics/commands', handler: handleMetricsCommands },
  { method: 'GET', pattern: '/api/timeline', handler: handleTimeline },
  { method: 'GET', pattern: '/api/missions', handler: handleListMissions },
  { method: 'POST', pattern: '/api/missions', handler: handleCreateMission },
  { method: 'POST', pattern: '/api/missions/:id/stop', handler: handleStopMission },
  { method: 'GET', pattern: '/api/missions/:id/events', handler: handleMissionEvents },
  { method: 'GET', pattern: '/api/saved-missions', handler: handleListSaved },
  { method: 'POST', pattern: '/api/saved-missions', handler: handleCreateSaved },
  { method: 'DELETE', pattern: '/api/saved-missions/:id', handler: handleDeleteSaved },
];

const ROUTES = ROUTE_DEFS.map((def) => ({ ...def, ...compilePattern(def.pattern) }));

export function createRouter(ctx) {
  return async function router(req, res, pathname, searchParams) {
    for (const route of ROUTES) {
      if (route.method !== req.method) continue;
      const match = route.regex.exec(pathname);
      if (!match) continue;

      const params = {};
      route.paramNames.forEach((name, i) => {
        params[name] = decodeURIComponent(match[i + 1]);
      });

      try {
        await route.handler(ctx, req, res, { params, searchParams });
      } catch (err) {
        console.error('tess-gui: route handler error:', err);
        if (!res.headersSent) {
          sendJson(res, 500, { error: 'internal server error' });
        } else {
          try {
            res.end();
          } catch {
            /* connection already gone */
          }
        }
      }
      return true;
    }
    return false;
  };
}
