// tess-gui claude-runner — spawns the user's logged-in `claude` CLI per mission.
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss
import { spawn, execFile } from 'node:child_process';
import { StringDecoder } from 'node:string_decoder';

export const MIN_CLI_VERSION = '2.0.0';

// A single stdout "line" (bytes buffered between two '\n's) is capped at 10MB.
// This is a defensive ceiling against a runaway/non-conforming child process,
// not an expected size for real stream-json events.
const MAX_LINE_BYTES = 10 * 1024 * 1024;
const KILL_GRACE_MS = 5000;

function parseVersionParts(raw) {
  if (typeof raw !== 'string') return null;
  const m = raw.match(/(\d+)\.(\d+)\.(\d+)/);
  if (!m) return null;
  return [Number(m[1]), Number(m[2]), Number(m[3])];
}

// Dependency-free major.minor compare (patch is ignored, per contract).
export function isCompatible(version) {
  const v = parseVersionParts(version);
  const min = parseVersionParts(MIN_CLI_VERSION);
  if (!v || !min) return false;
  if (v[0] !== min[0]) return v[0] > min[0];
  return v[1] >= min[1];
}

export function getClaudeVersion({ claudeBin = 'claude' } = {}) {
  return new Promise((resolve) => {
    execFile(claudeBin, ['--version'], { timeout: 5000 }, (err, stdout) => {
      if (err) {
        resolve(null);
        return;
      }
      resolve(stdout.trim());
    });
  });
}

export function runMission({ dir, prompt, claudeBin = 'claude', onEvent, onExit } = {}) {
  // --include-partial-messages is intentionally omitted: the dashboard client
  // renders complete assistant messages, not streaming deltas, so relaying
  // partial-message events would just require filtering them back out
  // downstream for no benefit to the current client.
  const args = ['-p', prompt, '--output-format', 'stream-json', '--verbose'];
  // stdin is explicitly ignored (not left as an unwritten-to pipe): the CLI
  // waits up to 3s for stdin data before proceeding, and every mission here
  // is prompt-driven via argv, never stdin.
  const child = spawn(claudeBin, args, { cwd: dir, shell: false, stdio: ['ignore', 'pipe', 'pipe'] });

  let exited = false;
  const emit = (event) => {
    if (exited || !onEvent) return;
    onEvent(event);
  };

  function emitLine(line) {
    if (line.length === 0) return;
    try {
      emit(JSON.parse(line));
    } catch {
      emit({ type: 'raw', text: line });
    }
  }

  const stdoutDecoder = new StringDecoder('utf8');
  let stdoutBuf = '';
  child.stdout.on('data', (chunk) => {
    stdoutBuf += stdoutDecoder.write(chunk);
    let idx;
    while ((idx = stdoutBuf.indexOf('\n')) !== -1) {
      emitLine(stdoutBuf.slice(0, idx));
      stdoutBuf = stdoutBuf.slice(idx + 1);
    }
    if (Buffer.byteLength(stdoutBuf, 'utf8') > MAX_LINE_BYTES) {
      emit({ type: 'error', text: `stdout line exceeded ${MAX_LINE_BYTES}-byte cap; buffer dropped` });
      stdoutBuf = '';
    }
  });

  child.stdout.on('end', () => {
    stdoutBuf += stdoutDecoder.end();
    if (stdoutBuf.length > 0) emitLine(stdoutBuf);
    stdoutBuf = '';
  });

  const stderrDecoder = new StringDecoder('utf8');
  child.stderr.on('data', (chunk) => {
    emit({ type: 'stderr', text: stderrDecoder.write(chunk) });
  });

  // Keyed off 'close', not 'exit': 'exit' can fire before the stdio streams
  // have finished flowing, which would lose trailing stdout data.
  child.on('close', (code, signal) => {
    exited = true;
    if (onExit) onExit({ code, signal });
  });

  // A spawn-level failure (e.g. ENOENT for a missing claudeBin) never reaches
  // 'close' — surface it as both an event and a terminal exit so callers
  // waiting on onExit are never left hanging.
  child.on('error', (err) => {
    emit({ type: 'error', text: err.message });
    if (!exited) {
      exited = true;
      if (onExit) onExit({ code: null, signal: null });
    }
  });

  function stop() {
    if (exited) return;
    child.kill('SIGTERM');
    const escalate = setTimeout(() => {
      if (!exited) child.kill('SIGKILL');
    }, KILL_GRACE_MS);
    escalate.unref();
  }

  return { pid: child.pid, stop };
}
