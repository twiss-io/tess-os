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

{{agency_name}}: {{agency_offer}}

## Now
- {{today}}: created at onboarding. Replace with what is true now (dated, at most 10 lines).

## Where things are
| What | Where |
|---|---|
| Services | [services.md](services.md) |
| Pricing | [pricing.md](pricing.md) |
| Pipeline | [pipeline.md](pipeline.md) |
| Team | [team.md](team.md) |
| SOPs | [sops/](sops/) |
| People | [people/](people/) |
| Clients | `brain/clients/<slug>/` (listed in `brain/START-HERE.md`) |

## Rules for this entity
- Each client is isolated: work for one client never reads or quotes another client's folder unless the task names both.
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
