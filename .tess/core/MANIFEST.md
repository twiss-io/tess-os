# Tess OS Core — MANIFEST

> Index of every framework-owned (`status: core-managed`) file in `.tess/core/`
> and its expected **live path** (the resolved location Claude reads).
> `.tess/core/` is the PRISTINE source; the live tree is the resolved output.
> Authoritative classification lives in `.tess/tess.lock` (per-file `status`/`tier`/`base_sha`).

- Total core files: **954**
- Security-tier files: **3** (`conductor/guardrails.md`, `conductor/verification-routing.md`, `conductor/channel-guardrails.md`)

## Live-path mapping (by core subtree)

| Core subtree | Live destination |
|---|---|
| `.tess/core/conductor/**` | `conductor/**` |
| `.tess/core/agents/**` | `agents/**` |
| `.tess/core/agents-dispatch/*.md` | `.claude/agents/*.md` |
| `.tess/core/hooks/*` | `.claude/hooks/*` ({{TESS_ROOT}} substituted) |
| `.tess/core/skills/**` | `.claude/skills/**` |
| `.tess/core/settings-core.json` | `.claude/settings.json` (rendered) |
| `.tess/core/templates/CLAUDE.md.tpl` | `CLAUDE.md` (rendered + operator/ stubs) |
| `.tess/core/templates/claude-md/*.md` | `CLAUDE.md` (composed fragments) |
| `.tess/core/templates/client/_template/**` | `clients/_template/**` |
| `.tess/core/MANIFEST.md` | — (core index, not a live doctrine path) |

## conductor/ — doctrine

| Core file | Live path | Tier |
|---|---|---|
| `conductor/README.md` | `conductor/README.md` | normal |
| `conductor/agent-lifecycle.md` | `conductor/agent-lifecycle.md` | normal |
| `conductor/channel-guardrails.md` | `conductor/channel-guardrails.md` | security |
| `conductor/commands.md` | `conductor/commands.md` | normal |
| `conductor/cross-guild-coordination.md` | `conductor/cross-guild-coordination.md` | normal |
| `conductor/daily-operating-behavior.md` | `conductor/daily-operating-behavior.md` | normal |
| `conductor/dispatch-brief.md` | `conductor/dispatch-brief.md` | normal |
| `conductor/doctrine.md` | `conductor/doctrine.md` | normal |
| `conductor/founders-office.md` | `conductor/founders-office.md` | normal |
| `conductor/guardrails.md` | `conductor/guardrails.md` | security |
| `conductor/hook-testing-protocol.md` | `conductor/hook-testing-protocol.md` | normal |
| `conductor/identity.md` | `conductor/identity.md` | normal |
| `conductor/memory-model.md` | `conductor/memory-model.md` | normal |
| `conductor/mission-control.md` | `conductor/mission-control.md` | normal |
| `conductor/mission-states.md` | `conductor/mission-states.md` | normal |
| `conductor/orchestra-model.md` | `conductor/orchestra-model.md` | normal |
| `conductor/outcome-orchestrators/README.md` | `conductor/outcome-orchestrators/README.md` | normal |
| `conductor/outcome-orchestrators/client-experience-orchestrator.md` | `conductor/outcome-orchestrators/client-experience-orchestrator.md` | normal |
| `conductor/outcome-orchestrators/founders-office-orchestrator.md` | `conductor/outcome-orchestrators/founders-office-orchestrator.md` | normal |
| `conductor/outcome-orchestrators/integration.md` | `conductor/outcome-orchestrators/integration.md` | normal |
| `conductor/outcome-orchestrators/operational-reliability-orchestrator.md` | `conductor/outcome-orchestrators/operational-reliability-orchestrator.md` | normal |
| `conductor/outcome-orchestrators/product-delivery-orchestrator.md` | `conductor/outcome-orchestrators/product-delivery-orchestrator.md` | normal |
| `conductor/outcome-orchestrators/revenue-orchestrator.md` | `conductor/outcome-orchestrators/revenue-orchestrator.md` | normal |
| `conductor/outcome-orchestrators/strategic-growth-orchestrator.md` | `conductor/outcome-orchestrators/strategic-growth-orchestrator.md` | normal |
| `conductor/output-framework.md` | `conductor/output-framework.md` | normal |
| `conductor/personality.md` | `conductor/personality.md` | normal |
| `conductor/playbooks/README.md` | `conductor/playbooks/README.md` | normal |
| `conductor/playbooks/event-launch-orchestration.md` | `conductor/playbooks/event-launch-orchestration.md` | normal |
| `conductor/playbooks/founder-decision-memo.md` | `conductor/playbooks/founder-decision-memo.md` | normal |
| `conductor/playbooks/investor-fundraising-prep.md` | `conductor/playbooks/investor-fundraising-prep.md` | normal |
| `conductor/playbooks/l99-merge-discipline.md` | `conductor/playbooks/l99-merge-discipline.md` | normal |
| `conductor/playbooks/product-build-mission.md` | `conductor/playbooks/product-build-mission.md` | normal |
| `conductor/playbooks/revenue-diagnosis.md` | `conductor/playbooks/revenue-diagnosis.md` | normal |
| `conductor/review-output-standards.md` | `conductor/review-output-standards.md` | normal |
| `conductor/soul.md` | `conductor/soul.md` | normal |
| `conductor/subagent-failure-protocol.md` | `conductor/subagent-failure-protocol.md` | normal |
| `conductor/user-profile.md` | `conductor/user-profile.md` | normal |
| `conductor/verification-routing.md` | `conductor/verification-routing.md` | security |

