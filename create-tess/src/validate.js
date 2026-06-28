// validate.js — name + enum validation (design doc §1.4 C3/C4/C5, §5.3).
//
// C5 (hard): YAML/markdown-safe charset, 1–30 chars, no control/emoji/RTL.
// C3 (block on installed collision): conductor name == an installed agent name.
// C4 (warn): conductor name == operator name.
import { VIBES, PATHS, PATHWAYS } from './args.js';

// HIGH-2(b): the first character MUST be alphanumeric — a leading hyphen makes a
// name flag-shaped (e.g. "--operator=--help"), which is argument-injection bait
// for tessctl. Forbidding a leading hyphen (and leading space/apostrophe) closes
// it at the source; names are additionally passed to tessctl after `--`.
// 1–30 chars: 1 leading alnum + up to 29 of the allowed set.
const NAME_RE = /^[A-Za-z0-9][A-Za-z0-9 '\-]{0,29}$/;
// Control chars (C0/C1), zero-width, BOM, and RTL/LTR directional marks are
// stripped before validation so paste artifacts don't survive. Escapes only —
// no literal control bytes in source.
const STRIP_RE =
  /[\u0000-\u001F\u007F-\u009F\u200B-\u200F\u202A-\u202E\u2060-\u2064\uFEFF]/g;
// After stripping, reject emoji / pictographic / variation-selector ranges.
const EMOJI_RE =
  /[\u{1F000}-\u{1FFFF}]|[\u{2190}-\u{27BF}]|[\u{FE00}-\u{FE0F}]/u;

// Returns { ok, value, error } — value is the trimmed, control-stripped name.
export function validateName(raw, label = 'name') {
  if (raw === null || raw === undefined) {
    return { ok: false, error: `${label} is required` };
  }
  const stripped = String(raw).replace(STRIP_RE, '').trim();
  if (!stripped) return { ok: false, error: `${label} cannot be empty` };
  if (EMOJI_RE.test(stripped)) {
    return { ok: false, error: `${label} cannot contain emoji or symbols` };
  }
  if (!NAME_RE.test(stripped)) {
    return {
      ok: false,
      error: `${label} must start with a letter or digit, then letters, digits, spaces, hyphens and apostrophes only (1–30 chars)`,
    };
  }
  return { ok: true, value: stripped };
}

// C3/C4 — relationship checks for the conductor name. `installedAgents` is the
// lower-cased set of agent names that WILL be installed for the chosen path.
export function checkConductorName(name, operatorName, installedAgents) {
  const lower = name.toLowerCase();
  const warnings = [];
  if (installedAgents && installedAgents.has(lower)) {
    return {
      block: true,
      reason: `"${name}" is the name of an agent in your squad — a conductor and an agent sharing a name is confusing in dispatch. Choose another name.`,
    };
  }
  if (operatorName && lower === operatorName.toLowerCase()) {
    warnings.push(
      `Your conductor and you share the name "${name}" — addressing may be ambiguous.`,
    );
  }
  if (name.length === 1) {
    warnings.push(`Single-character names read oddly in "Commander ${name}" frames.`);
  }
  return { block: false, warnings };
}

export function validateEnum(value, allowed, label) {
  if (!allowed.includes(value)) {
    return {
      ok: false,
      error: `${label} must be one of: ${allowed.join(' | ')} (got "${value}")`,
    };
  }
  return { ok: true, value };
}

export const validateVibe = (v) => validateEnum(v, VIBES, 'vibe');
export const validatePath = (v) => validateEnum(v, PATHS, 'path');
export const validatePathway = (v) => validateEnum(v, PATHWAYS, 'pathway');
