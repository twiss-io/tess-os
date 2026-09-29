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
//                                          default: the template BUNDLED inside
//                                          this package (local copy, no network) —
//                                          pass a git URL/path here to opt into a
//                                          live git fetch instead (see
//                                          scaffold.js BUNDLED_TEMPLATE_DIR)
//   template ref   : --template-ref      (env TESS_TEMPLATE_REF; pins a git-URL
//                                          clone to a tag/branch/SHA — only
//                                          meaningful alongside an explicit
//                                          --template-source git opt-in; see
//                                          scaffold.js resolveTemplateRef())
//   target dir     : --target / --dir / first positional
//   unattended     : --yes
//   overwrite      : --force
//   skip checks    : --no-doctor / --no-verify
//   skip gate      : --no-git-init / --no-gate-hooks

export const DEFAULTS = {
  operator: 'Operator',
  conductor: 'Tess',
  vibe: 'plain',
  path: 'founders',
  pathway: 'chief-of-staff',
};

export const VIBES = ['plain', 'rpg', 'command', 'studio'];
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
  '--template-ref': 'templateRef',
  '--target': 'target',
  '--dir': 'target',
  '--mode': 'mode',
  '--preset': 'preset',
};

const BOOL_ALIASES = {
  '--yes': 'yes',
  '-y': 'yes',
  '--force': 'force',
  '--no-doctor': 'noDoctor',
  '--no-verify': 'noVerify',
  '--no-git-init': 'noGitInit',
  '--no-gate-hooks': 'noGateHooks',
  '--no-onboarding': 'noOnboarding',
  '--help': 'help',
  '-h': 'help',
  '--version': 'version',
  '-v': 'version',
};

export function parseArgs(argv) {
  const opts = {
    yes: false,
    force: false,
    noDoctor: false,
    noVerify: false,
    noGitInit: false,
    noGateHooks: false,
    noOnboarding: false,
    help: false,
    templateSource: process.env.TESS_TEMPLATE_SOURCE || null,
    templateRef: process.env.TESS_TEMPLATE_REF || null,
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
        // user forgot a value); reject it. (A single '-' is allowed so values
        // such as negative numeric ids like -100… still parse.)
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
create-tess — the setup wizard for Tess OS

USAGE
  npm create tess [target] [options]
  npx create-tess [target] [options]

INTERACTIVE
  Run with no flags inside a terminal: a few plain questions, then setup.
  Prefer a themed setup? Add --vibe rpg, --vibe command or --vibe studio.

NON-INTERACTIVE (CI / power users)
  npm create tess my-os -- --yes \\
    --operator="Alex" --vibe=studio --path=builders \\
    --conductor="Atlas" --pathway=co-founder

OPTIONS
  --operator, --name <text>      operator name (default: Operator)
  --conductor, --assistant <t>   conductor name (default: Tess)
  --vibe <plain|rpg|command|studio>  wording of the setup (default: plain;
                                 the others are opt-in themes)
  --path <founders|builders|operators>   starter path: same crew of 9 on every path,
                                 only the suggested lenses differ (default: founders)
  --pathway <key>                conductor persona (default: chief-of-staff)
                                 chief-of-staff|co-founder|strategist|guide|operator
  --mode <personal|agency|organisation>  who this is for: just you, your business
                                 with clients, or a team (default: personal)
  --preset <none|solo-consultant|startup>  optional starter kit: solo-consultant
                                 (agency only) or startup (organisation only)
  --no-onboarding                do not set up the second brain now; Tess
                                 offers it the first time you open the folder
  --target, --dir <path>         target directory (default: cwd)
  --template-source <url|path>   OPT-IN: fetch the Tess OS template from this
                                 git URL or local path instead of the copy
                                 bundled inside this package (env:
                                 TESS_TEMPLATE_SOURCE). Default (unset): the
                                 bundled template — a local copy, no network
                                 or git clone involved.
  --template-ref <tag|branch|sha>  pin a git-URL --template-source to this ref
                                 (env: TESS_TEMPLATE_REF). Only meaningful
                                 alongside an explicit --template-source git
                                 opt-in — a custom source is otherwise cloned
                                 at its own default branch tip.
  --force                        overwrite a non-empty / existing-install target
  --no-doctor                    skip the post-bake integrity check
  --no-verify                    skip the post-bake verify check
  --no-git-init                  skip the automatic git init (default: on;
                                 skipped anyway if the target is already a
                                 git repo)
  --no-gate-hooks                skip tessctl gate install-hooks (default: on)
  --yes, -y                      run fully unattended with defaults for unset flags
  --help, -h                     show this help
  --version, -v                  print the create-tess version
`;
