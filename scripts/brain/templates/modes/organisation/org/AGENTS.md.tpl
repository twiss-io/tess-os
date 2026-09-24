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

{{org_name}}: the organisation's operating map. Seats (who is accountable for what), units, people, clients, processes and the operating rhythm.

## Now
- {{today}}: created at onboarding. Replace with what is true now (dated, at most 10 lines).

## Where things are
| What | Where |
|---|---|
| Direction (why, where, what) | [direction.md](direction.md) |
| Seat chart | [seats/](seats/) |
| Units | [units/](units/) |
| People directory | [people/](people/) |
| Clients | [clients/](clients/) |
| Vendors | [vendors/](vendors/) |
| Processes | [processes/](processes/) |
| Policies | [policies/](policies/) |
| Scorecard | [metrics/scorecard.md](metrics/scorecard.md) |
| Quarterly priorities | [priorities/](priorities/) |
| Cadence (weekly leadership meeting) | [cadence/](cadence/) |
| Meetings and issues list | [meetings/](meetings/) |
| Onboarding | [onboarding/](onboarding/) |
| Knowledge base | [kb/](kb/) |

## Rules for this entity
- A seat has exactly one holder; decisions follow the seat's decision rights.
- People files hold work facts only: never pay, performance, health, family or government IDs.
- Other people's words are recorded as facts unless they are a principal in `brain/brain.json`.
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
