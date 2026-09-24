// output.js — the wizard's post-bake terminal output: bake progress lines,
// gate status and fallback next steps, the first-push custody notice, and the
// arrival greeting. Split out of index.js to keep each module under the
// 300-line quality gate; no behaviour change.
import { resolve, relative } from 'node:path';
import { squadDisplayNames } from './roster.js';
import { buildArrival, RECRUIT_TIP } from './content/pathways.js';
import { c, plain, dim, bold } from './ui.js';

export function printBakeHeader(vibe) {
  const rule = plain ? '-'.repeat(57) : '─'.repeat(57);
  process.stdout.write('\n' + rule + '\n  ' + bold(vibe.bakeTitle) + '\n');
}

// A plain "done" line for the post-bake integrity checks.
export function okLine(label) {
  process.stdout.write(`  ${plain ? '[ok]' : c.green('✓')} ${label}\n`);
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
// fail-closed by design, not a gap: create-tess resets them to empty on
// every scaffold, regardless of what the SOURCE repo's own policy currently
// contains (see policy-reset.js). The maintainer repo (twiss-io/tess-os)
// separately registers its own verifiers, in its own policy.yaml, to govern
// its own development — that registration is never carried into a
// scaffolded project. Local hooks and a rendered workflow are useful setup,
// but they do not establish the external trust anchor or required GitHub
// enforcement a production gate needs. Say that plainly at the point an
// operator would otherwise mistake a successful scaffold for production
// readiness.
export function printFirstPushNotice() {
  const bang = plain ? '!' : c.yellow('!');
  process.stdout.write(
    `\n  ${bang} Local scaffold ready; protected production work remains blocked.\n`,
  );
  process.stdout.write(
    dim(
      '    This project ships with empty policy registries — fail-closed by\n' +
        '    design: you register your own verifier and sign-off keys. (The\n' +
        '    framework maintainer repository separately registers its own\n' +
        '    verifiers, in its own policy, to govern its own development — that\n' +
        '    registration is never carried into a scaffolded project.) So\n' +
        '    a first governed push can fail closed with no covering APPROVE verdict\n' +
        '    found. Do not bypass or disable the hook to represent a change as\n' +
        '    protected, or create, register, or sign review authority from this\n' +
        '    candidate repository. Record the\n' +
        "    gate output and base/head references, then escalate to your project's\n" +
        '    key-custody owner for an external custody decision and required\n' +
        '    GitHub-check enforcement.\n',
    ),
  );
}

// Report whether the ship-gate is actually live after scaffold. Prints a
// plain confirmation on success; on any incompleteness (git missing, hooks
// step failed, or the operator opted out via --no-git-init/--no-gate-hooks)
// it falls back to explicit, copy-pasteable numbered next-steps — the
// acceptable minimum when automatic activation doesn't land clean.
export function printGateStatus(gate, targetDir) {
  if (gate.gitInit === 'done') okLine('git init — repository created');
  else if (gate.gitInit === 'already') okLine('git repository — already present (left untouched)');

  if (gate.hooksInstalled === true && gate.gitHooksLive) {
    okLine('tessctl gate install-hooks — pre-commit/pre-push hooks + CI workflow live');
  }

  const gateNotLive =
    gate.gitInit === 'failed' ||
    gate.hooksInstalled === false ||
    (gate.hooksInstalled === true && !gate.gitHooksLive) ||
    gate.gitInit === 'skipped' ||
    gate.hooksInstalled === 'skipped';

  if (!gateNotLive) {
    printFirstPushNotice();
    return;
  }

  const hint = relTargetHint(targetDir);
  process.stdout.write(
    `\n  ${plain ? '!' : c.yellow('!')} The ship-gate is NOT fully enforcing yet — activate it yourself:\n`,
  );
  if (gate.error) process.stdout.write(dim(`    ${gate.error.split('\n')[0]}\n`));
  const steps = [];
  if (targetDir !== resolve(process.cwd())) steps.push(`cd ${hint}`);
  if (gate.gitInit !== 'done' && gate.gitInit !== 'already') steps.push('git init');
  steps.push('python3 .tess/bin/tessctl gate install-hooks');
  steps.forEach((s, i) => process.stdout.write(`    ${i + 1}. ${s}\n`));
}

export function printArrival(vibe, choices, checks) {
  const ctx = {
    operator: choices.operator,
    conductor: choices.conductor,
    vibeKey: choices.vibe,
    term: vibe.operatorTerm,
    squadNoun: vibe.squadNoun,
    squadNames: squadDisplayNames(choices.set),
    orchNames: choices.set.orchDisplay,
  };
  const rule = plain ? '='.repeat(57) : '─'.repeat(57);
  const dr = checks.doctor === false ? ' (doctor reported issues — run `tessctl render` after resolving)' : '';
  process.stdout.write(`\n${rule}\n`);
  process.stdout.write(buildArrival(choices.pathway, ctx) + '\n');
  process.stdout.write(`${rule}\n`);
  process.stdout.write(dim(RECRUIT_TIP) + dr + '\n');
}
