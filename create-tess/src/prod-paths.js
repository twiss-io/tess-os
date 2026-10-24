// prod-paths.js — let the adopter name their production code at install time.
//
// The shipped policy's `example-prod-service-placeholder` rule points at
// `__REPLACE_ME__/prod/**`, which matches nothing, so `tessctl doctor` warns
// that the ship gate reviews none of the app's code. The wizard asks for the
// real folders (Enter skips; --prod-paths sets them without a prompt) and
// writes them into that one rule, in both policy copies.
//
// The first push of a fresh install passes the gate only when Tess's files
// are the signed release, with the wizard's changes. tessctl accepts exactly
// this edit (`_policy_with_prod_paths_ok`): the placeholder line replaced by
// 1 to 20 distinct globs, one `        - "<glob>"` line each, nothing else
// changed. Keep the two sides in step.
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';

export const PROD_PLACEHOLDER_LINE = '        - "__REPLACE_ME__/prod/**"\n';
export const PROD_PATHS_MAX = 20;
const GLOB_RE = /^[A-Za-z0-9_.*][A-Za-z0-9_.*/-]{0,199}$/;
const EVERYTHING = new Set(['*', '**', '**/*', '**/**']);

const POLICY_REL_PATHS = ['core/policy/policy.yaml', join('.tess', 'core', 'policy', 'policy.yaml')];

// "src, api/**, apps/web" -> { ok, value: ['src/**', 'api/**', 'apps/web/**'] }.
// An entry without a `*` is a folder and covers everything under it. Empty
// input (or "skip") -> { ok, value: [] }: leave the placeholder as shipped.
export function parseProdPaths(raw) {
  const text = raw === null || raw === undefined ? '' : String(raw).trim();
  if (text === '' || text.toLowerCase() === 'skip') return { ok: true, value: [] };
  const out = [];
  for (const part of text.split(',')) {
    let g = part.trim().replace(/^\.\//, '');
    if (!g) continue;
    if (!g.includes('*')) g = `${g.replace(/\/+$/, '')}/**`;
    const why = globProblem(g);
    if (why) return { ok: false, error: `"${part.trim()}": ${why}` };
    if (!out.includes(g)) out.push(g);
  }
  if (out.length === 0) return { ok: true, value: [] };
  if (out.length > PROD_PATHS_MAX) {
    return { ok: false, error: `at most ${PROD_PATHS_MAX} folders or patterns` };
  }
  return { ok: true, value: out };
}

function globProblem(g) {
  if (g.startsWith('/')) return 'use a folder inside the project, not an absolute path';
  if (g.includes('..')) return 'use a folder inside the project (no "..")';
  if (EVERYTHING.has(g)) return 'that covers every file, so every change would need a review; name your app folders';
  if (g.includes('//')) return 'remove the double slash';
  if (g.includes('__REPLACE_ME__')) return 'name your own folder';
  if (!GLOB_RE.test(g)) return 'use letters, digits, ".", "_", "-", "/" and "*" only (no spaces or quotes)';
  return null;
}

// Policy text with the placeholder line replaced by one line per glob.
// Throws when the placeholder is not there exactly once (a template the
// wizard does not know), so nothing is half-written.
export function applyProdPaths(text, globs) {
  if (!globs.length) return { text, changed: false };
  const parts = text.split(PROD_PLACEHOLDER_LINE);
  if (parts.length !== 2) {
    throw new Error('the production placeholder line was not found exactly once in policy.yaml');
  }
  const lines = globs.map((g) => `        - "${g}"\n`).join('');
  return { text: parts[0] + lines + parts[1], changed: true };
}

// Write the globs into both policy copies of a scaffolded project. Returns
// { changed }. The caller re-pins the policy lock entry when changed.
export function setScaffoldedProdPaths(targetDir, globs) {
  if (!globs || !globs.length) return { changed: false };
  const updates = [];
  for (const rel of POLICY_REL_PATHS) {
    const file = join(targetDir, rel);
    if (!existsSync(file)) continue;
    updates.push([file, applyProdPaths(readFileSync(file, 'utf8'), globs).text]);
  }
  for (const [file, text] of updates) writeFileSync(file, text, 'utf8');
  return { changed: updates.length > 0 };
}
