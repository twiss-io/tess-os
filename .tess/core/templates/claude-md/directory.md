## Directory Structure

```
tess/
├── CLAUDE.md              ← entry point (this file; Claude Code)
├── AGENTS.md              ← entry point for AGENTS.md-reading runtimes (rendered; never hand-edit)
├── conductor/             ← {{ASSISTANT_NAME}}'s identity, doctrine, guardrails, commands
├── agents/                ← permanent and mission crew
├── memory/                ← open-projects registry: projects/<slug>.md cards + registry.md
├── kb/                    ← {{ASSISTANT_NAME}} internal knowledge base (Knowledge Base Framework)
│   ├── raw/               ← the operator writes here (articles, notes, inputs for ingestion)
│   ├── research/          ← dated research outputs (YAML frontmatter required)
│   ├── wiki/              ← {{ASSISTANT_NAME}}-maintained internal second brain (READ-ONLY to humans)
│   │   ├── index.md
│   │   ├── log.md         ← mission log
│   │   ├── concepts/
│   │   ├── missions/
│   │   ├── people/
│   │   ├── synthesis/
│   │   └── archive/       ← superseded but still-cited docs (created on first use)
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
    ├── research/      ← dated research outputs (YAML frontmatter required)
    ├── wiki/          ← {{ASSISTANT_NAME}} writes here — READ-ONLY to humans
    └── lint/          ← lint pass logs
```

**Knowledge Base Framework:** All client intelligence lives in the client's `kb/wiki/`. All internal {{ASSISTANT_NAME}} missions log to `kb/wiki/`. Wiki folders are maintained by {{ASSISTANT_NAME}} — never edited by humans directly.

### File Placement Contract

The tree above says what exists. This says where new files go. It binds {{ASSISTANT_NAME}}, every dispatched subagent, and every other runtime working in this project.

`<kb>` = `clients/<Client>/kb/` for client work, `kb/` for internal {{ASSISTANT_NAME}} work.

| What you are writing | Where it goes |
|---|---|
| Research output | `<kb>/research/YYYY-MM-DD-<kebab-slug>.md` with YAML frontmatter (`tags`, `date`, `sources_used`, `confidence`) |
| Mission record / final synthesis | `<kb>/wiki/missions/YYYY-MM-DD-<name>.md` |
| Cross-mission pattern, spec, HTML deliverable | `<kb>/wiki/synthesis/YYYY-MM-DD-<name>.{md,html}` |
| Session / continuity handover | `<kb>/wiki/missions/YYYY-MM-DD-session-handoff[-slug].md` |
| Superseded but still-cited document | `<kb>/wiki/archive/YYYY-MM-DD-<name>.md` |
| Open-project state card | `memory/projects/<slug>.md` (compiled into `memory/registry.md`; schema in `memory/README.md`) |
| Code, config or framework change in a repository | the repository path and branch the brief names; the deliverable is a commit or pull request, not a new document |
| Doctrine addition by the operator | `conductor/<file>.local.md`, appended to the rendered file and kept by `tessctl update` (never folded into a security-tier file) |
| Throwaway scratch, interim per-agent artifact | the session scratchpad the runtime supplies, **never inside the repo** |
| Operator- or client-supplied source material | `<kb>/raw/`: **agents never write here; humans only** |

**The repo root is closed.** Never create a new file at the repo root. The root holds only what the install ships (the entry points, `tess.manifest.json`, `tessctl`, and the package and tooling files) plus the root-level paths that `tess.manifest.json` names in `owned_globs` or `never_touch`. Anything else at the root is a misplacement, including handovers, specs, reports, exports and backups.

**Never default to the working directory.** A brief that names no destination, and fits no row above, is incomplete: stop and ask.

**Placed is not the same as committed.** `kb/**` and every client folder under `clients/` except `clients/_template/` are private overlay data (see `docs/DATA_LEAK_SAFETY.md`). They are gitignored, and the publish-clean pre-commit guard blocks them. Never commit them to a shared or public remote. Never force them in with `git add -f`, and never use `git commit --no-verify` to get past the guard (that also skips the secret scan). An operator who backs up the overlay does so outside this repository's git history, in a private store they control.
