// force-run.js — the index.js side of `--force` safety: when to plan, when to
// back up, and what to tell the operator. Every "left clean" line printed here
// is backed by a tree walk that matched the pre-run snapshot; without that
// match the text says the target is NOT clean and where the originals are.
import { existsSync, rmSync } from 'node:fs';
import {
  planForce,
  createBackup,
  restoreFromBackup,
  verifyAgainst,
  snapshotTree,
} from './force-plan.js';

function listDiffs(diffs, max = 20) {
  const lines = diffs.slice(0, max).map((d) => `    ${d}`);
  if (diffs.length > max) lines.push(`    ... +${diffs.length - max} more`);
  return lines.join('\n');
}

function refusalText(problems) {
  return (
    '--force refused before writing anything:\n' +
    problems.map((p) => `  - ${p}`).join('\n') +
    '\nMove those paths aside, or scaffold into a new directory.'
  );
}

function refusalStatus(targetDir, before) {
  const v = verifyAgainst(targetDir, before);
  return v.clean
    ? `  Nothing was written: the target is left clean (verified: ${v.entries} paths unchanged).\n`
    : `  ! The target changed while create-tess was reading it (${v.diffs.length} paths differ); ` +
        'create-tess did not write to it, but it is not claiming the target is unchanged.\n' +
        listDiffs(v.diffs) + '\n';
}

// Read-only preflight right after the template is staged. Returns null when
// the forced run may proceed, else { stdout, stderr } for the caller to print
// before exiting 1.
export function preflightForce(stagingDir, targetDir) {
  const before = snapshotTree(targetDir);
  const plan = planForce(stagingDir, targetDir);
  if (plan.problems.length === 0) return null;
  return { stdout: refusalStatus(targetDir, before), stderr: refusalText(plan.problems) };
}

// Just before the first write: re-plan (the target may have changed during an
// interactive journey), snapshot, and back up. Returns
// { refusal } or { before, backup }. createBackup() throws on failure after
// undoing its own moves; the caller then verifies against `before`.
export function beginForcedWrite(stagingDir, targetDir, state) {
  state.before = snapshotTree(targetDir);
  const plan = planForce(stagingDir, targetDir);
  if (plan.problems.length) {
    return { refusal: { stdout: refusalStatus(targetDir, state.before), stderr: refusalText(plan.problems) } };
  }
  state.backup = createBackup(targetDir, plan, state.before);
  return { refusal: null };
}

// Undo a failed run. `state` is null for a target that was absent or empty
// before the run (the whole directory is removed, as before 0.2.0); otherwise
// it holds the pre-run snapshot and, once created, the backup.
export function rollback(targetDir, state) {
  if (!state) {
    try {
      rmSync(targetDir, { recursive: true, force: true });
    } catch {
      /* verified below */
    }
    return existsSync(targetDir)
      ? { clean: false, stdout: `  ! Rollback incomplete: ${targetDir} could not be removed.\n` }
      : { clean: true, stdout: '  Rolled back: the target is left clean and re-runnable.\n' };
  }
  const r = state.backup
    ? restoreFromBackup(targetDir, state.backup, state.before)
    : { ...verifyAgainst(targetDir, state.before), errors: [], backupKept: false };
  if (r.clean) {
    return {
      clean: true,
      stdout: `  Rolled back: the target is left clean (verified: ${r.entries} paths match the pre-run snapshot).\n`,
    };
  }
  let out = `  ! Rollback INCOMPLETE: the target is NOT clean. ${r.diffs.length} paths differ from the pre-run snapshot:\n`;
  out += listDiffs(r.diffs) + '\n';
  for (const e of r.errors) out += `    error: ${e}\n`;
  if (state.backup && r.backupKept) {
    out += `  Your original files are in ${state.backup.name}/files (manifest.json lists them).\n`;
  }
  return { clean: false, stdout: out };
}

// Printed after a successful forced run. The backup is never deleted
// automatically: it holds the only copy of whatever the scaffold replaced.
export function backupNotice(backup, checks) {
  if (!backup) return '';
  const n = backup.moved.length + backup.overwritten.length;
  const passed = checks.doctor === true && checks.verify === true;
  return (
    `\n  Replaced paths (${n}) are backed up in ${backup.name}/ (manifest.json lists them; git ignores it).\n` +
    (passed
      ? '  doctor and verify passed. Delete the backup once you have checked nothing in it is still needed.\n'
      : '  doctor/verify did not both pass: keep the backup, and restore from it if this install is not what you want.\n')
  );
}
