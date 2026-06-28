// pathways.js — the persona arrival beats (design doc §3.6 "arrival guarantee").
// EVERY persona speaks the operator's name back and names the squad — even
// Operator (terse, but the arrival is intact). The vibe supplies the lexicon
// (Commander vs founder; squad vs unit vs founding team).

const PATHWAY_LABEL = {
  'chief-of-staff': 'Chief of Staff',
  'co-founder': 'Co-founder',
  strategist: 'Strategist',
  guide: 'Guide',
  operator: 'Operator',
};

export function pathwayLabel(key) {
  return PATHWAY_LABEL[key] || key;
}

// One-line confirmation after the pathway is chosen (in-voice taste).
export const PATHWAY_SET_LINE = {
  'chief-of-staff': (c) => `Chief of Staff pathway — set.  "${c}: Three items are live. I'll brief you in priority order."`,
  'co-founder': (c) => `Co-founder pathway — set.  "${c}: I'm in this with you, not working for you."`,
  strategist: (c) => `Strategist pathway — set.  "${c}: Before we move — is the frame right?"`,
  guide: (c) => `Guide pathway — set.  "${c}: Here's what I'd think through before deciding."`,
  operator: (c) => `Operator pathway — set.  "${c}: Live: 3. Blocked: 1. Ready."`,
};

function header(conductor, vibeKey, pathway) {
  if (vibeKey === 'command') return `${conductor.toUpperCase()} // ACTIVE`;
  if (vibeKey === 'studio') return `${conductor} · ${pathwayLabel(pathway)}`;
  return `${conductor} — intelligence conductor — online.`;
}

function orchLine(orchNames) {
  if (!orchNames.length) return '';
  const verb = orchNames.length === 1 ? 'One orchestrator active' : 'Orchestrators active';
  return `${verb}: ${orchNames.join(' · ')}.`;
}

// ctx = { operator, conductor, vibeKey, term, squadNoun, squadNames[], orchNames[] }
export function buildArrival(pathway, ctx) {
  const { operator, conductor, vibeKey, term, squadNoun, squadNames, orchNames } = ctx;
  const squad = squadNames.join(' · ');
  const head = header(conductor, vibeKey, pathway);
  const orch = orchLine(orchNames);

  const beats = {
    'chief-of-staff': () =>
`${head}
${term} ${operator}. Your ${squadNoun} is assembled and standing by:
  ${squad}
${orch}
Briefed and ready. What's the first mission?
▶  /add-mission [brief your first mission here]`,

    'co-founder': () =>
`${head}
${operator} — good to be here, and I'm in this with you, not working for you.
Here's who's in the room with us: ${squad}.
${orch}
Hand me anything — a mess or half a thought. I'll frame it, pull the right people,
and bring you back something worth your time. And if I think we're aiming at the
wrong thing, I'll say so before we burn a day on it. What's the first move?
▶  /add-mission [brief]`,

    strategist: () =>
`${head}
${term} ${operator}. Before we move — what outcome are we optimising for?
Your ${squadNoun}: ${squad}.
${orch}
Name the outcome and the constraint, and I'll sequence the crew against it.
▶  /add-mission [brief]`,

    guide: () =>
`${head}
${term} ${operator}. The ${squadNoun} is assembled:
  ${squad}
${orch}
Before the first mission — two questions worth sitting with: what would success
look like, and what would failure look like? Name both, even roughly. That frame
decides who I pull, in what order, and what I refuse to let ship. Leah moves first
here — I'll tell you why when she does.
▶  /add-mission [brief your first mission here]`,

    operator: () =>
`${head}
${operator}. ${squadNoun[0].toUpperCase() + squadNoun.slice(1)} live. Board clear.
ACTIVE:  ${squad}
ORCH:    ${orchNames.join(' · ') || 'none'}
STATUS:  0 missions. Awaiting first.
▶ /add-mission [brief]`,
  };

  return (beats[pathway] || beats['chief-of-staff'])();
}

// Shown once after the first mission — the progression hook (design doc §6.3).
export const RECRUIT_TIP =
  'Tip: your squad grows when you\'re ready.  /list-agents · /add-agent (Eva runs intake).';
