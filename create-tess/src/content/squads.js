// squads.js — display labels for the canonical install map (design doc §4).
// The INSTALL SET itself is read at runtime from the template's
// .tess/core/roster-paths.json (single source of truth); this module only
// supplies human-readable names/roles + per-vibe path framing for the reveal.

// agent-key → { name, role }. Falls back to a capitalised key if missing.
export const AGENT_DISPLAY = {
  // v0.2: the nine dispatchable roles — the same on every path.
  ada: { name: 'Ada', role: 'Builder — code and files' },
  morwenna: { name: 'Morwenna', role: 'Explorer — read-only search and mapping' },
  leah: { name: 'Leah', role: 'Researcher — read-only plus web, cites sources' },
  reid: { name: 'Reid', role: 'Code reviewer — read-only' },
  quinn: { name: 'Quinn', role: 'QA — runs tests, no push or merge' },
  cyra: { name: 'Cyra', role: 'Security + approval signer' },
  clio: { name: 'Clio', role: 'Scribe — brain records, every claim sourced' },
  vega: { name: 'Vega', role: 'Release and devops — behind the gate' },
  iris: { name: 'Iris', role: 'Designer — frontend and design skills' },
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

// Per-vibe framing for the STARTER_PATH select. v0.2: every path installs the
// same ten roles; the path only changes the suggested default lenses
// (roster-paths.json `default_lenses`), surfaced honestly in PATH_NOTES.
export const PATH_FRAMING = {
  rpg: {
    founders: { label: "FOUNDER'S PATH", hint: 'Same ten roles · strategy and commercial lenses first' },
    builders: { label: "BUILDER'S PATH", hint: 'Same ten roles · product and engineering lenses first' },
    operators: { label: "OPERATOR'S PATH", hint: 'Same ten roles · operations and CX lenses first' },
  },
  command: {
    founders: { label: 'ALPHA   — Founder\'s Office', hint: 'Ten roles · strategy lenses' },
    builders: { label: 'BRAVO   — Builder\'s Core', hint: 'Ten roles · engineering lenses' },
    operators: { label: 'CHARLIE — Operator\'s Base', hint: 'Ten roles · operations lenses' },
  },
  studio: {
    founders: { label: "The Founder's Studio", hint: 'Ten roles; strategy, revenue and founder lenses suggested.' },
    builders: { label: "The Builder's Studio", hint: 'Ten roles; product, engineering and QA lenses suggested.' },
    operators: { label: "The Operator's Studio", hint: 'Ten roles; operations, client and reliability lenses suggested.' },
  },
};


// Expectation-setting note shown at the reveal for each path.
export const PATH_NOTES = {
  founders: [
    'Every path installs the same ten roles. This one suggests strategy and commercial lenses first',
    '(Founder\'s Office, Revenue, Athena, Apolline, Naomi, Sienna, Zélie) — loaded into a role\'s brief on demand.',
  ],
  builders: [
    'Every path installs the same ten roles. This one suggests product and engineering lenses first',
    '(Product and Delivery, Elena, Freya, Petra, Selene, Joséphine) — loaded into a role\'s brief on demand.',
  ],
  operators: [
    'Every path installs the same ten roles. This one suggests operations and client lenses first',
    '(Operational Reliability, Client Experience, Adrienne, Evangeline, Joséphine, Corinne).',
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
