// tess-gui server entry — HTTP server, auth middleware, Origin check.
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss
//
// STUB (Wave 0 scaffold). Implemented in Wave 1 by Ada.
//
// Contract for start({ port, dir }):
//   - Binds an HTTP server to 127.0.0.1 only (never 0.0.0.0).
//   - Generates a random per-launch token; every route (except perhaps a
//     bare health check) must require it, e.g. as a query param or header
//     checked by auth middleware, and must reject mismatched Origin headers.
//   - Resolves an available port if `port` is 0.
//   - Returns { port, token, url } where url = `http://127.0.0.1:${port}/?token=${token}`.
//   - Never logs or returns the token anywhere other than this return value —
//     see gui/bin/tess-gui.mjs for why.
export async function start({ port = 0, dir = process.cwd() } = {}) {
  throw new Error('tess-gui server: start() not yet implemented (Wave 1)');
}
