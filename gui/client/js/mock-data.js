// Tess OS Mission Control — ?mock=1 canned fixtures.
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss
//
// Every shape here matches the real server response shape exactly (see
// gui/server/routes/*.js) — a mock/real shape divergence is exactly what hid
// the byModel bug in the previous build. tokensCaveat/costNote are copied
// verbatim from gui/server/routes/metrics.js's TOKENS_CAVEAT/COST_NOTE
// constants (not re-derived here, since client code can't import server
// code across the static-file boundary) — keep these two strings in sync
// with that file if it changes.

export const MOCK_HEALTH = {
  ok: true,
  version: '0.1.0',
  claude: { version: '2.1.4', compatible: true, minVersion: '2.0.0' },
  instanceDir: '/mock/instance',
};

// name -> description, sourced from conductor/commands.md's Quick Reference
// table (26 commands, matching the real .claude/commands/*.md set).
const COMMAND_DESCRIPTIONS = {
  'add-mission': 'Submit new mission for intake and routing',
  'review-mission': 'Full mission status snapshot',
  'route-mission': 'Re-evaluate orchestrator assignment',
  'show-owner': 'Display outcome owner',
  'show-active-guilds': 'List active guilds and roles',
  'show-risks': 'Surface risks and blockers',
  'show-next-moves': 'Display sequenced next actions',
  wake: 'Session start checklist — orient, check mission state, surface blockers',
  close: 'Session end checklist — confirm mission state, flag decisions, log to wiki',
  finalize: 'Deliver executive synthesis memo',
  summary: 'Mission status snapshot',
  reset: 'Clear mission and restart',
  'code-red': 'Emergency escalation',
  initiate: 'Equivalent to /add-mission — kept for backward compatibility',
  'founder-mode': "Activate Founder's Office routing",
  'revenue-mode': 'Activate Revenue Orchestrator routing',
  'product-mode': 'Activate P&D Orchestrator routing',
  'cx-mode': 'Activate CX Orchestrator routing',
  'ops-mode': 'Activate ORO routing',
  'strategic-mode': 'Activate SGO routing',
  'list-agents': 'View active crew',
  'add-agent': 'Recruit a new specialist',
  'remove-agent': 'Remove an agent',
  brainstorm: 'Open exploration mode',
  feedback: 'Apply system feedback',
  help: 'Command reference',
};

export const MOCK_COMMANDS = {
  commands: Object.keys(COMMAND_DESCRIPTIONS)
    .sort((a, b) => a.localeCompare(b))
    .map((name) => ({ name, description: COMMAND_DESCRIPTIONS[name] })),
  skippedCount: 2,
};

export const MOCK_ROSTER = {
  guilds: [
    {
      name: 'Permanent Crew',
      agents: [
        { name: 'Leah', role: 'Senior Researcher & Intelligence Lead' },
        { name: 'Eva', role: 'HR Specialist & AI Talent Strategist' },
        { name: 'Clio', role: 'Session Scribe and Minute-Taker' },
      ],
    },
    {
      name: 'Key Cross-Cutting Specialists',
      agents: [
        { name: 'Ada', role: 'Lead Backend Engineer' },
        { name: 'Iris', role: 'Lead Frontend Engineer' },
        { name: 'Cyra', role: 'Security and Risk Engineer' },
        { name: 'Reid', role: 'Code Quality and Standards Architect' },
        { name: 'Quinn', role: 'QA and Reliability Architect' },
        { name: 'Vega', role: 'DevOps and Infrastructure Engineer' },
        { name: 'Elena', role: 'Product Engineer' },
      ],
    },
    {
      name: 'Visual and Design Sub-Guild',
      agents: [
        { name: 'Iseult', role: 'Interface Visual Language Strategist' },
        { name: 'Corisande', role: 'Motion and Visual Reveal Strategist' },
      ],
    },
  ],
};

export const MOCK_TIMELINE = {
  entries: [
    { date: '2026-07-01', text: 'Verification pass completed — no critical or high-severity findings.' },
    {
      date: '2026-06-27',
      text: 'Command system fully wired — 26 commands, each backed by a real .claude/commands/<name>.md file.',
    },
    {
      date: '2026-06-10',
      text: 'Doctrine reform — dependency gates replace the fixed six-phase mission sequence.',
    },
  ],
};

const DAYS = [
  {
    date: '2026-06-28',
    sessions: 9,
    tokens: { input: 142000, output: 31000, cacheRead: 410000, cacheCreation: 6200 },
    byModel: { 'claude-sonnet-5': { input: 98000, output: 21000 }, 'claude-opus-4-8': { input: 44000, output: 10000 } },
  },
  {
    date: '2026-06-29',
    sessions: 12,
    tokens: { input: 188000, output: 39500, cacheRead: 522000, cacheCreation: 7800 },
    byModel: { 'claude-sonnet-5': { input: 140000, output: 29500 }, 'claude-opus-4-8': { input: 48000, output: 10000 } },
  },
  {
    date: '2026-06-30',
    sessions: 6,
    tokens: { input: 81000, output: 17800, cacheRead: 260000, cacheCreation: 3100 },
    byModel: { 'claude-sonnet-5': { input: 81000, output: 17800 } },
  },
  {
    // Deliberately includes the synthetic sentinel model — proves the
    // client filters it out of the rendered breakdown (format.js
    // realModelEntries / SYNTHETIC_MODEL_KEY).
    date: '2026-07-01',
    sessions: 14,
    tokens: { input: 224000, output: 47600, cacheRead: 601000, cacheCreation: 9400 },
    byModel: {
      'claude-sonnet-5': { input: 150000, output: 31000 },
      'claude-opus-4-8': { input: 73700, output: 16500 },
      '<synthetic>': { input: 300, output: 100 },
    },
  },
  {
    date: '2026-07-02',
    sessions: 17,
    tokens: { input: 265000, output: 58200, cacheRead: 715000, cacheCreation: 11200 },
    byModel: { 'claude-sonnet-5': { input: 198000, output: 44000 }, 'claude-opus-4-8': { input: 67000, output: 14200 } },
  },
  {
    date: '2026-07-03',
    sessions: 10,
    tokens: { input: 156000, output: 33400, cacheRead: 388000, cacheCreation: 5900 },
    byModel: { 'claude-sonnet-5': { input: 112000, output: 24000 }, 'claude-opus-4-8': { input: 44000, output: 9400 } },
  },
  {
    date: '2026-07-04',
    sessions: 4,
    tokens: { input: 52000, output: 11200, cacheRead: 140000, cacheCreation: 2100 },
    byModel: { 'claude-sonnet-5': { input: 52000, output: 11200 } },
  },
];

