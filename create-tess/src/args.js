// args.js — flag parsing for create-tess.
//
// Supports both interactive (no flags) and fully non-interactive (--yes + flags)
// modes. Flag names reconcile the task spec with the design-doc spec:
//   operator name  : --operator   (alias --name)        [design doc: --name]
//   conductor name : --conductor  (alias --assistant)   [design doc: --assistant]
//   vibe           : --vibe
//   starter path   : --path
//   pathway        : --pathway
//   template source: --template-source   (env TESS_TEMPLATE_SOURCE)
//   target dir     : --target / --dir / first positional
//   unattended     : --yes
//   overwrite      : --force
//   skip checks    : --no-doctor / --no-verify
//   telegram       : --telegram=<channel-id>

export const DEFAULTS = {
  operator: 'Operator',
  conductor: 'Tess',
  vibe: 'rpg',
  path: 'founders',
  pathway: 'chief-of-staff',
};

export const VIBES = ['rpg', 'command', 'studio'];
export const PATHS = ['founders', 'builders', 'operators'];
export const PATHWAYS = [
  'chief-of-staff',
  'co-founder',
  'strategist',
  'guide',
  'operator',
];

const VALUE_ALIASES = {
  '--operator': 'operator',
  '--name': 'operator',
  '--conductor': 'conductor',
  '--assistant': 'conductor',
  '--vibe': 'vibe',
  '--path': 'path',
  '--pathway': 'pathway',
  '--template-source': 'templateSource',
  '--target': 'target',
  '--dir': 'target',
  '--telegram': 'telegram',
};

const BOOL_ALIASES = {
  '--yes': 'yes',
  '-y': 'yes',
  '--force': 'force',
  '--no-doctor': 'noDoctor',
  '--no-verify': 'noVerify',
  '--help': 'help',
  '-h': 'help',
};

export function parseArgs(argv) {
  const opts = {
    yes: false,
    force: false,
    noDoctor: false,
    noVerify: false,
    help: false,
    telegram: null,
    templateSource: process.env.TESS_TEMPLATE_SOURCE || null,
    target: null,
  };
  const positionals = [];

  for (let i = 0; i < argv.length; i++) {
    let token = argv[i];
    if (token === '--') continue;

    // --key=value form
    let inlineVal = null;
    const eq = token.indexOf('=');
    if (token.startsWith('--') && eq !== -1) {
      inlineVal = token.slice(eq + 1);
      token = token.slice(0, eq);
    }

    if (Object.prototype.hasOwnProperty.call(BOOL_ALIASES, token)) {
      opts[BOOL_ALIASES[token]] = true;
      continue;
    }
    if (Object.prototype.hasOwnProperty.call(VALUE_ALIASES, token)) {
      const key = VALUE_ALIASES[token];
      let val;
      if (inlineVal !== null) {
        val = inlineVal;
      } else {
        // LOW: don't silently swallow the next flag as this flag's value. A
        // value beginning with '--' is almost certainly the next option (the
        // user forgot a value); reject it. (A single '-' is allowed so negative
        // Telegram channel ids like -100… still parse.)
        const next = argv[i + 1];
        if (next === undefined || next.startsWith('--')) {
          throw new Error(`flag ${token} requires a value`);
        }
        val = argv[++i];
      }
      opts[key] = val;
      continue;
    }
    if (token.startsWith('-')) {
      throw new Error(`unknown flag: ${token}`);
    }
    positionals.push(token);
  }

  // Target precedence: --target/--dir > first positional > cwd
  if (!opts.target && positionals.length > 0) opts.target = positionals[0];

  return opts;
}

// True when the wizard should run without any prompts.
export function isNonInteractive(opts) {
  // Explicit --yes, OR a non-TTY stdin (CI / piped) — both must run unattended.
  return Boolean(opts.yes) || !process.stdin.isTTY;
}

export const HELP = `
create-tess — the gamified first-run wizard for Tess OS

USAGE
  npm create tess [target] [options]
  npx create-tess [target] [options]

INTERACTIVE
  Run with no flags inside a TTY for the full gamified journey.

NON-INTERACTIVE (CI / power users)
  npm create tess my-os -- --yes \\
    --operator="Alex" --vibe=studio --path=builders \\
    --conductor="Atlas" --pathway=co-founder

OPTIONS
  --operator, --name <text>      operator name (default: Operator)
  --conductor, --assistant <t>   conductor name (default: Tess)
  --vibe <rpg|command|studio>    narrative skin (default: rpg)
  --path <founders|builders|operators>   starter squad (default: founders)
  --pathway <key>                conductor persona (default: chief-of-staff)
                                 chief-of-staff|co-founder|strategist|guide|operator
  --telegram <channel-id>        optional Telegram channel to wire (default: skipped)
  --target, --dir <path>         target directory (default: cwd)
  --template-source <url|path>   git URL or local path for the Tess OS template
                                 (env: TESS_TEMPLATE_SOURCE;
                                  default: https://github.com/twiss-io/tess-os.git)
  --force                        overwrite a non-empty / existing-install target
  --no-doctor                    skip the post-bake integrity check
  --no-verify                    skip the post-bake verify check
  --yes, -y                      run fully unattended with defaults for unset flags
  --help, -h                     show this help
`;
