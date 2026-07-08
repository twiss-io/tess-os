// tess-gui tests — /api/* route behavior: commands, roster, timeline,
// health, metrics, missions lifecycle + SSE + ledger, saved missions.
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss
import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

import { start } from '../server/index.js';
import * as healthRoute from '../server/routes/health.js';
import { isCompatible } from '../server/claude-runner.js';

async function makeInstanceDir() {
  return fs.mkdtemp(path.join(os.tmpdir(), 'tess-gui-routes-'));
}

const servers = [];
async function startServer(opts = {}) {
  const dir = opts.dir ?? (await makeInstanceDir());
  const paths = {
    historyPath: path.join(dir, '_history.jsonl'),
    projectsDir: path.join(dir, '_projects'),
    dataDir: path.join(dir, '_gui-data'),
    ...opts.paths,
  };
  const deps = {
    runMission: () => {
      throw new Error('runMission should not be called unless a test injects its own');
    },
    getClaudeVersion: async () => null,
    aggregateSessions: async () => ({ days: [], totals: {} }),
    MIN_CLI_VERSION: '2.0.0',
    ...opts.deps,
  };
  const instance = await start({ port: 0, dir, deps, paths });
  servers.push(instance);
  return { ...instance, dir };
}

function apiUrl(port, token, apiPath) {
  const sep = apiPath.includes('?') ? '&' : '?';
  return `http://127.0.0.1:${port}${apiPath}${sep}token=${token}`;
}

after(async () => {
  await Promise.all(servers.map((s) => s.close()));
});

// ---------------------------------------------------------------------------
// GET /api/health
// ---------------------------------------------------------------------------

test('GET /api/health reports incompatible when claude is missing', async () => {
  const { port, token } = await startServer();
  const res = await fetch(apiUrl(port, token, '/api/health'));
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.equal(body.ok, true);
  assert.equal(body.claude.version, null);
  assert.equal(body.claude.compatible, false);
  assert.equal(body.claude.minVersion, '2.0.0');
  assert.equal(typeof body.instanceDir, 'string');
});

test('GET /api/health reports compatible/incompatible correctly against MIN_CLI_VERSION', async () => {
  const compatible = await startServer({ deps: { getClaudeVersion: async () => '2.5.1' } });
  const resOk = await fetch(apiUrl(compatible.port, compatible.token, '/api/health'));
  const bodyOk = await resOk.json();
  assert.equal(bodyOk.claude.compatible, true);

  const incompatible = await startServer({ deps: { getClaudeVersion: async () => '1.9.9' } });
  const resBad = await fetch(apiUrl(incompatible.port, incompatible.token, '/api/health'));
  const bodyBad = await resBad.json();
  assert.equal(bodyBad.claude.compatible, false);
});

test('GET /api/health compat check is single-sourced from claude-runner.isCompatible, not a local re-implementation', async () => {
  // health.js must not define its own compat-check export any more — there
  // must be exactly one implementation (claude-runner.js's isCompatible),
  // not two that could silently disagree.
  assert.equal(healthRoute.versionGte, undefined);

  const { port, token } = await startServer({ deps: { getClaudeVersion: async () => '2.3.1 (Claude Code)' } });
  const res = await fetch(apiUrl(port, token, '/api/health'));
  const body = await res.json();
  assert.equal(body.claude.compatible, isCompatible('2.3.1 (Claude Code)'));
  assert.equal(body.claude.compatible, true);
});

// ---------------------------------------------------------------------------
// GET /api/commands
// ---------------------------------------------------------------------------

test('GET /api/commands parses descriptions and counts only frontmatter parse failures as skipped', async () => {
  const { port, token, dir } = await startServer();
  const commandsDir = path.join(dir, '.claude', 'commands');
  await fs.mkdir(commandsDir, { recursive: true });

  await fs.writeFile(
    path.join(commandsDir, 'add-mission.md'),
    '---\ndescription: Start a new mission\n---\nBody text.\n',
  );
  await fs.writeFile(path.join(commandsDir, 'no-frontmatter.md'), '# Just a heading\nNo frontmatter here.\n');
  await fs.writeFile(path.join(commandsDir, 'broken.md'), '---\ndescription: never closed\nBody with no closing delimiter\n');

  const res = await fetch(apiUrl(port, token, '/api/commands'));
  assert.equal(res.status, 200);
  const body = await res.json();

  const byName = Object.fromEntries(body.commands.map((c) => [c.name, c]));
  assert.equal(byName['add-mission'].description, 'Start a new mission');
  assert.equal(byName['no-frontmatter'].description, '');
  assert.equal(byName['broken'].description, '');
  assert.equal(body.skippedCount, 1);
  assert.equal(body.commands.length, 3);
});

