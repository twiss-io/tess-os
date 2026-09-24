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

Private area: {{name}}. Only this pointer is committed; the details stay local.

## Now
- {{today}}: created at onboarding. Keep this section to non-sensitive status only.

## Where things are
| What | Where |
|---|---|
| Details (local only, never committed) | `brain/.private/areas/{{slug}}/` |

## Rules for this entity
- Never copy details from `brain/.private/` into this file or any committed file.
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
