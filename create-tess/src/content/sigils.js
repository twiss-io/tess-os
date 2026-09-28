// sigils.js — ASCII cold-open art per vibe + a neutral wordmark.
// Each sigil has a `fancy` (box-drawing / block art, TTY ≥80 cols) and a
// `plain` line-mode fallback (non-TTY or narrow terminals, design doc §5.1).

export const NEUTRAL = {
  fancy: `
   ┌────────────────────────────────────────────┐
   │            T  E  S  S     O  S             │
   │          intelligence conductor os         │
   └────────────────────────────────────────────┘
   a crew of 9 specialists plus your assistant
`,
  plain: `TESS OS — intelligence conductor os
a crew of 9 specialists plus your assistant`,
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
  a crew of 9 specialists plus your assistant`,
    plain: `=== TESS OS — THE GUILD ===
a crew of 9 specialists plus your assistant`,
  },
  command: {
    fancy: `
  ╔═══════════════════════════════════════════════════╗
  ║        T E S S   O S   //  COMMAND PROTOCOL       ║
  ╚═══════════════════════════════════════════════════╝
  A crew of 9 specialists plus your assistant, ready today.`,
    plain: `// TESS OS // COMMAND PROTOCOL
A crew of 9 specialists plus your assistant, ready today.`,
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
   │   a crew of 9 specialists plus your assistant             │
   ╰────────────────────────────────────────────────────────────╯
`,
    plain: `TESS OS — THE STUDIO  (the drafting table — the house is empty)
a crew of 9 specialists plus your assistant`,
  },
};
