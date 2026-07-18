// scaffold.js — fetch the Tess OS template and lay it into the target.
// Default source is the public repo; --template-source / TESS_TEMPLATE_SOURCE
// overrides with a git URL OR a local path (e.g. /tmp/tess-os-build for tests).
// create-tess/ and .git are always excluded from what gets scaffolded.
import { existsSync, statSync, cpSync, readdirSync, chmodSync, mkdirSync, rmSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { execFileSync } from 'node:child_process';
import { isExcludedRel, makeCopyFilter } from './ignore.js';
import { resetPolicyFile } from './policy-reset.js';

export const DEFAULT_TEMPLATE_SOURCE = 'https://github.com/twiss-io/tess-os.git';

// The two on-disk copies of the ship-gate policy every scaffold produces:
// the LIVE path an operator actually edits, and its `.tess/core` mirror (the
// pristine copy base_sha-pinned in tess.lock, and what `tessctl restore`
// would reconstruct the live file FROM). Both must be reset identically —
// resetting only the live copy would leave the maintainer's key sitting in
// the core mirror, ready to leak back in on the next `tessctl restore`/
// `tessctl reset`.
const POLICY_REL_PATHS = ['core/policy/policy.yaml', join('.tess', 'core', 'policy', 'policy.yaml')];

// Top-level entries never copied into a scaffolded instance. Derived from the
// single shared ignore source (create-tess/src/ignore.js) — NOT a parallel list.
// This is only the fast top-level skip; per-file exclusion (globs, multi-component
// secret paths, snapshot/staging content) is enforced by makeCopyFilter during
// the recursive cpSync so a local --template-source can never drag in the
// author's vault.age / vault.recipients / snapshots / .env* / keys (Quinn MEDIUM).
function isExcludedTopEntry(entry) {
  return isExcludedRel(entry);
}

export function ensurePython3() {
  try {
    execFileSync('python3', ['--version'], { stdio: 'ignore' });
  } catch {
    throw new Error(
      'python3 is required (the Tess OS keystone, tessctl, is Python). Install Python 3 and retry.',
    );
  }
}

export function isLocalSource(source) {
  try {
    return existsSync(source) && statSync(source).isDirectory();
  } catch {
    return false;
  }
}

// Clobber-protection (design doc §5.1). Returns a reason string if the target
// must be refused, or null if it's safe to proceed.
export function clobberReason(targetDir, force) {
  if (force) return null;
  if (existsSync(join(targetDir, 'operator', 'profile.json')) ||
      existsSync(join(targetDir, 'tess.lock'))) {
    return (
      'This directory is already a Tess OS install. To change your setup, run ' +
      '`tessctl reconfigure` (or edit operator/profile.json and re-render). ' +
      'To start fresh elsewhere, pass a new directory or --force.'
    );
  }
  if (existsSync(targetDir)) {
    const entries = readdirSync(targetDir).filter((e) => e !== '.DS_Store');
    if (entries.length > 0) {
      return `Target directory ${targetDir} is not empty. Pass --force to scaffold into it anyway.`;
    }
  }
  return null;
}

// Reid LOW (transport-scheme hardening) — accept SAFE template-source forms ONLY.
// This supersedes the earlier HIGH-2(a) leading-'-' flag check and subsumes it: a
// flag-shaped source (leading '-') matches none of the safe forms, so it is still
// refused unless it names a real local directory (handled by the local branch and
// never handed to git). Allowed forms:
//   • https:// , git:// , ssh://  remote URLs
//   • scp-form  user@host:path    (e.g. git@github.com:twiss-io/tess-os.git)
//   • an existing LOCAL directory (relative or absolute)
// Everything else is refused — in particular the transport schemes git can be
// coerced through: `ext::sh -c …` (arbitrary-command → RCE-class) and `file://…`
// (local-file disclosure). Remote sources are still passed to git after `--`.
const SAFE_URL_SCHEME_RE = /^(?:https|git|ssh):\/\//;
const SCP_FORM_RE = /^[A-Za-z0-9._-]+@[A-Za-z0-9._-]+:/;

export function isSafeTemplateSource(source) {
  if (typeof source !== 'string' || source.length === 0) return false;
  // An existing local directory is always safe — it is copied, never cloned.
  if (isLocalSource(source)) return true;
  // Otherwise it must be an explicitly allowed remote transport form.
  return SAFE_URL_SCHEME_RE.test(source) || SCP_FORM_RE.test(source);
}

export function assertSafeTemplateSource(source) {
  if (!isSafeTemplateSource(source)) {
    throw new Error(
      `refusing template-source "${source}": not an allowed source. Use an ` +
        `https://, git://, or ssh:// URL, an scp-form git@host:path, or an ` +
        `existing local directory.`,
    );
  }
}

// Stage the template into `stagingDir` (a temp dir) so the journey can read the
// roster and validate names before the target is touched (atomicity, §6.5).
export function fetchTemplate(source, stagingDir) {
  // Defence in depth — refuse a flag-shaped source before it can reach git.
  assertSafeTemplateSource(source);
  mkdirSync(stagingDir, { recursive: true });
  if (isLocalSource(source)) {
    const abs = resolve(source);
    const filter = makeCopyFilter(abs);
    for (const entry of readdirSync(abs)) {
      if (isExcludedTopEntry(entry)) continue;
      cpSync(join(abs, entry), join(stagingDir, entry), {
        recursive: true,
        filter,
        dereference: false,
      });
    }
    return { mode: 'local', source: abs };
  }
  // Git URL → shallow clone, then strip .git + create-tess. The `--`
  // end-of-options guard means a flag-shaped <source> can never be read as a
  // git option (HIGH-2a; belt-and-suspenders with assertSafeTemplateSource).
  execFileSync('git', ['clone', '--depth', '1', '--', source, stagingDir], {
    stdio: 'inherit',
  });
  // Strip excluded dirs a clone brings in (so they never reach the target).
  for (const ex of ['.git', 'create-tess']) {
    const p = join(stagingDir, ex);
    if (existsSync(p)) rmSync(p, { recursive: true, force: true });
  }
  return { mode: 'git', source };
}

// Promote the staged template into the (confirmed) target directory.
//
// Returns { policyReset } — see resetScaffoldedPolicyKeys below. The caller
// (index.js) uses `policyReset.changed` to decide whether the scaffolded
// tess.lock also needs a scoped re-pin (a normalization that intentionally
// alters `.tess/core/policy/policy.yaml`'s bytes invalidates the base_sha
// tess.lock already pinned for that entry — `tessctl doctor` would otherwise
// report CORE TAMPER on a project that was never tampered with, only scaffolded).
export function promote(stagingDir, targetDir) {
  mkdirSync(targetDir, { recursive: true });
  const filter = makeCopyFilter(stagingDir);
  for (const entry of readdirSync(stagingDir)) {
    if (isExcludedTopEntry(entry)) continue;
    cpSync(join(stagingDir, entry), join(targetDir, entry), {
      recursive: true,
      filter,
      dereference: false,
    });
  }
  // Ensure the keystone wrappers are executable post-copy.
  for (const w of ['tessctl', join('.tess', 'bin', 'tessctl')]) {
    const p = join(targetDir, w);
    if (existsSync(p)) {
      try { chmodSync(p, 0o755); } catch { /* best effort */ }
    }
  }
  const policyReset = resetScaffoldedPolicyKeys(targetDir);
  return { policyReset };
}

// Fail-closed scaffold reset: a scaffolded project must never inherit the
// SOURCE repo's registered verifier_keys/signoff_keys (its OWN trust anchor —
// see the header comment in policy-reset.js). Applies the same
// comment-preserving reset to BOTH the live policy and its `.tess/core`
// mirror, independently (each is skipped, not required, if it doesn't exist —
// a minimal/test template may ship neither). NOT done via ignore.js exclusion
// — the scaffold still needs every other rule/comment in the file; only the
// two ALLOWED-KEY-SET maps are reset.
//
// Returns { changed, files } — `files` lists which of POLICY_REL_PATHS were
// actually rewritten (empty if the source already shipped the clean, empty
// default — the common case today, before any real verifier is registered).
export function resetScaffoldedPolicyKeys(targetDir) {
  const files = [];
  for (const rel of POLICY_REL_PATHS) {
    const { changed } = resetPolicyFile(join(targetDir, rel));
    if (changed) files.push(rel);
  }
  return { changed: files.length > 0, files };
}

// M2 — framework-managed paths that a `--force` re-scaffold over an EXISTING
// install must clean-replace rather than merge into. Without this, cpSync layers
// the new template over the old one and stale managed files (a renamed agent, a
// removed doctrine file) survive. Operator space (operator/**) and any other user
// data are deliberately NOT listed — they are preserved across a forced re-run.
export const MANAGED_PATHS = [
  join('.claude', 'agents'),
  join('.claude', 'commands'),
  'conductor',
  join('.tess', 'core'),
  'CLAUDE.md',
];

// Clear the managed dirs/files in `targetDir` so the subsequent promote() lays
// down a clean copy. Best-effort + idempotent (missing paths are skipped).
export function clearManagedDirs(targetDir) {
  for (const rel of MANAGED_PATHS) {
    const p = join(targetDir, rel);
    if (existsSync(p)) {
      try { rmSync(p, { recursive: true, force: true }); } catch { /* best effort */ }
    }
  }
}
