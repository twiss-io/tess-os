---
name: Bug report
about: Report something that isn't working as documented
title: "[bug] "
labels: bug
assignees: ''
---

<!--
SECURITY: Do NOT use this template to report a vulnerability.
See SECURITY.md and report privately instead.
-->

## What happened

A clear, concise description of the bug.

## What you expected

What you expected to happen instead.

## Steps to reproduce

1. …
2. …
3. …

## Component

Which part of Tess OS is affected?

- [ ] `tessctl` engine (init / update / doctor / verify / lock)
- [ ] vault (`tessctl vault`)
- [ ] roster / recruit
- [ ] `create-tess` wizard (`npm create tess`)
- [ ] doctrine / guardrails / gates (`conductor/`)
- [ ] guard hooks (`.claude/hooks/`)
- [ ] docs
- [ ] other (describe)

## Environment

- Tess OS version / commit:
- OS:
- Python version (`python3 --version`):
- Node version (`node --version`), if `create-tess` is involved:

## Logs / output

```text
Paste relevant output here. REDACT any secrets, tokens, or client data first.
```

## Anything else

Additional context, screenshots, or notes.
