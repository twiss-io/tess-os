---
name: tess-close
description: "Session end checklist — confirm mission state, flag open decisions for the operator, log session work to the wiki, and commit + push uncommitted changes."
---

<!-- Rendered by `tessctl render --target codex` from .tess/core/commands/close.md. Regenerate; do not hand-edit. -->

Tess OS command `/close`, packaged as an Agent Skill. Run it only when the user asks for it by name (`$tess-close` in Codex).

# /close

Run the session-end checklist from [conductor/daily-operating-behavior.md](../../../conductor/daily-operating-behavior.md):

1. **Confirm mission state** — in-progress, blocked, or completed ([conductor/mission-states.md](../../../conductor/mission-states.md)).
2. **Flag open decisions** that need the operator's input.
3. **Log session work** to `kb/wiki/log.md` and any relevant `kb/wiki/missions/` entry — wiki is Tess-maintained, never edited by humans (Knowledge Base Framework).
4. **Commit + push** any uncommitted changes (commit means commit *and* push; never local-only). Verify no secrets per [conductor/guardrails.md](../../../conductor/guardrails.md).
5. **Give the operator a closing summary** in the active session.

**Output:** session summary, open items, wiki-log confirmation, git-push confirmation.
