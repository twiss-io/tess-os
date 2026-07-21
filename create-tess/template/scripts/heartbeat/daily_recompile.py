"""The once-a-day recompile: regenerate memory/registry.md from the cards,
scan for unregistered open work, commit+push, and send one notification
digest.

Split out of run.py to keep per-card Tier-1/Tier-2 orchestration (the thing
that runs every tick) separate from this (the thing that runs once a day) —
two different cadences, two different responsibilities.

The "unregistered work" scan is entirely opt-in and config-driven — a fresh
instance with no `daily_recompile.*` config set scans nothing and reports an
empty digest rather than assuming any particular org, directory layout, or
memory convention.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config as config_mod
from . import notify, registry_gen, tier2_classify


def scan_memory_project_titles(glob_pattern: Optional[str]) -> List[str]:
    """`glob_pattern` is an operator-configured glob (e.g.
    "~/.claude/projects/*/memory/project_*.md") pointing at whatever
    convention the operator uses for cross-session project notes. None/empty
    (the shipped default) means this scan is skipped entirely — nothing is
    assumed about where or whether such files exist."""
    if not glob_pattern:
        return []
    titles = []
    base = Path(glob_pattern).expanduser()
    # Path.glob requires a relative pattern under some anchor; split into
    # anchor + pattern so an absolute glob with wildcards in the middle
    # (e.g. "~/.claude/projects/*/memory/project_*.md") still works.
    parts = base.parts
    anchor_parts, pattern_parts = [], []
    hit_wildcard = False
    for part in parts:
        if not hit_wildcard and "*" not in part and "?" not in part and "[" not in part:
            anchor_parts.append(part)
        else:
            hit_wildcard = True
            pattern_parts.append(part)
    anchor = Path(*anchor_parts) if anchor_parts else Path("/")
    pattern = str(Path(*pattern_parts)) if pattern_parts else base.name
    if not anchor.exists():
        return []
    for f in sorted(anchor.glob(pattern)):
        first_line = ""
        try:
            first_line = f.read_text(encoding="utf-8").splitlines()[0]
        except (OSError, IndexError):
            pass
        titles.append(f"{f.stem}: {first_line}")
    return titles


def scan_org_repos(orgs: List[str]) -> List[str]:
    """`orgs` is the operator-configured `daily_recompile.org_repo_scan` list
    (default empty — skipped entirely). Each org is scanned independently;
    a failure on one org is reported inline rather than aborting the others."""
    results: List[str] = []
    for org in orgs:
        try:
            out = subprocess.run(
                ["gh", "repo", "list", org, "--limit", "200",
                 "--json", "nameWithOwner,pushedAt,isArchived"],
                capture_output=True, text=True, timeout=30, check=False,
            )
            if out.returncode != 0:
                results.append(f"(org repo scan failed for {org}: {out.stderr.strip()[:200]})")
                continue
            repos = json.loads(out.stdout)
            results.extend(
                f"{r['nameWithOwner']} pushedAt={r.get('pushedAt')}"
                for r in repos if not r.get("isArchived")
            )
        except Exception as exc:  # noqa: BLE001 — best-effort scan, never crash the run over it
            results.append(f"(org repo scan failed for {org}: {exc})")
    return results


def run(
    all_cards: list,
    now: datetime,
    dry_run: bool,
    repo_root: Path,
    registry_path: Path,
    cfg: Optional[config_mod.HeartbeatConfig] = None,
) -> Dict[str, Any]:
    cfg = cfg or config_mod.load()
    existing_text = registry_path.read_text(encoding="utf-8") if registry_path.exists() else ""
    new_registry_text = registry_gen.regenerate(all_cards, existing_text, now)

    wiki_tail = ""
    if cfg.daily_recompile.wiki_log_path:
        wiki_log = repo_root / cfg.daily_recompile.wiki_log_path
        if wiki_log.exists():
            lines = wiki_log.read_text(encoding="utf-8").splitlines()
            wiki_tail = "\n".join(lines[-cfg.daily_recompile.wiki_log_tail_lines:])

    memory_titles = scan_memory_project_titles(cfg.daily_recompile.memory_project_glob)
    org_repos = scan_org_repos(cfg.daily_recompile.org_repo_scan)

    synthesis = tier2_classify.daily_recompile_synthesis(
        registry_snapshot=new_registry_text[:6000],
        memory_project_titles=memory_titles,
        wiki_log_tail=wiki_tail,
        org_repo_scan=org_repos,
        dry_run=dry_run,
        cfg=cfg,
    )

    digest_lines = [
        f"[heartbeat daily] {len(all_cards)} open, "
        f"{sum(1 for c in all_cards if c.is_stalled)} stalled, "
        f"{sum(1 for c in all_cards if c.priority == 'P0')} P0.",
    ]
    for cand in synthesis.get("unregistered_candidates", []):
        digest_lines.append(f"- unregistered candidate: {cand.get('name')} — {cand.get('evidence')}")
    for sus in synthesis.get("stale_card_suspects", []):
        digest_lines.append(f"- stale-card suspect: {sus.get('slug')} — {sus.get('why')}")
    digest = "\n".join(digest_lines)

    send_res = notify.send(digest, dry_run=dry_run, cfg=cfg)

    if not dry_run:
        registry_path.write_text(new_registry_text, encoding="utf-8")
        subprocess.run(["git", "-C", str(repo_root), "add", "memory/"], check=False)
        subprocess.run(
            ["git", "-C", str(repo_root), "commit", "-m",
             "chore(heartbeat): daily recompile — registry regenerated from cards\n\n"
             "Automated commit from scripts/heartbeat/run.py's daily recompile pass. "
             "No card narrative (next_move/resume/gates) was touched, only the "
             "auto-generated registry.md dashboard and mechanical evidence fields."],
            check=False,
        )
        subprocess.run(["git", "-C", str(repo_root), "push"], check=False)

    return {
        "new_registry_preview": new_registry_text[:2000],
        "synthesis": synthesis,
        "digest": digest,
        "notify": repr(send_res),
    }
