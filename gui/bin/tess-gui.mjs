#!/usr/bin/env node
// tess-gui — launcher for the Tess OS Mission Control dashboard.
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss
//
// SECURITY: never print the full tokened dashboard URL to stdout/terminal —
// terminal scrollback, tmux history, and CI logs all persist it, and the
// token is an RCE-equivalent credential (it authorizes spawning `claude`
// locally). Only the bare origin is printed. The full URL is used
// in-process to auto-open the browser and is available on request via
// --print-token.
import { start } from '../server/index.js';
import { spawn } from 'node:child_process';

process.on('unhandledRejection', (reason) => {
  console.error('tess-gui: unhandled rejection:', reason);
  process.exit(1);
});

function parseArgs(argv) {
  const opts = { port: 0, dir: process.cwd(), open: true, printToken: false };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === '--no-open') {
      opts.open = false;
    } else if (arg === '--print-token') {
      opts.printToken = true;
    } else if (arg === '--port') {
      opts.port = Number(argv[++i]);
    } else if (arg.startsWith('--port=')) {
      opts.port = Number(arg.slice('--port='.length));
    } else if (arg === '--dir') {
      opts.dir = argv[++i];
    } else if (arg.startsWith('--dir=')) {
      opts.dir = arg.slice('--dir='.length);
    }
  }
  return opts;
}

function openBrowser(url) {
  const platform = process.platform;
  const cmd =
    platform === 'darwin' ? ['open', [url]] :
    platform === 'win32' ? ['cmd', ['/c', 'start', '', url]] :
    ['xdg-open', [url]];
  spawn(cmd[0], cmd[1], { stdio: 'ignore', detached: true }).unref();
}

async function main(argv) {
  const opts = parseArgs(argv);
  const { port, token, url } = await start({ port: opts.port, dir: opts.dir });

  console.log(`tess-gui: dashboard running at http://127.0.0.1:${port}`);
  console.log("Opening dashboard — if it doesn't open, run: tess-gui --print-token");

  if (opts.printToken) {
    console.log(`tess-gui: full URL (contains your session token — do not share): ${url}`);
  }

  if (opts.open) {
    openBrowser(url);
  }
}

main(process.argv.slice(2)).catch((err) => {
  console.error('tess-gui: fatal:', err?.message ?? err);
  process.exit(1);
});
