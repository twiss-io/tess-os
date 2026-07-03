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
  const instance = await start({ port: 0, dir, deps: fakeDeps, ...opts });
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
