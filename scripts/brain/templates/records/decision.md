---
schema: 1
id: {{record_id}}
type: decision
title: {{title_q}}
status: pending-verification
tier: routine
authority: principal
decided_by: {{operator_slug_q}}
decider_seat: ""
entity: ""
consulted: []
informed: []
source_quote: {{quote_q}}
also_quoted: []
source_speaker: {{operator_slug_q}}
source_at: {{source_at_q}}
source_ref: "brain/brain.json#onboarding.answers"
source_session: {{source_session_q}}
approves_quote: ""
delegation_ref: ""
detected_by: onboarding
confirmed: false
verified: false
verified_at: ""
supersedes: ""
superseded_by: ""
body_sha256: ""
tags: [onboarding]
---
## Context
Recorded by onboarding from the operator's answer. It stays `pending-verification` until the quote is checked against the operator's own turn.

## Decision
We will run this brain as: {{modes_line}}. Preset: {{presets_line}}.

## Consequences
- Entity roots: {{entity_roots_line}}.
- The map is `brain/START-HERE.md`; each entity starts at its own `AGENTS.md`.
