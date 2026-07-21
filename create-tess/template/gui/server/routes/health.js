// tess-gui routes — GET /api/health
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss
import fs from 'node:fs';
import path from 'node:path';

import { sendJson } from './util.js';
import { isCompatible } from '../claude-runner.js';

// This is the single authoritative Claude CLI probe for both the health
// endpoint and mission admission. `probeFailed` is deliberately internal:
// callers must not disclose local CLI/probe details to the browser.
export async function getClaudeHealth(ctx) {
  let claudeVersion = null;
  let probeFailed = false;
  try {
    claudeVersion = (await ctx.deps.getClaudeVersion()) ?? null;
  } catch {
    probeFailed = true;
    claudeVersion = null;
  }

  const minVersion = ctx.deps.MIN_CLI_VERSION;
  const compatible = claudeVersion ? isCompatible(claudeVersion) : false;
  const resolved = typeof claudeVersion === 'string' && claudeVersion.trim().length > 0;

  return { version: claudeVersion, compatible, minVersion, resolved, probeFailed };
}

export async function handleHealth(ctx, req, res) {
  let version = null;
  try {
    const raw = fs.readFileSync(path.join(ctx.packageRoot, 'package.json'), 'utf8');
    version = JSON.parse(raw).version ?? null;
  } catch {
    version = null;
  }

  const claude = await getClaudeHealth(ctx);

  sendJson(res, 200, {
    ok: true,
    version,
    claude: { version: claude.version, compatible: claude.compatible, minVersion: claude.minVersion },
    instanceDir: ctx.dir,
  });
}