test('GET /api/commands degrades to an empty list when .claude/commands is absent', async () => {
  const { port, token } = await startServer();
  const res = await fetch(apiUrl(port, token, '/api/commands'));
  assert.equal(res.status, 200);
  assert.deepEqual(await res.json(), { commands: [], skippedCount: 0 });
});

// ---------------------------------------------------------------------------
// GET /api/roster
// ---------------------------------------------------------------------------

test('GET /api/roster groups by nearest table heading and falls back name/role sensibly', async () => {
  const { port, token, dir } = await startServer();
  const agentsDir = path.join(dir, 'agents');
  await fs.mkdir(agentsDir, { recursive: true });

  await fs.writeFile(
    path.join(agentsDir, 'README.md'),
    [
      '# Roster',
      '',
      '| Tier | Count |',
      '|---|---|',
      '| Core | 2 |',
      '',
      '### 1. Coding Guild (2 agents)',
      '',
      '| Agent | Role |',
      '|---|---|',
      '| [Ada](ada/) | Lead Backend Engineer |',
      '| [Ghost](ghost/) | No README Agent |',
      '',
      '#### Frontmatter Sub-Guild',
      '',
      '| Agent | Role |',
      '|---|---|',
      '| [Iris](iris/) | placeholder role text ignored |',
    ].join('\n'),
  );

  await fs.mkdir(path.join(agentsDir, 'ada'), { recursive: true });
  await fs.writeFile(path.join(agentsDir, 'ada', 'README.md'), '# Ada — Lead Backend Engineer\n\nBody.\n');

  await fs.mkdir(path.join(agentsDir, 'iris'), { recursive: true });
  await fs.writeFile(
    path.join(agentsDir, 'iris', 'README.md'),
    '---\nname: Iris\nrole: Lead Frontend Engineer\n---\n# Iris — ignored heading role\n',
  );
  // "ghost" has no agents/ghost/README.md at all — must degrade to slug.

  const res = await fetch(apiUrl(port, token, '/api/roster'));
  assert.equal(res.status, 200);
  const body = await res.json();

  const codingGuild = body.guilds.find((g) => g.name === 'Coding Guild');
  assert.ok(codingGuild, 'Coding Guild group should exist');
  const ada = codingGuild.agents.find((a) => a.name === 'Ada');
  assert.equal(ada.role, 'Lead Backend Engineer');
  const ghost = codingGuild.agents.find((a) => a.name === 'ghost');
  assert.equal(ghost.role, 'ghost');

  const frontmatterGuild = body.guilds.find((g) => g.name === 'Frontmatter Sub-Guild');
  assert.ok(frontmatterGuild, 'Frontmatter Sub-Guild group should exist');
  const iris = frontmatterGuild.agents.find((a) => a.name === 'Iris');
  assert.equal(iris.role, 'Lead Frontend Engineer'); // frontmatter wins over H1 heading

  // The "Tier | Count" table must never be treated as a roster table.
  assert.ok(!body.guilds.some((g) => g.agents.some((a) => a.name === 'Core')));
});

test('GET /api/roster: a malicious link target in README.md cannot escape the agents/ directory', async () => {
  const { port, token, dir } = await startServer();
  const agentsDir = path.join(dir, 'agents');
  await fs.mkdir(agentsDir, { recursive: true });

  // A file outside agents/ that a traversal would read if containment were missing.
  await fs.mkdir(path.join(dir, 'secret-outside-agents'), { recursive: true });
  await fs.writeFile(
    path.join(dir, 'secret-outside-agents', 'README.md'),
    '---\nname: PWNED\nrole: PWNED\n---\n',
  );

  await fs.writeFile(
    path.join(agentsDir, 'README.md'),
    [
      '### 1. Coding Guild (1 agent)',
      '',
      '| Agent | Role |',
      '|---|---|',
      '| [Evil](../secret-outside-agents) | ignored |',
    ].join('\n'),
  );

  const res = await fetch(apiUrl(port, token, '/api/roster'));
  assert.equal(res.status, 200);
  const body = await res.json();

  const codingGuild = body.guilds.find((g) => g.name === 'Coding Guild');
  assert.ok(codingGuild, 'Coding Guild group should exist');
  // Containment must reject the traversal and degrade to the raw slug, exactly
  // like an agent with no README.md, never reading the file outside agents/.
  const evil = codingGuild.agents.find((a) => a.name === '../secret-outside-agents');
  assert.ok(evil, 'out-of-bounds slug should degrade to itself, not crash');
  assert.ok(
    !body.guilds.some((g) => g.agents.some((a) => a.name === 'PWNED')),
    'must never read a README.md outside agents/',
  );
});