## agents/ — persona prose specs

736 files across 165 persona directories, each mapping `.tess/core/agents/<name>/** -> agents/<name>/**` (tier: normal).

Personas: README.md, ada, adrienne, alessia, alina, alouette, amandine, amara, anais, apolline, arielle, athena, aurora, aveline, beatrice, berenice, bettina, bianca, brand-guild.md, briony, callista, camille, cecily, celeste, celine, cerise, clara, clarisse, clio, coding-team.md, colette, coralie, corinne, corisande, cosima, creative-design-guild.md, cressida, cx-client-success-guild.md, cyra, danica, daphne, data-analytics-guild.md, delphine, domitille, elara, elena, elodie, eloise, elspeth, emmeline, estelle, eulalie, eva, evangeline, evelina, events-stagecraft-guild.md, finance-investor-guild.md, fiorella, fleur, floriane, freya, gaiane, genevieve, gia, growth-governance.md, growth-guild.md, helena, hesper, ilaria, imogen, intelligence-staffing.md, iris, isadora, iseult, isolde, jessamine, josephine, jovienne, juliette, lavinia, leah, legal-risk-guild.md, leonora, linnea, liora, livia, lucasta, lucienne, lysandra, madeleine, maelle, maialen, marcelline, margot, marina, mariselle, melisande, mira, mireille, mireya, morwenna, nadia, naomi, nerissa, noelle, noemi, nova, octavia, odette, ondine, opaline, ops-guild.md, oriana, orielle, ottilie, paloma, people-talent-guild.md, petra, procurement-vendor-guild.md, product-guild.md, queniva, quinn, reid, renee, research-knowledge-guild.md, romilly, rosalie, rowena, roxane, sabella, sabine, sales-bd-guild.md, selene, seraphine, sienna, simone, sofia, soraya, strategy-governance.md, strategy-guild.md, talia, tamsin, tatienne, thais, thea, theodora, transactions-ma-guild.md, valeria, valina, vega, verena, verity, vespera, victoria, violette, virelai, vivienne, xanthe, yselle, yvette, zara, zelie, zephirine, zinnia, zorine

## agents-dispatch/ — compiled .claude/agents/*.md dispatch defs

