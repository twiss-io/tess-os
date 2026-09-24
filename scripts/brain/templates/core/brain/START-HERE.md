---
schema: 1
type: start-here
---
# START HERE: {{operator_name}}'s brain

The map of this second brain. Read it first, then open the entity you need: every entity folder has an `AGENTS.md` that starts with START HERE. Rules for the brain: [README.md](README.md) (when present). Config and onboarding state: [brain.json](brain.json).

- Mode: {{modes_line}}. Preset: {{presets_line}}.
- Operator: {{operator_name}} (address as {{address_as}}). Assistant: {{assistant_name}}. Timezone: {{timezone}}.
- Principals (their words count as decisions, within their scope in brain.json): {{principals_line}}.
- Journal policy: {{journal}}. Private, never committed: `brain/.private/`.

## Where things go
| What | Where |
|---|---|
| Research | `brain/kb/research/YYYY-MM-DD-<slug>.md`; research for one entity goes in that entity's `kb/research/` |
| Human-supplied source material | `brain/kb/raw/` (humans write here; agents read only) |
| Decisions | `brain/decisions/D-YYYYMMDD-HHMM-<slug>.md`, or the owning entity's `decisions/` |
| Preferences and corrections | `brain/profile/` (summary: [profile.md](profile.md)) |
| Facts | the owning entity's `facts/`, or `brain/facts/` |
| Open loops | `brain/loops/` (summary: [open-loops.md](open-loops.md)) |
| Conversation journal | `brain/journal/YYYY/MM/DD/` (one file per session) |
| What the brain learned | [learned.md](learned.md) |
| Project state cards | `memory/projects/<entity>--<slug>.md` |
| Anything private | `brain/.private/` (local only) |

## Entities
Open the entity's START HERE before answering about it.

| Entity | Kind | Start here |
|---|---|---|

### Entity detail (generated)
<!-- tess:gen:entities:start -->
<!-- tess:gen:entities:end -->

## Recent decisions
<!-- tess:gen:recent-decisions:start -->
<!-- tess:gen:recent-decisions:end -->

## Open loops
<!-- tess:gen:open-loops:start -->
<!-- tess:gen:open-loops:end -->

## Health
<!-- tess:gen:health:start -->
<!-- tess:gen:health:end -->