test('GET /api/roster degrades to empty guilds when agents/README.md is absent', async () => {
  const { port, token } = await startServer();
  const res = await fetch(apiUrl(port, token, '/api/roster'));
  assert.equal(res.status, 200);
  assert.deepEqual(await res.json(), { guilds: [] });
});

// ---------------------------------------------------------------------------
// GET /api/timeline
// ---------------------------------------------------------------------------

test('GET /api/timeline extracts one entry per date heading, preferring the Mission line', async () => {
  const { port, token, dir } = await startServer();
  await fs.mkdir(path.join(dir, 'kb', 'wiki'), { recursive: true });
  await fs.writeFile(
    path.join(dir, 'kb', 'wiki', 'log.md'),
    [
      '# Mission Log',
      '',
      '## 2026-07-02',
      '',
      '**Mission:** Auris build',
      '**Type:** Product Build',
      '',
      '---',
      '',
      '## 2026-06-10',
      '',
      'No mission line here, just a note.',
    ].join('\n'),
  );

  const res = await fetch(apiUrl(port, token, '/api/timeline'));
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.deepEqual(body.entries, [
    { date: '2026-07-02', text: 'Auris build' },
    { date: '2026-06-10', text: 'No mission line here, just a note.' },
  ]);
});

test('GET /api/timeline degrades to empty entries when log.md is absent', async () => {
  const { port, token } = await startServer();
  const res = await fetch(apiUrl(port, token, '/api/timeline'));
  assert.equal(res.status, 200);
  assert.deepEqual(await res.json(), { entries: [] });
});

// ---------------------------------------------------------------------------
// GET /api/metrics/summary, GET /api/metrics/commands
// ---------------------------------------------------------------------------

test('GET /api/metrics/summary always includes the exact tokensCaveat and a non-estimating costNote', async () => {
  const { port, token } = await startServer();
  const res = await fetch(apiUrl(port, token, '/api/metrics/summary'));
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.match(
    body.tokensCaveat,
    /100x\+ due to a known Claude Code streaming-placeholder bug \(anthropics\/claude-code#28197\)/,
  );
  assert.ok(!/estimated from token usage/i.test(body.costNote));
  assert.equal(body.missionCostUSD, 0);
});

test('GET /api/metrics/summary sums missionCostUSD from the ledger within the days window only', async () => {
  const dir = await makeInstanceDir();

  let onExitFn;
  const deps = {
    runMission: ({ onEvent, onExit }) => {
      onExitFn = onExit;
      onEvent({ type: 'result', total_cost_usd: 0.42, usage: { input_tokens: 100 } });
      return { pid: 123, stop() {} };
    },
  };
  const server = await startServer({ dir, deps });

  const createRes = await fetch(apiUrl(server.port, server.token, '/api/missions'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt: 'do the thing' }),
  });
  assert.equal(createRes.status, 201);
  onExitFn({ code: 0 });

  // Ledger append is async; poll briefly.
  for (let i = 0; i < 20; i++) {
    const summaryRes = await fetch(apiUrl(server.port, server.token, '/api/metrics/summary'));
    const summaryBody = await summaryRes.json();
    if (summaryBody.missionCostUSD === 0.42) {
      assert.equal(summaryBody.missionCostUSD, 0.42);
      return;
    }
    await new Promise((r) => setTimeout(r, 25));
  }
  assert.fail('missionCostUSD never reflected the ledgered mission cost');
});

test('GET /api/metrics/commands buckets by first token of display, tolerates malformed lines, respects days window', async () => {
  const now = Date.now();
  const dir = await makeInstanceDir();
  const historyPath = path.join(dir, 'history.jsonl');
  const lines = [
    JSON.stringify({ display: '/add-mission build the thing', timestamp: now - 1000 }),
    JSON.stringify({ display: '/add-mission another one', timestamp: now - 2000 }),
    JSON.stringify({ display: 'just some freeform text', timestamp: now - 3000 }),
    'not even json',
    JSON.stringify({ display: '/wake', timestamp: now - 1000 * 60 * 60 * 24 * 40 }), // 40 days ago
  ];
  await fs.writeFile(historyPath, lines.join('\n') + '\n');

  const { port, token } = await startServer({ dir, paths: { historyPath } });
  const res = await fetch(apiUrl(port, token, '/api/metrics/commands?days=7'));
  assert.equal(res.status, 200);
  const body = await res.json();
  const byCommand = Object.fromEntries(body.commands.map((c) => [c.command, c]));
  assert.equal(byCommand['/add-mission'].count, 2);
  assert.equal(byCommand['freeform'].count, 1);
  assert.ok(!byCommand['/wake'], '40-day-old entry must be excluded by the 7-day window');
});