| Core file | Live path | Tier |
|---|---|---|
| `agents-dispatch/ada.md` | `.claude/agents/ada.md` | normal |
| `agents-dispatch/adrienne.md` | `.claude/agents/adrienne.md` | normal |
| `agents-dispatch/alessia.md` | `.claude/agents/alessia.md` | normal |
| `agents-dispatch/alina.md` | `.claude/agents/alina.md` | normal |
| `agents-dispatch/alouette.md` | `.claude/agents/alouette.md` | normal |
| `agents-dispatch/amandine.md` | `.claude/agents/amandine.md` | normal |
| `agents-dispatch/amara.md` | `.claude/agents/amara.md` | normal |
| `agents-dispatch/anais.md` | `.claude/agents/anais.md` | normal |
| `agents-dispatch/apolline.md` | `.claude/agents/apolline.md` | normal |
| `agents-dispatch/arielle.md` | `.claude/agents/arielle.md` | normal |
| `agents-dispatch/athena.md` | `.claude/agents/athena.md` | normal |
| `agents-dispatch/aurora.md` | `.claude/agents/aurora.md` | normal |
| `agents-dispatch/aveline.md` | `.claude/agents/aveline.md` | normal |
| `agents-dispatch/beatrice.md` | `.claude/agents/beatrice.md` | normal |
| `agents-dispatch/berenice.md` | `.claude/agents/berenice.md` | normal |
| `agents-dispatch/bettina.md` | `.claude/agents/bettina.md` | normal |
| `agents-dispatch/bianca.md` | `.claude/agents/bianca.md` | normal |
| `agents-dispatch/briony.md` | `.claude/agents/briony.md` | normal |
| `agents-dispatch/callista.md` | `.claude/agents/callista.md` | normal |
| `agents-dispatch/camille.md` | `.claude/agents/camille.md` | normal |
| `agents-dispatch/cecily.md` | `.claude/agents/cecily.md` | normal |
| `agents-dispatch/celeste.md` | `.claude/agents/celeste.md` | normal |
| `agents-dispatch/celine.md` | `.claude/agents/celine.md` | normal |
| `agents-dispatch/cerise.md` | `.claude/agents/cerise.md` | normal |
| `agents-dispatch/clara.md` | `.claude/agents/clara.md` | normal |
| `agents-dispatch/clarisse.md` | `.claude/agents/clarisse.md` | normal |
| `agents-dispatch/client-experience-orchestrator.md` | `.claude/agents/client-experience-orchestrator.md` | normal |
| `agents-dispatch/clio.md` | `.claude/agents/clio.md` | normal |
| `agents-dispatch/colette.md` | `.claude/agents/colette.md` | normal |
| `agents-dispatch/coralie.md` | `.claude/agents/coralie.md` | normal |
| `agents-dispatch/corinne.md` | `.claude/agents/corinne.md` | normal |
| `agents-dispatch/corisande.md` | `.claude/agents/corisande.md` | normal |
| `agents-dispatch/cosima.md` | `.claude/agents/cosima.md` | normal |
| `agents-dispatch/cressida.md` | `.claude/agents/cressida.md` | normal |
| `agents-dispatch/cyra.md` | `.claude/agents/cyra.md` | normal |
| `agents-dispatch/danica.md` | `.claude/agents/danica.md` | normal |
| `agents-dispatch/daphne.md` | `.claude/agents/daphne.md` | normal |
| `agents-dispatch/delphine.md` | `.claude/agents/delphine.md` | normal |
| `agents-dispatch/domitille.md` | `.claude/agents/domitille.md` | normal |
| `agents-dispatch/elara.md` | `.claude/agents/elara.md` | normal |
| `agents-dispatch/elena.md` | `.claude/agents/elena.md` | normal |
| `agents-dispatch/elodie.md` | `.claude/agents/elodie.md` | normal |
| `agents-dispatch/eloise.md` | `.claude/agents/eloise.md` | normal |
| `agents-dispatch/elspeth.md` | `.claude/agents/elspeth.md` | normal |
| `agents-dispatch/emmeline.md` | `.claude/agents/emmeline.md` | normal |
| `agents-dispatch/estelle.md` | `.claude/agents/estelle.md` | normal |
| `agents-dispatch/eulalie.md` | `.claude/agents/eulalie.md` | normal |
| `agents-dispatch/eva.md` | `.claude/agents/eva.md` | normal |
| `agents-dispatch/evangeline.md` | `.claude/agents/evangeline.md` | normal |
| `agents-dispatch/evelina.md` | `.claude/agents/evelina.md` | normal |
| `agents-dispatch/fiorella.md` | `.claude/agents/fiorella.md` | normal |
| `agents-dispatch/fleur.md` | `.claude/agents/fleur.md` | normal |
| `agents-dispatch/floriane.md` | `.claude/agents/floriane.md` | normal |
| `agents-dispatch/founders-office-orchestrator.md` | `.claude/agents/founders-office-orchestrator.md` | normal |
| `agents-dispatch/freya.md` | `.claude/agents/freya.md` | normal |
| `agents-dispatch/gaiane.md` | `.claude/agents/gaiane.md` | normal |
| `agents-dispatch/genevieve.md` | `.claude/agents/genevieve.md` | normal |
| `agents-dispatch/gia.md` | `.claude/agents/gia.md` | normal |
| `agents-dispatch/helena.md` | `.claude/agents/helena.md` | normal |
| `agents-dispatch/hesper.md` | `.claude/agents/hesper.md` | normal |
| `agents-dispatch/ilaria.md` | `.claude/agents/ilaria.md` | normal |
| `agents-dispatch/imogen.md` | `.claude/agents/imogen.md` | normal |
| `agents-dispatch/iris.md` | `.claude/agents/iris.md` | normal |
| `agents-dispatch/isadora.md` | `.claude/agents/isadora.md` | normal |
| `agents-dispatch/iseult.md` | `.claude/agents/iseult.md` | normal |
| `agents-dispatch/isolde.md` | `.claude/agents/isolde.md` | normal |
| `agents-dispatch/jessamine.md` | `.claude/agents/jessamine.md` | normal |
| `agents-dispatch/josephine.md` | `.claude/agents/josephine.md` | normal |
| `agents-dispatch/jovienne.md` | `.claude/agents/jovienne.md` | normal |
| `agents-dispatch/juliette.md` | `.claude/agents/juliette.md` | normal |
| `agents-dispatch/lavinia.md` | `.claude/agents/lavinia.md` | normal |
| `agents-dispatch/leah.md` | `.claude/agents/leah.md` | normal |
| `agents-dispatch/leonora.md` | `.claude/agents/leonora.md` | normal |
| `agents-dispatch/linnea.md` | `.claude/agents/linnea.md` | normal |
| `agents-dispatch/liora.md` | `.claude/agents/liora.md` | normal |
| `agents-dispatch/livia.md` | `.claude/agents/livia.md` | normal |
| `agents-dispatch/lucasta.md` | `.claude/agents/lucasta.md` | normal |
| `agents-dispatch/lucienne.md` | `.claude/agents/lucienne.md` | normal |
| `agents-dispatch/lysandra.md` | `.claude/agents/lysandra.md` | normal |
| `agents-dispatch/madeleine.md` | `.claude/agents/madeleine.md` | normal |
| `agents-dispatch/maelle.md` | `.claude/agents/maelle.md` | normal |
| `agents-dispatch/maialen.md` | `.claude/agents/maialen.md` | normal |
| `agents-dispatch/marcelline.md` | `.claude/agents/marcelline.md` | normal |
| `agents-dispatch/margot.md` | `.claude/agents/margot.md` | normal |
| `agents-dispatch/marina.md` | `.claude/agents/marina.md` | normal |
| `agents-dispatch/mariselle.md` | `.claude/agents/mariselle.md` | normal |
| `agents-dispatch/melisande.md` | `.claude/agents/melisande.md` | normal |
| `agents-dispatch/mira.md` | `.claude/agents/mira.md` | normal |
| `agents-dispatch/mireille.md` | `.claude/agents/mireille.md` | normal |
| `agents-dispatch/mireya.md` | `.claude/agents/mireya.md` | normal |
| `agents-dispatch/morwenna.md` | `.claude/agents/morwenna.md` | normal |
| `agents-dispatch/nadia.md` | `.claude/agents/nadia.md` | normal |
| `agents-dispatch/naomi.md` | `.claude/agents/naomi.md` | normal |
| `agents-dispatch/nerissa.md` | `.claude/agents/nerissa.md` | normal |
| `agents-dispatch/noelle.md` | `.claude/agents/noelle.md` | normal |
| `agents-dispatch/noemi.md` | `.claude/agents/noemi.md` | normal |
| `agents-dispatch/nova.md` | `.claude/agents/nova.md` | normal |
| `agents-dispatch/octavia.md` | `.claude/agents/octavia.md` | normal |
| `agents-dispatch/odette.md` | `.claude/agents/odette.md` | normal |
| `agents-dispatch/ondine.md` | `.claude/agents/ondine.md` | normal |
| `agents-dispatch/opaline.md` | `.claude/agents/opaline.md` | normal |
| `agents-dispatch/operational-reliability-orchestrator.md` | `.claude/agents/operational-reliability-orchestrator.md` | normal |
| `agents-dispatch/oriana.md` | `.claude/agents/oriana.md` | normal |
| `agents-dispatch/orielle.md` | `.claude/agents/orielle.md` | normal |
| `agents-dispatch/ottilie.md` | `.claude/agents/ottilie.md` | normal |
| `agents-dispatch/paloma.md` | `.claude/agents/paloma.md` | normal |
| `agents-dispatch/petra.md` | `.claude/agents/petra.md` | normal |
| `agents-dispatch/product-delivery-orchestrator.md` | `.claude/agents/product-delivery-orchestrator.md` | normal |
| `agents-dispatch/queniva.md` | `.claude/agents/queniva.md` | normal |
| `agents-dispatch/quinn.md` | `.claude/agents/quinn.md` | normal |
| `agents-dispatch/reid.md` | `.claude/agents/reid.md` | normal |
| `agents-dispatch/renee.md` | `.claude/agents/renee.md` | normal |
| `agents-dispatch/revenue-orchestrator.md` | `.claude/agents/revenue-orchestrator.md` | normal |
| `agents-dispatch/romilly.md` | `.claude/agents/romilly.md` | normal |
| `agents-dispatch/rosalie.md` | `.claude/agents/rosalie.md` | normal |
| `agents-dispatch/rowena.md` | `.claude/agents/rowena.md` | normal |
| `agents-dispatch/roxane.md` | `.claude/agents/roxane.md` | normal |
| `agents-dispatch/sabella.md` | `.claude/agents/sabella.md` | normal |
| `agents-dispatch/sabine.md` | `.claude/agents/sabine.md` | normal |
| `agents-dispatch/selene.md` | `.claude/agents/selene.md` | normal |
| `agents-dispatch/seraphine.md` | `.claude/agents/seraphine.md` | normal |
| `agents-dispatch/sienna.md` | `.claude/agents/sienna.md` | normal |
| `agents-dispatch/simone.md` | `.claude/agents/simone.md` | normal |
| `agents-dispatch/sofia.md` | `.claude/agents/sofia.md` | normal |
| `agents-dispatch/soraya.md` | `.claude/agents/soraya.md` | normal |
| `agents-dispatch/strategic-growth-orchestrator.md` | `.claude/agents/strategic-growth-orchestrator.md` | normal |
| `agents-dispatch/talia.md` | `.claude/agents/talia.md` | normal |
| `agents-dispatch/tamsin.md` | `.claude/agents/tamsin.md` | normal |
| `agents-dispatch/tatienne.md` | `.claude/agents/tatienne.md` | normal |
| `agents-dispatch/thais.md` | `.claude/agents/thais.md` | normal |
| `agents-dispatch/thea.md` | `.claude/agents/thea.md` | normal |
| `agents-dispatch/theodora.md` | `.claude/agents/theodora.md` | normal |
| `agents-dispatch/valeria.md` | `.claude/agents/valeria.md` | normal |
| `agents-dispatch/valina.md` | `.claude/agents/valina.md` | normal |
| `agents-dispatch/vega.md` | `.claude/agents/vega.md` | normal |
| `agents-dispatch/verena.md` | `.claude/agents/verena.md` | normal |
| `agents-dispatch/verity.md` | `.claude/agents/verity.md` | normal |
| `agents-dispatch/vespera.md` | `.claude/agents/vespera.md` | normal |
| `agents-dispatch/victoria.md` | `.claude/agents/victoria.md` | normal |
| `agents-dispatch/violette.md` | `.claude/agents/violette.md` | normal |
| `agents-dispatch/virelai.md` | `.claude/agents/virelai.md` | normal |
| `agents-dispatch/vivienne.md` | `.claude/agents/vivienne.md` | normal |
| `agents-dispatch/xanthe.md` | `.claude/agents/xanthe.md` | normal |
| `agents-dispatch/yselle.md` | `.claude/agents/yselle.md` | normal |
| `agents-dispatch/yvette.md` | `.claude/agents/yvette.md` | normal |
| `agents-dispatch/zara.md` | `.claude/agents/zara.md` | normal |
| `agents-dispatch/zelie.md` | `.claude/agents/zelie.md` | normal |
| `agents-dispatch/zephirine.md` | `.claude/agents/zephirine.md` | normal |
| `agents-dispatch/zinnia.md` | `.claude/agents/zinnia.md` | normal |
| `agents-dispatch/zorine.md` | `.claude/agents/zorine.md` | normal |

