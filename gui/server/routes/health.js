// tess-gui routes — GET /api/health
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss
import fs from 'node:fs';
import path from 'node:path';

import { sendJson } from './util.js';

function parseVersionTuple(value) {
  const match = typeof value === 'string' && value.match(/(\d+)\.(\d+)\.(\d+)/);
  if (!match) return null;
  return [Number(match[1]), Number(match[2]), Number(match[3])];
}

export function versionGte(a, b) {
  const va = parseVersionTuple(a);
  const vb = parseVersionTuple(b);
  if (!va || !vb) return false;
  for (let i = 0; i < 3; i++) {
    if (va[i] !== vb[i]) return va[i] > vb[i];
  }
  return true;
}

export async function handleHealth(ctx, req, res) {
  let version = null;
  try {
    const raw = fs.readFileSync(path.join(ctx.packageRoot, 'package.json'), 'utf8');
    version = JSON.parse(raw).version ?? null;
  } catch {
    version = null;
  }

  let claudeVersion = null;
  try {
    claudeVersion = (await ctx.deps.getClaudeVersion()) ?? null;
  } catch {
    claudeVersion = null;
  }

  const minVersion = ctx.deps.MIN_CLI_VERSION;
  const compatible = claudeVersion ? versionGte(claudeVersion, minVersion) : false;

  sendJson(res, 200, {
    ok: true,
    version,
    claude: { version: claudeVersion, compatible, minVersion },
    instanceDir: ctx.dir,
  });
}
