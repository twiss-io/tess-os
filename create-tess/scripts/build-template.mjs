#!/usr/bin/env node
// scripts/build-template.mjs — regenerate create-tess/template/, the bundled
// scaffold snapshot shipped INSIDE the published npm package (P0 G-01 BUNDLE
// fix, 2026-07-21).
//
// WHY: `npm create tess`'s DEFAULT flow used to depend on a runtime
// `git clone --depth 1 --branch <DEFAULT_TEMPLATE_REF> https://github.com/
// twiss-io/tess-os.git` — pinned to a `create-tess-v*` tag that has NEVER
// been cut, across three release cycles (0.1.1, 0.1.2, 0.1.3). Every
// zero-flag `npm create tess` run failed with "Remote branch ... not found".
// Xavier's fix: ship the template FILES inside the npm package itself and
// scaffold the default flow from that bundled LOCAL copy — no clone, no
// tag, no network dependency, for the path every user actually hits.
// `--template-source <git-url>` remains available as an explicit, opt-in
// escape hatch for anyone who deliberately wants a live git fetch instead
// (see scaffold.js DEFAULT_TEMPLATE_SOURCE / BUNDLED_TEMPLATE_DIR).
//
// This script is the maintainer step that PRODUCES the bundle. It is never
// run by a consumer's `npm install create-tess` — it runs at MAINTAINER
// TIME: manually via `npm run build-template`, and automatically via the
// `prepack` lifecycle hook right before `npm pack` / `npm publish` (see
// package.json), so a forgotten manual run can never ship a stale bundle.
// The regenerated `create-tess/template/` tree is also committed to the repo
// like any other source file — reviewable in a PR diff, and present so
// `npm test`'s offline end-to-end scaffold test can run without ever
// invoking this script.
//
// Source of truth: `git ls-files` at the repo root — i.e. EXACTLY the tree a
// `git clone` of this repo would produce (the root .gitignore's exclusions
// are already baked into what's tracked), never a raw filesystem walk (which
// would also sweep up untracked local cruft: node_modules/, .env, build
// output, an operator's own uncommitted scratch files). On top of that, the
// SAME shared security filter every real scaffold copy uses
// (src/ignore.js's isExcludedRel — the case/NFC-hardened secrets +
// framework-internal-CI exclusion single source of truth) is re-applied
// here, so tracked-but-scaffold-forbidden paths (this repo's OWN registered
// verifier/sign-off keys, its OWN release/publish CI workflows — see
// ignore.js's header comment) never enter the bundle in the first place,
// rather than relying solely on the scaffold-time filter to strip them back
// out of every install downstream. Defense in depth: fetchTemplate()/
// promote() still re-apply the same filter at scaffold time regardless.
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, rmSync, cpSync, readdirSync, statSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
const PKG_DIR = resolve(SCRIPT_DIR, '..'); // create-tess/
const REPO_ROOT = resolve(PKG_DIR, '..'); // tess-os/
const TEMPLATE_DIR = join(PKG_DIR, 'template');

function die(msg) {
  console.error(`build-template: ${msg}`);
  process.exit(1);
}

// Sanity check: refuse to build from the wrong tree (e.g. this script copied
// somewhere else, or create-tess/ vendored standalone without its parent repo).
if (!existsSync(join(REPO_ROOT, 'tess.manifest.json'))) {
  die(
    `expected the Tess OS repo root at ${REPO_ROOT} (resolved as ` +
      `create-tess/scripts/../..) but tess.manifest.json is missing there — ` +
      `refusing to build a bundle from the wrong tree.`,
  );
}

const { isExcludedRel } = await import(join(PKG_DIR, 'src', 'ignore.js'));

let lsFilesOut;
try {
  lsFilesOut = execFileSync('git', ['-C', REPO_ROOT, 'ls-files', '-z'], {
    maxBuffer: 1024 * 1024 * 64,
  });
} catch (err) {
  die(`\`git ls-files\` failed — is ${REPO_ROOT} a git working tree? ${err.message}`);
}