## hooks/ — guard hooks ({{TESS_ROOT}}-tokenised)

| Core file | Live path | Tier |
|---|---|---|
| `hooks/anti-fabrication-guard.sh` | `.claude/hooks/anti-fabrication-guard.sh` | normal |
| `hooks/dispatch-guard.sh` | `.claude/hooks/dispatch-guard.sh` | normal |
| `hooks/task-lock-clear.sh` | `.claude/hooks/task-lock-clear.sh` | normal |
| `hooks/task-lock-set.sh` | `.claude/hooks/task-lock-set.sh` | normal |
| `hooks/telegram-format-guard.sh` | `.claude/hooks/telegram-format-guard.sh` | normal |
| `hooks/utc-local-context.sh` | `.claude/hooks/utc-local-context.sh` | normal |

## skills/ — framework skills

| Core file | Live path | Tier |
|---|---|---|
| `skills/3d-web-experience/SKILL.md` | `.claude/skills/3d-web-experience/SKILL.md` | normal |
| `skills/browser-use/SKILL.md` | `.claude/skills/browser-use/SKILL.md` | normal |
| `skills/browser-use/references/cdp-python.md` | `.claude/skills/browser-use/references/cdp-python.md` | normal |
| `skills/browser-use/references/multi-session.md` | `.claude/skills/browser-use/references/multi-session.md` | normal |
| `skills/design-taste-frontend/SKILL.md` | `.claude/skills/design-taste-frontend/SKILL.md` | normal |
| `skills/full-output-enforcement/SKILL.md` | `.claude/skills/full-output-enforcement/SKILL.md` | normal |
| `skills/high-end-visual-design/SKILL.md` | `.claude/skills/high-end-visual-design/SKILL.md` | normal |
| `skills/industrial-brutalist-ui/SKILL.md` | `.claude/skills/industrial-brutalist-ui/SKILL.md` | normal |
| `skills/minimalist-ui/SKILL.md` | `.claude/skills/minimalist-ui/SKILL.md` | normal |
| `skills/redesign-existing-projects/SKILL.md` | `.claude/skills/redesign-existing-projects/SKILL.md` | normal |

