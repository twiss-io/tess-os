// index.js — create-tess orchestrator.
// Bootstrap → fetch template → journey (interactive or flags) → promote →
// write operator profile → keystone bake → doctor/verify → arrival greeting.
import { join } from 'node:path';
import { mkdtempSync, rmSync, readdirSync } from 'node:fs';
import { tmpdir } from 'node:os';

import { parseArgs, isNonInteractive, HELP, DEFAULTS } from './args.js';
import {
  ensurePython3,
  clobberReason,
  fetchTemplate,
  promote,
  isSafeTemplateSource,
  BUNDLED_TEMPLATE_DIR,
  isLocalSource,
  resolveTemplateRef,
} from './scaffold.js';
import { loadRoster, installSetForPath } from './roster.js';
import { writeProfile, bake, check, activateGate, regenPolicyLock } from './keystone.js';
import { runJourney } from './journey.js';
import { preflightForce, beginWrite, rollback, verifyOnly, backupNotice } from './force-run.js';
import { resolveTarget } from './target.js';
import { VIBES } from './content/vibes.js';
import {
  validateName,
  checkConductorName,
  validateVibe,
  validatePath,
  validatePathway,
} from './validate.js';
import { c, plain, dim, accent } from './ui.js';
import {
  printBakeHeader,
  okLine,
  makeBakeProgress,
  printGateStatus,
  printArrival,
} from './output.js';

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
    set,
  };
}

// The REAL directory: a symlinked --target is followed once, here, so every
// check, snapshot and write sees the same tree (target.js).
function targetOrDie(raw) {
  let target;
  try {
    target = resolveTarget(raw);
  } catch (err) {
    die(err.message);
  }
  if (target.viaSymlink) {
    const note = `--target ${target.given} is a symlink; scaffolding into ${target.dir}`;
    process.stdout.write((plain ? '' : '  ') + dim(note) + '\n');
  }
  return target;
}

export async function main(argv) {
  const opts = parseArgs(argv);
  if (opts.help) {
    process.stdout.write(HELP + '\n');
    return;
  }

  const target = targetOrDie(opts.target || process.cwd());
  const targetDir = target.dir;
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

  // Did the target already hold content before we touched it? If so (only
  // possible with --force), the run is planned read-only first, everything it
  // replaces is backed up, and a failure restores and re-verifies the tree.
  // A target that existed empty is snapshotted too, so a failure empties it
  // again instead of deleting it. A target the run creates is removed
  // (force-run.js rollback).
  const hadContent =
    target.existed && readdirSync(targetDir).filter((e) => e !== '.DS_Store').length > 0;
  const forced = Boolean(opts.force) && hadContent;
  const runState = target.existed ? { before: null, backup: null, hadContent } : null;

  // Stage the template into a temp dir so the journey can read the real roster
  // and validate names before the target is ever touched (atomicity §6.5).
  const staging = mkdtempSync(join(tmpdir(), 'create-tess-'));
  let choices;
  let vibe;
  let checks;
  let gate;
  const refuse = (refusal) => {
    rmSync(staging, { recursive: true, force: true });
    process.stdout.write(refusal.stdout);
    die(refusal.stderr);
  };
  try {
    const refSuffix = templateRef ? ` @ ${templateRef}` : '';
    const fetchLabel = usingBundledDefault
      ? 'Fetching keystone (bundled template — no network required) …'
      : `Fetching keystone (${isLocalSource(source) ? 'local template' : 'git'}: ${source}${refSuffix}) …`;
    process.stdout.write((plain ? '' : '  ') + dim(fetchLabel) + '\n');
    fetchTemplate(source, staging, templateRef);
    // --force over existing content: refuse type conflicts and managed-path
    // collisions before the journey, with nothing written.
    if (forced) {
      const refusal = preflightForce(staging, targetDir);
      if (refusal) refuse(refusal);
    }
    const roster = loadRoster(staging);

    if (isNonInteractive(opts)) {
      choices = resolveFromFlags(opts, roster);
    } else {
      choices = await runJourney(roster);
    }
    vibe = VIBES[choices.vibe];

    // ── S8: the write gate ──────────────────────────────────────────────────
    // From here the target is mutated. HIGH-1 + M1: wrap promote + bake +
    // profile-write so ANY failure rolls the target back — no half-promoted
    // template, no poisoning operator/profile.json or tess.lock that
    // clobberReason() would later refuse without --force. The rollback
    // reports "clean" only after verifying it.
    if (runState) {
      let begun;
      try {
        begun = beginWrite(staging, targetDir, runState);
      } catch (err) {
        // Nothing was scaffolded. createBackup() undoes its own moves; verify.
        rmSync(staging, { recursive: true, force: true });
        if (runState.before) process.stdout.write(verifyOnly(targetDir, runState));
        die(`--force stopped before scaffolding: ${err.message}`);
      }
      if (begun.refusal) refuse(begun.refusal);
    }
    try {
      // M2: for a forced re-scaffold of a real install, beginForcedWrite()
      // already moved the managed paths into the backup, so stale framework
      // files can't survive the merge.
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
      rmSync(staging, { recursive: true, force: true });
      const r = rollback(targetDir, runState, target.createdRoot);
      process.stdout.write(r.stdout);
      die(
        `setup failed during scaffold/bake (${r.clean ? 'rolled back' : 'rollback incomplete, see above'}).\n` +
          `  ${err.message}`,
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
  if (runState) process.stdout.write(backupNotice(runState.backup, checks));
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
