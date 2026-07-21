// template-drift-guard.test.js — regression guard for the create-tess
// bundle build/commit drift class (PR #160 gap-loop fix, Reid HIGH).
//
// THE BUG: `create-tess/template/` is BOTH committed to the repo (reviewable
// in a PR diff) AND regenerated fresh by scripts/build-template.mjs
// (manually via `npm run build-template`, automatically via the `prepack`
// lifecycle hook before every `npm pack`/`npm publish`). Nothing enforced
// that the two ever actually agreed — a maintainer could commit a stale
// snapshot (or simply forget to re-run the build after editing
// src/ignore.js or adding new tracked files at the repo root) and nobody
// would notice until the DIFFERENCE silently shipped to npm on the next
// real publish, since `prepack` regenerates from the true, current source
// tree regardless of what the last reviewed diff showed.
//
// Reid's review caught exactly this on PR #160 HEAD (commit 3774525): a
// fresh `node scripts/build-template.mjs` run produced 4 more files than
// the committed diff — `operator/profile.json`, `kb/wiki/index.md`,
// `kb/wiki/log.md` (this repo's own root, live operator/self-governance
// state — see ignore.js's EXCLUDE_REL_PATHS / EXCLUDE_CONTENT_PREFIXES for
// the fix), and `proving-ground/tasks/06-research-log-analysis/fixture/
// access.log` (a legitimate, safe-to-ship test fixture that a stray
// top-level `*.log` rule in create-tess/.gitignore was silently hiding from
// every `git add` — see that file's own fix).
//
// THIS TEST closes the gap permanently: build the template fresh (into an
// isolated repo snapshot, never the shared working-tree copy — same
// isolation pattern, and for the same reason, as
// offline-bundle-scaffold.test.js's snapshotRepo(): build-template.mjs's own
// `rm -rf` + regenerate would otherwise race any other test file
// concurrently reading the real, shared create-tess/template/ under
// `node --test`'s default per-file concurrency) and assert its file set AND
// byte content are IDENTICAL to the committed tree — not merely
// count-identical, which would pass right through a same-count,
// different-file (or same-file, edited-content) drift.
import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, rmSync, cpSync, readdirSync, readFileSync, existsSync } from 'node:fs';
import { join, resolve, dirname, relative, sep } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';

const TEST_DIR = dirname(fileURLToPath(import.meta.url));
const PKG_DIR = resolve(TEST_DIR, '..'); // create-tess/
const REPO_ROOT = resolve(PKG_DIR, '..'); // tess-os/

const tempDirs = [];
after(() => {
  for (const d of tempDirs) rmSync(d, { recursive: true, force: true });
});
function mkTemp(prefix) {
  const d = mkdtempSync(join(tmpdir(), prefix));
  tempDirs.push(d);
  return d;
}

// Recursive relative-path file listing, POSIX-separator, sorted — a plain
// diffable file-set snapshot regardless of host OS.
function walkFiles(root) {
  const out = [];
  (function rec(dir) {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const p = join(dir, entry.name);
      if (entry.isDirectory()) rec(p);
      else out.push(relative(root, p).split(sep).join('/'));
    }
  })(root);
  return out.sort();
}

