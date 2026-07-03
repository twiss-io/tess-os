// tess-gui server entry — HTTP server, auth middleware, Origin check.
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss
//
// Contract for start({ port, dir, openBrowser, deps }):
//   - Binds an HTTP server to 127.0.0.1 only (never 0.0.0.0).
//   - Generates a random per-launch token; every /api/* route requires it
//     (Authorization: Bearer <token> header or ?token= query param).
//   - Rejects requests with a mismatched Host header (DNS-rebinding) or a
//     present-but-mismatched Origin header, for both static and API routes.
//   - Resolves an available port if `port` is 0.
//   - Returns { port, token, url, close() } where
//     url = `http://127.0.0.1:${port}/?token=${token}`.
//   - `deps` is an optional override for the default runner/aggregator
//     modules (used by tests to avoid depending on a real `claude` binary).
//   - Never logs or returns the token anywhere other than this return value —
//     see gui/bin/tess-gui.mjs for why.
import http from 'node:http';
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { createRouter } from './routes/index.js';
import { sendJson } from './routes/util.js';

const CSP =
  "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; " +
  "font-src https://fonts.gstatic.com; connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'";

// The dashboard client is a growing set of ES modules and stylesheets under
// gui/client/ (e.g. js/*.js, css/*.css) rather than a fixed 3-file layout, so
// static serving is extension-bounded rather than an exact-name allowlist.
// Path containment (resolveStaticPath) is the real traversal defense; the
// extension check is defense in depth against exposing unexpected file
// types (dotfiles, source maps, etc.) that might land in gui/client/.
const STATIC_MIME_BY_EXT = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
};

function applySecurityHeaders(res) {
  res.setHeader('Content-Security-Policy', CSP);
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('Referrer-Policy', 'no-referrer');
}

// Compares two secrets in constant time regardless of length by hashing both
// to a fixed-size digest first — crypto.timingSafeEqual throws on a length
// mismatch, and an early-return length check would itself leak timing.
function safeCompare(a, b) {
  const hashA = crypto.createHash('sha256').update(String(a)).digest();
  const hashB = crypto.createHash('sha256').update(String(b)).digest();
  return crypto.timingSafeEqual(hashA, hashB);
}

function isAllowedHost(hostHeader, port) {
  if (!hostHeader) return false;
  const allowed = new Set([`127.0.0.1:${port}`, `localhost:${port}`]);
  if (port === 80) {
    allowed.add('127.0.0.1');
    allowed.add('localhost');
  }
  return allowed.has(hostHeader);
}

function isAllowedOrigin(originHeader, port) {
  if (!originHeader) return true;
  const allowed = new Set([`http://127.0.0.1:${port}`, `http://localhost:${port}`]);
  return allowed.has(originHeader);
}

function extractToken(req, parsedUrl) {
  const authHeader = req.headers['authorization'];
  if (typeof authHeader === 'string' && authHeader.startsWith('Bearer ')) {
    return authHeader.slice('Bearer '.length);
  }
  const queryToken = parsedUrl.searchParams.get('token');
  return queryToken || null;
}

function isAuthorized(req, parsedUrl, token) {
  const supplied = extractToken(req, parsedUrl);
  if (!supplied) return false;
  return safeCompare(supplied, token);
}

// Resolves a requested static path against clientDir, rejecting traversal
// and "sibling directory" bypasses (e.g. a naive prefix check would let
// `gui/clientEVIL` pass a `startsWith('gui/client')` test).
export function resolveStaticPath(clientDir, relativePath) {
  // Control characters (e.g. a decoded %00) pass both the containment check
  // below and the extension gate, then make fs.readFile throw synchronously
  // (ERR_INVALID_ARG_VALUE) instead of erroring through its callback — reject
  // them here so that surfaces as an ordinary 404, not a 500.
  if (/[\x00-\x1f]/.test(relativePath)) {
    return null;
  }
  const resolved = path.resolve(clientDir, relativePath);
  const base = clientDir.endsWith(path.sep) ? clientDir : clientDir + path.sep;
  if (resolved !== clientDir && !resolved.startsWith(base)) {
    return null;
  }
  return resolved;
}

// Pure so it can be unit-tested against synthetic paths without touching
// disk or the real gui/client/ tree.
export function staticMimeType(resolvedPath) {
  return STATIC_MIME_BY_EXT[path.extname(resolvedPath).toLowerCase()] ?? null;
}

async function serveStatic(ctx, pathname, res) {
  const relativePath = pathname === '/' ? 'index.html' : pathname.replace(/^\/+/, '');
  const resolved = resolveStaticPath(ctx.clientDir, relativePath);
  if (!resolved) {
    sendJson(res, 404, { error: 'not found' });
    return;
  }

  const mimeType = staticMimeType(resolved);
  if (!mimeType) {
    sendJson(res, 404, { error: 'not found' });
    return;
  }

  // resolveStaticPath only validates the requested path string; it doesn't
  // account for symlinks. A symlink placed under gui/client/ pointing
  // outside it would still pass that check and be followed by fs.readFile,
  // so re-verify containment against the real (symlink-resolved) path too.
  // ctx.realClientDir is resolved once at startup, so this adds only one
  // extra realpath syscall per static request, not two.
  let realResolved;
  try {
    realResolved = await fs.promises.realpath(resolved);
  } catch {
    sendJson(res, 404, { error: 'not found' });
    return;
  }
  const realBase = ctx.realClientDir.endsWith(path.sep) ? ctx.realClientDir : ctx.realClientDir + path.sep;
  if (realResolved !== ctx.realClientDir && !realResolved.startsWith(realBase)) {
    sendJson(res, 404, { error: 'not found' });
    return;
  }

  const ext = path.extname(resolved).toLowerCase();
  fs.readFile(resolved, (err, data) => {
    if (err) {
      sendJson(res, 404, { error: 'not found' });
      return;
    }
    const headers = { 'Content-Type': mimeType };
    if (ext === '.html') headers['Cache-Control'] = 'no-store';
    res.writeHead(200, headers);
    res.end(data);
  });
}

