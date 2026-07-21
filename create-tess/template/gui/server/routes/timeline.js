// tess-gui routes — GET /api/timeline
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss
import fs from 'node:fs/promises';
import path from 'node:path';

import { sendJson } from './util.js';

export function parseTimelineEntries(content) {
  const lines = content.split('\n');
  const entries = [];
  let currentDate = null;
  let currentText = null;

  const flush = () => {
    if (currentDate) entries.push({ date: currentDate, text: currentText ?? '' });
  };

  for (const line of lines) {
    const dateMatch = line.match(/^##\s+(\d{4}-\d{2}-\d{2})\s*$/);
    if (dateMatch) {
      flush();
      currentDate = dateMatch[1];
      currentText = null;
      continue;
    }
    if (!currentDate || currentText !== null) continue;

    const missionMatch = line.match(/^\*\*Mission:\*\*\s*(.+)$/);
    if (missionMatch) {
      currentText = missionMatch[1].trim();
      continue;
    }
    const trimmed = line.trim();
    if (trimmed && trimmed !== '---') {
      currentText = trimmed.replace(/^\*\*[^*]+\*\*:?\s*/, '');
    }
  }
  flush();

  return entries;
}

export async function handleTimeline(ctx, req, res) {
  const logPath = path.join(ctx.dir, 'kb', 'wiki', 'log.md');
  let content;
  try {
    content = await fs.readFile(logPath, 'utf8');
  } catch {
    sendJson(res, 200, { entries: [] });
    return;
  }
  sendJson(res, 200, { entries: parseTimelineEntries(content) });
}