const tracked = lsFilesOut.toString('utf8').split('\0').filter(Boolean);
if (tracked.length === 0) die('`git ls-files` returned zero tracked files — refusing to build an empty bundle.');

const keepFiles = new Set();
const keepDirs = new Set(['']); // '' = the copy root itself, always kept.

for (const rel of tracked) {
  // Never bundle the create-tess package into its own template — a scaffold
  // must never contain a nested create-tess/ (mirrors isExcludedTopEntry's
  // 'create-tess' EXCLUDE_NAMES entry, applied here at BUILD time instead of
  // scaffold time so the npm tarball never even carries the extra bytes).
  if (rel === 'create-tess' || rel.startsWith('create-tess/')) continue;
  // The single shared secrets + framework-internal-CI exclusion filter.
  if (isExcludedRel(rel)) continue;

  keepFiles.add(rel);
  const parts = rel.split('/');
  for (let i = 1; i < parts.length; i++) keepDirs.add(parts.slice(0, i).join('/'));
}

if (keepFiles.size === 0) {
  die('every tracked file was excluded — refusing to build an empty bundle (check ignore.js / create-tess/ scoping).');
}

rmSync(TEMPLATE_DIR, { recursive: true, force: true });
mkdirSync(TEMPLATE_DIR, { recursive: true });

const filter = (src) => {
  const rel = relative(REPO_ROOT, src).split(sep).join('/');
  if (rel === '') return true;
  return keepFiles.has(rel) || keepDirs.has(rel);
};

// Copy top-level entries individually (never the repo root as a whole) —
// TEMPLATE_DIR lives INSIDE the repo root (create-tess/template/), so a
// single whole-tree cpSync(REPO_ROOT, TEMPLATE_DIR, ...) is refused outright
// by Node (EINVAL: "cannot copy X to a subdirectory of self") before the
// filter is ever consulted. Skipping 'create-tess' at this top level (same
// as fetchTemplate()'s local-source branch in src/scaffold.js) sidesteps the
// self-containment entirely, exactly like that existing code path does.
for (const entry of readdirSync(REPO_ROOT)) {
  if (entry === 'create-tess' || entry === '.git') continue;
  if (!keepDirs.has(entry) && !keepFiles.has(entry)) continue; // not tracked / excluded
  cpSync(join(REPO_ROOT, entry), join(TEMPLATE_DIR, entry), {
    recursive: true,
    filter,
    dereference: false,
  });
}

