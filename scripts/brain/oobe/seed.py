"""The explicit path list for a new instance's first (seed) commit.

The seed commit used to be `git add -A`. When a .gitignore was missing (npm
strips it from the create-tess tarball) that staged operator/profile.json,
.env and client data, the installed publish-clean pre-commit gate refused
them, and onboarding could never make its first commit. The seed commit is
now path-scoped: every untracked, not-ignored file EXCEPT the paths the
publish-clean gate treats as private. The private rules are read from the
installed tessctl (the same constants its pre-commit gate enforces); the
copy below is only a fallback for an install whose tessctl cannot be loaded,
and tests/test_brain_seed_commit.py keeps it identical to tessctl's.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Callable, List, Tuple

FALLBACK_PRIVATE_GLOBS = [
    "kb/**", "clients/*/**", "operator/**", ".env", ".env.*", "*.local.md", "**/*.local.md",
    "missions/**", ".tess/state/**", "UPGRADE-NOTES.md", ".mcp.json", "**/*.age",
    ".claude/vault/**", "clients/*/.vault/**",
    # v0.2.1 #202: brain/.private/ and per-area .private/ folders are never committed.
    "brain/**/.private/**", "**/.private/**",
]
FALLBACK_ALLOWLIST = frozenset({
    "operator/build-facts-stub.md", "operator/identity-stub.md", "operator/org-channels.md",
    "operator/user-profile.md", "missions/README.md", ".claude/vault/.gitkeep",
    ".claude/vault/vault.registry.json", ".env.example",
})


def _glob_regex(pattern: str) -> str:
    """'**' spans whole segments, '*'/'?' never cross '/' (tessctl _glob_to_regex semantics)."""
    segs, out, need_sep, i = pattern.split("/"), [], False, 0
    while i < len(segs):
        if segs[i] == "**":
            j = i
            while j < len(segs) and segs[j] == "**":
                j += 1
            if j == len(segs):
                out.append("/.*" if need_sep else ".*")
            else:
                out.append(("/" if need_sep else "") + "(?:.*/)?")
            need_sep, i = False, j
            continue
        seg = re.escape(segs[i]).replace(r"\*", "[^/]*").replace(r"\?", "[^/]")
        out.append(("/" if need_sep else "") + seg)
        need_sep, i = True, i + 1
    return "(?s:" + "".join(out) + r")\Z"


def _fallback_match(path: str, globs: List[str]) -> bool:
    return any(re.match(_glob_regex(g), path) for g in globs)


def load_rules(root: Path) -> Tuple[List[str], frozenset, Callable[[str, List[str]], bool]]:
    """(private_globs, allowlist, matcher), from the installed tessctl when it loads."""
    engine = root / ".tess" / "bin" / "tessctl"
    try:
        loader = importlib.machinery.SourceFileLoader("_tess_seed_rules", str(engine))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
        return (list(mod._PUBLISH_CLEAN_PRIVATE_GLOBS), frozenset(mod._PUBLISH_CLEAN_ALLOWLIST),
                mod.path_matches_globs)
    except (OSError, ImportError, AttributeError, SyntaxError, SystemExit):
        return FALLBACK_PRIVATE_GLOBS, FALLBACK_ALLOWLIST, _fallback_match


def owned_globs(root: Path) -> List[str]:
    try:
        return list(json.loads((root / "tess.manifest.json").read_text(encoding="utf-8"))
                    .get("owned_globs", []))
    except (OSError, ValueError):
        return []


def is_private(path: str, private: List[str], allow: frozenset, owned: List[str],
               match: Callable[[str, List[str]], bool]) -> bool:
    """True when the publish-clean gate would refuse to commit `path`."""
    if os.path.basename(path) == ".gitkeep" or path in allow or match(path, owned):
        return False
    return match(path, private)


def seed_paths(root: Path) -> Tuple[List[str], List[str]]:
    """(paths to commit, private paths left out) for the seed commit."""
    # --cached too (v1.0 B4): a seed commit that failed (for example, refused by
    # a hook) leaves its files staged, and the re-run must still commit them.
    # The same private/allow filters below apply to staged and untracked files.
    listed = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others",
                             "--exclude-standard"],
                            capture_output=True, text=True, check=True).stdout
    private, allow, match = load_rules(root)
    owned = owned_globs(root)
    keep, held = [], []
    for path in sorted(p for p in listed.split("\0") if p):
        (held if is_private(path, private, allow, owned, match) else keep).append(path)
    return keep, held
