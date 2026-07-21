// tess-gui routes — GET/POST /api/saved-missions, DELETE /api/saved-missions/:id
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss
import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';

import { sendJson, readJsonBody } from './util.js';

async function readSaved(ctx) {
  try {
    const raw = await fs.readFile(ctx.savedMissionsPath, 'utf8');
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

async function writeSaved(ctx, missions) {
  await fs.mkdir(path.dirname(ctx.savedMissionsPath), { recursive: true });
  await fs.writeFile(ctx.savedMissionsPath, JSON.stringify(missions, null, 2), 'utf8');
}

// Chains every read-modify-write through ctx.savedMissionsQueue so
// concurrent requests never race on the same file.
function withQueue(ctx, fn) {
  const result = ctx.savedMissionsQueue.then(fn, fn);
  ctx.savedMissionsQueue = result.then(
    () => {},
    () => {},
  );
  return result;
}

export async function handleListSaved(ctx, req, res) {
  const missions = await withQueue(ctx, () => readSaved(ctx));
  sendJson(res, 200, { missions });
}

export async function handleCreateSaved(ctx, req, res) {
  let body;
  try {
    body = await readJsonBody(req);
  } catch (err) {
    sendJson(res, err.statusCode ?? 400, { error: 'invalid request body' });
    return;
  }

  const label = typeof body.label === 'string' ? body.label.trim() : '';
  const prompt = typeof body.prompt === 'string' ? body.prompt.trim() : '';
  if (!label || !prompt) {
    sendJson(res, 400, { error: 'label and prompt are required' });
    return;
  }

  const entry = { id: crypto.randomUUID(), label, prompt, createdAt: new Date().toISOString() };

  await withQueue(ctx, async () => {
    const missions = await readSaved(ctx);
    missions.push(entry);
    await writeSaved(ctx, missions);
  });

  sendJson(res, 201, entry);
}

export async function handleDeleteSaved(ctx, req, res, { params }) {
  let found = false;

  await withQueue(ctx, async () => {
    const missions = await readSaved(ctx);
    const next = missions.filter((m) => m.id !== params.id);
    found = next.length !== missions.length;
    if (found) await writeSaved(ctx, next);
  });

  if (!found) {
    sendJson(res, 404, { error: 'saved mission not found' });
    return;
  }
  sendJson(res, 200, { ok: true });
}