// ── Content overrides (P0 G-01 MEDIUM-1, PR #160 revision-2, Cyra) ────────
// A small, EXPLICIT set of repo-root paths whose SOURCE content is this
// repo's own live, fully-populated doctrine — not a "structure-only" leak
// like kb/wiki/{index,log}.md (EXCLUDE_CONTENT_PREFIXES, dir + .gitkeep
// only) and not something writeProfile() silently regenerates fresh at
// scaffold time like operator/profile.json (EXCLUDE_REL_PATHS) — but whose
// BUNDLED counterpart must still exist and read as a real, usable file: a
// generic, fill-in-the-blank template, never the maintainer's own real
// calibration. Cyra (PR #160 security re-review): `operator/user-profile.md`
// + `conductor/user-profile.md` carry a full, unmodified, real
// behavioral/psychographic calibration profile — confirmed byte-identical
// to the live production Tess instance's own conductor/user-profile.md —
// shipped as the default persona to every `npm create tess` scaffold, with
// none of the genericization pass (name/identity → "the operator",
// specifics → placeholders) already applied to conductor/founders-office.md
// and conductor/channel-guardrails.md.
//
// Applied as a final, unconditional OVERWRITE after the normal tracked-file
// copy above — deliberately NOT an isExcludedRel() exclusion. An exclusion
// would just DROP the file from the bundle entirely (the kb/wiki/{index,
// log}.md treatment); these two files are meant to exist and be readable in
// every scaffold, just never with THIS repo's own populated content.
//
// Deliberately scoped to the BUNDLE ONLY: this does not touch the repo
// ROOT's own operator/user-profile.md / conductor/user-profile.md (this
// repo's own live, dogfooded calibration, used for THIS repo's own Tess
// instance) — whether the repo ROOT copies themselves should also be
// genericized is a separate, non-blocking call flagged for Xavier on
// PR #160's review thread, out of scope here.
//
// `conductor/user-profile.md` is CORE-MANAGED (tess.lock: tier `normal`,
// core_key `.tess/core/conductor/user-profile.md`, live_path
// `conductor/user-profile.md`) — tessctl doctor/verify run TWO independent
// checks against it: Check A (`.tess/core/<key>` bytes == tess.lock's pinned
// `base_sha`) and Check B (the live copy == freshly-rendered core). Writing
// the generic override to ONLY the live path — the first cut of this fix —
// left the `.tess/core` mirror holding the OLD (real-calibration) bytes,
// which passed Check A (still matched the OLD pin) but failed Check B on
// EVERY single `npm create tess` run (live now permanently disagrees with
// core) — the wizard's own embedded `tessctl doctor`/`verify` reported
// ISSUES and the process exited non-zero for every user. `operator/
// user-profile.md` has NO tess.lock entry at all (operator/** is pure
// never_touch instance data, not core-managed) — no equivalent concern
// there.
// Fix: overwrite BOTH the live path and its `.tess/core` mirror with the
// IDENTICAL generic bytes (Check B passes: live == core), then re-pin ONLY
// that one tess.lock entry's `base_sha` — the same surgical, single-entry
// re-pin `keystone.js`'s `regenPolicyLock` performs for the analogous
// policy.yaml case (`tessctl lock --regen --yes --only <core_key>`), but
// done here as a plain, DETERMINISTIC string/hash patch rather than by
// shelling out to that command. Reason: `tessctl lock --regen` (even
// `--only`-scoped) also bumps the lock file's top-level
// `framework.last_updated` WALL-CLOCK timestamp — harmless for its designed
// use (a maintainer re-baselining a real scaffold at run time, a one-shot
// action with no "previous build" to diff against) but fatal for a
// COMMITTED, reproducible build artifact: `template-drift-guard.test.js`
// rebuilds this exact bundle fresh and asserts it is byte-identical to the
// committed tree, and a real `prepack` before `npm publish` does the same
// implicitly — either would spuriously "drift" on this one timestamp field
// alone, forever, even with zero actual content change. Patching only the
// `base_sha:` line for this ONE entry, leaving every other byte of
// tess.lock (including that timestamp) untouched, keeps the bundle build
// fully deterministic — same inputs always produce the same bundle.
const OVERRIDES_DIR = join(SCRIPT_DIR, 'template-overrides');
const CONTENT_OVERRIDES = {
  'operator/user-profile.md': join(OVERRIDES_DIR, 'operator-user-profile.md'),
  'conductor/user-profile.md': join(OVERRIDES_DIR, 'conductor-user-profile.md'),
  // Core mirror of conductor/user-profile.md — MUST stay byte-identical to
  // the live path above (see comment block).
  '.tess/core/conductor/user-profile.md': join(OVERRIDES_DIR, 'conductor-user-profile.md'),
};

for (const [rel, overrideSrc] of Object.entries(CONTENT_OVERRIDES)) {
  if (!existsSync(overrideSrc)) die(`content-override source missing: ${overrideSrc}`);
  const dest = join(TEMPLATE_DIR, ...rel.split('/'));
  mkdirSync(dirname(dest), { recursive: true });
  cpSync(overrideSrc, dest);
}

