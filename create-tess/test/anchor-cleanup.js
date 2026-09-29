// anchor-cleanup.js — v1.0.0: a wizard run that passes `tessctl verify`
// records Tess's safety files (the enforcement anchor) under the REAL OS
// user's ~/.config/tess/projects: tessctl and the hooks read the home from the
// OS user record, never from $HOME, so a test cannot move it. Importing this
// module removes, before and after the file's tests, every anchor and path
// marker whose project lived in the temp directory and no longer exists,
// and approved-file copies that no remaining anchor names.
// Content-addressed copies in ~/.config/tess/anchor-blobs/ are shared and kept.
import { before } from 'node:test';
import { spawnSync } from 'node:child_process';
import { tmpdir } from 'node:os';

const PY = `
import json, os, pwd, shutil, sys
from pathlib import Path
tmp = os.path.realpath(sys.argv[1])
projects = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".config" / "tess" / "projects"
for p in list(projects.glob("*/anchor.json")) + list(projects.glob("by-path/*.json")):
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        continue
    where = os.path.realpath(str(doc.get("project_path") or doc.get("path") or "/nonexistent"))
    if (where.startswith(tmp + os.sep) or where.startswith("/private" + tmp + os.sep)) and not os.path.exists(where):
        shutil.rmtree(p.parent, ignore_errors=True) if p.name == "anchor.json" else p.unlink()
# Approved-file copies no remaining anchor names, older than 30 minutes (so a
# concurrently running install keeps the copies it has just written).
blobs = projects.parent / "anchor-blobs"
used = set()
for p in projects.glob("*/anchor.json"):
    try:
        used |= {r.get("blob") for r in json.loads(p.read_text(encoding="utf-8"))["files"].values()}
    except (OSError, ValueError, KeyError, AttributeError):
        pass
import time
for b in (blobs.iterdir() if blobs.is_dir() else []):
    try:
        if b.name not in used and time.time() - b.stat().st_mtime > 1800:
            b.unlink()
    except OSError:
        pass
`;

export function forgetTempAnchors() {
  spawnSync('python3', ['-I', '-c', PY, tmpdir()], { encoding: 'utf8' });
}

before(forgetTempAnchors);
// At process exit, after every `after` hook has removed the file's temp dirs.
process.on('exit', forgetTempAnchors);
