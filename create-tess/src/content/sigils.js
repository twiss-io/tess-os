// sigils.js — ASCII cold-open art per vibe + a neutral wordmark.
// Each sigil has a `fancy` (box-drawing / block art, TTY ≥80 cols) and a
// `plain` line-mode fallback (non-TTY or narrow terminals, design doc §5.1).

export const NEUTRAL = {
  fancy: `
   ┌────────────────────────────────────────────┐
   │            T  E  S  S     O  S             │
   │          intelligence conductor os         │
   └────────────────────────────────────────────┘
   v0.1  •  ~150 agents standing by  •  6 orchestrators loaded
`,
  plain: `TESS OS — intelligence conductor os
v0.1  •  ~150 agents standing by  •  6 orchestrators loaded`,
};

export const SIGILS = {
  rpg: {
    fancy: `
     ✦ · · · · · · · · · · · · · · · · · ✦
   ·       ████████╗███████╗███████╗███████╗  ·
   ·          ██║   █████╗  ███████╗███████╗  ·
   ·          ██║   ██╔══╝  ╚════██║╚════██║  ·
   ·          ██║   ███████╗███████║███████║  ·
   ·          ╚═╝   ╚══════╝╚══════╝╚══════╝  ·
   ·          INTELLIGENCE CONDUCTOR OS       ·
     ✦ · · · · · · · · · · · · · · · · · ✦
  v0.1  •  ~150 agents standing by  •  6 orchestrators loaded`,
    plain: `=== TESS OS — THE GUILD ===
~150 agents standing by  •  6 orchestrators loaded`,
  },
  command: {
    fancy: `
  ╔═══════════════════════════════════════════════════╗
  ║        T E S S   O S   //  COMMAND PROTOCOL       ║
  ╚═══════════════════════════════════════════════════╝
  ~150 specialist agents waiting. Starter squad activates today. The rest, you recruit.`,
    plain: `// TESS OS // COMMAND PROTOCOL
~150 specialist agents waiting. Starter squad activates today. The rest, you recruit.`,
  },
  // L2 — a BESPOKE drafting-table sigil (rounded frame + an L-square ruler in
  // the margin), distinct from the neutral wordmark so the Studio cold-open no
  // longer shows the same box twice.
  studio: {
    fancy: `
   ╭────────────────────────────────────────────────────────────╮
   │   ┌┄┄┐                                                     │
   │   ┆  └┄┄┄┄┄  T E S S   O S                                 │
   │   ┆  ┌┄┄┄┄┄  T H E   S T U D I O                           │
   │   └┄┄┘  the drafting table — the house is empty            │
   │   you choose who walks in first; the bench fills the rest  │
   ╰────────────────────────────────────────────────────────────╯
   ~150 on the bench  •  6 orchestrators on call`,
    plain: `TESS OS — THE STUDIO  (the drafting table — the house is empty)
you choose who walks in first; ~150 on the bench  •  6 orchestrators on call`,
  },
};
