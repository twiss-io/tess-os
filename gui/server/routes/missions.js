// tess-gui routes — GET/POST /api/missions, POST /api/missions/:id/stop,
// GET /api/missions/:id/events (SSE), append-only mission ledger.
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss
import crypto from 'node:crypto';
import fsp from 'node:fs/promises';
import path from 'node:path';

import { sendJson, readJsonBody } from './util.js';
import { getClaudeHealth } from './health.js';

const MAX_CONCURRENT = 3;
const MAX_BUFFER = 500;

function countRunning(missions) {
  let running = 0;
  for (const mission of missions.values()) {
    if (mission.status === 'running') running += 1;
  }
  return running;
}

function publicMission(mission) {
  return {
    id: mission.id,
    label: mission.label,
    prompt: mission.prompt,
    status: mission.status,
    startedAt: mission.startedAt,
    endedAt: mission.endedAt,
    costUSD: mission.costUSD,
    usage: mission.usage,
  };
}

function sseWrite(res, eventName, dataObj) {
  try {
    res.write(`event: ${eventName}\ndata: ${JSON.stringify(dataObj)}\n\n`);
  } catch {
    // subscriber connection is already gone
  }
}

function broadcast(mission, eventName, dataObj) {
  for (const res of mission.subscribers) sseWrite(res, eventName, dataObj);
}

async function appendLedger(ctx, mission) {
  const line =
    JSON.stringify({
      id: mission.id,
      label: mission.label,
      prompt: mission.prompt,
      startedAt: mission.startedAt,
      endedAt: mission.endedAt,
      status: mission.status,
      costUSD: mission.costUSD,
      usage: mission.usage,
    }) + '\n';

  ctx.ledgerQueue = ctx.ledgerQueue.then(
    async () => {
      await fsp.mkdir(path.dirname(ctx.ledgerPath), { recursive: true });
      await fsp.appendFile(ctx.ledgerPath, line, 'utf8');
    },
    () => {},
  );

  try {
    await ctx.ledgerQueue;
  } catch (err) {
    console.error('tess-gui: failed to append mission ledger:', err?.message ?? err);
  }
}

function finishMission(ctx, mission, { code = null } = {}) {
  if (mission.endedAt) return; // already finished — never double-finalize
  mission.endedAt = new Date().toISOString();
  if (mission.stoppedByUser) {
    mission.status = 'stopped';
  } else if (code === 0) {
    mission.status = 'done';
  } else {
    mission.status = 'error';
  }

  const durationMs = Date.parse(mission.endedAt) - Date.parse(mission.startedAt);
  broadcast(mission, 'done', { status: mission.status, costUSD: mission.costUSD, durationMs });
  for (const res of mission.subscribers) {
    try {
      res.end();
    } catch {
      /* already closed */
    }
  }
  mission.subscribers.clear();

  appendLedger(ctx, mission).catch(() => {});
}

export async function handleListMissions(ctx, req, res) {
  sendJson(res, 200, { missions: Array.from(ctx.missions.values()).map(publicMission) });
}

export async function handleCreateMission(ctx, req, res) {
  let body;
  try {
    body = await readJsonBody(req);
  } catch (err) {
    sendJson(res, err.statusCode ?? 400, { error: 'invalid request body' });
    return;
  }

  const prompt = typeof body.prompt === 'string' ? body.prompt.trim() : '';
  if (!prompt) {
    sendJson(res, 400, { error: 'prompt is required' });
    return;
  }
  const label = typeof body.label === 'string' && body.label.trim() ? body.label.trim() : prompt.slice(0, 80);

  // Mission launch is a server-side authority boundary. Re-use the same
  // probe that backs /api/health, but intentionally give callers no CLI
  // detail: an unavailable, incompatible, failed, or unresolved probe must
  // never be able to reach runMission().
  const claude = await getClaudeHealth(ctx);
  if (claude.probeFailed || !claude.resolved || !claude.compatible) {
    sendJson(res, 503, { error: 'service unavailable' });
    return;
  }

  if (countRunning(ctx.missions) >= MAX_CONCURRENT) {
    sendJson(res, 409, { error: 'maximum concurrent missions reached' });
    return;
  }

  const id = crypto.randomUUID();
  const mission = {
    id,
    label,
    prompt,
    status: 'running',
    startedAt: new Date().toISOString(),
    endedAt: null,
    costUSD: null,
    usage: null,
    stoppedByUser: false,
    buffer: [],
    subscribers: new Set(),
    proc: null,
  };
  ctx.missions.set(id, mission);

  const onEvent = (event) => {
    mission.buffer.push(event);
    if (mission.buffer.length > MAX_BUFFER) mission.buffer.shift();
    if (event && event.type === 'result') {
      if (typeof event.total_cost_usd === 'number') mission.costUSD = event.total_cost_usd;
      if (event.usage) mission.usage = event.usage;
    }
    broadcast(mission, 'msg', event);
  };

  const onExit = (info) => finishMission(ctx, mission, info ?? {});

  try {
    mission.proc = ctx.deps.runMission({ dir: ctx.dir, prompt, onEvent, onExit });
  } catch (err) {
    console.error('tess-gui: failed to start mission:', err?.message ?? err);
    finishMission(ctx, mission, { code: null });
  }

  sendJson(res, 201, { id });
}

export async function handleStopMission(ctx, req, res, { params }) {
  const mission = ctx.missions.get(params.id);
  if (!mission) {
    sendJson(res, 404, { error: 'mission not found' });
    return;
  }

  mission.stoppedByUser = true;
  if (mission.status === 'running' && mission.proc && typeof mission.proc.stop === 'function') {
    try {
      mission.proc.stop();
    } catch (err) {
      console.error('tess-gui: error stopping mission:', err?.message ?? err);
    }
  }

  sendJson(res, 200, { ok: true });
}

export async function handleMissionEvents(ctx, req, res, { params }) {
  const mission = ctx.missions.get(params.id);
  if (!mission) {
    sendJson(res, 404, { error: 'mission not found' });
    return;
  }

  res.writeHead(200, {
    'Content-Type': 'text/event-stream; charset=utf-8',
    'Cache-Control': 'no-store',
    Connection: 'keep-alive',
  });

  sseWrite(res, 'status', { status: mission.status });
  for (const event of mission.buffer) sseWrite(res, 'msg', event);

  if (mission.status !== 'running') {
    const durationMs = mission.endedAt ? Date.parse(mission.endedAt) - Date.parse(mission.startedAt) : null;
    sseWrite(res, 'done', { status: mission.status, costUSD: mission.costUSD, durationMs });
    res.end();
    return;
  }

  mission.subscribers.add(res);
  const heartbeat = setInterval(() => {
    try {
      res.write(': heartbeat\n\n');
    } catch {
      /* ignore */
    }
  }, 15000);

  const cleanup = () => {
    clearInterval(heartbeat);
    mission.subscribers.delete(res);
  };
  req.on('close', cleanup);
  res.on('close', cleanup);
}
