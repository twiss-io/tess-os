<!-- TESS OPERATOR STUB — real build/test/lint facts for THIS project
     Zone: {{OPERATOR_BUILD_FACTS}} in .tess/core/templates/agents-md/AGENTS.md.tpl
     inject: false   (when false, this zone renders to an empty string, so
     AGENTS.md carries zero fabricated build facts. Flip to true and run
     `tessctl render --target codex` / `--target generic` to surface this
     block for any single-agent harness reading AGENTS.md.)
     tessctl cannot know your build/test/lint commands — that is a fact
     about THIS project, not the framework. Fill in your own; do not leave
     the placeholder text below if you flip inject to true. -->
---
zone: OPERATOR_BUILD_FACTS
inject: false
---

- Build: `<your build command>`
- Test: `<your test command>`
- Lint: `<your lint command>`
