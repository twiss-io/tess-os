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

Unit: {{name}}. What this unit owns and delivers (at most 3 lines).

## Now
- {{today}}: created at onboarding. Replace with what is true now (dated, at most 10 lines).

## Where things are
| What | Where |
|---|---|
| Seats in this unit | `brain/org/seats/` |
| Processes | `brain/org/processes/` |

## Rules for this entity
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
