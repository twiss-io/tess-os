#!/usr/bin/env node
// create-tess — the gamified first-run wizard for Tess OS.
// `npm create tess` / `npx create-tess` → keystone render → live agent OS.
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss
//
// Entry shim: keep this thin. All logic lives in src/ so the package stays
// testable and each module stays well under the 300-line quality gate.
import { main } from '../src/index.js';

process.on('unhandledRejection', (reason) => {
  console.error('create-tess: unhandled rejection:', reason);
  process.exit(1);
});

main(process.argv.slice(2)).catch((err) => {
  console.error('create-tess: fatal:', err?.message ?? err);
  process.exit(1);
});