// Re-pin tess.lock's base_sha for `.tess/core/conductor/user-profile.md` to
// match the override content's ACTUAL bytes on disk — `sha256_file()`'s own
// definition in .tess/bin/tessctl is `"sha256:" + sha256(path.read_bytes())
// .hexdigest()`, replicated exactly here (Node's `crypto` against the same
// bytes just written to `dest` above, not a re-derivation from the override
// SOURCE file — the two are cpSync'd byte-for-byte identical, but hashing
// what's actually on disk in the bundle is the more defensible ground truth).
const CONDUCTOR_USER_PROFILE_LOCK_CORE_KEY = '.tess/core/conductor/user-profile.md';
const coreMirrorPath = join(TEMPLATE_DIR, ...CONDUCTOR_USER_PROFILE_LOCK_CORE_KEY.split('/'));
const newSha = createHash('sha256').update(readFileSync(coreMirrorPath)).digest('hex');

const lockPath = join(TEMPLATE_DIR, '.tess', 'tess.lock');
if (!existsSync(lockPath)) die(`bundled tess.lock missing at ${lockPath} — cannot re-pin ${CONDUCTOR_USER_PROFILE_LOCK_CORE_KEY}`);
const lockText = readFileSync(lockPath, 'utf8');
const lockLines = lockText.split('\n');
// tess.lock's `files:` entries are `  <core_key>:` at 2-space indent, with
// each attribute (status/tier/base_sha/live_path/last_updated) at 4-space
// indent directly below. Locate the entry header line, then only the very
// next `    base_sha: sha256:...` line beneath it — scoped precisely enough
// that no other entry (or any entry whose core_key happens to be a PREFIX
// of this one) can ever be matched instead.
const entryHeader = `  ${CONDUCTOR_USER_PROFILE_LOCK_CORE_KEY}:`;
const headerIdx = lockLines.findIndex((l) => l === entryHeader);
if (headerIdx === -1) die(`tess.lock has no entry for ${CONDUCTOR_USER_PROFILE_LOCK_CORE_KEY} — cannot re-pin`);
let baseShaIdx = -1;
for (let i = headerIdx + 1; i < lockLines.length; i++) {
  const line = lockLines[i];
  // Stop at the next entry (a 2-space-indented, non-4-space-indented line)
  // or end of the files: block — never search past this entry's own block.
  if (!line.startsWith('    ')) break;
  if (/^    base_sha: sha256:[0-9a-f]{64}$/.test(line)) {
    baseShaIdx = i;
    break;
  }
}
if (baseShaIdx === -1) die(`tess.lock entry for ${CONDUCTOR_USER_PROFILE_LOCK_CORE_KEY} has no base_sha line — cannot re-pin`);
lockLines[baseShaIdx] = `    base_sha: sha256:${newSha}`;
writeFileSync(lockPath, lockLines.join('\n'), 'utf8');

// Report what actually landed — a quick sanity signal for the maintainer
// running this by hand, and useful CI log output when prepack runs it.
function countFiles(dir) {
  let n = 0;
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, entry.name);
    if (entry.isDirectory()) n += countFiles(p);
    else n += 1;
  }
  return n;
}
function sizeBytes(dir) {
  let total = 0;
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, entry.name);
    if (entry.isDirectory()) total += sizeBytes(p);
    else total += statSync(p).size;
  }
  return total;
}

const fileCount = countFiles(TEMPLATE_DIR);
const mb = (sizeBytes(TEMPLATE_DIR) / (1024 * 1024)).toFixed(2);
// stderr, deliberately — this runs as the `prepack` lifecycle hook during
// `npm pack --json`/`npm publish`, and npm interleaves a lifecycle script's
// OWN stdout directly into the surrounding command's stdout with no
// separator. `npm pack --json`'s output is meant to be machine-parseable
// JSON; a stray stdout line here would corrupt that for every consumer
// (this script's own maintainers included) that does `JSON.parse(npm pack
// --json's stdout)`. Diagnostic/progress output belongs on stderr.
console.error(`build-template: wrote ${fileCount} files (${mb} MB) to ${relative(REPO_ROOT, TEMPLATE_DIR)}/`);
