---
id: example-project
title: "Example Project — replace me"
state: ACTIVE
owner: unassigned
priority: P2
repo: your-org/your-repo
working_clone: "/absolute/path/to/your/local/clone (origin=your-org/your-repo, clean, on main)"
heartbeat:
  cadence: "session-driven, no fixed loop — resumes when someone picks up open PRs/issues"
  last_activity: "2026-01-01T00:00:00Z"
  activity_proof: "REPLACE ME: e.g. 'commit abc1234 on your-org/your-repo — verified via `gh api repos/your-org/your-repo/commits`.'"
  stall_after: "7 days with no commit to main and no PR movement"
stall:
  stalled: false
  reason: null
  since: null
next_move: "REPLACE ME: the single next action, specific enough that a fresh session could act on it without asking a clarifying question."
resume: |
  fresh clone from origin HEAD (your-org/your-repo) — never resume from a local copy that might be behind.
  1. Re-verify current state with a primary source (e.g. `gh pr list --repo your-org/your-repo --state open`), not this file's own memory of it.
  2. REPLACE ME: any other re-verification steps specific to this project.
gates:
  - "REPLACE ME: any pending external dependency, approval, or decision blocking this project (or delete this field if none)."
next_move_detail: "REPLACE ME: optional — the fuller version of next_move if it needs more than one line."
facts_last_verified: "2026-01-01T00:00:00Z"
---

# Example Project

This is a template card, not a live project — `scripts/heartbeat/run.py`
excludes files named `EXAMPLE.md`/`README.md` from its processing loop (see
`cards.py`'s `list_card_paths`), so this file is safe to leave in place as a
schema reference even after you've added your own real cards alongside it.

**Copy this file** to `memory/projects/<your-project-slug>.md`, fill in every
`REPLACE ME` above, and delete this body section (keep the frontmatter shape
exactly — every field the heartbeat reads or writes is listed in
`memory/README.md`'s schema reference).

## Field notes

- `id` must match the filename stem (`<slug>.md`).
- `state` is a free-text label — if your team already has a mission-state
  taxonomy, use those values; otherwise pick something consistent
  (ACTIVE / PAUSED / AWAITING DECISION / UNDER REVIEW / DONE work well).
- `stall.reason`, once set by the heartbeat's Tier-2 classifier, is always
  one of the fixed enum in `scripts/heartbeat/tier2_classify.py`'s
  `STALL_REASON_ENUM`: `awaiting-decision`, `blocked-external`,
  `attention-shift`, `error`, `frontier-reached`.
- Only six leaf fields are ever mechanically written by the heartbeat itself
  (`heartbeat.last_activity`, `heartbeat.activity_proof`, `stall.stalled`,
  `stall.reason`, `stall.since`, `facts_last_verified`) — everything else
  (`next_move`, `resume`, `gates`, this body) is yours to maintain by hand.
