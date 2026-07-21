// tess-gui routes — GET /api/commands
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss
import fs from 'node:fs/promises';
import path from 'node:path';

import { sendJson } from './util.js';

// Parses a leading YAML-ish frontmatter block (--- ... ---). Returns
// failed:true only when a block was opened but never closed — a file with
// no frontmatter at all is not a failure, just absent.
export function parseFrontmatter(content) {
  if (!content.startsWith('---')) return { fields: {}, failed: false };
  const lines = content.split('\n');
  if (lines[0].trim() !== '---') return { fields: {}, failed: false };
  let end = -1;
  for (let i = 1; i < lines.length; i++) {
    if (lines[i].trim() === '---') {
      end = i;
      break;
    }
  }
  if (end === -1) return { fields: {}, failed: true };

  const fields = {};
  for (const line of lines.slice(1, end)) {
    const match = line.match(/^([A-Za-z0-9_-]+):\s*(.*)$/);
    if (!match) continue;
    let value = match[2].trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    fields[match[1]] = value;
  }
  return { fields, failed: false };
}

export async function handleCommands(ctx, req, res) {
  const commandsDir = path.join(ctx.dir, '.claude', 'commands');

  let entries;
  try {
    entries = await fs.readdir(commandsDir, { withFileTypes: true });
  } catch {
    sendJson(res, 200, { commands: [], skippedCount: 0 });
    return;
  }

  const commands = [];
  let skippedCount = 0;

  for (const entry of entries) {
    if (!entry.isFile() || !entry.name.endsWith('.md')) continue;
    const name = entry.name.slice(0, -'.md'.length);

    let content;
    try {
      content = await fs.readFile(path.join(commandsDir, entry.name), 'utf8');
    } catch {
      skippedCount += 1;
      continue;
    }

    const { fields, failed } = parseFrontmatter(content);
    if (failed) skippedCount += 1;
    commands.push({ name, description: fields.description ?? '' });
  }

  commands.sort((a, b) => a.name.localeCompare(b.name));
  sendJson(res, 200, { commands, skippedCount });
}
