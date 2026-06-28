// index.js — create-tess orchestrator.
// Bootstrap → fetch template → journey (interactive or flags) → promote →
// write operator profile → keystone bake → doctor/verify → arrival greeting.
import { resolve, join } from 'node:path';
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
  DEFAULT_TEMPLATE_SOURCE,
  isLocalSource,
} from './scaffold.js';
import { loadRoster, installSetForPath, squadDisplayNames } from './roster.js';
import { writeProfile, bake, check } from './keystone.js';
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
  const source = opts.templateSource || DEFAULT_TEMPLATE_SOURCE;

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
  try {
    const srcKind = isLocalSource(source) ? 'local template' : 'git';
    process.stdout.write(
      (plain ? '' : '  ') + dim(`Fetching keystone (${srcKind}: ${source}) …`) + '\n',
    );
    fetchTemplate(source, staging);
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

      promote(staging, targetDir);
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

    // Integrity checks (unless skipped). check() never throws — it returns
    // booleans — so it stays outside the rollback gate.
    checks = check(targetDir, { doctor: !opts.noDoctor, verify: !opts.noVerify });
  } finally {
    rmSync(staging, { recursive: true, force: true });
  }

  if (checks.doctor !== null) okLine(`tessctl doctor — ${checks.doctor ? 'OK' : 'ISSUES'}`);
  if (checks.verify !== null) okLine(`tessctl verify — ${checks.verify ? 'OK' : 'ISSUES'}`);
  process.stdout.write('  ' + (plain ? '*' : accent('★')) + '  Your system is live.\n');

  // Arrival — the conductor speaks the operator's name back (design doc §3.6).
  printArrival(vibe, choices, checks);

  // Non-zero exit if a requested integrity check failed (CI signal).
  if (checks.doctor === false || checks.verify === false) {
    process.exitCode = 2;
  }
  return { targetDir, choices: { ...choices, set: undefined }, checks };
}
