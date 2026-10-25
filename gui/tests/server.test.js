// tess-gui tests — server bootstrap, auth, Host/Origin checks, security
// headers, static serving, path traversal.
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss
import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

import http from 'node:http';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

import { start, resolveStaticPath, staticMimeType } from '../server/index.js';

// fetch()/undici treat "Host" as a forbidden header and silently ignore
// attempts to override it, so a raw http.request is needed to actually send
// a spoofed Host header to the server.
function rawRequest(port, { host, path: reqPath = '/api/health' } = {}) {
  return new Promise((resolve, reject) => {
    const req = http.request(
      { host: '127.0.0.1', port, path: reqPath, method: 'GET', headers: { Host: host } },
      (res) => {
        res.resume();
        res.on('end', () => resolve(res));
      },
    );
    req.on('error', reject);
    req.end();
  });
}

const fakeDeps = {
  runMission: () => {
    throw new Error('runMission should not be called in these tests');
  },
  getClaudeVersion: async () => '2.3.0',
  aggregateSessions: async () => ({ days: [], totals: {} }),
  MIN_CLI_VERSION: '2.0.0',
};

async function makeInstanceDir() {
  return fs.mkdtemp(path.join(os.tmpdir(), 'tess-gui-test-'));
}

const servers = [];
async function startServer(opts = {}) {
  const dir = opts.dir ?? (await makeInstanceDir());
  // The fixture folder is its own project root, and the server sees a clean
  // environment (no agent-session markers) unless a test passes one.
  const instance = await start({ port: 0, dir, projectRoot: dir, env: {}, deps: fakeDeps, ...opts });
  servers.push(instance);
  return instance;
}

after(async () => {
  await Promise.all(servers.map((s) => s.close()));
});

test('start() binds 127.0.0.1 and returns port/token/url/close', async () => {
  const { port, token, url, close } = await startServer();
  assert.ok(port > 0);
  assert.match(token, /^[0-9a-f]{64}$/);
  assert.equal(url, `http://127.0.0.1:${port}/?token=${token}`);
  assert.equal(typeof close, 'function');
});

test('static index.html is served without a token and carries security headers', async () => {
  const { port } = await startServer();
  const res = await fetch(`http://127.0.0.1:${port}/`);
  assert.equal(res.status, 200);
  const body = await res.text();
  assert.match(body, /Mission Control/);
  assert.equal(res.headers.get('content-security-policy'), "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'");
  assert.equal(res.headers.get('x-content-type-options'), 'nosniff');
  assert.equal(res.headers.get('referrer-policy'), 'no-referrer');
  assert.equal(res.headers.get('cache-control'), 'no-store');
});

test('static app.js is served with the correct content type and is cacheable (not no-store)', async () => {
  const { port } = await startServer();

  const js = await fetch(`http://127.0.0.1:${port}/app.js`);
  assert.equal(js.status, 200);
  assert.match(js.headers.get('content-type'), /text\/javascript/);
  assert.notEqual(js.headers.get('cache-control'), 'no-store');
});

test('static assets under nested client subdirectories (css/, js/) are served correctly', async () => {
  const { port } = await startServer();

  const css = await fetch(`http://127.0.0.1:${port}/css/tokens.css`);
  assert.equal(css.status, 200);
  assert.match(css.headers.get('content-type'), /text\/css/);

  const js = await fetch(`http://127.0.0.1:${port}/js/dom.js`);
  assert.equal(js.status, 200);
  assert.match(js.headers.get('content-type'), /text\/javascript/);
});

test('staticMimeType rejects disallowed extensions even for paths that resolve cleanly inside clientDir', () => {
  assert.equal(staticMimeType('/instance/gui/client/index.html'), 'text/html; charset=utf-8');
  assert.equal(staticMimeType('/instance/gui/client/js/dom.js'), 'text/javascript; charset=utf-8');
  assert.equal(staticMimeType('/instance/gui/client/css/tokens.css'), 'text/css; charset=utf-8');
  assert.equal(staticMimeType('/instance/gui/client/stowaway.env'), null);
  assert.equal(staticMimeType('/instance/gui/client/.git/config'), null);
});

