// tess-gui claude-runner — spawns the user's logged-in `claude` CLI per mission.
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss
//
// STUB (Wave 0 scaffold). Implemented in Wave 1 by Selene.
//
// Contract for runMission(command, { cwd, onEvent }):
//   - Spawns `claude -p <command> --output-format stream-json --verbose
//     --include-partial-messages` as a foreground child process (never
//     `claude --bg` — see design doc §7 on macOS Full Disk Access).
//   - Never reads .claude/vault/ or .claude/tess-secrets/ directly; only the
//     CLI itself resolves credentials.
//   - Streams parsed JSONL events to onEvent(event) as they arrive — see
//     jsonl-stream.js for the line-buffering contract.
//   - Runs a startup preflight (`claude --version`) and fails loud with a
//     clear upgrade message rather than surfacing a raw CLI error mid-mission.
export function runMission(command, { cwd, onEvent } = {}) {
  throw new Error('tess-gui claude-runner: runMission() not yet implemented (Wave 1)');
}

export const MIN_CLI_VERSION = '2.0.0';