test(
  'create-tess/template/ (committed) matches a fresh `node scripts/build-template.mjs` run byte-for-byte — no build/commit drift',
  { timeout: 120000 },
  () => {
    // Full-repo snapshot: build-template.mjs shells out to
    // `git -C REPO_ROOT ls-files` and resolves REPO_ROOT relative to its own
    // script location, so it needs a real, complete working tree (including
    // .git) to run at all — same requirement, same isolation rationale, as
    // offline-bundle-scaffold.test.js's own snapshotRepo() helper.
    const snap = mkTemp('create-tess-drift-guard-repo-snapshot-');
    cpSync(REPO_ROOT, snap, { recursive: true, dereference: false });

    const committedTemplate = join(PKG_DIR, 'template');
    const freshTemplate = join(snap, 'create-tess', 'template');

    const build = spawnSync(
      process.execPath,
      [join(snap, 'create-tess', 'scripts', 'build-template.mjs')],
      { cwd: snap, encoding: 'utf8' },
    );
    assert.equal(
      build.status,
      0,
      `scripts/build-template.mjs failed against a fresh repo snapshot\nSTDOUT:\n${build.stdout}\nSTDERR:\n${build.stderr}`,
    );

    const committedFiles = walkFiles(committedTemplate);
    const freshFiles = walkFiles(freshTemplate);
    const freshSet = new Set(freshFiles);
    const committedSet = new Set(committedFiles);

    const missingFromCommitted = freshFiles.filter((f) => !committedSet.has(f));
    const extraInCommitted = committedFiles.filter((f) => !freshSet.has(f));
    assert.deepEqual(
      missingFromCommitted,
      [],
      'committed create-tess/template/ is STALE — a fresh build produces files not present in the ' +
        'committed diff (these would silently ship to npm on the next publish without ever appearing ' +
        `in a reviewed PR diff): ${missingFromCommitted.join(', ')}\n` +
        'Run `npm run build-template` (create-tess/) and commit the result.',
    );
    assert.deepEqual(
      extraInCommitted,
      [],
      'committed create-tess/template/ carries files a fresh build no longer produces (stale/orphaned): ' +
        `${extraInCommitted.join(', ')}\nRun \`npm run build-template\` (create-tess/) and commit the result.`,
    );

    // File-set parity alone is not sufficient — a same-name file whose
    // CONTENT changed upstream since the last commit (e.g. a doctrine file
    // edited after the bundle was last regenerated) must also fail here,
    // not just a count/name check.
    const mismatched = [];
    for (const rel of committedFiles) {
      const a = readFileSync(join(committedTemplate, ...rel.split('/')));
      const b = readFileSync(join(freshTemplate, ...rel.split('/')));
      if (!a.equals(b)) mismatched.push(rel);
    }
    assert.deepEqual(
      mismatched,
      [],
      'committed create-tess/template/ has STALE CONTENT (same file list, different bytes) for: ' +
        `${mismatched.join(', ')}\nRun \`npm run build-template\` (create-tess/) and commit the result.`,
    );
  },
);

test("the bundled template never carries this repo's own root operator/self-governance state", () => {
  const bundled = join(PKG_DIR, 'template');
  // PR #160 gap-loop fix (Reid HIGH): these are THIS repo's own live,
  // root-level operator identity + internal wiki/mission-log — never
  // scaffold-template content. `operator/profile.json` is regenerated fresh
  // by writeProfile()/tessctl at real scaffold time regardless (see
  // keystone.js), so excluding it from the bundle changes nothing about a
  // real scaffold's behavior — it only closes the drift/leak-shaped gap in
  // what gets published. `kb/wiki/{index,log}.md` ship EMPTY, the same
  // treatment every other `.tess/state/**` subsystem already gets — see
  // ignore.js's EXCLUDE_REL_PATHS / EXCLUDE_CONTENT_PREFIXES.
  for (const forbidden of ['operator/profile.json', 'kb/wiki/index.md', 'kb/wiki/log.md']) {
    assert.ok(
      !existsSync(join(bundled, ...forbidden.split('/'))),
      `bundle must not contain ${forbidden} (this repo's own live operator/wiki state)`,
    );
  }
  // The wiki STRUCTURE (not its content) still ships — a scaffolded
  // instance's own kb/wiki/ needs these directories to exist, exactly like
  // .tess/state/**'s own .gitkeep-only subdirs.
  for (const keep of [
    'kb/wiki/concepts/.gitkeep',
    'kb/wiki/missions/.gitkeep',
    'kb/wiki/people/.gitkeep',
    'kb/wiki/synthesis/.gitkeep',
  ]) {
    assert.ok(
      existsSync(join(bundled, ...keep.split('/'))),
      `bundle must still ship the wiki STRUCTURE at ${keep}, only its live content is stripped`,
    );
  }
  // clients/_template/kb/wiki/** is legitimate, already-genericized generic
  // starter content ([Client Name] placeholders, never live data) — must be
  // unaffected by the root-only kb/wiki exclusion above.
  for (const keep of ['clients/_template/kb/wiki/index.md', 'clients/_template/kb/wiki/log.md']) {
    assert.ok(
      existsSync(join(bundled, ...keep.split('/'))),
      `bundle must still ship the legitimate generic starter content at ${keep}`,
    );
  }
  // The legitimate, safe-to-ship proving-ground test fixture (previously
  // hidden from every commit by a stray create-tess/.gitignore `*.log`
  // rule, not by any deliberate exclusion) must be present.
  assert.ok(
    existsSync(join(bundled, 'proving-ground', 'tasks', '06-research-log-analysis', 'fixture', 'access.log')),
    'bundle must ship the proving-ground research-log-analysis fixture (was silently gitignored, not excluded)',
  );
});
