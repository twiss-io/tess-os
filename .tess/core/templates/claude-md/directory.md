## Directory Structure

```
tess/
├── CLAUDE.md              ← entry point (this file)
├── conductor/             ← {{ASSISTANT_NAME}}'s identity, doctrine, guardrails, commands
├── agents/                ← permanent and mission crew
├── kb/                    ← {{ASSISTANT_NAME}} internal knowledge base (Knowledge Base Framework)
│   ├── raw/               ← the operator writes here (articles, notes, inputs for ingestion)
│   ├── wiki/              ← {{ASSISTANT_NAME}}-maintained internal second brain (READ-ONLY to humans)
│   │   ├── index.md
│   │   ├── log.md         ← mission log
│   │   ├── concepts/
│   │   ├── missions/
│   │   ├── people/
│   │   └── synthesis/
│   └── lint/              ← lint pass logs
└── clients/               ← one folder per client (each is a mini operating system)
    ├── _template/         ← copy for new clients
    ├── ClientA/
    ├── ClientB/
    ├── ClientC/
    └── ClientD/
```

Each client folder is a mini operating system:

```
[client]/
├── CLAUDE.md          ← {{ASSISTANT_NAME}}'s operating brief for this client
├── admin/
│   ├── contracts/     ← signed agreements, SOWs, NDAs
│   ├── invoices/      ← billing records
│   └── notes/         ← meeting notes, call summaries
├── branding/
│   ├── current/       ← live, approved brand assets
│   ├── staging/       ← assets in review or pending approval
│   ├── archive/       ← superseded versions
│   └── ideation/      ← concepts, explorations, mood boards
├── dev.nosync/        ← code repos (excluded from cloud sync)
└── kb/                ← client knowledge base ({{ASSISTANT_NAME}}-maintained)
    ├── raw/           ← the operator and client write here
    ├── wiki/          ← {{ASSISTANT_NAME}} writes here — READ-ONLY to humans
    └── lint/          ← lint pass logs
```

**Knowledge Base Framework:** All client intelligence lives in the client's `kb/wiki/`. All internal {{ASSISTANT_NAME}} missions log to `kb/wiki/`. Wiki folders are maintained by {{ASSISTANT_NAME}} — never edited by humans directly.