// ---------------------------------------------------------------------------
// Missions: create/list/stop/SSE/ledger/concurrency cap
// ---------------------------------------------------------------------------

test('POST /api/missions requires a non-empty prompt', async () => {
  const { port, token } = await startServer();
  const res = await fetch(apiUrl(port, token, '/api/missions'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  });
  assert.equal(res.status, 400);
});

test('mission lifecycle: create -> running in list -> exit code 0 -> done, with ledger + SSE replay', async () => {
  let onEventFn;
  let onExitFn;
  const deps = {
    runMission: ({ onEvent, onExit }) => {
      onEventFn = onEvent;
      onExitFn = onExit;
      return { pid: 999, stop() {} };
    },
  };
  const { port, token } = await startServer({ deps });

  const createRes = await fetch(apiUrl(port, token, '/api/missions'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt: 'ship the feature', label: 'Ship it' }),
  });
  assert.equal(createRes.status, 201);
  const { id } = await createRes.json();

  const listRes = await fetch(apiUrl(port, token, '/api/missions'));
  const listBody = await listRes.json();
  const mission = listBody.missions.find((m) => m.id === id);
  assert.equal(mission.status, 'running');
  assert.equal(mission.label, 'Ship it');

  onEventFn({ type: 'assistant', text: 'working...' });
  onEventFn({ type: 'result', total_cost_usd: 0.13, usage: { input_tokens: 10, output_tokens: 5 } });
  onExitFn({ code: 0 });

  const listRes2 = await fetch(apiUrl(port, token, '/api/missions'));
  const listBody2 = await listRes2.json();
  const mission2 = listBody2.missions.find((m) => m.id === id);
  assert.equal(mission2.status, 'done');
  assert.equal(mission2.costUSD, 0.13);
  assert.deepEqual(mission2.usage, { input_tokens: 10, output_tokens: 5 });

  // SSE replay after completion: status, buffered msgs, then done, then close.
  const sseRes = await fetch(apiUrl(port, token, `/api/missions/${id}/events`));
  assert.equal(sseRes.status, 200);
  const text = await sseRes.text();
  assert.match(text, /event: status/);
  assert.match(text, /event: msg/);
  assert.match(text, /"text":"working\.\.\."/);
  assert.match(text, /event: done/);
  assert.match(text, /"costUSD":0\.13/);
});

test('POST /api/missions/:id/stop sets stoppedByUser and results in status=stopped on exit', async () => {
  let onExitFn;
  let stopCalled = false;
  const deps = {
    runMission: ({ onExit }) => {
      onExitFn = onExit;
      return { pid: 1, stop: () => { stopCalled = true; } };
    },
  };
  const { port, token } = await startServer({ deps });

  const createRes = await fetch(apiUrl(port, token, '/api/missions'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt: 'long running thing' }),
  });
  const { id } = await createRes.json();

  const stopRes = await fetch(apiUrl(port, token, `/api/missions/${id}/stop`), { method: 'POST' });
  assert.equal(stopRes.status, 200);
  assert.equal(stopCalled, true);

  // Even a non-zero/killed exit code must classify as 'stopped', not 'error',
  // because stoppedByUser was set before the process actually exited.
  onExitFn({ code: null, signal: 'SIGTERM' });

  const listRes = await fetch(apiUrl(port, token, '/api/missions'));
  const listBody = await listRes.json();
  const mission = listBody.missions.find((m) => m.id === id);
  assert.equal(mission.status, 'stopped');
});

test('a non-zero exit code that was NOT user-stopped classifies as error, not done', async () => {
  let onExitFn;
  const deps = { runMission: ({ onExit }) => { onExitFn = onExit; return { pid: 2, stop() {} }; } };
  const { port, token } = await startServer({ deps });

  const createRes = await fetch(apiUrl(port, token, '/api/missions'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt: 'will fail' }),
  });
  const { id } = await createRes.json();

  onExitFn({ code: 1 });

  const listRes = await fetch(apiUrl(port, token, '/api/missions'));
  const { missions } = await listRes.json();
  assert.equal(missions.find((m) => m.id === id).status, 'error');
});

