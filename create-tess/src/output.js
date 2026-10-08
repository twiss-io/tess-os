// output.js — the wizard's post-bake terminal output: bake progress lines,
// gate status and fallback next steps, the first-push custody notice, and the
// arrival greeting. Split out of index.js to keep each module under the
// 300-line quality gate; no behaviour change.
import { resolve, relative } from 'node:path';
import { squadDisplayNames } from './roster.js';
import { buildArrival, crewTip } from './content/pathways.js';
import { c, plain, dim, bold } from './ui.js';

export function printBakeHeader(vibe) {
  const rule = plain ? '-'.repeat(57) : '─'.repeat(57);
  process.stdout.write('\n' + rule + '\n  ' + bold(vibe.bakeTitle) + '\n');
}

// A plain "done" line for the post-bake integrity checks.
export function okLine(label) {
  process.stdout.write(`  ${plain ? '[ok]' : c.green('✓')} ${label}\n`);
}

// A pass/fail line for a post-bake check: never "[ok]" in front of a failure.
export function checkLine(passed, okLabel, failLabel) {
  if (passed) okLine(okLabel);
  else process.stdout.write(`  ${plain ? '[!!]' : c.red('✗')} ${failLabel}\n`);
}

// L1 — a vibe-aware bake-step printer: prefixes each completed step with the
// chosen vibe's glyph so the climax reads per-world, not as a generic log.
export function makeBakeProgress(vibe) {
  const glyph = plain || !vibe.bakeGlyph ? '' : dim(vibe.bakeGlyph) + ' ';
  return (label, phase) => {
    if (phase === 'done') {
      process.stdout.write(`  ${plain ? '[ok]' : c.green('✓')} ${glyph}${label}\n`);
    }
  };
}

// Best-effort hint for the "cd" step in the fallback next-steps — relative to
// cwd when the target is a descendant of it, else the absolute path.
export function relTargetHint(targetDir) {
  const rel = relative(process.cwd(), targetDir);
  return rel && !rel.startsWith('..') ? rel : targetDir;
}

// A fresh scaffold always ships with empty verifier/sign-off registries —
// fail-closed by design (policy-reset.js). Local hooks are useful setup, but
// they are not the external trust anchor a production gate needs. The detail
// (the expected "no covering APPROVE verdict found" block, key custody,
// required GitHub checks) lives in SECURITY.md and docs/GATE_QUICKSTART.md;
// the wizard says it in one plain line so a successful setup is never
// mistaken for production protection, without burying the next step.
export const PRODUCTION_NOTE =
  'Using Tess OS to guard real production code needs extra setup first: see SECURITY.md in the folder.';

// The post-bake integrity checks, in plain words (the tessctl verb in brackets
// is for whoever helps the operator if a check fails).
export function printChecks(checks) {
  if (checks.doctor !== null) {
    checkLine(checks.doctor, 'Checked every Tess OS file: all in place (tessctl doctor OK)',
      'Checked every Tess OS file: problems found (tessctl doctor ISSUES)');
  }
  if (checks.verify !== null) {
    checkLine(checks.verify, 'Checked the install matches the release (tessctl verify OK)',
      'Checked the install matches the release: it does not (tessctl verify ISSUES)');
  }
  if (checks.anchor !== null && checks.anchor !== undefined) {
    checkLine(checks.anchor, 'Recorded your safety files outside the folder (tessctl anchor OK)',
      'Could not record your safety files outside the folder (run `./tessctl anchor accept`)');
  }
}

// Report whether the ship-gate is actually live after scaffold. Prints a
// plain confirmation on success; on any incompleteness (git missing, hooks
// step failed, or the operator opted out via --no-git-init/--no-gate-hooks)
// it falls back to explicit, copy-pasteable numbered next-steps — the
// acceptable minimum when automatic activation doesn't land clean.
export function printGateStatus(gate, targetDir) {
  if (gate.gitInit === 'already') okLine('Your folder already had a git history (left untouched)');

  const gateNotLive =
    gate.gitInit === 'failed' ||
    gate.hooksInstalled === false ||
    (gate.hooksInstalled === true && !gate.gitHooksLive) ||
    gate.gitInit === 'skipped' ||
    gate.hooksInstalled === 'skipped';

  if (!gateNotLive) return;

  const hint = relTargetHint(targetDir);
  process.stdout.write(
    `\n  ${plain ? '!' : c.yellow('!')} The safety checks that run on every save are not on yet. To turn them on, run:\n`,
  );
  if (gate.error) process.stdout.write(dim(`    ${gate.error.split('\n')[0]}\n`));
  const steps = [];
  if (targetDir !== resolve(process.cwd())) steps.push(`cd ${hint}`);
  if (gate.gitInit !== 'done' && gate.gitInit !== 'already') steps.push('git init');
  steps.push('python3 .tess/bin/tessctl gate install-hooks');
  steps.forEach((s, i) => process.stdout.write(`    ${i + 1}. ${s}\n`));
}

export function printArrival(vibe, choices) {
  // The plain setup ends on the final screen alone: no second greeting, no
  // list of team names (v1.0 e2e review, S4).
  if (vibe.key === 'plain') return;
  const ctx = {
    operator: choices.operator,
    conductor: choices.conductor,
    vibeKey: choices.vibe,
    squadNoun: vibe.squadNoun,
    squadNames: squadDisplayNames(choices.set),
    orchNames: choices.set.orchDisplay,
  };
  const rule = plain ? '='.repeat(57) : '─'.repeat(57);
  process.stdout.write(`\n${rule}\n`);
  process.stdout.write(buildArrival(choices.pathway, ctx) + '\n');
  process.stdout.write(`${rule}\n`);
  process.stdout.write(dim(crewTip(ctx.squadNames.length)) + '\n');
}
