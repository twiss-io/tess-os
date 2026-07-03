// tess-gui routes — GET /api/roster
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss
import fs from 'node:fs/promises';
import path from 'node:path';

import { sendJson } from './util.js';

function stripHeadingDecoration(heading) {
  return heading
    .replace(/^\d+\.\s*/, '')
    .replace(/\s*\(\d+(?:\s+agents?)?\)\s*$/i, '')
    .trim();
}

// Groups agents by the nearest heading (##/###/####) above the markdown
// table they appear in. Only tables whose header row mentions both "Agent"
// and "Role" are treated as roster tables — this naturally skips unrelated
// tables (e.g. "Roster at a Glance", "Resolved Overlaps") without special
// casing them.
export function parseGuildGroups(readmeContent) {
  const lines = readmeContent.split('\n');
  const guilds = [];
  const guildByName = new Map();
  let currentHeading = null;
  let inTable = false;
  let sawSeparator = false;

  for (const rawLine of lines) {
    const headingMatch = rawLine.match(/^#{2,4}\s+(.*)$/);
    if (headingMatch) {
      currentHeading = stripHeadingDecoration(headingMatch[1]);
      inTable = false;
      sawSeparator = false;
      continue;
    }

    const trimmed = rawLine.trim();
    if (!trimmed.startsWith('|')) {
      inTable = false;
      sawSeparator = false;
      continue;
    }

    if (!inTable) {
      if (/agent/i.test(trimmed) && /role/i.test(trimmed)) inTable = true;
      continue;
    }

    if (!sawSeparator) {
      if (/^\|[\s:-]+\|/.test(trimmed)) sawSeparator = true;
      continue;
    }

    const rowMatch = trimmed.match(/^\|\s*\[([^\]]+)\]\(([^)]+)\)\s*\|/);
    if (!rowMatch) continue;
    const slug = rowMatch[2].replace(/\/+$/, '').trim();
    if (!slug) continue;

    let group = guildByName.get(currentHeading);
    if (!group) {
      group = { name: currentHeading || 'Ungrouped', agents: [] };
      guildByName.set(currentHeading, group);
      guilds.push(group);
    }
    group.agents.push({ slug });
  }

  return guilds;
}

function splitNameRole(heading) {
  const parts = heading.split(/\s+[—–-]\s+/);
  return { name: parts[0]?.trim(), role: parts[1]?.trim() };
}

function parseAgentFrontmatter(content) {
  if (!content.startsWith('---')) return {};
  const lines = content.split('\n');
  if (lines[0].trim() !== '---') return {};
  let end = -1;
  for (let i = 1; i < lines.length; i++) {
    if (lines[i].trim() === '---') {
      end = i;
      break;
    }
  }
  if (end === -1) return {};
  const fields = {};
  for (const line of lines.slice(1, end)) {
    const match = line.match(/^([A-Za-z0-9_-]+):\s*(.*)$/);
    if (match) fields[match[1]] = match[2].trim().replace(/^["']|["']$/g, '');
  }
  return fields;
}

export async function resolveAgentIdentity(agentsDir, slug) {
  let content;
  try {
    content = await fs.readFile(path.join(agentsDir, slug, 'README.md'), 'utf8');
  } catch {
    return { name: slug, role: slug };
  }

  const fm = parseAgentFrontmatter(content);
  let name = fm.name;
  let role = fm.role;

  if (!name || !role) {
    const h1Match = content.match(/^#\s+(.+)$/m);
    if (h1Match) {
      const parsed = splitNameRole(h1Match[1].trim());
      name = name || parsed.name;
      role = role || parsed.role;
    }
  }

  return { name: name || slug, role: role || slug };
}

export async function handleRoster(ctx, req, res) {
  const agentsDir = path.join(ctx.dir, 'agents');

  let readmeContent;
  try {
    readmeContent = await fs.readFile(path.join(agentsDir, 'README.md'), 'utf8');
  } catch {
    sendJson(res, 200, { guilds: [] });
    return;
  }

  const groups = parseGuildGroups(readmeContent);
  const guilds = [];
  for (const group of groups) {
    const agents = [];
    for (const { slug } of group.agents) {
      try {
        agents.push(await resolveAgentIdentity(agentsDir, slug));
      } catch {
        agents.push({ name: slug, role: slug });
      }
    }
    guilds.push({ name: group.name, agents });
  }

  sendJson(res, 200, { guilds });
}
