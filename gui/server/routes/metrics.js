// tess-gui routes — GET /api/metrics/summary, GET /api/metrics/commands
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss
import fs from 'node:fs';
import readline from 'node:readline';

import { sendJson } from './util.js';

export const TOKENS_CAVEAT =
  'input_tokens may undercount actual usage by 100x+ due to a known Claude Code streaming-placeholder bug ' +
  '(anthropics/claude-code#28197) — treat as directional only, not exact.';

export const COST_NOTE =
  'missionCostUSD is a local estimate, not billing data — the Claude Code CLI computes it from a bundled ' +
  'price table, so it can drift from your actual Anthropic bill. It reflects costs reported for missions ' +
  'launched from this dashboard only; cost is not tracked for missions run outside tess-gui and is not ' +
  'available in historical session logs.';

export function parseDays(searchParams) {
  const raw = Number(searchParams.get('days'));
  if (!Number.isFinite(raw) || raw <= 0) return 7;
  return Math.min(Math.floor(raw), 90);
}

async function readLedgerEntries(ledgerPath) {
  let raw;
  try {
    raw = await fs.promises.readFile(ledgerPath, 'utf8');
  } catch {
    return [];
  }
  const entries = [];
  for (const line of raw.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      entries.push(JSON.parse(trimmed));
    } catch {
      // tolerate malformed ledger lines
    }
  }
  return entries;
}

export async function handleMetricsSummary(ctx, req, res, { searchParams }) {
  const days = parseDays(searchParams);

  let summary;
  try {
    summary = await ctx.deps.aggregateSessions({ projectsDir: ctx.projectsDir, instanceDir: ctx.dir, sinceDays: days });
  } catch (err) {
    console.error('tess-gui: aggregateSessions failed:', err?.message ?? err);
    summary = { days: [], totals: {} };
  }

  const cutoff = Date.now() - days * 24 * 60 * 60 * 1000;
  const ledgerEntries = await readLedgerEntries(ctx.ledgerPath);
  let missionCostUSD = 0;
  for (const entry of ledgerEntries) {
    const endedAt = entry?.endedAt ? Date.parse(entry.endedAt) : NaN;
    if (Number.isFinite(endedAt) && endedAt >= cutoff && typeof entry.costUSD === 'number') {
      missionCostUSD += entry.costUSD;
    }
  }

  sendJson(res, 200, {
    days: summary.days ?? [],
    totals: summary.totals ?? {},
    missionCostUSD,
    costNote: COST_NOTE,
    tokensCaveat: TOKENS_CAVEAT,
  });
}

export async function handleMetricsCommands(ctx, req, res, { searchParams }) {
  const days = parseDays(searchParams);
  const cutoff = Date.now() - days * 24 * 60 * 60 * 1000;
  const historyPath = ctx.historyPath;

  let readable = true;
  try {
    await fs.promises.access(historyPath, fs.constants.R_OK);
  } catch {
    readable = false;
  }

  if (!readable) {
    sendJson(res, 200, { commands: [] });
    return;
  }

  const buckets = new Map();
  await new Promise((resolve) => {
    const stream = fs.createReadStream(historyPath, { encoding: 'utf8' });
    const rl = readline.createInterface({ input: stream, crlfDelay: Infinity });
    rl.on('line', (line) => {
      const trimmed = line.trim();
      if (!trimmed) return;
      let entry;
      try {
        entry = JSON.parse(trimmed);
      } catch {
        return;
      }
      const timestamp = Number(entry.timestamp);
      if (!Number.isFinite(timestamp) || timestamp < cutoff) return;
      const display = typeof entry.display === 'string' ? entry.display : '';
      const command = display.startsWith('/') ? display.split(/\s+/)[0] : 'freeform';
      const bucket = buckets.get(command) ?? { count: 0, lastUsed: 0 };
      bucket.count += 1;
      if (timestamp > bucket.lastUsed) bucket.lastUsed = timestamp;
      buckets.set(command, bucket);
    });
    rl.on('close', resolve);
    stream.on('error', resolve);
  });

  const commands = Array.from(buckets.entries())
    .map(([command, { count, lastUsed }]) => ({ command, count, lastUsed: new Date(lastUsed).toISOString() }))
    .sort((a, b) => b.count - a.count);

  sendJson(res, 200, { commands });
}
