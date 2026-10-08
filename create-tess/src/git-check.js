// git-check.js — preflight for git, which Tess OS uses to keep the history of
// your folder (every save is a git commit) and to run its safety checks.
//
// Checked BEFORE anything is written, like Python (python.js): a computer
// without git gets one plain message and an untouched target, never a
// half-finished install. Messages are written for someone who has never used
// a terminal before.
import { spawnSync } from 'node:child_process';

const DOWNLOAD = 'https://git-scm.com/downloads';

export function missingGitMessage(platform = process.platform) {
  const how =
    platform === 'darwin'
      ? '  On a Mac: open the Terminal app, type  xcode-select --install  and press Return,\n' +
        '  then click Install in the window that appears. When it finishes, run this installer again.\n' +
        `  (Or install git from ${DOWNLOAD} and run this installer again.)`
      : `  Install git from ${DOWNLOAD}, then run this installer again.`;
  return (
    'Tess OS needs git (it keeps the history of your folder), and this computer does not have it yet.\n' +
    `${how}\n  Nothing was installed.`
  );
}

// Returns { ok, version, message }. Never throws.
export function checkGit({ cmd = 'git', env = process.env, platform = process.platform } = {}) {
  const probe = spawnSync(cmd, ['--version'], { env, encoding: 'utf8', timeout: 60000 });
  // ENOENT (not installed) and the macOS /usr/bin/git stub that exits non-zero
  // until the Command Line Tools are installed look the same to a user.
  const m = /git version (\d+\.\d+(?:\.\d+)?)/.exec(probe.stdout || '');
  if (probe.error || probe.status !== 0 || !m) {
    return { ok: false, version: null, message: missingGitMessage(platform) };
  }
  return { ok: true, version: m[1], message: null };
}

// The wizard's preflight: returns an error message, or null when git is fine
// or not needed. git keeps the folder's history and runs the save-time safety
// checks, and the second brain's first save is a git commit. Only a run that
// opts out of git (--no-git-init: no repository, so onboarding saves without
// a commit) from the bundled template can go without it.
export function gitPreflight(opts, usingBundledDefault, probe = checkGit) {
  if (opts.noGitInit && usingBundledDefault) return null;
  const g = probe();
  return g.ok ? null : g.message;
}
