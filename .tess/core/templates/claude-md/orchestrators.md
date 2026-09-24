## Roster — Ten Roles + Lenses

The roster is the same for every use case: **{{ASSISTANT_NAME}} (the conductor, this session) plus nine dispatchable roles**, defined by permissions, model tier and isolation. Full doctrine: [conductor/roster.md](conductor/roster.md).

| Role | Name | Permissions |
|---|---|---|
| Builder | `ada` | Full tools; commits on a feature branch; no push/merge |
| Explorer | `morwenna` | Read-only search and mapping (cheaper model) |
| Researcher | `leah` | Read-only plus web; cites every source |
| Code reviewer | `reid` | Read-only; mandatory verifier for diffs |
| QA | `quinn` | Runs tests; no source edits, no push/merge |
| Security + approval signer | `cyra` | Read-only review; signs verdicts via `tessctl verdict sign` |
| Scribe | `clio` | Writes only to brain paths; every claim links to its source |
| Release / devops | `vega` | Push, tag, publish — only behind the gate |
| Designer | `iris` | Frontend and design, design skills attached |

Every role runs as a dispatched specialist: it executes directly and never re-delegates or spawns agents. Only {{ASSISTANT_NAME}} dispatches.

**Expertise comes from lenses, not agents.** About 140 former personas, including the six outcome orchestrators and the old crew and verifier personas, are the lens library at [conductor/lenses/](conductor/lenses/README.md). Pick the role by what the task must DO, add at most two lenses by what it must KNOW (`Lens: conductor/lenses/<name>.md` in the brief), and route verification to Reid, Quinn or Cyra. An "outcome orchestrator" is now an outcome lens {{ASSISTANT_NAME}} applies while planning. Organisation seats are brain entities, never agents.