test('unknown static path returns 404', async () => {
  const { port } = await startServer();
  const res = await fetch(`http://127.0.0.1:${port}/does-not-exist.txt`);
  assert.equal(res.status, 404);
});

test('/api/* without a token is rejected with 401', async () => {
  const { port } = await startServer();
  const res = await fetch(`http://127.0.0.1:${port}/api/health`);
  assert.equal(res.status, 401);
});

test('/api/* with a wrong token (including mismatched length) is rejected with 401, not 500', async () => {
  const { port } = await startServer();
  const short = await fetch(`http://127.0.0.1:${port}/api/health?token=x`);
  assert.equal(short.status, 401);

  const long = await fetch(`http://127.0.0.1:${port}/api/health?token=${'f'.repeat(200)}`);
  assert.equal(long.status, 401);

  const wrongBearer = await fetch(`http://127.0.0.1:${port}/api/health`, {
    headers: { Authorization: 'Bearer not-the-real-token' },
  });
  assert.equal(wrongBearer.status, 401);
});

test('/api/* with the correct token via query param succeeds', async () => {
  const { port, token } = await startServer();
  const res = await fetch(`http://127.0.0.1:${port}/api/health?token=${token}`);
  assert.equal(res.status, 200);
});

test('/api/* with the correct token via Authorization: Bearer header succeeds', async () => {
  const { port, token } = await startServer();
  const res = await fetch(`http://127.0.0.1:${port}/api/health`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  assert.equal(res.status, 200);
});

test('a mismatched Origin header is rejected with 403 (static and API)', async () => {
  const { port, token } = await startServer();

  const staticRes = await fetch(`http://127.0.0.1:${port}/`, {
    headers: { Origin: 'http://evil.example.com' },
  });
  assert.equal(staticRes.status, 403);

  const apiRes = await fetch(`http://127.0.0.1:${port}/api/health?token=${token}`, {
    headers: { Origin: 'http://evil.example.com' },
  });
  assert.equal(apiRes.status, 403);
});

test('a matching Origin header (127.0.0.1 or localhost) is allowed', async () => {
  const { port, token } = await startServer();
  const res = await fetch(`http://127.0.0.1:${port}/api/health?token=${token}`, {
    headers: { Origin: `http://127.0.0.1:${port}` },
  });
  assert.equal(res.status, 200);
});

test('a mismatched Host header is rejected with 403 (DNS-rebinding defense)', async () => {
  const { port, token } = await startServer();
  const res = await rawRequest(port, { host: 'attacker.example.com', path: `/api/health?token=${token}` });
  assert.equal(res.statusCode, 403);
});

test('a matching Host header (127.0.0.1:port or localhost:port) is allowed', async () => {
  const { port, token } = await startServer();
  const res = await rawRequest(port, { host: `127.0.0.1:${port}`, path: `/api/health?token=${token}` });
  assert.equal(res.statusCode, 200);
});

test('resolveStaticPath rejects traversal and sibling-directory bypasses', () => {
  const clientDir = path.join('/instance', 'gui', 'client');

  assert.equal(resolveStaticPath(clientDir, 'index.html'), path.join(clientDir, 'index.html'));
  assert.equal(resolveStaticPath(clientDir, '../../etc/passwd'), null);
  assert.equal(resolveStaticPath(clientDir, '../clientEVIL/secret.txt'), null);
});

test('resolveStaticPath rejects control characters (e.g. a decoded null byte)', () => {
  const clientDir = path.join('/instance', 'gui', 'client');

  assert.equal(resolveStaticPath(clientDir, 'index.html\u0000.js'), null);
  assert.equal(resolveStaticPath(clientDir, 'app.js'), path.join(clientDir, 'app.js'));
});

test('a request containing a null byte 404s instead of crashing into a 500', async () => {
  const { port } = await startServer();
  const res = await fetch(`http://127.0.0.1:${port}/index.html%00.js`);
  assert.equal(res.status, 404);
  const body = await res.json();
  assert.equal(body.error, 'not found');
});

test('a symlink under gui/client/ pointing outside it is rejected (realpath containment)', async () => {
  const clientDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'client');
  const outsideDir = await makeInstanceDir();
  const secretPath = path.join(outsideDir, 'secret.js');
  await fs.writeFile(secretPath, 'SECRET_OUTSIDE_CLIENT_DIR');

  const symlinkPath = path.join(clientDir, 'tmp-symlink-escape-test.js');
  await fs.symlink(secretPath, symlinkPath);

  try {
    const { port } = await startServer();
    const res = await fetch(`http://127.0.0.1:${port}/tmp-symlink-escape-test.js`);
    assert.equal(res.status, 404);
    const text = await res.text();
    assert.ok(!text.includes('SECRET_OUTSIDE_CLIENT_DIR'));
  } finally {
    await fs.rm(symlinkPath, { force: true });
  }
});

