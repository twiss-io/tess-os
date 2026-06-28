// vibes.js — the three narrative skins (design doc §2). One engine, one install
// map; vibe only relabels. Copy is house "never hype" standard: grounded, warm,
// honest. Each vibe supplies the lexicon + framing for every downstream step.

export const VIBE_ORDER = ['rpg', 'command', 'studio'];

// L3 / Lysandra #5 — the one honesty line that must surface for EVERY vibe, not
// just Studio. The vibe is paint; the engine and the install set are identical
// underneath. It rides as a DIMMED follow-line beneath each vibe's `engaged`
// beat (see journey.js S1) — lifted off the cinematic line so it never competes
// with the moment, but present on every path so no skin can quietly imply it
// changes the system's power.
export const VIBE_HONESTY =
  'Same engine underneath — the vibe sets the language, not the power.';

export const VIBES = {
  // ── 2.1 RPG / Guild ──────────────────────────────────────────────────────
  rpg: {
    key: 'rpg',
    label: 'The Guild Path',
    tag: 'RPG',
    selectLabel: 'The Guild Path     Build your squad. Grow your army.',
    selectHint: 'RPG',
    engaged: `The Guild Path — engaged.   Squads. Missions. Recruits. Your army starts small.`,
    operatorTerm: 'Commander',
    worldNoun: 'Guild',
    squadNoun: 'squad',
    lore: `A different kind of intelligence has been running here. Not a single AI — a
coordinated crew of specialists: strategists, engineers, researchers, operators,
builders. Each one deployable on command. This is Tess OS. Welcome, Commander.`,
    namePrompt: "You'll need a name in these lands. What do they call you?",
    nameConfirm: (op) =>
      `Commander ${op} — set. Every agent in this system answers to you.`,
    conductorPrompt: `Your conductor. This platform is Tess OS; the conductor is the command-layer
intelligence you're about to name — the one who routes your missions and briefs
your squad. Its default name is Tess, but this is your system.
What will you call your conductor?  (Enter to keep Tess)`,
    conductorConfirm: (c) =>
      `${c} — that's the name. Your conductor routes every mission and brings every thread back to you.`,
    pathPrompt:
      'Your starter squad. ~150 agents stand by; you start with a few who are excellent.',
    pathwayPrompt: (c) => `How should ${c} show up in the room?`,
    telegramPrompt: 'Connect Telegram now?  (optional — you can do this later)',
    telegramSkip: 'Skipped. Run /telegram:configure anytime to wire a channel.',
    bakeTitle: 'Assembling your intelligence system.',
    recapVerb: 'Open the gates?',
    outroRule: 'Your army grows from here.',
    // L1 — per-vibe bake-climax copy, keyed to the 5 real keystone operations.
    // The climax should read as a guild ritual, not an installer log.
    bakeGlyph: '✦',
    bakeSteps: {
      roster: 'Mustering your squad',
      setOperator: (x) => `Marking you as ${x.operatorTerm} ${x.operator}`,
      rename: (x) => `Naming your conductor — ${x.conductor}`,
      pathway: (x) => `Attuning ${x.conductor} to your command`,
      render: 'Forging the doctrine',
    },
  },

  // ── 2.2 Command / Squad ──────────────────────────────────────────────────
  command: {
    key: 'command',
    label: 'The Tactical Path',
    tag: 'Command',
    selectLabel: 'The Tactical Path  Assemble your unit. Run operations.',
    selectHint: 'Command',
    engaged: `TACTICAL PATH ENGAGED.`,
    operatorTerm: 'Commander',
    worldNoun: 'Command',
    squadNoun: 'unit',
    lore: `INITIALISING... You are about to build a unit of specialist AI agents. A single
command intelligence. A chain of dispatch. Nothing acts without orders. You give them.`,
    namePrompt: 'Commander designation required. What name do you operate under?',
    nameConfirm: (op) => `DESIGNATION SET: Commander ${op}. Every agent answers to you.`,
    conductorPrompt: `Designate your command intelligence. This platform is Tess OS; this is the command
AI that runs your unit. Name it. Examples: Apex / Meridian / Zero / Sigma.
(Enter to keep Tess)`,
    conductorConfirm: (c) =>
      `DESIGNATION CONFIRMED: ${c} — all dispatch and synthesis flows through it.`,
    pathPrompt: 'Select your starter squad.',
    pathwayPrompt: (c) => `Set the command register. How does ${c} operate with you?`,
    telegramPrompt: 'Connect Telegram now?',
    telegramSkip: 'Skipped (/telegram:configure later).',
    bakeTitle: 'Configuration complete. Installing unit. Rendering doctrine.',
    recapVerb: 'Open the doors?',
    outroRule: 'Recruit as missions expand.',
    // L1 — clipped, status-readout bake (transcript B lexicon).
    bakeGlyph: '◼',
    bakeSteps: {
      roster: 'Installing squad agents',
      setOperator: (x) => `Writing commander profile — ${x.operator}`,
      rename: (x) => `Designating command intelligence as ${x.conductor}`,
      pathway: (x) => `Setting register to ${x.pathwayLabel}`,
      render: 'Rendering CLAUDE.md from operator stubs',
    },
    // 2.2 structural signature — the only branch in any journey.
    doctrineGate: {
      title: 'COMMAND & SQUAD — PROTOCOL DOCTRINE',
      body: `Chain of authority:
  Commander → Command AI → Orchestrators → Agents
Every task is dispatched. Every dispatch has a brief.
Starter squad active today. Recruit as missions expand.`,
      confirm: 'Doctrine received. Proceed to unit composition?',
      no: 'No — re-pick vibe',
    },
  },

  // ── 2.3 Studio / Agency ──────────────────────────────────────────────────
  studio: {
    key: 'studio',
    label: 'The Studio Path',
    tag: 'Studio',
    selectLabel: 'The Studio Path    Commission your crew. Build an agency.',
    selectHint: 'Studio',
    engaged: `The Studio Path — the doors are unlocked.`,
    operatorTerm: 'founder',
    worldNoun: 'The Studio',
    squadNoun: 'founding team',
    lore: `Most people open a terminal and get a tool. You're about to open a studio.
Behind this prompt is a full house — around a hundred and fifty of them.
None of them work for a platform. They're about to work for you. Let's hire your team.`,
    namePrompt: 'Before we open the doors — what should the studio call you?',
    nameHint: "First name's plenty. This is how your team will address you.",
    nameConfirm: (op) =>
      `Welcome in, ${op}. From here you're the founder. We don't assign you a team — you build one.`,
    conductorPrompt: `A studio this size needs someone who runs it when you're not looking — briefs the
team, guards the standard, hands you decisions already thought through. The platform
is Tess OS; this is your managing partner. What's their name?  (Enter to keep Tess)`,
    conductorHint: 'There\'s no default here. No "Tess" unless you make one.',
    conductorConfirm: (c) => `${c}. Done — ${c} runs the floor now.`,
    pathPrompt: 'Every studio starts with one practice. What are you here to build first?',
    pathHint:
      "You're choosing who walks in first — not who you're allowed to hire. The other ~145 are on the bench.",
    pathwayPrompt: (c) => `Same person, five ways to work. How should ${c} run with you?`,
    telegramPrompt: 'Connect Telegram now?',
    telegramSkip: 'Skipped (/telegram:configure later).',
    bakeTitle: 'Opening the studio.',
    recapVerb: 'Open the doors?',
    outroRule: 'The rest of the house is on the bench. Bring them on as you grow.',
    // L1 — the agency bake reads like onboarding a firm (transcript C lexicon).
    bakeGlyph: '◐',
    bakeSteps: {
      roster: 'Bringing your founding team onto the books',
      setOperator: 'Drawing up the paperwork',
      rename: (x) => `Setting ${x.conductor} as the one who runs the floor`,
      pathway: 'Writing the house standards — focus, trust, review',
      render: 'Opening the studio floor',
    },
  },
};
