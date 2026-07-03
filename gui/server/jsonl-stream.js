// tess-gui jsonl-stream — backpressure-safe streaming JSONL reader and
// session/token aggregator for Claude Code project transcripts.
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss
import { createReadStream } from 'node:fs';
import { readdir, stat } from 'node:fs/promises';
import { createInterface } from 'node:readline';
import path from 'node:path';

// How many leading lines of a candidate session file we'll scan looking for a
// `cwd` field before giving up. Real transcripts open with a handful of
// metadata lines (last-prompt, permission-mode, ...) before the first line
// that carries `cwd` — see streamJsonlFile/aggregateSessions doc below.
const CWD_PROBE_LINE_LIMIT = 50;

export function streamJsonlFile(filePath, onObj, { onError } = {}) {
  return new Promise((resolve, reject) => {
    let lines = 0;
    let skipped = 0;
    let settled = false;

    const stream = createReadStream(filePath, { encoding: 'utf8' });
    const rl = createInterface({ input: stream, crlfDelay: Infinity });

    const cleanup = () => {
      rl.removeAllListeners();
      stream.removeAllListeners('error');
      rl.close();
      stream.destroy();
    };

    const fail = (err) => {
      if (settled) return;
      settled = true;
      cleanup();
      reject(err);
    };

    const succeed = () => {
      if (settled) return;
      settled = true;
      resolve({ lines, skipped });
    };

    rl.on('line', (line) => {
      if (settled || line.length === 0) return;
      lines++;
      let obj;
      try {
        obj = JSON.parse(line);
      } catch (parseErr) {
        skipped++;
        if (onError) {
          try {
            onError(parseErr, line);
          } catch {
            // onError itself must never abort the stream.
          }
        }
        return;
      }
      try {
        onObj(obj);
      } catch (consumerErr) {
        // Fail-loud: a throwing consumer aborts the stream and rejects.
        fail(consumerErr);
      }
    });

    rl.on('close', succeed);
    stream.on('error', fail);
    rl.on('error', fail);
  });
}

// Reads forward (never the whole file) until it finds a parseable line
// carrying a string `cwd` field, or gives up after CWD_PROBE_LINE_LIMIT
// lines / EOF. Real transcripts do NOT always carry `cwd` on their very
// first line (queue-operation/last-prompt/permission-mode header lines
// often precede it) — this scans rather than trusting line 1, and never
// attempts to reconstruct a cwd from the project directory's slug name.
function findCwd(filePath) {
  return new Promise((resolve) => {
    let settled = false;
    let probed = 0;
    const stream = createReadStream(filePath, { encoding: 'utf8' });
    const rl = createInterface({ input: stream, crlfDelay: Infinity });

    const finish = (value) => {
      if (settled) return;
      settled = true;
      rl.removeAllListeners();
      stream.removeAllListeners('error');
      rl.close();
      stream.destroy();
      resolve(value);
    };

    rl.on('line', (line) => {
      if (settled || line.length === 0) return;
      probed++;
      try {
        const obj = JSON.parse(line);
        if (typeof obj.cwd === 'string') {
          finish(obj.cwd);
          return;
        }
      } catch {
        // keep scanning past malformed lines
      }
      if (probed >= CWD_PROBE_LINE_LIMIT) finish(null);
    });
    rl.on('close', () => finish(null));
    stream.on('error', () => finish(null));
    rl.on('error', () => finish(null));
  });
}

function emptyDayBucket() {
  return {
    sessions: new Set(),
    tokens: { input: 0, output: 0, cacheRead: 0, cacheCreation: 0 },
    byModel: new Map(),
  };
}

export async function aggregateSessions({ projectsDir, instanceDir, sinceDays }) {
  const cutoffMs = Date.now() - sinceDays * 24 * 60 * 60 * 1000;
  const normalizedInstanceDir = path.resolve(instanceDir);

  const dayMap = new Map();
  const allSessions = new Set();

  let projectEntries;
  try {
    projectEntries = await readdir(projectsDir, { withFileTypes: true });
  } catch {
    return { days: [], totals: emptyTotals() };
  }

  for (const projectEntry of projectEntries) {
    if (!projectEntry.isDirectory()) continue;
    const projectDir = path.join(projectsDir, projectEntry.name);

    let fileEntries;
    try {
      fileEntries = await readdir(projectDir, { withFileTypes: true });
    } catch {
      continue;
    }

    for (const fileEntry of fileEntries) {
      if (!fileEntry.isFile() || !fileEntry.name.endsWith('.jsonl')) continue;
      const filePath = path.join(projectDir, fileEntry.name);

      let stats;
      try {
        stats = await stat(filePath);
      } catch {
        continue;
      }
      // Transcripts are append-only, so mtime reflects the latest write: an
      // mtime older than the window means every line in the file predates it.
      if (stats.mtimeMs < cutoffMs) continue;

      const cwd = await findCwd(filePath);
      if (cwd === null || path.resolve(cwd) !== normalizedInstanceDir) continue;

      await streamJsonlFile(
        filePath,
        (obj) => {
          if (obj.type !== 'assistant') return;
          if (typeof obj.timestamp !== 'string') return;
          const tsMs = Date.parse(obj.timestamp);
          if (Number.isFinite(tsMs) && tsMs < cutoffMs) return;

          const date = obj.timestamp.slice(0, 10); // ISO-8601 UTC timestamp — no TZ conversion needed
          let day = dayMap.get(date);
          if (!day) {
            day = emptyDayBucket();
            dayMap.set(date, day);
          }

          if (typeof obj.sessionId === 'string') {
            day.sessions.add(obj.sessionId);
            allSessions.add(obj.sessionId);
          }

          const usage = obj.message?.usage ?? {};
          const input = usage.input_tokens ?? 0;
          const output = usage.output_tokens ?? 0;
          const cacheRead = usage.cache_read_input_tokens ?? 0;
          const cacheCreation = usage.cache_creation_input_tokens ?? 0;

          day.tokens.input += input;
          day.tokens.output += output;
          day.tokens.cacheRead += cacheRead;
          day.tokens.cacheCreation += cacheCreation;

          // model is never filtered here, including the literal "<synthetic>"
          // marker for zero-usage error/retry lines — display filtering is
          // the client's concern, not the aggregator's.
          const model = obj.message?.model ?? 'unknown';
          let modelStats = day.byModel.get(model);
          if (!modelStats) {
            modelStats = { input: 0, output: 0 };
            day.byModel.set(model, modelStats);
          }
          modelStats.input += input;
          modelStats.output += output;
        },
        { onError: () => {} },
      );
    }
  }

  const days = [...dayMap.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, day]) => ({
      date,
      sessions: day.sessions.size,
      tokens: { ...day.tokens },
      byModel: Object.fromEntries(day.byModel),
    }));

  const totals = days.reduce((acc, day) => {
    acc.tokens.input += day.tokens.input;
    acc.tokens.output += day.tokens.output;
    acc.tokens.cacheRead += day.tokens.cacheRead;
    acc.tokens.cacheCreation += day.tokens.cacheCreation;
    for (const [model, stats] of Object.entries(day.byModel)) {
      if (!acc.byModel[model]) acc.byModel[model] = { input: 0, output: 0 };
      acc.byModel[model].input += stats.input;
      acc.byModel[model].output += stats.output;
    }
    return acc;
  }, emptyTotals());
  totals.sessions = allSessions.size;

  return { days, totals };
}

function emptyTotals() {
  return { sessions: 0, tokens: { input: 0, output: 0, cacheRead: 0, cacheCreation: 0 }, byModel: {} };
}
