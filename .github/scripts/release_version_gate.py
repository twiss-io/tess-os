#!/usr/bin/env python3
"""release_version_gate.py <tag> [--root DIR] — fail unless every version agrees.

A framework release tag v<X> must match:
package.json version, create-tess/package.json version, .tess/tess.lock
framework.version, and a `## [<X>]` section in CHANGELOG.md. Stdlib only.

SPDX-License-Identifier: Apache-2.0
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def lock_version(text: str) -> str | None:
    m = re.search(r"^framework:\n((?:[ \t]+.*\n?)*)", text, re.M)
    v = re.search(r"^[ \t]+version:[ \t]*['\"]?([^'\"\s]+)", m.group(1), re.M) if m else None
    return v.group(1) if v else None


def check(tag: str, root: Path) -> list:
    m = re.fullmatch(r"v(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)", tag)
    if not m:
        return ["tag %r is not v<semver>" % tag]
    want = m.group(1)
    found = {}
    for label, rel in (("package.json", "package.json"), ("create-tess/package.json", "create-tess/package.json")):
        try:
            found[label] = json.loads((root / rel).read_text(encoding="utf-8")).get("version")
        except (OSError, ValueError) as exc:
            found[label] = "unreadable (%s)" % exc
    try:
        found[".tess/tess.lock framework.version"] = lock_version((root / ".tess" / "tess.lock").read_text(encoding="utf-8"))
    except OSError as exc:
        found[".tess/tess.lock framework.version"] = "unreadable (%s)" % exc
    errors = ["%s is %s, tag says %s" % (k, v, want) for k, v in found.items() if v != want]
    try:
        changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    except OSError:
        changelog = ""
    if not re.search(r"^## \[" + re.escape(want) + r"\]", changelog, re.M):
        errors.append("CHANGELOG.md has no '## [%s]' section" % want)
    return errors


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("tag")
    ap.add_argument("--root", default=".")
    a = ap.parse_args(argv)
    errors = check(a.tag, Path(a.root))
    for e in errors:
        print("::error::version gate: %s" % e)
    if errors:
        print("Refusing to release %s: bump every version above in one commit, then re-tag." % a.tag)
        return 1
    print("OK: %s agrees with both package.json files, tess.lock and CHANGELOG.md." % a.tag)
    return 0


if __name__ == "__main__":
    sys.exit(main())
