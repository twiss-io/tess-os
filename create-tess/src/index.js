// index.js — create-tess orchestrator.
// Bootstrap → fetch template → journey (interactive or flags) → promote →
// write operator profile → keystone bake → doctor/verify → arrival greeting.
import { resolve, join, relative } from 'node:path';
import { mkdtempSync, rmSync, existsSync, readdirSync } from 'node:fs';
import { tmpdir } from 'node:os';

import { parseArgs, isNonInteractive, HELP, DEFAULTS } from './args.js';
import {
  ensurePython3,
  clobberReason,
  fetchTemplate,
  promote,
  clearManagedDirs,
  isSafeTemplateSource,
  BUNDLED_TEMPLATE_DIR,
  isLocalSource,
  resolveTemplateRef,
} from './scaffold.js';
import { loadRoster, installSetForPath, squadDisplayNames } from './roster.js';
import { writeProfile, bake, check, activateGate, regenPolicyLock } from './keystone.js';
import { runJourney } from './journey.js';
import { VIBES } from './content/vibes.js';
import { buildArrival, RECRUIT_TIP } from './content/pathways.js';
import {
  validateName,
  checkConductorName,
  validateVibe,
  validatePath,
  validatePathway,
} from './validate.js';
import { c, plain, dim, accent, bold } from './ui.js';

function die(msg, code = 1) {
  console.error(plain ? `error: ${msg}` : c.red(`error: ${msg}`));
  process.exit(code);
}

// Resolve every axis from flags + --yes defaults; hard-exit on any violation
// (design doc §5.4 — a flags-mode violation is a non-zero exit, no re-prompt).
//
// LOW: defaults are '--yes and unset' (design doc §5.4). Without --yes, an unset
// axis is NOT silently defaulted — it is required. This makes all five axes
// symmetric (previously only --operator was gated on --yes, while
// vibe/path/pathway/conductor defaulted unconditionally — a surprising asymmetry).
function resolveFromFlags(opts, roster) {
  const yes = Boolean(opts.yes);
  const pick = (val, def) =>
    val !== undefined && val !== null ? val : yes ? def : undefined;
  const operatorRaw = pick(opts.operator, DEFAULTS.operator);
  const conductorRaw = pick(opts.conductor, DEFAULTS.conductor);
  const vibe = pick(opts.vibe, DEFAULTS.vibe);
  const path = pick(opts.path, DEFAULTS.path);
  const pathway = pick(opts.pathway, DEFAULTS.pathway);

  const missing = [];
  if (operatorRaw === undefined) missing.push('--operator');
  if (conductorRaw === undefined) missing.push('--conductor');
  if (vibe === undefined) missing.push('--vibe');
  if (path === undefined) missing.push('--path');
  if (pathway === undefined) missing.push('--pathway');
  if (missing.length) {
    die(
      `non-interactive mode needs ${missing.join(', ')} — pass them explicitly, ` +
        `or --yes to use defaults for every unset axis`,
    );
  }

  for (const [v, fn] of [[vibe, validateVibe], [path, validatePath], [pathway, validatePathway]]) {
    const r = fn(v);
    if (!r.ok) die(r.error);
  }
  const op = validateName(operatorRaw, 'operator');
  if (!op.ok) die(op.error);
  const cond = validateName(conductorRaw, 'conductor');
  if (!cond.ok) die(cond.error);

  const set = installSetForPath(roster, path);
  const chk = checkConductorName(cond.value, op.value, set.installedNameSet);
  if (chk.block) die(chk.reason);

  return {
    vibe,
    operator: op.value,
    conductor: cond.value,
    path,
    pathway,
    telegram: opts.telegram || null,
    set,
  };
}

function printBakeHeader(vibe) {
  const rule = plain ? '-'.repeat(57) : '─'.repeat(57);
  process.stdout.write('\n' + rule + '\n  ' + bold(vibe.bakeTitle) + '\n');
}

// A plain "done" line for the post-bake integrity checks.
function okLine(label) {
  process.stdout.write(`  ${plain ? '[ok]' : c.green('✓')} ${label}\n`);
}

// L1 — a vibe-aware bake-step printer: prefixes each completed step with the
// chosen vibe's glyph so the climax reads per-world, not as a generic log.
function makeBakeProgress(vibe) {
  const glyph = plain || !vibe.bakeGlyph ? '' : dim(vibe.bakeGlyph) + ' ';
  return (label, phase) => {
    if (phase === 'done') {
      process.stdout.write(`  ${plain ? '[ok]' : c.green('✓')} ${glyph}${label}\n`);
    }
  };
}