test('a live traversal request over HTTP is rejected end-to-end, not just at the unit level', async () => {
  // fetch()'s own URL parser normalizes literal ".." segments before the
  // request ever hits the wire, so a meaningful server-side test has to
  // percent-encode the slashes (server-side decodeURIComponent reveals the
  // real ".." only after the request is already routed to serveStatic()).
  const { port } = await startServer();

  const encodedTraversal = await fetch(`http://127.0.0.1:${port}/${encodeURIComponent('../server/index.js')}`);
  assert.equal(encodedTraversal.status, 404);

  const encodedSiblingDir = await fetch(`http://127.0.0.1:${port}/${encodeURIComponent('../clientEVIL/secret.txt')}`);
  assert.equal(encodedSiblingDir.status, 404);
});

test('request errors never crash the process and always produce a JSON error body', async () => {
  const { port, token } = await startServer();
  const res = await fetch(`http://127.0.0.1:${port}/api/does-not-exist?token=${token}`);
  assert.equal(res.status, 404);
  const body = await res.json();
  assert.equal(body.error, 'not found');
});


// ---------------------------------------------------------------------------
// Audit hardening C4: working-folder confinement and agent-session refusals.
// ---------------------------------------------------------------------------

// A start() that should be refused: if it wrongly resolves, close the
// server so the test fails instead of leaving a listener behind.
async function assertStartRefused(opts, pattern) {
  let instance = null;
  await assert.rejects(
    (async () => {
      instance = await start(opts);
    })(),
    pattern,
  );
  if (instance) await instance.close();
}

test('start() refuses a working folder outside the project root', async () => {
  const root = await makeInstanceDir();
  const outside = await makeInstanceDir();
  await assertStartRefused({ port: 0, dir: outside, projectRoot: root, env: {}, deps: fakeDeps }, /outside the project root/);
  await assertStartRefused({ port: 0, dir: path.join(root, '..'), projectRoot: root, env: {}, deps: fakeDeps }, /outside the project root/);
});

test('start() refuses an in-root link to a folder outside the project root', async () => {
  const root = await makeInstanceDir();
  const outside = await makeInstanceDir();
  await fs.symlink(outside, path.join(root, 'linked'));
  await assertStartRefused({ port: 0, dir: path.join(root, 'linked'), projectRoot: root, env: {}, deps: fakeDeps }, /outside the project root/);
});

test('start() defaults the project root to the instance that holds the gui package', async () => {
  const guiDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
  const instanceRoot = path.dirname(guiDir);
  const inside = await startServer({ dir: instanceRoot, projectRoot: undefined });
  assert.ok(inside.port > 0);
  const outside = await makeInstanceDir();
  await assertStartRefused({ port: 0, dir: outside, env: {}, deps: fakeDeps }, /outside the project root/);
});