## templates/ — entry-point template, fragments, client scaffold

| Core file | Live path | Tier |
|---|---|---|
| `templates/CLAUDE.md.tpl` | `CLAUDE.md` | normal |
| `templates/claude-md/commands.md` | `CLAUDE.md` | normal |
| `templates/claude-md/directory.md` | `CLAUDE.md` | normal |
| `templates/claude-md/orchestrators.md` | `CLAUDE.md` | normal |
| `templates/claude-md/rule-zero.md` | `CLAUDE.md` | normal |
| `templates/claude-md/system-laws.md` | `CLAUDE.md` | normal |
| `templates/client/_template/CLAUDE.md` | `clients/_template/CLAUDE.md` | normal |
| `templates/client/_template/branding/DESIGN.md` | `clients/_template/branding/DESIGN.md` | normal |
| `templates/client/_template/kb/lint/lint-log.md` | `clients/_template/kb/lint/lint-log.md` | normal |
| `templates/client/_template/kb/research/.gitkeep` | `clients/_template/kb/research/.gitkeep` | normal |
| `templates/client/_template/kb/wiki/index.md` | `clients/_template/kb/wiki/index.md` | normal |
| `templates/client/_template/kb/wiki/log.md` | `clients/_template/kb/wiki/log.md` | normal |

## (root) — settings + index

| Core file | Live path | Tier |
|---|---|---|
| `MANIFEST.md` | `—` | normal |
| `settings-core.json` | `.claude/settings.json` | normal |