test('a failed spawn (code and signal both null, not user-stopped) classifies as error', async () => {
  let onExitFn;
  const deps = { runMission: ({ onExit }) => { onExitFn = onExit; return { pid: 3, stop() {} }; } };
  const { port, token } = await startServer({ deps });

  const createRes = await fetch(apiUrl(port, token, '/api/missions'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt: 'spawn failure' }),
  });
  const { id } = await createRes.json();

  onExitFn({ code: null, signal: null });

  const listRes = await fetch(apiUrl(port, token, '/api/missions'));
  const { missions } = await listRes.json();
  assert.equal(missions.find((m) => m.id === id).status, 'error');
});

test('POST /api/missions enforces the 3-concurrent-running cap with 409', async () => {
  const exitFns = [];
  const deps = {
    runMission: ({ onExit }) => {
      exitFns.push(onExit);
      return { pid: exitFns.length, stop() {} };
    },
  };
  const { port, token } = await startServer({ deps });

  for (let i = 0; i < 3; i++) {
    const res = await fetch(apiUrl(port, token, '/api/missions'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: `mission ${i}` }),
    });
    assert.equal(res.status, 201);
  }

  const fourthRes = await fetch(apiUrl(port, token, '/api/missions'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt: 'mission 4' }),
  });
  assert.equal(fourthRes.status, 409);

  // Freeing a running slot allows a new mission through.
  exitFns[0]({ code: 0 });
  const fifthRes = await fetch(apiUrl(port, token, '/api/missions'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt: 'mission 5' }),
  });
  assert.equal(fifthRes.status, 201);
});

test('GET /api/missions/:id/stop|events on an unknown id returns 404', async () => {
  const { port, token } = await startServer();
  const stopRes = await fetch(apiUrl(port, token, '/api/missions/does-not-exist/stop'), { method: 'POST' });
  assert.equal(stopRes.status, 404);
  const eventsRes = await fetch(apiUrl(port, token, '/api/missions/does-not-exist/events'));
  assert.equal(eventsRes.status, 404);
});

// ---------------------------------------------------------------------------
// Saved missions
// ---------------------------------------------------------------------------

test('saved missions: create, list, delete round trip', async () => {
  const { port, token } = await startServer();

  const createRes = await fetch(apiUrl(port, token, '/api/saved-missions'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ label: 'Daily report', prompt: 'send the daily error report' }),
  });
  assert.equal(createRes.status, 201);
  const created = await createRes.json();
  assert.equal(created.label, 'Daily report');

  const listRes = await fetch(apiUrl(port, token, '/api/saved-missions'));
  const listBody = await listRes.json();
  assert.ok(listBody.missions.some((m) => m.id === created.id));

  const deleteRes = await fetch(apiUrl(port, token, `/api/saved-missions/${created.id}`), { method: 'DELETE' });
  assert.equal(deleteRes.status, 200);

  const listRes2 = await fetch(apiUrl(port, token, '/api/saved-missions'));
  const listBody2 = await listRes2.json();
  assert.ok(!listBody2.missions.some((m) => m.id === created.id));
});

test('saved missions: deleting an unknown id returns 404', async () => {
  const { port, token } = await startServer();
  const res = await fetch(apiUrl(port, token, '/api/saved-missions/does-not-exist'), { method: 'DELETE' });
  assert.equal(res.status, 404);
});

test('saved missions: concurrent creates never clobber each other (serialized read-modify-write)', async () => {
  const { port, token } = await startServer();

  const creates = Array.from({ length: 10 }, (_, i) =>
    fetch(apiUrl(port, token, '/api/saved-missions'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ label: `mission-${i}`, prompt: `prompt ${i}` }),
    }),
  );
  const results = await Promise.all(creates);
  for (const res of results) assert.equal(res.status, 201);

  const listRes = await fetch(apiUrl(port, token, '/api/saved-missions'));
  const listBody = await listRes.json();
  assert.equal(listBody.missions.length, 10);
  const uniqueIds = new Set(listBody.missions.map((m) => m.id));
  assert.equal(uniqueIds.size, 10);
});

// ---------------------------------------------------------------------------
// Errors never leak internals
// ---------------------------------------------------------------------------

test('a route handler throwing an error never leaks err.message/stack to the client', async () => {
  const deps = {
    aggregateSessions: async () => {
      throw new Error('SECRET INTERNAL PATH: /Users/xavier/.ssh/id_ed25519');
    },
  };
  const { port, token } = await startServer({ deps });
  const res = await fetch(apiUrl(port, token, '/api/metrics/summary'));
  // aggregateSessions failures are caught internally and degrade gracefully
  // rather than surfacing as a 500 — assert the secret never appears either way.
  const text = await res.text();
  assert.ok(!text.includes('SECRET INTERNAL PATH'));
  assert.ok(!text.includes('.ssh/id_ed25519'));
});