function sumField(path) {
  return DAYS.reduce((acc, day) => {
    const value = path.split('.').reduce((obj, key) => obj?.[key], day);
    return acc + (Number(value) || 0);
  }, 0);
}

export const MOCK_TOKENS_CAVEAT =
  'input_tokens may undercount actual usage by 100x+ due to a known Claude Code streaming-placeholder bug ' +
  '(anthropics/claude-code#28197) — treat as directional only, not exact.';

export const MOCK_COST_NOTE =
  'missionCostUSD is a local estimate, not billing data — the Claude Code CLI computes it from a bundled ' +
  'price table, so it can drift from your actual Anthropic bill. It reflects costs reported for missions ' +
  'launched from this dashboard only; cost is not tracked for missions run outside tess-gui and is not ' +
  'available in historical session logs.';

export const MOCK_METRICS_SUMMARY = {
  days: DAYS,
  totals: {
    sessions: sumField('sessions'),
    tokens: {
      input: sumField('tokens.input'),
      output: sumField('tokens.output'),
      cacheRead: sumField('tokens.cacheRead'),
      cacheCreation: sumField('tokens.cacheCreation'),
    },
  },
  missionCostUSD: 4.62,
  costNote: MOCK_COST_NOTE,
  tokensCaveat: MOCK_TOKENS_CAVEAT,
};

export const MOCK_METRICS_COMMANDS = {
  commands: [
    { command: '/add-mission', count: 41, lastUsed: '2026-07-04T08:12:00.000Z' },
    { command: '/review-mission', count: 27, lastUsed: '2026-07-03T22:40:00.000Z' },
    { command: '/summary', count: 19, lastUsed: '2026-07-04T07:05:00.000Z' },
    { command: 'freeform', count: 15, lastUsed: '2026-07-02T16:20:00.000Z' },
    { command: '/wake', count: 12, lastUsed: '2026-07-04T06:00:00.000Z' },
  ],
};

export const MOCK_SAVED_MISSIONS_SEED = [
  {
    id: 'seed-1',
    label: 'Weekly ops health check',
    prompt: '/ops-mode review fleet uptime and flag anything trending toward an SLA breach this week',
    createdAt: '2026-06-20T09:00:00.000Z',
  },
  {
    id: 'seed-2',
    label: 'Draft investor update',
    prompt: "/founder-mode draft this month's investor update — revenue trend, key wins, and one candid risk",
    createdAt: '2026-06-25T14:30:00.000Z',
  },
];

// ~9s canned playback exercising every SSE msg-event kind the live view
// must render: system init (dim), assistant text, assistant tool_use (mono
// chip), stderr (dim red mono), raw (plain mono) — plus status/done.
export const MISSION_SCRIPT_TEMPLATE = [
  { delay: 200, event: 'status', data: { status: 'running' } },
  { delay: 300, event: 'msg', data: { type: 'system', subtype: 'init', cwd: '/mock/instance', model: 'claude-opus-4-8' } },
  {
    delay: 1200,
    event: 'msg',
    data: {
      type: 'assistant',
      message: { role: 'assistant', content: [{ type: 'text', text: 'Reviewing the mission brief and framing the outcome type…' }] },
    },
  },
  {
    delay: 1300,
    event: 'msg',
    data: {
      type: 'assistant',
      message: { role: 'assistant', content: [{ type: 'tool_use', id: 'toolu_1', name: 'Read', input: { file_path: 'conductor/doctrine.md' } }] },
    },
  },
  {
    delay: 900,
    event: 'msg',
    data: {
      type: 'assistant',
      message: { role: 'assistant', content: [{ type: 'text', text: 'Doctrine confirms this routes through the Product and Delivery Orchestrator.' }] },
    },
  },
  {
    delay: 1400,
    event: 'msg',
    data: {
      type: 'assistant',
      message: { role: 'assistant', content: [{ type: 'tool_use', id: 'toolu_2', name: 'Bash', input: { command: 'git log --oneline -5' } }] },
    },
  },
  { delay: 600, event: 'msg', data: { type: 'stderr', text: 'warning: detached HEAD state (informational)' } },
  { delay: 700, event: 'msg', data: { type: 'raw', text: '7b6b1d7 feat(gui): scaffold tess-gui optional dashboard package' } },
  {
    delay: 1500,
    event: 'msg',
    data: {
      type: 'assistant',
      message: { role: 'assistant', content: [{ type: 'text', text: 'Routing confirmed. Drafting the crew plan for review.' }] },
    },
  },
  { delay: 900, event: 'status', data: { status: 'done' } },
  { delay: 100, event: 'done', data: { status: 'done', costUSD: 0.0842, durationMs: 9100 } },
];