function postMission(port, token, body) {
  return fetch(`http://127.0.0.1:${port}/api/missions?token=${token}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

for (const marker of ['TESS_DISPATCHED', 'TESS_CONSULT_DEPTH', 'CLAUDECODE', 'CLAUDE_CODE_ENTRYPOINT',
  'CODEX_THREAD_ID', 'CODEX_SANDBOX', 'CODEX_SANDBOX_NETWORK_DISABLED']) {
  test(`mission launch is refused when the launcher runs inside an agent session (${marker})`, async () => {
    let calls = 0;
    const deps = { ...fakeDeps, runMission: () => { calls += 1; return { pid: 1, stop() {} }; } };
    const { port, token } = await startServer({ env: { [marker]: '1' }, deps });
    const res = await postMission(port, token, { prompt: 'hello' });
    assert.equal(res.status, 403);
    const body = await res.json();
    assert.match(body.error, /agent session/);
    assert.equal(calls, 0, 'runMission must never be reached');
  });
}

test('mission launch outside an agent session reaches runMission with only the confined folder and prompt', async () => {
  const calls = [];
  const deps = {
    ...fakeDeps,
    runMission: (args) => {
      calls.push(args);
      return { pid: 1, stop() {} };
    },
  };
  const dir = await makeInstanceDir();
  const { port, token } = await startServer({ dir, env: {}, deps });
  const res = await postMission(port, token, {
    prompt: 'hello',
    permissionMode: 'acceptEdits',
    tools: 'Bash,Edit',
    dir: os.tmpdir(),
  });
  assert.equal(res.status, 201);
  assert.equal(calls.length, 1);
  const realDir = await fs.realpath(dir);
  assert.deepEqual(Object.keys(calls[0]).sort(), ['dir', 'onEvent', 'onExit', 'projectRoot', 'prompt']);
  assert.equal(await fs.realpath(calls[0].dir), realDir);
  assert.equal(await fs.realpath(calls[0].projectRoot), realDir);
  assert.equal(calls[0].prompt, 'hello');
});

// The launcher refuses --print-token inside an agent session: it exits
// before starting the server and never prints the tokened URL.
function runLauncher(args, env, timeoutMs = 8000) {
  const launcher = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'bin', 'tess-gui.mjs');
  return new Promise((resolve) => {
    const child = spawn(process.execPath, [launcher, ...args], { env, stdio: ['ignore', 'pipe', 'pipe'] });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (c) => { stdout += c; });
    child.stderr.on('data', (c) => { stderr += c; });
    const timer = setTimeout(() => {
      try { process.kill(child.pid, 'SIGTERM'); } catch { /* already gone */ }
    }, timeoutMs);
    child.on('close', (code, signal) => {
      clearTimeout(timer);
      resolve({ code, signal, stdout, stderr });
    });
  });
}

function cleanEnv() {
  const env = {};
  for (const k of ['PATH', 'HOME', 'TMPDIR', 'SYSTEMROOT']) if (process.env[k] !== undefined) env[k] = process.env[k];
  return env;
}

for (const marker of ['TESS_DISPATCHED', 'CLAUDECODE', 'CODEX_THREAD_ID']) {
  test(`--print-token is refused inside an agent session (${marker})`, async () => {
    const guiDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
    const r = await runLauncher(['--print-token', '--no-open', '--port', '0', '--dir', guiDir],
      { ...cleanEnv(), [marker]: '1' });
    assert.equal(r.signal, null, 'the launcher must exit on its own, not keep serving');
    assert.notEqual(r.code, 0);
    assert.doesNotMatch(r.stdout + r.stderr, /token=/);
    assert.doesNotMatch(r.stdout, /dashboard running/);
    assert.match(r.stderr, /agent session/);
  });
}
