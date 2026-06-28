// squads.js — display labels for the canonical install map (design doc §4).
// The INSTALL SET itself is read at runtime from the template's
// .tess/core/roster-paths.json (single source of truth); this module only
// supplies human-readable names/roles + per-vibe path framing for the reveal.

// agent-key → { name, role }. Falls back to a capitalised key if missing.
export const AGENT_DISPLAY = {
  // founders
  athena: { name: 'Athena', role: 'Chief Strategy Officer' },
  apolline: { name: 'Apolline', role: 'Chief Sales Strategist' },
  zelie: { name: 'Zélie', role: 'Presentation & Deck Design' },
  // builders
  elena: { name: 'Elena', role: 'Product Engineer' },
  ada: { name: 'Ada', role: 'Lead Backend Engineer' },
  iris: { name: 'Iris', role: 'Lead Frontend Engineer' },
  quinn: { name: 'Quinn', role: 'QA & Reliability Architect' },
  reid: { name: 'Reid', role: 'Code Quality & Standards' },
  // operators
  adrienne: { name: 'Adrienne', role: 'Chief of Staff & Executive Operations' },
  evangeline: { name: 'Evangeline', role: 'Chief Customer Experience Strategist' },
  clio: { name: 'Clio', role: 'Session Scribe' },
  // universal base
  leah: { name: 'Leah', role: 'Researcher — research gate, informs every mission' },
  eva: { name: 'Eva', role: 'Talent & Recruiting — pulls agents off the bench' },
};

export const ORCH_DISPLAY = {
  'founders-office-orchestrator': "Founder's Office",
  'revenue-orchestrator': 'Revenue',
  'product-delivery-orchestrator': 'Product & Delivery',
  'operational-reliability-orchestrator': 'Operational Reliability',
  'client-experience-orchestrator': 'Client Experience',
  'strategic-growth-orchestrator': 'Strategic Growth',
};

export function displayAgent(key) {
  return AGENT_DISPLAY[key] || { name: key.charAt(0).toUpperCase() + key.slice(1), role: '' };
}

export function displayOrch(key) {
  return ORCH_DISPLAY[key] || key;
}

// Per-vibe framing for the STARTER_PATH select. label/hint shown in the menu;
// `intro` is the vibe-flavoured one-liner above the reveal. Eva's three copy
// fixes (founders investor-narrative, builders intentional-5, operators scribe)
// live in PATH_NOTES below and are surfaced honestly at the reveal.
export const PATH_FRAMING = {
  rpg: {
    founders: { label: "FOUNDER'S SQUAD", hint: 'Strategic · Commercial · High-stakes' },
    builders: { label: "BUILDER'S SQUAD", hint: 'Technical · Product · Ship-first' },
    operators: { label: "OPERATOR'S SQUAD", hint: 'Execution · CX · Reliability' },
  },
  command: {
    founders: { label: 'ALPHA   — Founder\'s Office', hint: 'Strategic · Commercial' },
    builders: { label: 'BRAVO   — Builder\'s Core', hint: 'Technical · Product' },
    operators: { label: 'CHARLIE — Operator\'s Base', hint: 'Execution · CX' },
  },
  studio: {
    founders: { label: "The Founder's Studio", hint: 'Strategy, revenue, the founder\'s office.' },
    builders: { label: "The Builder's Studio", hint: 'Product, engineering, QA.' },
    operators: { label: "The Operator's Studio", hint: 'Operations, client experience, reliability.' },
  },
};

// Eva's three copy fixes (task requirement), folded into the wizard copy as an
// honest expectation-setting note shown at the squad reveal for each path.
export const PATH_NOTES = {
  founders: [
    'Zélie designs your decks — but no narrative writer ships with this squad.',
    'So "frame your investor pitch" is your natural FIRST RECRUIT, not a day-one promise.',
  ],
  builders: [
    'Five agents, not three — and that is intentional. You need the full stack from day one:',
    'product, backend, frontend, QA and code-quality all in the room before you ship.',
  ],
  operators: [
    'Your scribe (Clio) is on staff — she makes sure nothing\'s lost between sessions.',
    'That\'s week-2 institutional-memory infrastructure, not day-one output. Set up to compound.',
  ],
};

// The PATHWAY (persona) menu — labels + one-line descriptions (design doc §3).
export const PATHWAY_OPTIONS = [
  { value: 'chief-of-staff', label: 'CHIEF OF STAFF', hint: 'Formal, precise, executive.' },
  { value: 'co-founder', label: 'CO-FOUNDER', hint: 'Peer-to-peer, direct. Says "we".' },
  { value: 'strategist', label: 'STRATEGIST', hint: 'Analytical, challenges your thinking.' },
  { value: 'guide', label: 'GUIDE', hint: 'Developmental, contextual — teaches as it goes.' },
  { value: 'operator', label: 'OPERATOR', hint: 'Mission-focused, tight, action-first.' },
];
