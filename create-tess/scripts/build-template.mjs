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
import { existsSync, mkdirSync, rmSync, cpSync, readdirSync, statSync } from 'node:fs';
import { dirname, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

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
