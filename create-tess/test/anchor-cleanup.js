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
// `npm test` also runs this file directly: `pretest` records what
// ~/.config/tess holds (`snapshot`), and `posttest`, after every test process
// has exited, removes the copies this run added that no anchor names and the
// directories it created and left empty, and the brain state folders it
// added that hold only a project id (the wizard's brain setup makes one per
// temp install under ~/.config/tess/brain/projects) (`final`), so a passing run leaves
// ~/.config/tess as it found it. Each copy is a whole file (tessctl alone is
// ~1.4 MB), so they are not left to accumulate.
import { before } from 'node:test';
import { spawnSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const SNAPSHOT = join(tmpdir(), 'create-tess-anchor-snapshot.json');

const PY = `
import json, os, pwd, shutil, sys, time
from pathlib import Path
tmp, mode, snap = os.path.realpath(sys.argv[1]), sys.argv[2], sys.argv[3]
tess = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".config" / "tess"
projects, blobs = tess / "projects", tess / "anchor-blobs"
dirs = (blobs, projects / "by-path", projects)  # innermost first
brain = tess / "brain" / "projects"
if mode == "snapshot":
    Path(snap).write_text(json.dumps({
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
        new = start is not None and b.name not in start["blobs"]
        if b.name not in used and (new or time.time() - b.stat().st_mtime > 1800):
            b.unlink()
    except OSError:
        pass
if start is not None:
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
    Path(snap).unlink(missing_ok=True)
`;

function run(mode) {
  const r = spawnSync('python3', ['-I', '-c', PY, tmpdir(), mode, SNAPSHOT], { encoding: 'utf8' });
  if (r.status !== 0 && mode !== 'each') {
    process.stderr.write(`anchor-cleanup ${mode}: ${r.stderr || r.error || 'failed'}\n`);
  }
}

export function forgetTempAnchors() {
  run('each');
}

// `node test/anchor-cleanup.js snapshot|final` (npm pretest / posttest).
if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const mode = process.argv[2];
  if (mode !== 'snapshot' && mode !== 'final') {
    process.stderr.write('usage: node test/anchor-cleanup.js snapshot|final\n');
    process.exit(2);
  }
  run(mode);
} else {
  before(forgetTempAnchors);
  // At process exit, after every `after` hook has removed the file's temp dirs.
  process.on('exit', forgetTempAnchors);
}
