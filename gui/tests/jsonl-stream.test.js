import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync, utimesSync, openSync, writeSync, closeSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { streamJsonlFile, aggregateSessions } from '../server/jsonl-stream.js';

function tmpDir() {
  return mkdtempSync(join(tmpdir(), 'tess-gui-jsonl-'));
}

test('streamJsonlFile: parses valid lines, skips malformed ones, ignores blank lines', async () => {
  const dir = tmpDir();
  const file = join(dir, 'session.jsonl');
  writeFileSync(
    file,
    [
      '{"a":1}',
      '',
      'not json',
      '{"a":2}',
      '   ',
      '{"a":3}',
    ].join('\n') + '\n',
  );

  const seen = [];
  const errors = [];
  const result = await streamJsonlFile(file, (obj) => seen.push(obj), {
    onError: (err, raw) => errors.push({ message: err.message, raw }),
  });

  try {
    assert.deepEqual(seen, [{ a: 1 }, { a: 2 }, { a: 3 }]);
    // '   ' is non-empty as a raw line (whitespace), so it IS attempted and fails to parse
    // — only the fully-empty '' line is skipped without counting.
    assert.equal(errors.length, 2);
    assert.deepEqual(errors.map((e) => e.raw), ['not json', '   ']);
    assert.equal(result.lines, 5); // 3 valid + 2 malformed; the one fully-empty line is not counted
    assert.equal(result.skipped, 2);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('streamJsonlFile: a throwing consumer aborts the stream and rejects with the same error', async () => {
  const dir = tmpDir();
  const file = join(dir, 'session.jsonl');
  writeFileSync(file, ['{"a":1}', '{"a":2}', '{"a":3}'].join('\n') + '\n');

  const seen = [];
  const boom = new Error('boom');
  await assert.rejects(
    streamJsonlFile(file, (obj) => {
      seen.push(obj);
      if (obj.a === 2) throw boom;
    }),
    (err) => err === boom,
  );

  try {
    assert.deepEqual(seen, [{ a: 1 }, { a: 2 }], 'must not process lines after the consumer throws');
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('streamJsonlFile: rejects on a missing file', async () => {
  await assert.rejects(streamJsonlFile('/no/such/file.jsonl', () => {}));
});

function writeSession(filePath, lines) {
  writeFileSync(filePath, lines.map((l) => JSON.stringify(l)).join('\n') + '\n');
}

function daysAgoIso(n, hour = 10) {
  const d = new Date(Date.now() - n * 24 * 60 * 60 * 1000);
  d.setUTCHours(hour, 0, 0, 0);
  return d.toISOString();
}

function dateBucket(iso) {
  return iso.slice(0, 10);
}

test('aggregateSessions: matches by cwd read from content (not the first line), aggregates tokens/models/sessions per day, ignores non-matching cwd and stale mtime', async () => {
  const root = tmpDir();
  const projectsDir = join(root, 'projects');
  const instanceDir = join(root, 'instance');
  mkdirSync(instanceDir, { recursive: true });

  const matchingProject = join(projectsDir, 'proj-a');
  mkdirSync(matchingProject, { recursive: true });

  const day1Ts = daysAgoIso(5, 10);
  const day1LaterTs = daysAgoIso(5, 11);
  const day2Ts = daysAgoIso(4, 9);
  const day1 = dateBucket(day1Ts);
  const day2 = dateBucket(day2Ts);

  // Real transcripts often carry a couple of header lines with no `cwd`
  // before the first line that has it — mirror that shape here.
  const day1File = join(matchingProject, 'session-1.jsonl');
  writeSession(day1File, [
    { type: 'last-prompt', sessionId: 's1' },
    { type: 'permission-mode', sessionId: 's1' },
    { type: 'system', cwd: instanceDir, sessionId: 's1' },
    {
      type: 'assistant',
      timestamp: day1Ts,
      sessionId: 's1',
      cwd: instanceDir,
      message: {
        model: 'claude-opus-4-8',
        usage: { input_tokens: 100, output_tokens: 20, cache_read_input_tokens: 5, cache_creation_input_tokens: 1 },
      },
    },
    {
      type: 'assistant',
      timestamp: day1LaterTs,
      sessionId: 's2',
      cwd: instanceDir,
      message: {
        model: '<synthetic>',
        usage: { input_tokens: 0, output_tokens: 0 },
      },
    },
    {
      type: 'assistant',
      timestamp: day2Ts,
      sessionId: 's1',
      cwd: instanceDir,
      message: {
        model: 'claude-opus-4-8',
        usage: { input_tokens: 50, output_tokens: 10 },
      },
    },
    // non-assistant lines must not contribute tokens/sessions
    { type: 'user', timestamp: day2Ts, sessionId: 's1', cwd: instanceDir },
  ]);

  // Different cwd — must be excluded entirely.
  const otherProject = join(projectsDir, 'proj-b');
  mkdirSync(otherProject, { recursive: true });
  writeSession(join(otherProject, 'session-2.jsonl'), [
    { type: 'system', cwd: join(root, 'not-the-instance') },
    {
      type: 'assistant',
      timestamp: day1Ts,
      sessionId: 'other',
      cwd: join(root, 'not-the-instance'),
      message: { model: 'claude-opus-4-8', usage: { input_tokens: 9999, output_tokens: 9999 } },
    },
  ]);

  // Matching cwd but mtime well outside the window — must be skipped
  // without even being opened for its cwd.
  const staleTs = daysAgoIso(400, 10);
  const staleFile = join(matchingProject, 'session-stale.jsonl');
  writeSession(staleFile, [
    { type: 'system', cwd: instanceDir },
    {
      type: 'assistant',
      timestamp: staleTs,
      sessionId: 'stale',
      cwd: instanceDir,
      message: { model: 'claude-opus-4-8', usage: { input_tokens: 8888, output_tokens: 8888 } },
    },
  ]);
  const oldTime = new Date(staleTs);
  utimesSync(staleFile, oldTime, oldTime);

  // A subagent-nested jsonl file must NOT be recursed into / aggregated —
  // only top-level per-project session files are in scope.
  const subagentDir = join(matchingProject, 'session-1', 'subagents');
  mkdirSync(subagentDir, { recursive: true });
  writeSession(join(subagentDir, 'agent-x.jsonl'), [
    { type: 'system', cwd: instanceDir },
    {
      type: 'assistant',
      timestamp: day1Ts,
      sessionId: 'subagent',
      cwd: instanceDir,
      message: { model: 'claude-opus-4-8', usage: { input_tokens: 7777, output_tokens: 7777 } },
    },
  ]);

  // A non-.jsonl file alongside real sessions must be ignored.
  writeFileSync(join(matchingProject, 'notes.json'), '{}');

  try {
    const result = await aggregateSessions({ projectsDir, instanceDir, sinceDays: 30 });

    assert.equal(result.days.length, 2);
    const [d1, d2] = result.days;

    assert.equal(d1.date, day1);
    assert.equal(d1.sessions, 2); // s1, s2
    assert.deepEqual(d1.tokens, { input: 100, output: 20, cacheRead: 5, cacheCreation: 1 });
    assert.deepEqual(d1.byModel, {
      'claude-opus-4-8': { input: 100, output: 20 },
      '<synthetic>': { input: 0, output: 0 },
    });

    assert.equal(d2.date, day2);
    assert.equal(d2.sessions, 1); // s1 again
    assert.deepEqual(d2.tokens, { input: 50, output: 10, cacheRead: 0, cacheCreation: 0 });
    assert.deepEqual(d2.byModel, { 'claude-opus-4-8': { input: 50, output: 10 } });

    assert.equal(result.totals.sessions, 2, 'distinct sessions across the whole window, not summed per-day');
    assert.deepEqual(result.totals.tokens, { input: 150, output: 30, cacheRead: 5, cacheCreation: 1 });
    assert.deepEqual(result.totals.byModel, {
      'claude-opus-4-8': { input: 150, output: 30 },
      '<synthetic>': { input: 0, output: 0 },
    });
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test('aggregateSessions: bounded memory on a large (>=50MB) matching session file', async () => {
  const root = tmpDir();
  const projectsDir = join(root, 'projects');
  const instanceDir = join(root, 'instance');
  mkdirSync(instanceDir, { recursive: true });
  const project = join(projectsDir, 'proj-big');
  mkdirSync(project, { recursive: true });
  const file = join(project, 'big-session.jsonl');

  const TARGET_BYTES = 55 * 1024 * 1024;
  const fd = openSync(file, 'w');
  try {
    writeSync(fd, JSON.stringify({ type: 'system', cwd: instanceDir }) + '\n');
    let written = 0;
    let i = 0;
    const filler = 'x'.repeat(2000); // pad each line so we reach the target size without absurd line counts
    while (written < TARGET_BYTES) {
      const line =
        JSON.stringify({
          type: 'assistant',
          timestamp: `2026-06-01T${String(i % 24).padStart(2, '0')}:00:00.000Z`,
          sessionId: `s${i % 500}`,
          cwd: instanceDir,
          message: {
            model: i % 7 === 0 ? '<synthetic>' : 'claude-opus-4-8',
            usage: { input_tokens: 10, output_tokens: 5, cache_read_input_tokens: 1, cache_creation_input_tokens: 1 },
          },
          filler,
        }) + '\n';
      written += writeSync(fd, line);
      i++;
    }
  } finally {
    closeSync(fd);
  }

  try {
    if (global.gc) global.gc();
    const before = process.memoryUsage().rss;
    const result = await aggregateSessions({ projectsDir, instanceDir, sinceDays: 3650 });
    if (global.gc) global.gc();
    const after = process.memoryUsage().rss;
    const deltaMb = (after - before) / (1024 * 1024);

    assert.ok(result.totals.tokens.input > 0, 'sanity: real data was aggregated');
    // The file is ~55MB; a bounded streaming aggregator should need nowhere
    // near that much resident memory to process it (no whole-file buffering).
    assert.ok(deltaMb < 150, `expected bounded RSS growth, got +${deltaMb.toFixed(1)}MB`);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
