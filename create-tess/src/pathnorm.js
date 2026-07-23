// pathnorm.js — pure, dependency-free path-component normalization
// primitives, extracted out of ignore.js (PR #145 LOW item, Reid review):
// ignore.js was already 349 lines pre-fix, over this repo's 300-line file
// gate, and the HIGH-fix + MEDIUM-fix documentation added there pushed it
// further over. These three functions touch no filesystem state and have no
// dependency on ignore.js's EXCLUDE_* config, so they extract cleanly —
// giving them their own focused module and their own unit tests
// (test/pathnorm.test.js) independent of ignore.js's fs-touching
// isExcludedRel/makeCopyFilter. ignore.js re-exports `normalizeComponent`
// (its existing public surface — test/secrets-casefold-bypass.test.js and
// any external consumer of `create-tess/src/ignore.js` keep working
// unmodified) and imports `normalizePath`/`basenameMatchesGlob` internally.
//
// ---------------------------------------------------------------------------
// Case/Unicode-robust normalization (CRITICAL, secrets-exclusion case-fold
// bypass — 2026-07 security audit, live-reproduced on macOS). Every string
// comparison in ignore.js used to be a plain JS `===`/`.startsWith()`/
// `Set.has()` against the path exactly as written. macOS (APFS, default) and
// Windows (NTFS, default) — the two documented default deployment
// filesystems — are case-INSENSITIVE, so a secret dir under non-canonical
// case, e.g. `.Claude/Tess-Secrets/`, is the SAME INODE as
// `.claude/tess-secrets/` but a DIFFERENT STRING: every check silently
// returned false and the scaffolder COPIED the secret tree verbatim into
// produced instances — `vault.age`, `identity.age`, live
// `.claude/tess-secrets/*` tokens, the PRIVATE `.tess/keys/verifiers/**`/
// `signoffs/**` trust-anchor keys, and real `.tess/state/memory/**` operator
// data. Reproduced: `isExcludedRel` returned `false` for
// `.Claude/Tess-Secrets/token.env` despite it being the same inode as
// `.claude/tess-secrets/token.env`. This is the SAME bug CLASS as #117/#140
// (fixed on the Python `tessctl` side with inode-identity —
// `_paths_are_same_location`/`_path_is_prefix`, `.tess/bin/tessctl`) landing
// again in the JS scaffolder.
//
// Fix, mirroring tessctl's OWN two-layer pattern rather than reinventing it:
//
//   1. `normalizeComponent` (this module) — the string-level fallback,
//      always available even when the candidate path does not (yet) exist
//      on disk. NFC-normalizes (so an NFD-decomposed component compares
//      equal to its NFC-composed form — both encode "the same grapheme" as
//      different UTF-8 byte sequences), THEN casefolds via `toLowerCase()`,
//      THEN strips trailing dots/spaces — mirrors tessctl's write-gate
//      per-component normalization (`check_manifest_write_gate`'s
//      `.rstrip('. ').lower()`, `.tess/bin/tessctl`), extended with NFC
//      since this filter, unlike that Python gate, also has to cope with a
//      case-insensitive filesystem's Unicode-equivalence edge cases.
//      Applied (via `normalizePath`) to every path component ignore.js
//      compares against EXCLUDE_NAMES/EXCLUDE_DIR_PREFIXES/
//      EXCLUDE_CONTENT_PREFIXES/EXCLUDE_REL_PATHS/the basename globs/the
//      `.env` check.
//
//   2. Inode identity (ignore.js's `statOrNull`-backed comparison inside
//      `makeCopyFilter`) — the JS analogue of tessctl's
//      `_paths_are_same_location` (`os.path.samefile` / `(st_dev, st_ino)`
//      inode identity): when BOTH paths exist, ask the filesystem itself
//      whether they are the SAME inode — correct regardless of case-folding
//      AND NFC/NFD, because inode identity is a filesystem-resolution
//      property, not a string property this module would otherwise have to
//      reimplement. Lives in ignore.js, not here, since it needs fs access
//      and the EXCLUDE_DIR_PREFIXES config this module deliberately has no
//      dependency on.
//
// ★ This is a DENYLIST (default-allow): any case/normalization ambiguity —
// a stat failure, a partial match, anything the fallback can't resolve
// cleanly — must resolve to EXCLUDE, never to "copy it anyway". Every helper
// below is written fail-closed: the risky branch always returns `true`
// (excluded)/`false` (not-a-safe-match), never the reverse.
//
// Exported (like scaffold.js's buildCloneArgs/resolveTemplateRef) as a pure,
// dependency-free primitive so the NFC-then-casefold ordering is directly
// unit-testable: lower-casing an NFD-decomposed grapheme (e.g. "e" plus a
// COMBINING ACUTE ACCENT codepoint, U+0065 U+0301) WITHOUT normalizing
// first does NOT converge with the lower-cased form of its NFC-precomposed
// counterpart (U+00C9 lower-cases to U+00E9, a single codepoint) -- the two
// stay different byte sequences. Only NFC-normalizing FIRST makes them
// compare equal, so that step is load-bearing, not redundant with
// casefolding alone. See test/pathnorm.test.js (primitive-level) and
// test/secrets-casefold-bypass.test.js (ignore.js-surface regression lock)
// — the source comment deliberately avoids a literal accented character
// itself, so this file's own bytes can't silently drift between NFC/NFD
// depending on the editor that touched it last.
// ★ Issue #146 (Cyra, PR #145 re-review — pre-existing, narrow residual, NOT
// a regression of the HIGH fix below). `normalizeComponent`'s trailing
// `[. ]` strip only ever collapsed a component that is ENTIRELY dots/spaces.
// A "noise" component built instead from Unicode general-category Cf
// (format-control) codepoints — zero-width space U+200B, ZWNJ/ZWJ, soft
// hyphen U+00AD (Cf, verified — not a printable hyphen), the BOM/ZWNBSP
// U+FEFF, the LRM/RLM/Arabic-letter-mark bidi controls, word joiner, … — or
// from a LONE combining mark (general category Mn/Mc/Me) with no preceding
// base character to attach to, does NOT normalize to empty under the
// original rule: it is real, non-empty, non-dot/-space content, so it
// survives `normalizePath`'s `.filter(Boolean)` untouched. Interposed
// WITHIN a forbidden EXCLUDE_DIR_PREFIXES/EXCLUDE_CONTENT_PREFIXES root
// (e.g. `.tess/<U+200B>/keys/verifiers/cyra.asc`), it still defeats the
// string prefix-match exactly like the all-dots/all-space vector PR #145
// closed — the interposed segment breaks the contiguous comparison while
// remaining, under the old rule, a "real" segment.
//
// FIX — extend the SAME normalize-to-empty mechanism, not a new one:
//   1. Strip every Cf-category codepoint from the ENTIRE component (not
//      only a trailing run) — `\p{Cf}` is exhaustive over Unicode's format-
//      control block, so this needs no per-character allowlist to maintain.
//      A component composed ENTIRELY of such codepoints collapses to `''`
//      and is dropped by `normalizePath`'s existing `.filter(Boolean)` (PR
//      #145's HIGH fix) — the SAME fail-safe machinery, a wider input set.
//      Applied BEFORE the trailing dot/space strip (not after): a Cf
//      codepoint trailing a run of literal dots/spaces (e.g. `". ​"`)
//      would otherwise block that regex's end-anchor from reaching the real
//      dots/spaces underneath it — stripping the invisible layer first
//      restores the original rule's own reach.
//   2. Collapse a component that is, after step 1, ENTIRELY combining marks
//      (`\p{M}`, general categories Mn/Mc/Me) to `''` too — a "combining-
//      only" component, issue #146's third named vector: no base character
//      means nothing for the mark to combine with, so it is orphaned by
//      construction. NOT applied to a mark that has a base alongside it in
//      the same component (an ordinary accented letter) — by this point
//      `.normalize('NFC')` (the very first step) has already composed any
//      such base+mark sequence back into its single precomposed codepoint
//      wherever Unicode defines one (see this function's header test,
//      test/pathnorm.test.js's NFC/NFD regression lock), so a RAW combining
//      mark surviving to this check has already failed to compose with
//      anything — orphaned, not merely decomposed. This scoping is
//      deliberate and load-bearing: an earlier, broader draft of this fix
//      that instead force-excluded ANY component containing a non-
//      `[A-Za-z0-9._-]` character (Cyra's alternate "match-forcing token"
//      framing in #146, taken literally) was rejected during review — it
//      would have flipped test/secrets-casefold-bypass.test.js's own
//      negative control ("a legitimate, non-secret file that happens to
//      carry accented characters is kept ... the fix must not become an
//      overbroad hammer against ordinary unicode filenames", e.g.
//      `agents/café-notes/README.md`) from KEPT to wrongly EXCLUDED. Only
//      the two provably-noise categories above (invisible format-control
//      codepoints; marks with no base to attach to) are collapsed — real,
//      printable, identity-bearing Unicode text of any script is left
//      exactly as NFC + casefold already handled it, unaffected by this fix.
//      See test/pathnorm.test.js and test/secrets-noise-component-bypass.test.js
//      for the empirically-verified (buggy-before / correct-after)
//      regression lock on all three named vectors, plus the café negative
//      control proving this fix does not regress the existing one.
const FORMAT_CONTROL_RE = /\p{Cf}/gu;
const COMBINING_ONLY_RE = /^\p{M}+$/u;

