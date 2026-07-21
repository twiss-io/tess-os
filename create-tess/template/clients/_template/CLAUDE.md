# [Client Name] — Tess Client Operating File

**Status:** [Active / Onboarding / Paused]
**Client since:** [Date]
**Primary contact:** [Name, role]
**Industry:** [Industry]
**Stage:** [Stage of business]

---

## Who This Client Is

[1-2 paragraph description of the client, their business, what they do, and why they're working with the operator/Tess.]

---

## What Tess Does For This Client

[Description of Tess's role with this client — mission types, outcomes being pursued.]

---

## Operating Conventions

- **Primary orchestrator for most missions:** [Orchestrator name]
- **Known sensitivities:** [Anything Tess should know about handling this client's context]
- **Communication style:** [How the client prefers to receive outputs]
- **Key constraints:** [Budget, timeline, regulatory, or other constraints]

---

## Active Priorities

[Current strategic priorities or live missions for this client.]

---

## Folder Structure

```
[client-name]/
├── CLAUDE.md          ← this file — Tess's operating brief for this client
├── admin/
│   ├── contracts/     ← signed agreements, SOWs, NDAs
│   ├── invoices/      ← billing records
│   └── notes/         ← meeting notes, call summaries
├── branding/
│   ├── current/       ← live, approved brand assets
│   ├── staging/       ← assets in review or pending approval
│   ├── archive/       ← superseded versions
│   └── ideation/      ← concepts, explorations, mood boards
├── dev.nosync/        ← GitHub repos (excluded from cloud sync)
│   └── [repo-name]/
└── kb/                ← the agency Knowledge Base (Tess-maintained)
    ├── raw/           ← the operator and client write here
    │   ├── briefs/
    │   ├── documents/
    │   └── notes/
    ├── wiki/          ← Tess writes here — READ-ONLY to humans
    │   ├── index.md
    │   ├── log.md
    │   ├── concepts/
    │   ├── missions/
    │   ├── people/
    │   └── synthesis/
    ├── research/      ← all web research outputs (YYYY-MM-DD-<slug>.md)
    └── lint/
        └── lint-log.md
```

---

## Knowledge Base Commands

**Ingest new material:** Drop files in kb/raw/ and tell Tess: "Ingest new sources for [Client Name]."
**Lint pass:** Tell Tess: "Run a lint pass on [Client Name]'s wiki."
**Research output:** All web research for this client goes to kb/research/ — filename format: YYYY-MM-DD-<kebab-slug>.md. No exceptions.

---

## Mission Log

[kb/wiki/log.md](kb/wiki/log.md)
