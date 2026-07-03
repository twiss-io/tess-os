// tess-gui tests — claude-runner.js: spawning the logged-in `claude` CLI
// per mission.
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, chmodSync, rmSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { runMission, getClaudeVersion, isCompatible, MIN_CLI_VERSION } from '../server/claude-runner.js';

function tmpDir() {
  return mkdtempSync(join(tmpdir(), 'tess-gui-runner-'));
}

// Writes an executable fake `claude` binary (a Node script). Deliberately
// avoids process.exit() inside these fixtures: killing the event loop before
// pending stdout writes finish draining can truncate data on a pipe, which
// is exactly the kind of relay bug this test suite needs to catch, not cause.
function writeFakeBin(dir, name, body) {
  const p = join(dir, name);
  writeFileSync(p, `#!/usr/bin/env node\n${body}\n`);
  chmodSync(p, 0o755);
  return p;
}

function collectRun(bin, opts = {}) {
  const events = [];
  let exitInfo = null;
  let resolveDone;
  const done = new Promise((resolve) => {
    resolveDone = resolve;
  });
  const { pid, stop } = runMission({
    dir: opts.dir,
    prompt: opts.prompt ?? 'hello',
    claudeBin: bin,
    onEvent: (e) => events.push(e),
    onExit: (info) => {
      exitInfo = info;
      resolveDone();
    },
  });
  return { events, done, pid, stop, getExitInfo: () => exitInfo };
}

