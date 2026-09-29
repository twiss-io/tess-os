// brain.js — "Who is this for?" and the second-brain onboarding the wizard
// runs itself, so nobody has to type `python3 scripts/brain/onboard.py`.
//
// The wizard only answers the first two onboarding steps (mode, preset) and
// the names it already asked for; `onboard.py init --non-interactive` fills
// every other answer with its documented default, and `apply` scaffolds
// brain/ and makes the instance's first, path-scoped commit through the
// installed gate. Onboarding is best-effort: a failure never undoes the
// install, it is reported in plain words with the one next step.
import { execFileSync } from 'node:child_process';
import { existsSync, mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, basename } from 'node:path';
import { plain, dim, accent } from './ui.js';
import { relTargetHint } from './output.js';

export const BRAIN_MODES = ['personal', 'agency', 'organisation'];
// One optional preset per mode (scripts/brain/presets/*.json base_mode).
export const BRAIN_PRESETS = { agency: 'solo-consultant', organisation: 'startup' };

export const MODE_OPTIONS = [
  { value: 'personal', label: 'Just me', hint: 'my own work, projects and life' },
  { value: 'agency', label: 'My business, with clients', hint: 'a firm or freelancer serving clients' },
  { value: 'organisation', label: 'A team or company', hint: 'several people, each with a role' },
];
const PRESET_QUESTIONS = {
  agency: 'Do you work on your own? (adds a proposals folder, a pipeline and a rate card)',
  organisation: 'Is it a small startup of 1 to 10 people? (adds founder, product, growth and operations roles)',
};
const MODE_WORDS = { personal: 'you', agency: 'your business', organisation: 'your team' };

export function validateMode(mode) {
  if (BRAIN_MODES.includes(mode)) return { ok: true, value: mode };
  return { ok: false, error: `--mode must be one of ${BRAIN_MODES.join(', ')} (got "${mode}")` };
}

// '--preset none' and an unset preset both mean "no preset".
export function validatePreset(mode, preset) {
  if (preset === undefined || preset === null || preset === 'none') return { ok: true, value: null };
  if (BRAIN_PRESETS[mode] === preset) return { ok: true, value: preset };
  const allowed = BRAIN_PRESETS[mode] ? `none or ${BRAIN_PRESETS[mode]}` : 'none';
  return { ok: false, error: `--preset for --mode ${mode} must be ${allowed} (got "${preset}")` };
}

// Flags mode: an unset --mode is 'personal' with or without --yes, so every
// pre-0.2.1 flag set keeps working. Returns { mode, preset } or { error }.
export function resolveBrainFlags(opts) {
  const mode = validateMode(opts.mode ?? 'personal');
  if (!mode.ok) return { error: mode.error };
  const preset = validatePreset(mode.value, opts.preset);
  if (!preset.ok) return { error: preset.error };
  return { mode: mode.value, preset: preset.value };
}

// Interactive: two plain questions. `p` is @clack/prompts, `bail` its cancel guard.
// Also returns what the person chose ON SCREEN (`said`), so onboarding records
// their answer, not a command-line flag they never typed (v1.0 e2e review, S3).
export async function askWhoFor(p, bail) {
  const mode = bail(await p.select({ message: 'Who is this for?', options: MODE_OPTIONS }));
  const said = { mode: MODE_OPTIONS.find((o) => o.value === mode).label, preset: null };
  let preset = null;
  if (BRAIN_PRESETS[mode]) {
    const yes = bail(await p.confirm({ message: PRESET_QUESTIONS[mode], initialValue: true }));
    if (yes) preset = BRAIN_PRESETS[mode];
    said.preset = yes ? 'Yes' : 'No';
  }
  return { mode, preset, said };
}

// The answers file `onboard.py init --answers` reads for a wizard run where the
// person answered on screen. Each quote is exactly what they chose or typed
// (the option text, "Yes"/"No", or the name they typed). A name they did not
// type (Enter kept "Tess") is recorded as a default with no quote, never as
// words they said. Flag runs never come here: their quotes stay the flag text.
export function onScreenAnswers({ mode, preset, operator, conductor, said }) {
  const answers = [{ step: 1, field: 'mode', value: mode, quote: said.mode }];
  if (said.preset) answers.push({ step: 2, field: 'preset', value: preset || 'none', quote: said.preset });
  answers.push({ step: 3, field: 'operator_name', value: operator, quote: said.operator || operator });
  if (said.conductor) answers.push({ step: 3, field: 'assistant_name', value: conductor, quote: said.conductor });
  else answers.push({ step: 3, field: 'assistant_name', value: conductor, quote: '', runtime: 'default' });
  return { schema: 1, runtime: 'setup-wizard', session: '', answers };
}

function gitIdentityEnv(targetDir, operator) {
  let email = '';
  try {
    email = execFileSync('git', ['config', 'user.email'], { cwd: targetDir, encoding: 'utf8' }).trim();
  } catch { /* unset */ }
  if (email) return {};
  // No git identity on this computer (common on a brand-new Mac). Author only
  // this first local commit as the operator; nothing is written to git config.
  const name = operator || 'Tess OS';
  const addr = 'tess@localhost';
  return { GIT_AUTHOR_NAME: name, GIT_AUTHOR_EMAIL: addr, GIT_COMMITTER_NAME: name, GIT_COMMITTER_EMAIL: addr };
}

