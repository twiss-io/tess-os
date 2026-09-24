---
schema: 1
type: entity
kind: {{kind}}
id: {{id_q}}
name: {{name_q}}
status: active
owner: {{operator_slug_q}}
privacy: {{privacy}}
created: {{today}}
last_verified: {{today}}
verify_via: operator
---
# START HERE: {{name}}

Client: {{name}}. What we do for them and why it matters to them (at most 3 lines).

## Now
- {{today}}: created at onboarding. Replace with what is true now (dated, at most 10 lines).

## Where things are
| What | Where |
|---|---|
| Contacts | [contacts.md](contacts.md) |
| Code repositories (pointers) | [repos.md](repos.md) |
| Projects | [projects/](projects/) |
| Meetings | [meetings/](meetings/) |
| Research | [kb/research/](kb/research/) |
| Wiki | [kb/wiki/](kb/wiki/) |
| Source material (humans only) | [kb/raw/](kb/raw/) |
| Brand assets | [brand/current/](brand/current/) |
| Contracts, SOWs, invoices (pointers only) | [admin/README.md](admin/README.md) |

## Rules for this entity
- Client data stays in this folder: never carry it into another client's output.
- Only this client's owner and the operator decide here (see principals in `brain/brain.json`).
- Record decisions with the principal's exact words (skill brain-decide); never a paraphrase, a question or your own suggestion.
- Secrets, government IDs, pay, health or HR records and contract files never go here: write a pointer to where they live.

## Decisions (latest 5 accepted)
<!-- tess:gen:decisions:start -->
<!-- tess:gen:decisions:end -->

## Open loops
<!-- tess:gen:loops:start -->
<!-- tess:gen:loops:end -->

## Facts (verified)
<!-- tess:gen:facts:start -->
<!-- tess:gen:facts:end -->

## State cards
<!-- tess:gen:cards:start -->
<!-- tess:gen:cards:end -->
