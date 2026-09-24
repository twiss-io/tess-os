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

{{operator_name}}'s personal layer: areas of responsibility, active projects, resources, people and routines.

## Now
- {{today}}: created at onboarding. Replace with what is true now (dated, at most 10 lines).

## Where things are
| What | Where |
|---|---|
| Areas (ongoing) | [areas/](areas/) |
| Projects (with an end) | [projects/](projects/) |
| Resources | [resources/](resources/) |
| People | [people/](people/) |
| Routines | [routines.md](routines.md) |
| Archive | [archive/](archive/) |

## Rules for this entity
- A project has a goal, a done-when and a next action; an area has none of these and never ends.
- Health and money details live in `brain/.private/areas/<area>/` (local only); keep only pointers here.
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