// HIGH-1 — roll the target back to a clean, re-runnable state after a failed
// write/bake. If we created the target (it was absent/empty pre-run) the whole
// directory is removed; otherwise (forced re-scaffold over an existing dir) we
// remove only the operator profile a re-run keys on, never user data.
function rollbackTarget(targetDir, preexisted) {
  try {
    if (!preexisted) {
      rmSync(targetDir, { recursive: true, force: true });
    } else {
      rmSync(join(targetDir, 'operator', 'profile.json'), { force: true });
    }
  } catch {
    /* best-effort rollback */
  }
}

// Best-effort hint for the "cd" step in the fallback next-steps — relative to
// cwd when the target is a descendant of it, else the absolute path.
function relTargetHint(targetDir) {
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
function printFirstPushNotice() {
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
        '    gate output and base/head references, then escalate to Xavier for an\n' +
        '    external custody decision and required GitHub-check enforcement.\n',
    ),
  );
}

// Report whether the ship-gate is actually live after scaffold. Prints a
// plain confirmation on success; on any incompleteness (git missing, hooks
// step failed, or the operator opted out via --no-git-init/--no-gate-hooks)
// it falls back to explicit, copy-pasteable numbered next-steps — the
// acceptable minimum when automatic activation doesn't land clean.
function printGateStatus(gate, targetDir) {
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

function printArrival(vibe, choices, checks) {
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

export async function main(argv) {
  const opts = parseArgs(argv);
  if (opts.help) {
    process.stdout.write(HELP + '\n');
    return;
  }

  const targetDir = resolve(opts.target || process.cwd());
  // DEFAULT (P0 G-01 BUNDLE fix): scaffold from the template bundled INSIDE
  // this package — a local copy, never a git clone/network fetch. An
  // explicit --template-source (flag or TESS_TEMPLATE_SOURCE env var) is the
  // ONLY way to opt into a live git fetch instead; see scaffold.js's header
  // comment for why the old git-clone default was removed.
  const usingBundledDefault = !opts.templateSource;
  const source = opts.templateSource || BUNDLED_TEMPLATE_DIR;
  // The bundle ships with every published package; its absence means a
  // corrupted/incomplete install (or a from-source dev checkout that never
  // ran `npm run build-template`) — fail with a specific, actionable message
  // rather than falling through to isSafeTemplateSource's generic "not an
  // allowed source" (which would be true, but wouldn't say WHY or what to do).
  if (usingBundledDefault && !isLocalSource(source)) {
    die(
      `the bundled Tess OS template is missing from this create-tess install ` +
        `(expected at ${source}). This package may be corrupted or incomplete — ` +
        `reinstall it (\`npm install create-tess\`), or run \`npm run ` +
        `build-template\` if you're working from a source checkout. To fetch ` +
        `from git instead, pass --template-source <url> explicitly.`,
    );
  }
  // Pinned-clone reproducibility (P0 G-01, opt-in git path only): resolves to
  // an explicit --template-ref/TESS_TEMPLATE_REF when set, else the
  // DEFAULT_TEMPLATE_REF release tag for an explicit DEFAULT_TEMPLATE_SOURCE
  // opt-in, else null (unpinned — a custom source is cloned at its own
  // branch tip). A no-op for the bundled-default local source.
  const templateRef = resolveTemplateRef(source, opts.templateRef);

  // Bootstrap gates (design doc §5.1).
  ensurePython3();
  // Reid LOW: refuse any template source that is not an allowed transport form
  // up front (blocks `ext::`/`file://` coercion and flag-shaped argument injection
  // into `git clone`); see isSafeTemplateSource for the allowlist.
  if (!isSafeTemplateSource(source)) {
    die(
      `--template-source "${source}" is not an allowed source. Use an https://, ` +
        `git://, or ssh:// URL, an scp-form git@host:path, or an existing local directory.`,
    );
  }
  const refusal = clobberReason(targetDir, opts.force);
  if (refusal) die(refusal);

  // Did the target already hold content before we touched it? Determines the
  // rollback strategy (HIGH-1) and whether --force must clean-replace (M2).
  const targetPreexisted =
    existsSync(targetDir) &&
    readdirSync(targetDir).filter((e) => e !== '.DS_Store').length > 0;

  // Stage the template into a temp dir so the journey can read the real roster
  // and validate names before the target is ever touched (atomicity §6.5).
  const staging = mkdtempSync(join(tmpdir(), 'create-tess-'));
  let choices;
  let vibe;
  let checks;
  let gate;
  try {
    const refSuffix = templateRef ? ` @ ${templateRef}` : '';
    const fetchLabel = usingBundledDefault
      ? 'Fetching keystone (bundled template — no network required) …'
      : `Fetching keystone (${isLocalSource(source) ? 'local template' : 'git'}: ${source}${refSuffix}) …`;
    process.stdout.write((plain ? '' : '  ') + dim(fetchLabel) + '\n');
    fetchTemplate(source, staging, templateRef);
    const roster = loadRoster(staging);

    if (isNonInteractive(opts)) {
      choices = resolveFromFlags(opts, roster);
    } else {
      choices = await runJourney(roster);
    }
    vibe = VIBES[choices.vibe];

    // ── S8: the write gate ──────────────────────────────────────────────────
    // From here the target is mutated. HIGH-1 + M1: wrap promote + bake +
    // profile-write so ANY failure rolls the target back to a clean,
    // re-runnable state — no half-promoted template, no poisoning
    // operator/profile.json or tess.lock that clobberReason() would later refuse
    // without --force.
    try {
      // M2: a forced re-scaffold over an existing install clean-replaces the
      // managed dirs first, so stale framework files can't survive the merge.
      if (opts.force && targetPreexisted) clearManagedDirs(targetDir);

      const { policyReset } = promote(staging, targetDir);
      // The scaffold reset (scaffold.js resetScaffoldedPolicyKeys) may have
      // just rewritten `.tess/core/policy/policy.yaml`'s bytes — collapsing
      // the source repo's own registered verifier_keys/signoff_keys back to
      // the empty, fail-closed default so this project never inherits
      // another repo's trust anchor (see policy-reset.js). That intentional
      // rewrite invalidates the base_sha tess.lock inherited from the
      // source; re-pin ONLY that one entry (scoped, never an unscoped
      // regen) before doctor ever runs, so a fresh scaffold is
      // `tessctl doctor`-clean, not reported as CORE-TAMPERED.
      if (policyReset.changed) regenPolicyLock(targetDir);
      printBakeHeader(vibe);
      bake(targetDir, choices, makeBakeProgress(vibe));
      // PREFERRED (HIGH-1): write operator/profile.json only AFTER a successful
      // bake. A failed run then leaves NO profile.json — the key clobberReason()
      // gates on — so the directory stays re-runnable.
      writeProfile(targetDir, { ...choices, wizardVersion: '1.0.0' });
    } catch (err) {
      rollbackTarget(targetDir, targetPreexisted);
      rmSync(staging, { recursive: true, force: true });
      die(
        `setup failed during scaffold/bake — rolled back; the target is left ` +
          `clean and re-runnable.\n  ${err.message}`,
      );
    }

    // Gate activation — `git init` + `tessctl gate install-hooks` (best-effort,
    // never throws; see keystone.js activateGate() for why this is
    // deliberately outside the rollback contract above).
    gate = activateGate(targetDir, {
      onStep: makeBakeProgress(vibe),
      skipGitInit: Boolean(opts.noGitInit),
      skipHooks: Boolean(opts.noGateHooks),
    });

    // Integrity checks (unless skipped). check() never throws — it returns
    // booleans — so it stays outside the rollback gate.
    checks = check(targetDir, { doctor: !opts.noDoctor, verify: !opts.noVerify });
  } finally {
    rmSync(staging, { recursive: true, force: true });
  }

  if (checks.doctor !== null) okLine(`tessctl doctor — ${checks.doctor ? 'OK' : 'ISSUES'}`);
  if (checks.verify !== null) okLine(`tessctl verify — ${checks.verify ? 'OK' : 'ISSUES'}`);
  printGateStatus(gate, targetDir);
  process.stdout.write(
    '  ' + (plain ? '*' : accent('★')) +
      '  Local scaffold complete; production protection requires external custody and required GitHub checks.\n',
  );

  // Arrival — the conductor speaks the operator's name back (design doc §3.6).
  printArrival(vibe, choices, checks);

  // Non-zero exit if a requested integrity check failed (CI signal).
  if (checks.doctor === false || checks.verify === false) {
    process.exitCode = 2;
  }
  return { targetDir, choices: { ...choices, set: undefined }, checks, gate };
}
