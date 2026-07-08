// tess-gui routes — GET /api/health
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss
import fs from 'node:fs';
import path from 'node:path';

import { sendJson } from './util.js';
import { isCompatible } from '../claude-runner.js';

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
  const compatible = claudeVersion ? isCompatible(claudeVersion) : false;

  sendJson(res, 200, {
    ok: true,
    version,
    claude: { version: claudeVersion, compatible, minVersion },
    instanceDir: ctx.dir,
  });
}
