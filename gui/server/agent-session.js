// tess-gui agent-session detection and project-root confinement.
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss
//
// The dashboard's token authorizes spawning `claude`, so the launcher must
// not hand it to, or launch missions for, an AI agent that started it. The
// signals are the ones Tess already uses, not new ones:
//   * TESS_DISPATCHED and TESS_CONSULT_DEPTH, which tessctl's dispatch
//     drivers set in every child they start (.tess/bin/tessctl
//     _run_child_env; the gate's nested-agent rule reads TESS_CONSULT_DEPTH);
//   * the Claude Code / Codex session markers in tessctl's
//     AGENT_SESSION_MARKERS (the same tuple as scripts/brain/brainlib/roots.py).
import fs from 'node:fs';
import path from 'node:path';

export const DISPATCH_MARKERS = Object.freeze(['TESS_DISPATCHED', 'TESS_CONSULT_DEPTH']);
export const AGENT_SESSION_MARKERS = Object.freeze([
  'CODEX_THREAD_ID',
  'CODEX_SANDBOX',
  'CODEX_SANDBOX_NETWORK_DISABLED',
  'CLAUDECODE',
  'CLAUDE_CODE_ENTRYPOINT',
]);

// The first agent-session signal set in `env`, or null. A dispatch marker
// counts when set to anything but empty or "0"; a session marker counts
// whenever it is present, as in tessctl.
export function agentSessionMarker(env = process.env) {
  for (const name of DISPATCH_MARKERS) {
    const v = env[name];
    if (typeof v === 'string' && v.trim() !== '' && v.trim() !== '0') return name;
  }
  for (const name of AGENT_SESSION_MARKERS) {
    if (Object.prototype.hasOwnProperty.call(env, name)) return name;
  }
  return null;
}

// The real path of `dir` when it is `projectRoot` or lies under it (links
// on the way and at the end followed); throws otherwise. Both must exist.
export function confineToProjectRoot(dir, projectRoot) {
  if (typeof dir !== 'string' || !dir || typeof projectRoot !== 'string' || !projectRoot) {
    throw new Error('tess-gui: a working folder and its project root are required');
  }
  const realRoot = fs.realpathSync(projectRoot);
  let realDir;
  try {
    realDir = fs.realpathSync(dir);
  } catch {
    throw new Error('tess-gui: the working folder does not exist or is outside the project root');
  }
  const rel = path.relative(realRoot, realDir);
  if (rel === '' || (!rel.startsWith('..') && !path.isAbsolute(rel))) return realDir;
  throw new Error('tess-gui: the working folder is outside the project root');
}
