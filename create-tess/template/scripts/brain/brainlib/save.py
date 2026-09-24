"""`tessbrain.py save`: saved = in its owning folder + linked from its START
HERE + committed + pushed (spec 10.9).

1. Refuse any new/changed brain file that nothing links to (names the link).
2. Stage ONLY brain/ and the state-card folder (`git add -- <paths>`).
3. Redaction scan of the staged brain files, plus gitleaks when installed.
4. Commit those paths only; the repository's own hooks always run.
5. Push only when save.autopush is on and the remote is neither the public
   framework repo nor reported PUBLIC by `gh`. Git hooks are never bypassed:
   if the ship-gate refuses a brand-new instance's first push, the tool
   points to the one-time operator seed-push step in docs/brain/ONBOARDING.md.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List

from . import gitutil, reach, redact
from .config import Config


def _paths(cfg: Config) -> List[str]:
    return [p for p in ("brain", cfg.state_cards) if (cfg.root / p).exists()]


def _changed(cfg: Config) -> List[str]:
    return [p for xy, p in gitutil.porcelain(cfg.root, _paths(cfg)) if xy != "!!"]


def _scan(cfg: Config, files: List[str]) -> List[str]:
    hits = []
    for rel in files:
        p = cfg.root / rel
        if p.is_file() and p.stat().st_size < 4 * 1024 * 1024:
            for n, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                kinds = redact.scan(line)
                if kinds:
                    hits.append("%s:%d (%s)" % (rel, n, ", ".join(kinds)))
    return hits


def _gitleaks(cfg: Config) -> str:
    exe = shutil.which("gitleaks")
    if not exe:
        return ""
    try:
        p = subprocess.run([exe, "protect", "--staged", "--no-banner", "--redact", "--source", str(cfg.root)],
                           capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        return "gitleaks could not run: %s" % exc
    return "" if p.returncode == 0 else "gitleaks reported leaks in the staged files:\n%s" % (p.stdout + p.stderr)[-2000:]


def visibility(url: str) -> str:
    """'public' | 'private' | 'unknown' via `gh repo view` (best effort)."""
    m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?/?$", url or "")
    if not m or not shutil.which("gh"):
        return "unknown"
    try:
        p = subprocess.run(["gh", "repo", "view", m.group(1), "--json", "visibility"], capture_output=True,
                           text=True, timeout=20)
        return str(json.loads(p.stdout).get("visibility", "unknown")).lower() if p.returncode == 0 else "unknown"
    except (OSError, ValueError, subprocess.SubprocessError):
        return "unknown"


def push_verdict(cfg: Config, url: str) -> str:
    """'' when pushing is allowed, else the reason it is refused."""
    for pat in cfg.framework_patterns:
        if re.search(pat, url or ""):
            return "remote %s is the public Tess OS framework repo; brain data never goes there" % url
    local = url.startswith(("/", "file://", "./", "../")) or (url and ":" not in url)
    if local:
        return ""
    vis = visibility(url)
    if vis == "public":
        return "remote %s is PUBLIC (gh repo view); refusing to push private brain data" % url
    if vis == "unknown" and str(cfg.remote.get("visibility")) != "private":
        return ("cannot confirm %s is private (gh missing or no access); set remote.visibility to \"private\" in "
                "brain/brain.json after checking, or push by hand" % url)
    return ""


def run(cfg: Config, message: str, dry_run: bool = False) -> Dict:
    out: Dict = {"ok": False, "committed": "", "pushed": False, "notes": []}
    if not gitutil.is_repo(cfg.root):
        out["error"] = "not a git repository"
        return out
    if not dry_run:  # generated blocks first, so new entities and records are linked from START HERE
        from . import index
        rc, msgs = index.regenerate(cfg)
        out["notes"] += msgs
    changed = _changed(cfg)
    orphans = reach.unreachable(cfg, [cfg.root / p for p in changed if p.startswith("brain/")])
    if orphans:
        out["error"] = "unreachable, not saved: " + "; ".join(
            "%s (add a link to it in %s)" % (cfg.rel(p), cfg.rel(reach.owning_start(cfg, p))) for p in orphans)
        return out
    if not changed:
        out.update(ok=True, notes=["nothing to commit"])
        return _push(cfg, out, dry_run)
    leaks = _scan(cfg, [p for p in changed])
    if leaks:
        out["error"] = "secret-shaped content, not saved: " + "; ".join(leaks[:10])
        return out
    if dry_run:
        out.update(ok=True, notes=["would commit %d file(s)" % len(changed)])
        return out
    paths = [p for p in _paths(cfg) if any(c == p or c.startswith(p + "/") for c in changed)]
    rc, _, err = gitutil.run(cfg.root, ["add", "--"] + paths)
    if rc != 0:
        out["error"] = "git add failed: %s" % err.strip()
        return out
    g = _gitleaks(cfg)
    if g:
        out["error"] = g
        return out
    rc, so, se = gitutil.run(cfg.root, ["commit", "-m", message or "brain: save", "--only", "--"] + paths, timeout=300)
    if rc != 0:
        out["error"] = "git commit refused (the repository's hooks ran): %s" % (so + se).strip()[-1500:]
        return out
    out.update(ok=True, committed=gitutil.head(cfg.root))
    return _push(cfg, out, dry_run)


def _push(cfg: Config, out: Dict, dry_run: bool) -> Dict:
    if not cfg.autopush:
        out["notes"].append("autopush is off: push when you are ready (save.autopush in brain/brain.json)")
        return out
    name = str(cfg.remote.get("name") or "origin")
    url = gitutil.remote_url(cfg.root, name)
    if not url:
        out["notes"].append("no git remote %r; add a PRIVATE remote to back up the brain" % name)
        return out
    why = push_verdict(cfg, url)
    if why:
        out["notes"].append("not pushed: " + why)
        return out
    if dry_run:
        out["notes"].append("would push to %s" % name)
        return out
    rc, so, se = gitutil.run(cfg.root, ["push", "-u", name, "HEAD"], timeout=300)
    if rc == 0:
        out["pushed"] = True
    elif "COVERING_APPROVAL_MISSING" in so + se:
        out["notes"].append("the ship-gate refused this instance's first push. Do the one-time operator seed push "
                            "described in docs/brain/ONBOARDING.md (after reading git log), then save again.")
    else:
        out["notes"].append("push failed: %s" % (so + se).strip()[-800:])
    return out
