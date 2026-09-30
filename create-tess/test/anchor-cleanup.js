// anchor-cleanup.js — v1.0.0: a wizard run that passes `tessctl verify`
// records Tess's safety files (the enforcement anchor) under the REAL OS
// user's ~/.config/tess/projects: tessctl and the hooks read the home from the
// OS user record, never from $HOME, so a test cannot move it. Importing this
// module removes, before and after the file's tests, every anchor and path
// marker whose project lived in the temp directory and no longer exists, and
// approved-file copies (anchor-blobs/) that no remaining anchor names and are
// 30+ minutes old. The age guard is there because `node --test` runs the test
// files as concurrent processes: a sibling may have written its copies and
// not yet its anchor.json.
//
// `npm test` runs this file directly (`node test/anchor-cleanup.js run`): it
// records what ~/.config/tess holds (`snapshot`), runs `node --test` over
// test/*.test.js, and, after every test process has exited, removes the copies this run added that no anchor names and the
// directories it created and left empty, and the brain state folders it
// added that hold only a project id (the wizard's brain setup makes one per
// temp install under ~/.config/tess/brain/projects) (`final`), so a passing run leaves
// ~/.config/tess as it found it. Each copy is a whole file (tessctl alone is
// ~1.4 MB), so they are not left to accumulate.
//
// Concurrent runs: each run's snapshot has its own name (runner PID, start
// time, random suffix), so two `npm test` runs never read or delete each
// other's snapshot. While another run's snapshot names a live runner, `final`
// does not remove items this run merely did not see at its start (they may be
// that run's); the 30-minute rule for unnamed copies still applies, and the
// last run to finish does the precise sweep. Snapshots of dead runners are
// ignored and deleted.
import { before } from 'node:test';
import { spawnSync } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { readdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

export const SNAPSHOT_PREFIX = 'create-tess-anchor-snapshot-';

export function snapshotPath(dir = tmpdir()) {
  const id = `${process.pid}-${Date.now()}-${randomBytes(4).toString('hex')}`;
  return join(dir, `${SNAPSHOT_PREFIX}${id}.json`);
}

const PY = `
import json, os, pwd, shutil, sys, time
from pathlib import Path
tmp, mode, snap = os.path.realpath(sys.argv[1]), sys.argv[2], sys.argv[3]
owner, prefix = int(sys.argv[4]), sys.argv[5]
tess = Path(sys.argv[6]) if len(sys.argv) > 6 else Path(pwd.getpwuid(os.getuid()).pw_dir) / ".config" / "tess"
projects, blobs = tess / "projects", tess / "anchor-blobs"
dirs = (blobs, projects / "by-path", projects)  # innermost first
brain = tess / "brain" / "projects"
if mode == "snapshot":
    Path(snap).write_text(json.dumps({
        "pid": owner,
        "blobs": sorted(p.name for p in blobs.iterdir()) if blobs.is_dir() else [],
        "brain": sorted(p.name for p in brain.iterdir()) if brain.is_dir() else [],
        "dirs": [str(d) for d in dirs if d.is_dir()]}))
    sys.exit(0)
start = None
if mode == "final":
    try:
        start = json.loads(Path(snap).read_text())
    except (OSError, ValueError):
        start = None
def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True  # exists, owned by someone else
    return True
others = False  # another run is still going: keep what it may have added
if start is not None:
    for f in Path(snap).parent.glob(prefix + "*.json"):
        if str(f) == snap:
            continue
        try:
            pid = int(json.loads(f.read_text())["pid"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if pid != owner and alive(pid):
            others = True
        elif not alive(pid):
            f.unlink(missing_ok=True)  # an aborted run's snapshot
for p in list(projects.glob("*/anchor.json")) + list(projects.glob("by-path/*.json")):
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        continue
    where = os.path.realpath(str(doc.get("project_path") or doc.get("path") or "/nonexistent"))
    if (where.startswith(tmp + os.sep) or where.startswith("/private" + tmp + os.sep)) and not os.path.exists(where):
        shutil.rmtree(p.parent, ignore_errors=True) if p.name == "anchor.json" else p.unlink()
used = set()
for p in projects.glob("*/anchor.json"):
    try:
        used |= {r.get("blob") for r in json.loads(p.read_text(encoding="utf-8"))["files"].values()}
    except (OSError, ValueError, KeyError, AttributeError):
        pass
for b in (blobs.iterdir() if blobs.is_dir() else []):
    try:
        new = start is not None and not others and b.name not in start["blobs"]
        if b.name not in used and (new or time.time() - b.stat().st_mtime > 1800):
            b.unlink()
    except OSError:
        pass
if start is not None and not others:
    # The brain's per-install state folder (brain/projects/<sha256(path)[:24]>)
    # that a wizard run in a temp dir creates: removed when this run added it
    # and it holds nothing but the random project id (no ledger, no outbox).
    for d in (brain.iterdir() if brain.is_dir() and "brain" in start else []):
        try:
            if d.name not in start["brain"] and d.is_dir() and not d.is_symlink() \\
                    and [c.name for c in d.iterdir()] == ["id"] and (d / "id").is_file():
                (d / "id").unlink()
                d.rmdir()
        except OSError:
            pass
    for d in dirs:
        if str(d) not in start["dirs"]:
            try:
                d.rmdir()  # only when empty
            except OSError:
                pass
if mode == "final":
    Path(snap).unlink(missing_ok=True)
`;

// `tessDir` is for this file's own test only; by default the sweep reads the
// real OS user's ~/.config/tess, as tessctl and the hooks do.
export function sweep(mode, snap = '', { tessDir, owner = process.pid } = {}) {
  const args = ['-I', '-c', PY, tmpdir(), mode, snap, String(owner), SNAPSHOT_PREFIX];
  if (tessDir) args.push(tessDir);
  const r = spawnSync('python3', args, { encoding: 'utf8' });
  if (r.status !== 0 && mode !== 'each') {
    process.stderr.write(`anchor-cleanup ${mode}: ${r.stderr || r.error || 'failed'}\n`);
  }
  return r.status;
}

export function forgetTempAnchors() {
  sweep('each');
}

// `node test/anchor-cleanup.js run [node --test flags]` (npm test).
function runSuite(extra) {
  const pkg = dirname(dirname(fileURLToPath(import.meta.url)));
  const files = readdirSync(join(pkg, 'test')).filter((f) => f.endsWith('.test.js')).sort()
    .map((f) => join('test', f));
  const snap = snapshotPath();
  sweep('snapshot', snap);
  const r = spawnSync(process.execPath, ['--test', ...extra, ...files], { cwd: pkg, stdio: 'inherit' });
  sweep('final', snap);
  if (r.error) process.stderr.write(`anchor-cleanup run: ${r.error}\n`);
  return r.status ?? 1;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  if (process.argv[2] !== 'run') {
    process.stderr.write('usage: node test/anchor-cleanup.js run [node --test flags]\n');
    process.exit(2);
  }
  process.exit(runSuite(process.argv.slice(3)));
} else {
  before(forgetTempAnchors);
  // At process exit, after every `after` hook has removed the file's temp dirs.
  process.on('exit', forgetTempAnchors);
}
