---
description: Capture and apply feedback to the system — refine orchestration, output, crew, or tone based on the operator's input.
argument-hint: [feedback]
---

# /feedback

Apply this feedback to the system: **$ARGUMENTS**

1. **Classify** the feedback — orchestration, output quality, crew, tone, or doctrine.
2. **Apply it** for the session immediately.
3. **Persist it** if it should outlast the session: update the relevant doctrine file under [conductor/](../../conductor/README.md) (sync doctrine on changes) and/or record a memory note. Commit + push doctrine changes and log to `kb/wiki/`.

Radical honesty applies — if the feedback conflicts with a guardrail or system law, surface the tension rather than silently overriding. Structural doctrine changes that affect safety gate on the operator's explicit confirmation.
