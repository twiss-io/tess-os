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
import { existsSync, readFileSync, statSync } from 'node:fs';

// The canonical git URL — used ONLY when a caller explicitly opts into a
// live git fetch (passes this URL, or any other URL/path, as
// --template-source / TESS_TEMPLATE_SOURCE). No longer the wizard's actual
// default source (see scaffold.js's BUNDLED_TEMPLATE_DIR); kept as a named
// export because it is still the canonical value documentation/tests
// reference for "the real upstream repo", and because resolveTemplateRef()
// below still keys its pin decision off it.
export const DEFAULT_TEMPLATE_SOURCE = 'https://github.com/twiss-io/tess-os.git';

// Ref pin for an EXPLICIT git-URL opt-in against DEFAULT_TEMPLATE_SOURCE.
// An unpinned `git clone` would land on whatever the default branch's HEAD is
// at the moment the command runs. Pinning to the framework release tag makes
// a given create-tess version's opt-in git fetch reproduce the same released
// tess-os tree its bundled template was built from.
//
// The framework tag is `v<version>` and every release cuts it on the same
// commit as `create-tess-v<version>`, with both package.json versions equal
// (.github/scripts/release_version_gate.py enforces that). So the pin is
// DERIVED from this package's own version rather than hand-maintained: a
// literal here was left at 'v0.2.0' through the 1.0.0 release (v1.0 code
// review, HIGH), silently pinning an opt-in git fetch to an old framework.
// Earlier still it named `create-tess-v0.1.2`, a tag that was never cut.
// `--template-ref`/`TESS_TEMPLATE_REF` still overrides it (for example `main`
// or a commit SHA).
const PACKAGE_VERSION = JSON.parse(
  readFileSync(new URL('../package.json', import.meta.url), 'utf8'),
).version;
export const DEFAULT_TEMPLATE_REF = `v${PACKAGE_VERSION}`;

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
//   • an https:// URL — and then only a SIGNED Tess OS release tag, verified with
//     the release keys this package ships before anything is checked out or run
//     (release-verify.js; v1.0 audit, create-tess/git-template-source/
//     unauthenticated-template-executed-and-anchored)
//   • an existing LOCAL directory (relative or absolute), named on the command
//     line with --template-source (index.js refuses one that only comes from the
//     TESS_TEMPLATE_SOURCE environment variable)
// Everything else is refused: plaintext git:// (no transport integrity), ssh://
// and scp-form git@host:path (the release signature is the check that matters,
// and https is the one transport it is offered over), and the transport schemes
// git can be coerced through: `ext::sh -c …` (arbitrary-command → RCE-class) and
// `file://…` (local-file disclosure). Remote sources are passed to git after `--`.
const SAFE_URL_SCHEME_RE = /^https:\/\/[^\s]+$/;

export const TEMPLATE_SOURCE_HINT =
  'Use an https:// URL of a signed Tess OS release (with --template-ref v1.2.3), or an ' +
  'existing local folder given with --template-source.';

export function isSafeTemplateSource(source) {
  if (typeof source !== 'string' || source.length === 0) return false;
  // An existing local directory is always safe — it is copied, never cloned.
  if (isLocalSource(source)) return true;
  // Otherwise it must be an https:// URL (signature-checked before use).
  return SAFE_URL_SCHEME_RE.test(source);
}

export function assertSafeTemplateSource(source) {
  if (!isSafeTemplateSource(source)) {
    throw new Error(`refusing template-source "${source}": not an allowed source. ${TEMPLATE_SOURCE_HINT}`);
  }
}
