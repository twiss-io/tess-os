"""Tier-1 evidence probes — $0, no LLM, ever.

Every function here shells out to `gh` (already-authenticated per
`gh auth status`) and returns primary-source facts: the newest commit on
the repo's default branch and the newest PR activity (open or closed,
last 5). This is the cost floor the design requires — the moving-path,
which runs every tick for every open project, must never invoke a model.
Two `gh api` calls per repo, comfortably inside GitHub's 5000/hr
authenticated rate limit for any registry of realistic size.

A probe failure (auth, network, renamed/deleted repo) raises ProbeError
rather than being swallowed into a false "no activity" reading — a
network blip must never be misreported as a real stall.

Ported unchanged from the reference implementation — `probe_repo(repo)`
already takes the repo as a plain "org/name" string (read from each card's
own `repo:` field), so there is nothing project-specific to generalize here.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


class ProbeError(Exception):
    """A probe command failed. Callers must surface this per-card and skip
    classification for that card this run, never treat it as 'no activity'."""


@dataclass
class Evidence:
    repo: str
    latest_commit_sha: Optional[str]
    latest_commit_ts: Optional[datetime]
    latest_commit_message: Optional[str]
    latest_pr_number: Optional[int]
    latest_pr_ts: Optional[datetime]
    latest_pr_state: Optional[str]
    checked_at: datetime

    @property
    def latest_ts(self) -> Optional[datetime]:
        candidates = [t for t in (self.latest_commit_ts, self.latest_pr_ts) if t]
        return max(candidates) if candidates else None

    @property
    def proof(self) -> str:
        parts = []
        if self.latest_commit_sha:
            parts.append(
                f'commit {self.latest_commit_sha[:9]} on {self.repo} '
                f'({_fmt(self.latest_commit_ts)}) — "{self.latest_commit_message}"'
            )
        if self.latest_pr_number:
            parts.append(
                f"PR #{self.latest_pr_number} ({self.latest_pr_state}, "
                f"updated {_fmt(self.latest_pr_ts)})"
            )
        if not parts:
            return f"no commit/PR evidence returned for {self.repo}"
        return (
            "; ".join(parts)
            + f" — verified via `gh api repos/{self.repo}/commits` + "
            f"`gh pr list --repo {self.repo}` at {_fmt(self.checked_at)}"
        )


def _fmt(ts: Optional[datetime]) -> str:
    if ts is None:
        return "unknown"
    return ts.isoformat().replace("+00:00", "Z")


def _run(cmd: list, timeout: int = 20) -> str:
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        raise ProbeError(f"could not run: {' '.join(cmd)} — {exc}") from exc
    if result.returncode != 0:
        raise ProbeError(
            f"command failed ({result.returncode}): {' '.join(cmd)}\n"
            f"{result.stderr.strip()}"
        )
    return result.stdout


def _parse_ts(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def probe_repo(repo: str) -> Evidence:
    """repo is 'org/name' exactly as stored on the card's `repo:` field."""
    checked_at = datetime.now(timezone.utc)

    commit_sha = commit_ts = commit_msg = None
    raw = _run(["gh", "api", f"repos/{repo}/commits", "-X", "GET", "-f", "per_page=1"])
    try:
        commits = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProbeError(f"commit probe returned non-JSON for {repo}: {exc}") from exc
    if commits:
        try:
            commit_sha = commits[0]["sha"]
            commit_ts = _parse_ts(commits[0]["commit"]["committer"]["date"])
            commit_msg = commits[0]["commit"]["message"].splitlines()[0][:120]
        except (KeyError, IndexError) as exc:
            raise ProbeError(f"commit probe shape unexpected for {repo}: {exc}") from exc

    pr_number = pr_ts = pr_state = None
    raw = _run([
        "gh", "pr", "list", "--repo", repo, "--state", "all",
        "--limit", "5", "--json", "number,state,updatedAt",
    ])
    try:
        prs = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProbeError(f"PR probe returned non-JSON for {repo}: {exc}") from exc
    if prs:
        latest = max(prs, key=lambda p: p["updatedAt"])
        pr_number = latest["number"]
        pr_ts = _parse_ts(latest["updatedAt"])
        pr_state = latest["state"]

    return Evidence(
        repo=repo,
        latest_commit_sha=commit_sha,
        latest_commit_ts=commit_ts,
        latest_commit_message=commit_msg,
        latest_pr_number=pr_number,
        latest_pr_ts=pr_ts,
        latest_pr_state=pr_state,
        checked_at=checked_at,
    )
