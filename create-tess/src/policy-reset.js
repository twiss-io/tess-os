// policy-reset.js — reset a scaffolded project's policy key registries to the
// clean, empty, fail-closed default (`verifier_keys: {}` / `signoff_keys: {}`),
// comment-preserving, every other line byte-for-byte untouched.
//
// WHY THIS EXISTS: the SOURCE repo used as --template-source (default:
// https://github.com/twiss-io/tess-os.git, the maintainer repo itself) may
// legitimately have real entries registered under `policy.verifier_keys` /
// `policy.signoff_keys` in its OWN `core/policy/policy.yaml` — those keys
// govern THAT repo's OWN development (e.g. `chore/register-verifier-cyra-
// phase1`, PR #91, registers Cyra so twiss-io/tess-os's gate can accept her
// verdicts on ITS OWN doctrine changes). A repo's registered verifier is its
// own trust anchor, scoped to its own history and its own reviewers.
//
// Without this reset, `promote()` copies `core/policy/policy.yaml` (and its
// `.tess/core` mirror) VERBATIM — a scaffolded USER project would silently
// inherit the maintainer's registered key as its OWN trust anchor. That is
// backwards: a covering verdict is only meaningful because SOMEONE the
// project's own operator chose to trust signed it. A freshly scaffolded
// project has made no such choice yet, so it must ship fail-closed — empty
// registries, no verdict can ever verify, `tessctl gate` blocks until the
// operator registers their OWN keys. See conductor/verdict-signing.md.
//
// This module ONLY resets `policy.verifier_keys` / `policy.signoff_keys`
// back to their empty inline form. It does not touch rules, hard_floor_rules,
// comments, or any other line — a scaffolded project's actual gate RULES
// (which paths are prod_touching/client_facing) are still whatever the
// template ships, exactly as before this change. Only the ALLOWED-KEY SET
// is reset, because that is the one thing that is never transferable between
// repositories.
import { readFileSync, writeFileSync, existsSync } from 'node:fs';

// The two policy.schema.json keys this module resets. Both are optional maps
// at the schema level (core/contracts/policy.schema.json) — an empty `{}` is
// always schema-valid, and is the shipped default in this repo's own
// core/policy/policy.yaml today (verified against the real file, not assumed).
export const RESET_KEYS = ['verifier_keys', 'signoff_keys'];

// Count of leading ASCII space characters (the YAML in this repo is
// space-indented only — this deliberately does NOT treat tabs as
// indentation, matching the file's own convention).
function leadingSpaces(line) {
  let n = 0;
  while (n < line.length && line[n] === ' ') n += 1;
  return n;
}

// Split `text` into lines that each RETAIN their trailing '\n' (mirrors
// Python's `str.splitlines(keepends=True)`), except a final line with no
// trailing newline, which is kept newline-less. Returns [] for empty input.
export function splitKeepEnds(text) {
  if (text === '') return [];
  const out = text.match(/[^\n]*\n|[^\n]+$/g);
  return out || [];
}

// Reset a single `${keyName}: <map>` block in `text` back to the clean, empty
// inline form `${keyName}: {}`, leaving every other line — every comment,
// every OTHER key, every rule — byte-for-byte untouched.
//
// Mirrors (deliberately, independently — not imported, so a bug in this
// module can never mask a real drift in the engine, and vice versa) the same
// block-detection shape the Python engine's own comment-preserving patcher
// (`_policy_yaml_upsert_verifier_key` in .tess/bin/tessctl, and the test
// helper `_policy_text_with_empty_verifier_keys` added alongside PR #91)
// already uses for the inverse operation (upserting AN entry INTO the empty
// form). This function does the reverse: collapsing however many entries are
// currently present back down to the clean empty baseline.
//
// Returns { text, changed }. Throws if `keyName:` never appears in `text` at
// all (a policy.yaml missing the key entirely is a different, louder problem
// than "already empty" — this function must never silently no-op on that).
export function resetKeyToEmptyInline(text, keyName) {
  const lines = splitKeepEnds(text);
  const emptyForm = `${keyName}: {}`;
  const blockHeader = `${keyName}:`;

  let idx = null;
  let indent = null;
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    const stripped = line.slice(leadingSpaces(line));
    if (stripped.startsWith('#')) continue; // skip commented-out example blocks
    const trimmed = line.trim();
    if (trimmed === emptyForm || trimmed === blockHeader) {
      idx = i;
      indent = leadingSpaces(line);
      break;
    }
  }
  if (idx === null) {
    throw new Error(`no \`${keyName}:\` key found in policy text`);
  }

  if (lines[idx].trim() === emptyForm) {
    return { text, changed: false }; // already clean — nothing to reset
  }

  // `${keyName}:` opens a block — consume every line more-indented than the
  // header until a line at or below the header's own indent is reached (the
  // next sibling key, or a comment introducing it). A run of blank lines is
  // only part of the block if a MORE-indented line follows it (an interior
  // separator between entries) — a trailing blank line immediately before
  // the next sibling key/comment belongs to THAT section, not this block,
  // and must be left untouched. `pendingBlank` tracks an as-yet-uncommitted
  // blank run so it can be rolled back out of the removed range.
  let end = idx + 1;
  let pendingBlank = 0;
  while (end < lines.length) {
    const line = lines[end];
    if (line.trim() === '') {
      pendingBlank += 1;
      end += 1;
      continue;
    }
    if (leadingSpaces(line) <= indent) {
      end -= pendingBlank; // roll back: this blank run belongs to what follows
      break;
    }
    pendingBlank = 0; // this blank run was interior to the block — consume it
    end += 1;
  }

  const newLines = [
    ...lines.slice(0, idx),
    `${' '.repeat(indent)}${emptyForm}\n`,
    ...lines.slice(end),
  ];
  return { text: newLines.join(''), changed: true };
}

// Reset BOTH `verifier_keys` and `signoff_keys` in `text`. Returns
// { text, changed } — `changed` is true if EITHER key was non-empty.
export function resetPolicyKeyRegistries(text) {
  let out = text;
  let changed = false;
  for (const key of RESET_KEYS) {
    const r = resetKeyToEmptyInline(out, key);
    out = r.text;
    changed = changed || r.changed;
  }
  return { text: out, changed };
}

// Reset the policy.yaml file at `filePath` in place (no-op, no write, if the
// file does not exist — a minimal/test template may not ship one). Returns
// { existed, changed }.
export function resetPolicyFile(filePath) {
  if (!existsSync(filePath)) return { existed: false, changed: false };
  const original = readFileSync(filePath, 'utf8');
  const { text, changed } = resetPolicyKeyRegistries(original);
  if (changed) writeFileSync(filePath, text, 'utf8');
  return { existed: true, changed };
}
