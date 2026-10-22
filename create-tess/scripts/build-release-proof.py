#!/usr/bin/env python3
"""Build create-tess/release-proof.json for the signed release tag the npm
package is built from.

    python3 create-tess/scripts/build-release-proof.py --tag v1.0.0

The wizard copies the file into every install as .tess/release-proof.json, so
the install's first push passes the review gate with no verdict when its
protected files are exactly this release (tessctl: "the first push of a fresh
install"). The proof holds the raw tag object (its OpenPGP signature and its
SSH release signature), the commit object, every tree object of the release
commit (the git blob id of every file the template ships) and the raw bytes
of tess.lock and the two policy.yaml copies. Nothing here is trusted as
given: the gate re-hashes every object and verifies the tag with the release
keys the engine pins.

This script refuses to write a proof that does not verify against those
pinned keys, or whose tag does not name the checked-out commit (so the proof
always matches the template `npm pack` builds from the same tree).
Maintainer/CI only: never shipped (create-tess/scripts is not in "files").
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = PKG_DIR.parent


def _git(*args: str) -> str:
    r = subprocess.run(["git", "-C", str(REPO_ROOT), *args], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"build-release-proof: git {args[0]} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def _engine():
    path = REPO_ROOT / ".tess" / "bin" / "tessctl"
    loader = SourceFileLoader("tessctl_engine", str(path))
    mod = module_from_spec(spec_from_loader("tessctl_engine", loader))
    loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--tag", required=True, help="framework release tag, e.g. v1.0.0")
    ap.add_argument("--out", default=str(PKG_DIR / "release-proof.json"))
    args = ap.parse_args()

    tag = args.tag
    if _git("cat-file", "-t", f"refs/tags/{tag}") != "tag":
        sys.exit(f"build-release-proof: {tag} is not an annotated tag")
    commit = _git("rev-parse", f"refs/tags/{tag}^{{commit}}")
    head = _git("rev-parse", "HEAD")
    if commit != head:
        sys.exit(f"build-release-proof: {tag} names {commit[:12]}, but the checked-out tree is "
                 f"{head[:12]}; build the package from the tagged commit")

    m = _engine()
    proof = m._release_proof_build(REPO_ROOT, f"refs/tags/{tag}", tag, commit, {},
                                   full=True, blob_paths=m.RELEASE_PROOF_BLOB_PATHS)
    text = json.dumps(proof, indent=1, sort_keys=True) + "\n"

    def blob(rel: str) -> bytes | None:
        r = subprocess.run(["git", "-C", str(REPO_ROOT), "cat-file", "blob", f"{commit}:{rel}"],
                           capture_output=True)
        return r.stdout if r.returncode == 0 else None

    try:
        name, cid, resolve = m._release_proof_verify(
            text, m.RELEASE_ANCHOR_OPENPGP_FP, blob(m.RELEASE_KEY_FILE), None,
            ssh_pin=m.RELEASE_ANCHOR_SSH_FP, ssh_key_bytes=blob(m.RELEASE_SSH_SIGNERS_FILE))
    except m.ReleaseProofError as e:
        sys.exit(f"build-release-proof: the proof does not verify against the pinned release "
                 f"keys ({e.code}); refusing to ship it")
    missing = [rel for rel in m.RELEASE_PROOF_BLOB_PATHS if resolve.release_bytes(rel) is None]
    if name != tag or cid != commit or missing:
        sys.exit(f"build-release-proof: incomplete proof (tag {name}, missing {missing})")

    Path(args.out).write_text(text, encoding="utf-8")
    print(f"build-release-proof: wrote {args.out} for {tag} ({commit[:12]}, "
          f"{len(proof['trees'])} trees, {len(proof['blobs'])} blobs, {len(text)} bytes)",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