async function loadDefaultDeps() {
  let runnerMod = {};
  try {
    runnerMod = await import('./claude-runner.js');
  } catch (err) {
    console.error('tess-gui: failed to load claude-runner.js:', err?.message ?? err);
  }
  // aggregateSessions lives in jsonl-stream.js, not claude-runner.js — loaded
  // separately so one module being incomplete doesn't take down the other.
  let streamMod = {};
  try {
    streamMod = await import('./jsonl-stream.js');
  } catch (err) {
    console.error('tess-gui: failed to load jsonl-stream.js:', err?.message ?? err);
  }
  return {
    runMission:
      runnerMod.runMission ??
      (() => {
        throw new Error('tess-gui: runMission is not available (claude-runner.js not implemented)');
      }),
    getClaudeVersion: runnerMod.getClaudeVersion ?? (async () => null),
    aggregateSessions: streamMod.aggregateSessions ?? (async () => ({ days: [], totals: {} })),
    MIN_CLI_VERSION: runnerMod.MIN_CLI_VERSION ?? '0.0.0',
  };
}

function createRequestHandler(ctx, router) {
  return async (req, res) => {
    try {
      applySecurityHeaders(res);

      let parsedUrl;
      let pathname;
      try {
        parsedUrl = new URL(req.url, 'http://127.0.0.1');
        pathname = decodeURIComponent(parsedUrl.pathname);
      } catch {
        sendJson(res, 400, { error: 'bad request' });
        return;
      }

      if (!isAllowedHost(req.headers.host, ctx.port)) {
        sendJson(res, 403, { error: 'forbidden' });
        return;
      }
      if (!isAllowedOrigin(req.headers.origin, ctx.port)) {
        sendJson(res, 403, { error: 'forbidden' });
        return;
      }

      if (pathname.startsWith('/api/')) {
        if (!isAuthorized(req, parsedUrl, ctx.token)) {
          sendJson(res, 401, { error: 'unauthorized' });
          return;
        }
        const handled = await router(req, res, pathname, parsedUrl.searchParams);
        if (!handled) sendJson(res, 404, { error: 'not found' });
        return;
      }

      if (req.method !== 'GET') {
        sendJson(res, 404, { error: 'not found' });
        return;
      }
      await serveStatic(ctx, pathname, res);
    } catch (err) {
      console.error('tess-gui: request error:', err);
      if (!res.headersSent) {
        sendJson(res, 500, { error: 'internal server error' });
      } else {
        try {
          res.end();
        } catch {
          /* connection already gone */
        }
      }
    }
  };
}

export async function start({ port = 0, dir = process.cwd(), openBrowser, deps: depsOverride, paths: pathsOverride } = {}) {
  const defaultDeps = await loadDefaultDeps();
  const deps = { ...defaultDeps, ...depsOverride };

  const packageRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

  // historyPath/projectsDir/dataDir are overridable (via `paths`) so tests
  // never have to read or depend on real ~/.claude/ state or on-disk
  // gui/.data/ (which is otherwise shared, persistent, and process-wide).
  const paths = {
    historyPath: path.join(os.homedir(), '.claude', 'history.jsonl'),
    projectsDir: path.join(os.homedir(), '.claude', 'projects'),
    dataDir: path.join(packageRoot, '.data'),
    ...pathsOverride,
  };
  const dataDir = paths.dataDir;

  const clientDir = path.join(packageRoot, 'client');
  // Resolved once at startup (not per-request) since it can't change during
  // the process lifetime — see the realpath containment check in serveStatic.
  const realClientDir = await fs.promises.realpath(clientDir);

  const ctx = {
    dir: path.resolve(dir),
    packageRoot,
    clientDir,
    realClientDir,
    port: 0,
    token: crypto.randomBytes(32).toString('hex'),
    deps,
    missions: new Map(),
    dataDir,
    ledgerPath: path.join(dataDir, 'missions.jsonl'),
    savedMissionsPath: path.join(dataDir, 'saved-missions.json'),
    savedMissionsQueue: Promise.resolve(),
    ledgerQueue: Promise.resolve(),
    historyPath: paths.historyPath,
    projectsDir: paths.projectsDir,
  };

  const router = createRouter(ctx);
  const server = http.createServer(createRequestHandler(ctx, router));

  await new Promise((resolve, reject) => {
    const onError = (err) => reject(err);
    server.once('error', onError);
    server.listen(port, '127.0.0.1', () => {
      server.removeListener('error', onError);
      resolve();
    });
  });

  ctx.port = server.address().port;
  const url = `http://127.0.0.1:${ctx.port}/?token=${ctx.token}`;

  if (typeof openBrowser === 'function') {
    try {
      openBrowser(url);
    } catch (err) {
      console.error('tess-gui: openBrowser failed:', err?.message ?? err);
    }
  }

  function close() {
    return new Promise((resolve) => {
      for (const mission of ctx.missions.values()) {
        for (const subscriber of mission.subscribers) {
          try {
            subscriber.end();
          } catch {
            /* already closed */
          }
        }
        mission.subscribers.clear();
      }
      if (typeof server.closeAllConnections === 'function') {
        server.closeAllConnections();
      }
      server.close(() => resolve());
    });
  }

  return { port: ctx.port, token: ctx.token, url, close };
}