export function normalizeComponent(c) {
  const stripped = c.normalize('NFC').toLowerCase().replace(FORMAT_CONTROL_RE, '').replace(/[. ]+$/, '');
  return COMBINING_ONLY_RE.test(stripped) ? '' : stripped;
}

// ★ HIGH (Reid, PR #145 review) — empty-normalized-component join corruption.
// `normalizeComponent` strips a component that is ENTIRELY dots/spaces (e.g.
// a literal `...` directory — legal `mkdir`, no special filesystem meaning;
// or a leading `.` from a `./`-prefixed relative path; or a whitespace-only
// component) down to `''`. Joining that empty string back in with `/` used
// to corrupt the path used for prefix matching — either a double `//`
// (`.tess` + '' + `keys/...` -> `.tess//keys/...`) or a leading `/`
// (`.` + `.tess/...` -> `/.tess/...`) — and NEITHER string `startsWith`
// its intended EXCLUDE_DIR_PREFIXES/EXCLUDE_CONTENT_PREFIXES entry anymore,
// so a secret nested under a noise component slipped through as `false`
// (kept) instead of `true` (excluded). Reproduced pre-fix:
//   isExcludedRel('.tess/.../keys/verifiers/cyra.asc')  -> false (BUG)
//   isExcludedRel('./.tess/keys/verifiers/cyra.asc')    -> false (BUG, Cyra)
//   isExcludedRel('.tess/.  /keys/verifiers/cyra.asc')  -> false (BUG)
// FIX — fail-safe DENYLIST semantics: DROP empty-after-normalization
// components entirely (a second `.filter(Boolean)` AFTER the map, not just
// the pre-map split filter) rather than joining them back in, so the noise
// component effectively vanishes from the matched path and the secret's
// canonical prefix still lines up: `.tess/.../keys/verifiers/cyra.asc`
// normalizes to the SAME matched string as `.tess/keys/verifiers/cyra.asc`.
// Over-EXCLUDING an ordinary path that happens to collapse onto a forbidden
// prefix this way is the acceptable failure direction for a denylist;
// under-excluding a secret is not. See test/pathnorm.test.js and
// test/secrets-casefold-bypass.test.js for the empirically-verified
// (buggy-before / correct-after) regression lock on all three vectors above.
export function normalizePath(relForward) {
  return relForward.split('/').filter(Boolean).map(normalizeComponent).filter(Boolean).join('/');
}

// Basename suffix glob match — the `*.<suffix>` shape (`endsWith`) or an
// exact non-glob basename. Used by ignore.js's EXCLUDE_BASENAME_GLOBS check.
export function basenameMatchesGlob(base, glob) {
  return glob.startsWith('*') ? base.endsWith(glob.slice(1)) : base === glob;
}
