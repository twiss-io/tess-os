// python.js — preflight for the Python that runs tessctl and onboarding.
//
// Only presence and version are checked: tessctl carries its own copy of
// PyYAML (.tess/vendor/yaml), so a stock macOS /usr/bin/python3 3.9 without
// pip packages is enough. Messages are written for someone who has never
// used a terminal before.
import { spawnSync } from 'node:child_process';

export const MIN_PYTHON = [3, 9];
const MIN_TEXT = `${MIN_PYTHON[0]}.${MIN_PYTHON[1]}`;
const DOWNLOAD = 'https://www.python.org/downloads/';

export function missingPythonMessage(platform = process.platform) {
  const how =
    platform === 'darwin'
      ? '  On a Mac: open the Terminal app, type  xcode-select --install  and press Return,\n' +
        '  then click Install in the window that appears. When it finishes, run this installer again.\n' +
        `  (Or install Python from ${DOWNLOAD} and run this installer again.)`
      : `  Install Python from ${DOWNLOAD}, then run this installer again.`;
  return `Tess OS needs Python ${MIN_TEXT} or newer, and this computer does not have it yet.\n${how}`;
}

export function oldPythonMessage(version) {
  return (
    `Tess OS needs Python ${MIN_TEXT} or newer, and this computer has Python ${version}.\n` +
    `  Install a newer Python from ${DOWNLOAD}, then run this installer again.`
  );
}

// Returns { ok, version, message }. Never throws.
export function checkPython({ cmd = 'python3', env = process.env, platform = process.platform } = {}) {
  const probe = spawnSync(cmd, ['-c', 'import sys; print("%d.%d" % sys.version_info[:2])'], {
    env,
    encoding: 'utf8',
    timeout: 60000,
  });
  // ENOENT (not installed) and the macOS /usr/bin/python3 stub that exits
  // non-zero until the Command Line Tools are installed look the same to a user.
  const version = (probe.stdout || '').trim();
  if (probe.error || probe.status !== 0 || !/^\d+\.\d+$/.test(version)) {
    return { ok: false, version: null, message: missingPythonMessage(platform) };
  }
  const [major, minor] = version.split('.').map(Number);
  if (major < MIN_PYTHON[0] || (major === MIN_PYTHON[0] && minor < MIN_PYTHON[1])) {
    return { ok: false, version, message: oldPythonMessage(version) };
  }
  return { ok: true, version, message: null };
}
