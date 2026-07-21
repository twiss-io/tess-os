// git-template-source.js — the explicit, opt-in "live git fetch" template
// source: what counts as a SAFE source string, how a source resolves to a
// pinned ref, and how that resolves to a `git clone` argv.
//
// Extracted out of scaffold.js (Reid LOW, PR #160 gap-loop fix — scaffold.js
// crossed this repo's 300-line file gate; this is the self-contained
// "git opt-in" cluster it called out for a clean split). Zero behavior
// change: every export here is byte-identical in implementation to what
// previously lived in scaffold.js, just relocated. scaffold.js re-exports
// the full public surface below for backward compatibility with existing
// importers (index.js, test/units.test.js) — no consumer needed to change
// its import path.
//
// This module has no dependency on ignore.js/policy-reset.js/the filesystem
// copy machinery — it is pure string/argv logic (isLocalSource is the one
// exception, a thin existsSync/statSync check used both here and by
// scaffold.js's own fetchTemplate() local-vs-git branch), independently
// unit-testable without a real clone or the network — see
// test/units.test.js's "clone pin" / arg-injection coverage.
import { existsSync, statSync } from 'node:fs';

// The canonical git URL — used ONLY when a caller explicitly opts into a
// live git fetch (passes this URL, or any other URL/path, as
// --template-source / TESS_TEMPLATE_SOURCE). No longer the wizard's actual
// default source (see scaffold.js's BUNDLED_TEMPLATE_DIR); kept as a named
// export because it is still the canonical value documentation/tests
// reference for "the real upstream repo", and because resolveTemplateRef()
// below still keys its pin decision off it.
export const DEFAULT_TEMPLATE_SOURCE = 'https://github.com/twiss-io/tess-os.git';

// Ref pin for an EXPLICIT git-URL opt-in against DEFAULT_TEMPLATE_SOURCE
// (P0 G-01, npm scaffold key-leak audit, 2026-07 — carried forward, opt-in
// scope only, from the mechanism described above). An unpinned `git clone`
// would land on whatever commit happens to be the default branch's HEAD tip
// at the exact moment the command runs — a moving target the operator has
// no control over. A pinned, tagged ref would make a given create-tess
// version's OPT-IN git fetch reproduce the exact same, already-CI-passed
// tess-os commit every time, IF the tag existed.
//
// STATUS (2026-07-21): this tag has never actually been cut — see
// scaffold.js's header. Left unchanged (not bumped) rather than pointed at
// yet another not-yet-cut tag name: bumping the string would misrepresent
// progress on a problem this PR does not claim to fix. This is now a
// documented, low-impact gap scoped to the explicit opt-in git path only —
// it no longer affects the default `npm create tess` flow, which the BUNDLE
// fix removes entirely from the git-clone dependency. Anyone hitting this
// on the opt-in path today already has the documented workaround:
// `--template-ref`/`TESS_TEMPLATE_REF` pins to any ref that DOES exist
// (e.g. `main`, or a real commit SHA). Cutting the tag remains Xavier's
// separate, credentialed release action (create-tess/README.md's "Release"
// section) — not a side effect of a code PR.
export const DEFAULT_TEMPLATE_REF = 'create-tess-v0.1.2';

export function isLocalSource(source) {
  try {
    return existsSync(source) && statSync(source).isDirectory();
  } catch {
    return false;
  }
}

// Resolve the git ref to pin a git-URL clone to. An explicit ref (CLI
// `--template-ref` / env `TESS_TEMPLATE_REF`) always wins, for ANY source —
// an operator or CI job pointing at a specific commit/tag/branch is always
// respected. Absent an explicit ref, the DEFAULT_TEMPLATE_REF pin applies
// ONLY when `source` is DEFAULT_TEMPLATE_SOURCE — a custom `--template-source`
// (an operator's own fork, a private mirror, a CI fixture pointing at a
// throwaway repo) has no reason to carry a `create-tess-v*` tag at all, so
// it is cloned at ITS OWN default branch tip. Irrelevant to the wizard's
// actual default flow, which never calls this with a git source at all
// (source defaults to BUNDLED_TEMPLATE_DIR, a local path — see index.js);
// this only matters for an explicit git-URL opt-in.
export function resolveTemplateRef(source, explicitRef) {
  if (explicitRef) return explicitRef;
  return source === DEFAULT_TEMPLATE_SOURCE ? DEFAULT_TEMPLATE_REF : null;
}

// Build the `git clone` argv for fetchTemplate's git-URL branch. Exported as
// a pure, dependency-free function (no execFileSync call inside) so the
// pinning behavior is unit-testable without invoking git or the network —
// see test/units.test.js "clone pin" coverage.
export function buildCloneArgs(source, stagingDir, ref) {
  return ref
    ? ['clone', '--depth', '1', '--branch', ref, '--', source, stagingDir]
    : ['clone', '--depth', '1', '--', source, stagingDir];
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