test('runMission: relays NDJSON events and reports a clean exit', async () => {
  const dir = tmpDir();
  const bin = writeFakeBin(
    dir,
    'claude',
    `process.stdout.write(JSON.stringify({type:'a',n:1}) + '\\n');
     process.stdout.write(JSON.stringify({type:'b',n:2}) + '\\n');`,
  );
  try {
    const { events, done, getExitInfo } = collectRun(bin);
    await done;
    assert.deepEqual(events, [
      { type: 'a', n: 1 },
      { type: 'b', n: 2 },
    ]);
    assert.deepEqual(getExitInfo(), { code: 0, signal: null });
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('runMission: never passes the prompt through a shell — metacharacters arrive as one intact argv entry', async () => {
  const dir = tmpDir();
  const sentinel = join(dir, 'sentinel');
  const bin = writeFakeBin(
    dir,
    'claude',
    `for (const a of process.argv.slice(2)) {
       process.stdout.write(JSON.stringify({type:'argv', value:a}) + '\\n');
     }`,
  );
  const payload = `\`touch ${sentinel}\` && $(touch ${sentinel}) ; touch ${sentinel} # ${sentinel}`;
  try {
    const { events, done } = collectRun(bin, { prompt: payload });
    await done;
    const argvEvents = events.filter((e) => e.type === 'argv').map((e) => e.value);
    assert.deepEqual(argvEvents, ['-p', payload, '--output-format', 'stream-json', '--verbose']);
    assert.equal(existsSync(sentinel), false, 'shell metacharacters in the prompt must never execute');
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('runMission: buffers a JSON line correctly when it arrives split across two stdout chunks', async () => {
  const dir = tmpDir();
  const bin = writeFakeBin(
    dir,
    'claude',
    `process.stdout.write('{"type":"part1"');
     setTimeout(() => {
       process.stdout.write('}\\n{"type":"part2"}\\n');
     }, 40);`,
  );
  try {
    const { events, done } = collectRun(bin);
    await done;
    assert.deepEqual(events, [{ type: 'part1' }, { type: 'part2' }]);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('runMission: an unparseable stdout line is relayed as a raw event, not dropped or crashed on', async () => {
  const dir = tmpDir();
  const bin = writeFakeBin(
    dir,
    'claude',
    `process.stdout.write('not json at all\\n');
     process.stdout.write(JSON.stringify({type:'after'}) + '\\n');`,
  );
  try {
    const { events, done } = collectRun(bin);
    await done;
    assert.deepEqual(events, [
      { type: 'raw', text: 'not json at all' },
      { type: 'after' },
    ]);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('runMission: child stdin is ignored, not left open as an unwritten-to pipe (regression for 3s stdin-wait stall)', async () => {
  const dir = tmpDir();
  const bin = writeFakeBin(
    dir,
    'claude',
    `let ended = false;
     process.stdin.on('end', () => { ended = true; });
     process.stdin.resume();
     setTimeout(() => {
       process.stdout.write(JSON.stringify({type:'stdin-ended', value: ended}) + '\\n');
     }, 200);`,
  );
  try {
    const { events, done } = collectRun(bin);
    await done;
    const event = events.find((e) => e.type === 'stdin-ended');
    assert.ok(event, 'expected the fake binary to report its stdin state');
    assert.equal(
      event.value,
      true,
      'child stdin must reach EOF immediately (ignored), not sit open waiting for data the parent never sends',
    );
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('runMission: stderr output is relayed as a stderr event', async () => {
  const dir = tmpDir();
  const bin = writeFakeBin(dir, 'claude', `process.stderr.write('warning: something\\n');`);
  try {
    const { events, done } = collectRun(bin);
    await done;
    const stderrEvents = events.filter((e) => e.type === 'stderr');
    assert.equal(stderrEvents.length, 1);
    assert.match(stderrEvents[0].text, /warning: something/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('runMission: a final unterminated stdout line is still flushed at process end', async () => {
  const dir = tmpDir();
  const bin = writeFakeBin(dir, 'claude', `process.stdout.write(JSON.stringify({type:'trailing'}));`);
  try {
    const { events, done } = collectRun(bin);
    await done;
    assert.deepEqual(events, [{ type: 'trailing' }]);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('runMission: a single stdout line exceeding the 10MB cap is dropped with an error event, not buffered unbounded', async () => {
  const dir = tmpDir();
  const bin = writeFakeBin(
    dir,
    'claude',
    `const chunk = 'x'.repeat(1024 * 1024);
     for (let i = 0; i < 12; i++) process.stdout.write(chunk);`,
  );
  try {
    const { events, done } = collectRun(bin);
    await done;
    const errorEvents = events.filter((e) => e.type === 'error');
    assert.equal(errorEvents.length, 1);
    assert.match(errorEvents[0].text, /10485760-byte cap/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('runMission: spawn failure (missing binary) still reaches onExit, not just onEvent', async () => {
  const dir = tmpDir();
  const missing = join(dir, 'does-not-exist-claude');
  try {
    const { events, done, getExitInfo } = collectRun(missing);
    await done;
    assert.ok(events.some((e) => e.type === 'error'), 'a spawn ENOENT must surface an error event');
    assert.deepEqual(getExitInfo(), { code: null, signal: null });
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('runMission: stop() escalates SIGTERM to SIGKILL after the grace period if the process ignores it', async () => {
  const dir = tmpDir();
  const bin = writeFakeBin(
    dir,
    'claude',
    `process.on('SIGTERM', () => {}); // swallow it to force escalation
     setInterval(() => {}, 1000);`,
  );
  try {
    const { done, stop, getExitInfo } = collectRun(bin);
    // give the fake process a moment to install its SIGTERM handler before we stop it
    await new Promise((r) => setTimeout(r, 500));
    const start = Date.now();
    stop();
    await done;
    const elapsedMs = Date.now() - start;

    assert.equal(getExitInfo().signal, 'SIGKILL', 'a SIGTERM-ignoring process must eventually be SIGKILLed');
    assert.ok(elapsedMs >= 4900, `expected the ~5s grace period to elapse before SIGKILL, got ${elapsedMs}ms`);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('getClaudeVersion: resolves the trimmed version string on success', async () => {
  const dir = tmpDir();
  const bin = writeFakeBin(
    dir,
    'claude',
    `if (process.argv[2] === '--version') { console.log('2.3.1 (Claude Code)'); }`,
  );
  try {
    const version = await getClaudeVersion({ claudeBin: bin });
    assert.equal(version, '2.3.1 (Claude Code)');
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('getClaudeVersion: resolves null on nonzero exit', async () => {
  const dir = tmpDir();
  const bin = writeFakeBin(dir, 'claude', `process.exitCode = 1;`);
  try {
    const version = await getClaudeVersion({ claudeBin: bin });
    assert.equal(version, null);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('getClaudeVersion: resolves null when the binary does not exist', async () => {
  const dir = tmpDir();
  try {
    const version = await getClaudeVersion({ claudeBin: join(dir, 'nope') });
    assert.equal(version, null);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('isCompatible: major.minor compare against MIN_CLI_VERSION, patch ignored', () => {
  assert.equal(MIN_CLI_VERSION, '2.0.0');
  assert.equal(isCompatible('2.0.0'), true);
  assert.equal(isCompatible('2.0.9'), true, 'higher patch, same minor, is compatible');
  assert.equal(isCompatible('2.1.0'), true, 'higher minor is compatible');
  assert.equal(isCompatible('3.0.0'), true, 'higher major is compatible');
  assert.equal(isCompatible('1.9.9'), false, 'lower major is not compatible');
  assert.equal(isCompatible('1.99.0'), false, 'major dominates even with a much higher minor');
  assert.equal(isCompatible('2.3.1 (Claude Code)'), true, 'extracts the version out of surrounding text');
  assert.equal(isCompatible('garbage'), false);
  assert.equal(isCompatible(undefined), false);
  assert.equal(isCompatible(null), false);
});
