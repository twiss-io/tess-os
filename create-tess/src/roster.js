// roster.js — read the canonical install map from the template's
// .tess/core/roster-paths.json (the SYSTEM OF RECORD, design doc §1.3) and
// derive the per-path install set used by the squad reveal, C3 collision
// validation, and the arrival beat. The wizard never hardcodes the install set.
import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { displayAgent, displayOrch } from './content/squads.js';

export function loadRoster(templateDir) {
  const p = join(templateDir, '.tess', 'core', 'roster-paths.json');
  if (!existsSync(p)) {
    throw new Error(
      `template is missing .tess/core/roster-paths.json (looked in ${templateDir}) — not a Tess OS template?`,
    );
  }
  const data = JSON.parse(readFileSync(p, 'utf8'));
  if (!data.paths || !data.universal_base) {
    throw new Error('roster-paths.json is malformed (no paths / universal_base)');
  }
  return data;
}

// Returns the full install picture for a path.
export function installSetForPath(roster, path) {
  const def = roster.paths[path];
  if (!def) {
    throw new Error(
      `unknown path "${path}" — valid: ${Object.keys(roster.paths).join(' | ')}`,
    );
  }
  const base = roster.universal_base.slice();
  const squad = def.squad.slice();
  const orchestrators = (def.orchestrators || []).slice();
  // Agents (not orchestrators) that get a live dispatch file → C3 collision set.
  const agentKeys = [...squad, ...base];
  return {
    path,
    squad,
    base,
    orchestrators,
    agentKeys,
    installedNameSet: new Set(agentKeys.map((k) => k.toLowerCase())),
    // Display tuples for the reveal / arrival.
    squadDisplay: squad.map(displayAgent),
    baseDisplay: base.map(displayAgent),
    orchDisplay: orchestrators.map(displayOrch),
  };
}

// Convenience: just the display names (e.g. "Elena · Ada · …") for the arrival.
export function squadDisplayNames(set) {
  return [...set.squadDisplay, ...set.baseDisplay].map((a) => a.name);
}