function lastLines(err) {
  const text = [err.stdout, err.stderr].filter(Boolean).join('\n').trim() || err.message;
  return text.split('\n').slice(-8).join('\n');
}

// Returns { status: 'done'|'kept'|'skipped'|'failed', commit, detail }.
export function runOnboarding(targetDir, { mode, preset, operator, conductor, said }, onStep = () => {}) {
  const script = join(targetDir, 'scripts', 'brain', 'onboard.py');
  if (!existsSync(script)) return { status: 'skipped', commit: null, detail: 'onboarding tool not in template' };
  // A --force re-scaffold keeps the operator's existing brain; never re-onboard it.
  if (existsSync(join(targetDir, 'brain', 'brain.json'))) return { status: 'kept', commit: null, detail: '' };
  const env = { ...process.env, ...gitIdentityEnv(targetDir, operator) };
  const run = (args) =>
    execFileSync('python3', [script, ...args], { cwd: targetDir, env, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });
  let init;
  let answersDir = null;
  if (said) {
    answersDir = mkdtempSync(join(tmpdir(), 'create-tess-answers-'));
    const file = join(answersDir, 'answers.json');
    writeFileSync(file, JSON.stringify(onScreenAnswers({ mode, preset, operator, conductor, said })), { mode: 0o600 });
    init = ['init', '--non-interactive', '--answers', file];
  } else {
    init = ['init', '--non-interactive', '--mode', mode, '--operator', operator, '--assistant', conductor];
    if (preset) init.push('--preset', preset);
  }
  try {
    onStep('Setting up your second brain', 'start');
    try {
      run(init);
    } finally {
      if (answersDir) rmSync(answersDir, { recursive: true, force: true });
    }
    const out = run(['apply']);
    onStep('Setting up your second brain', 'done');
    const m = /committed: ([0-9a-f]{4,40})/.exec(out);
    return { status: 'done', commit: m ? m[1] : null, detail: out };
  } catch (err) {
    return { status: 'failed', commit: null, detail: lastLines(err) };
  }
}

// The last thing a person sees: what was made and the one next step, in plain
// words. The next step names the folder by the name the person typed, because
// that is what they will look for in Claude Code or Codex.
// The one-time question each app asks the first time the folder is opened.
// Codex runs Tess's safety hooks only in a trusted project, after the hooks
// are approved (again after each Tess update: approval is pinned to a hash).
export const FIRST_OPEN_CLAUDE = '  In Claude Code: when it asks whether you trust this folder, say yes.';
export const FIRST_OPEN_CODEX = "  In Codex: trust this folder and approve Tess's hooks when asked (/hooks).";

// A path as one shell word: plain names stay as typed, anything else is quoted.
function shellWord(p) {
  return /^[\w.\/-]+$/.test(p) ? p : `'${p.replace(/'/g, "'\\''")}'`;
}

export function printFinalScreen(targetDir, opts) {
  const { mode, brain, checks, conductor = 'Tess', crew = 9, productionNote = '' } = opts;
  const w = (s = '') => process.stdout.write(s + '\n');
  const bullet = plain ? '-' : '•';
  const safe = checks.doctor !== false && checks.verify !== false;
  const folder = basename(targetDir);
  w();
  w(plain ? 'ALL SET' : accent('All set.'));
  w(`Tess OS is ready in the folder "${folder}".`);
  w(dim(`  (full path: ${targetDir})`));
  w();
  w('What was created:');
  w(`  ${bullet} Your AI team: a crew of ${crew} specialists plus your assistant, ${conductor}.`);
  if (brain.status === 'kept') w(`  ${bullet} Your existing second brain in the brain folder, kept as it was.`);
  if (brain.status === 'done') {
    const saved = brain.commit ? `, saved in git (first save ${brain.commit})` : '';
    w(`  ${bullet} A second brain for ${MODE_WORDS[mode] || 'you'} in the brain folder${saved}.`);
  }
  if (brain.status === 'failed') w(`  ${bullet} Your second brain: not set up yet (${conductor} will finish it with you).`);
  w(`  ${bullet} Safety checks: ${safe ? 'passed' : 'found a problem (see the lines above)'}.`);
  w();
  w('What to do next:');
  w('  In this terminal, type these two lines, pressing Return after each:');
  w(`      cd ${shellWord(relTargetHint(targetDir))}`);
  w('      claude            (or: codex, if you use Codex)');
  w(`  Then say hi. ${conductor}, your assistant, will take it from there.`);
  w(dim(`  (Or open the folder "${folder}" in Claude Code or Codex and say hi.)`));
  w(FIRST_OPEN_CLAUDE);
  w(FIRST_OPEN_CODEX);
  if (brain.status === 'failed') {
    w();
    w(`Your second brain was not set up automatically. ${conductor} will offer to finish it the`);
    w('first time you open the folder. Details for a helper:');
    w(dim(brain.detail.split('\n').map((l) => '    ' + l).join('\n')));
  }
  if (productionNote) {
    w();
    w(dim(productionNote));
  }
}
