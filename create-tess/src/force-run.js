// force-run.js — the index.js side of the rollback contract: when to plan,
// when to back up, and what to tell the operator. Every "left clean" line
// printed here is backed by a tree walk that matched the pre-run snapshot (or,
// for a directory the run created, by that directory being gone again);
// without that match the text says the target is NOT clean and where the
// originals are.
//
// `state` for a target that existed before the run:
//   { before, backup, hadContent }
//   before      the pre-run snapshot (set by beginWrite / preflightForce);
//   backup      what createBackup() moved or copied aside, or null;
//   hadContent  the target held content (a --force run). An empty snapshot
//               then means the walk saw nothing, so nothing can be verified.
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

const UNVERIFIABLE =
  'the pre-run snapshot of this non-empty target is empty, so create-tess cannot verify it';

// verifyAgainst(), except that a target known to hold content can never be
// "verified" against an empty snapshot.
function verifyState(targetDir, state) {
  if (state.hadContent && state.before.size === 0) {
    return { clean: false, diffs: [UNVERIFIABLE], entries: 0 };
  }
  return verifyAgainst(targetDir, state.before);
}

function refusalStatus(targetDir, state) {
  const v = verifyState(targetDir, state);
  return v.clean
    ? `  Nothing was written: the target is left clean (verified: ${v.entries} paths unchanged).\n`
    : `  ! create-tess did not write to the target, but cannot claim it is unchanged (${v.diffs.length} paths differ):\n` +
        listDiffs(v.diffs) + '\n';
}

// Snapshot the target, or explain why it cannot be: --force must read every
// file to back it up and to verify a rollback. Returns { before } or
// { refusal: { stdout, stderr } }.
function takeSnapshot(targetDir) {
  try {
    return { before: snapshotTree(targetDir) };
  } catch (err) {
    const why =
      err.code === 'EACCES' || err.code === 'EPERM'
        ? `--force needs to read every file in the target (to back it up and verify a rollback), ` +
          `and cannot read ${err.path || 'one of them'} (${err.code}). Fix its permissions, or ` +
          'scaffold into a new directory.'
        : `create-tess could not snapshot the target: ${err.message}`;
    return { refusal: { stdout: '  Nothing was written to the target.\n', stderr: why } };
  }
}

// Read-only preflight right after the template is staged (--force over
// content only). Returns null when the run may proceed, else
// { stdout, stderr } for the caller to print before exiting 1.
export function preflightForce(stagingDir, targetDir) {
  const snap = takeSnapshot(targetDir);
  if (snap.refusal) return snap.refusal;
  const plan = planForce(stagingDir, targetDir);
  if (plan.problems.length === 0) return null;
  const state = { before: snap.before, hadContent: true };
  return { stdout: refusalStatus(targetDir, state), stderr: refusalText(plan.problems) };
}

// Just before the first write into a target that already existed: snapshot
// it; for --force over content, also re-plan (the target may have changed
// during an interactive journey) and back up (state.backup stays null when
// the plan replaces nothing). Returns { refusal }. createBackup() throws on
// failure after undoing its own moves; the caller then calls verifyOnly().
export function beginWrite(stagingDir, targetDir, state) {
  const snap = takeSnapshot(targetDir);
  if (snap.refusal) return { refusal: snap.refusal };
  state.before = snap.before;
  if (!state.hadContent) return { refusal: null };
  const plan = planForce(stagingDir, targetDir);
  if (plan.problems.length) {
    return { refusal: { stdout: refusalStatus(targetDir, state), stderr: refusalText(plan.problems) } };
  }
  state.backup = createBackup(targetDir, plan, state.before);
  return { refusal: null };
}

// The run created the target (and maybe parents): remove `createdRoot`, the
// shallowest directory it created, and check it is gone.
function removeCreated(createdRoot) {
  try {
    rmSync(createdRoot, { recursive: true, force: true });
  } catch {
    /* verified below */
  }
  return existsSync(createdRoot)
    ? { clean: false, stdout: `  ! Rollback incomplete: ${createdRoot} could not be removed.\n` }
    : { clean: true, stdout: '  Rolled back: the target is left clean and re-runnable.\n' };
}

// Undo a failed run. `state` is null when the target did not exist before
// the run; `createdRoot` is then what to remove (default: the target).
export function rollback(targetDir, state, createdRoot = targetDir) {
  if (!state) return removeCreated(createdRoot);
  if (state.hadContent && state.before.size === 0) {
    // A restore deletes every path missing from the snapshot. With an empty
    // snapshot of a non-empty target that is everything, so do not attempt it.
    let out = `  ! Rollback NOT attempted: ${UNVERIFIABLE}. Nothing was deleted; check ${targetDir} by hand.\n`;
    if (state.backup) out += `  Your original files are in ${state.backup.name}/files (manifest.json lists them).\n`;
    return { clean: false, stdout: out };
  }
  const r = restoreFromBackup(targetDir, state.backup, state.before);
  if (r.clean) {
    const what = r.entries === 0 ? 'empty again, as before the run' : `${r.entries} paths match the pre-run snapshot`;
    return { clean: true, stdout: `  Rolled back: the target is left clean (verified: ${what}).\n` };
  }
  let out = `  ! Rollback INCOMPLETE: the target is NOT clean. ${r.diffs.length} paths differ from the pre-run snapshot:\n`;
  out += listDiffs(r.diffs) + '\n';
  for (const e of r.errors) out += `    error: ${e}\n`;
  if (state.backup && r.backupKept) {
    out += `  Your original files are in ${state.backup.name}/files (manifest.json lists them).\n`;
  }
  return { clean: false, stdout: out };
}

// Nothing was scaffolded (the backup step itself failed): only verify.
export function verifyOnly(targetDir, state) {
  const v = verifyState(targetDir, state);
  return v.clean
    ? `  Nothing was scaffolded: the target is left clean (verified: ${v.entries} paths unchanged).\n`
    : `  ! The target is NOT clean: ${v.diffs.length} paths differ from the pre-run snapshot:\n${listDiffs(v.diffs)}\n`;
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
