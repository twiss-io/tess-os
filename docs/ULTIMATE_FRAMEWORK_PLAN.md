---
title: "Tess OS — The Ultimate Plug-and-Play Framework Plan"
status: PLAN ONLY — design document, nothing here is implemented by this document
date: 2026-07-07
author: Fable 5 systems-architecture pass (dispatched by Tess)
sources_studied:
  - /Users/twiss-cloud-sync/Documents/tess/conductor/ (full doctrine: dispatch-brief, verification-routing, guardrails, doctrine, subagent-failure-protocol, orchestra-model, agent-lifecycle, cross-guild-coordination, outcome-orchestrators/, review-output-standards)
  - /Users/twiss-cloud-sync/Documents/tess/CLAUDE.md (Rule Zero + system laws)
  - twiss-io/tess-os PUBLIC repo @ v0.1.1 (cloned, read: tessctl verbs, tess.lock, tess.manifest.json, .claude/{agents,commands,hooks}, create-tess wizard, README)
  - projects.nosync/tess-os (this repo — the April 2026 TessOS SaaS dashboard)
  - kb/wiki/synthesis/2026-06-27-tess-os-public-library-design.md, 2026-07-02-tess-os-gui-design.md, 2026-06-29-tess-os-knowledge-graph-second-brain.md
confidence: high on Tess-OS/doctrine facts (verified against primary artifacts); high on Codex/Gemini mechanics marked "(verified)" (checked against openai/codex and google-gemini/gemini-cli official docs via Context7, 2026-07-07); medium on Cursor/Copilot rows (re-verify at build time — these products version fast)
---

# Tess OS — The Ultimate Plug-and-Play Framework
## Enforcing safe shipping for coding agents — independent of the agent's quality

> **⚠️ SUPERSESSION NOTICE (2026-07-08) — read this before anything below.**
> This plan's central productivity claim — that mounting the doctrine
> described below into an agent's context makes that agent produce
> measurably better verified output — was tested by this repo's own
> proving-ground harness on 2026-07-07, twice, fairly, and **disproved**:
>
> - Run 1 (tasks 01–10): `weak+tess-os` vs `weak+bare` showed no delta
>   (ceiling effect — both 100%); `strong+tess-os` vs `strong+bare`
>   **regressed −10 points** at **3.18× cost**.
> - Run 2 — FAIR (tasks 11–19, purpose-built to discriminate, a
>   dispatch-guard friction bug fixed first): `weak+tess-os` vs `weak+bare`
>   **regressed −11.1 points (8/9 vs 9/9, n=9)** at **2.71× cost**;
>   `strong+tess-os` vs `strong+bare` showed no delta at 1.74× cost; and
>   the literal thesis comparison — `weak+tess-os` vs `strong+bare` — was
>   **strictly worse** (−11.1 points, 8/9 vs 9/9, n=9) despite being 32%
>   cheaper.
> - Across 19 tasks and ~80 trials: every miss happened under the tess-os
>   scaffold; **zero misses happened bare.** Every `bare` cell in both
>   runs was run with `--allow-impure-bare` (no `ANTHROPIC_API_KEY` in
>   this build environment forced impure-bare mode — see the reports'
>   "Known limitation" sections); "bare" here means "bare, approximately"
>   (still inheriting the operator's plugins/MCP/tool list), not a
>   stripped baseline.
>
> Full reports: [`proving-ground/reports/2026-07-07.md`](../proving-ground/reports/2026-07-07.md),
> [`proving-ground/reports/2026-07-07-fair.md`](../proving-ground/reports/2026-07-07-fair.md).
>
> Every "structure raises output quality" claim in this document is
> therefore **historical design rationale**, annotated in place rather
> than deleted (so the reasoning that led here stays legible), never a
> standing claim. What the benchmark did **not** touch — and remains
> undamaged — is the **ship-gate** (`tessctl gate`, git/CI-enforced,
> model-independent) and the multi-agent conductor runtime (untested by
> this benchmark, not vindicated by it either — see the reports'
> discussion of scope). The framework's defensible value after this
> result is **enforcement**, stated at the grain it actually operates:
> **a change to a policy-flagged path cannot ship without a signed
> covering verdict, at git/CI, provided CI runs as a required check from
> a trusted engine** (Part D7, Part C8). That is the one claim this repo
> now markets.

> **Xavier's goal (verbatim):** "ensure this is the ultimate plug and play framework for Claude Code, Codex and frontier models AI assistant" — robust to agent quality, "especially agents that are of lower quality compared to Fable."

> **Scope note — two artifacts named "tess-os."** (1) *This* repo (`projects.nosync/tess-os`) is the April-2026 **TessOS SaaS dashboard** (Next.js 16 + Supabase; agent runs, conversations, cost tracking — see `business-plan-v1.md`). (2) **`twiss-io/tess-os`** (public, live, v0.1.1, `npm create tess`) is the **framework product** this plan is about: doctrine + roster + keystone upgrade engine + vault + wizard. This plan designs the evolution of (2); (1) becomes the optional Mission-Control surface in Phase 4. The plan lives here because this is where Xavier asked for it.

---

## 1. Executive Summary — The Thesis

**Ship-safety is a property of the boundary, not the model.** (The stronger
claim — that system structure raises model output quality — was tested
2026-07-07 and disproven; see the supersession notice above and
`proving-ground/reports/`.) The Tess doctrine has already shown this much in
production: a 165-persona multi-agent operation runs real client work
(SuperCane prod deploys, payment audits, live incident ops) on a mix of model
tiers, and its post-mortems show that every serious failure was a *structure*
failure, not a *model* failure — and no recurrence of that failure class has
been observed since each corresponding structural fix (bounded to the
incidents on record, not a claim the failure class is provably eliminated).
(This production incident history is a distinct claim from the
benchmark above — it is about the multi-agent conductor runtime's containment
record, not about mounting doctrine as context in a single headless agent
call — and the benchmark neither confirms nor disproves it; it remains
untested by proving-ground, not vindicated by it.)

| Incident (from doctrine changelogs) | Failure class | Structural fix that now exists |
|---|---|---|
| 2026-05-31 fabricated-UUID void targeted the wrong live payment | Agent inherited the orchestrator's *transcription* of data | Dispatch briefs must point at **primary artifacts, never transcribed data** (`dispatch-brief.md` field 3) |
| 2026-05-12 production delete completed seconds before "scratch that" | One-shot destructive dispatch | Mandatory 3-step verify → go/no-go → execute (`dispatch-brief.md`) |
| 2026-05-10 Tess-Deploy shipped 5 critical/high security gaps incl. a cross-tenant leak | Review was discretionary and skipped | **Mandatory** verification-before-anything-visible (`verification-routing.md`) |
| 2026-06-01 false client status sent | Completion claimed before reading results | anti-fabrication-guard hook: completion-claim messages **denied** while a dispatch is in flight |
| Repeated same-mistake retries burning budget | Untyped retry | Typed retry: classify cause → **changed brief** → cap at 3 → escalate with per-attempt log (`subagent-failure-protocol.md`) |

**[SUPERSEDED — see notice above.]** The proving ground tested the
equalizer hypothesis on 2026-07-07 (both runs, both tiers): doctrine-as-
context produced zero improvement and a weak-tier regression at 1.7–2.7×
cost. The framework's defensible value is the enforcement boundary (Part
C8 / Part D7) — bad output can't ship — not output enhancement.

**What must change to be "ultimate plug-and-play":** today the doctrine is (a) prose that only a strong model reliably self-enforces, (b) wired 100% to Claude Code (`CLAUDE.md`, `.claude/**` — the public repo contains **zero** references to Codex, Gemini, or AGENTS.md; verified by grep), and (c) enforced by exactly two bash hooks that only Claude Code can fire. The plan below converts the doctrine into **machine-checkable contracts** (schemas + a deterministic `tessctl gate` spine that works from git hooks and CI on *any* harness), splits the product into a **portable core + per-assistant adapters**, and adds the **proving ground** — which tested exactly that claim and disproved it (weak+framework: −11.1 pts vs strong+bare, fair run). The harness's standing jobs are now: (a) enforcement demonstration (the gate arena), (b) regression CI for any doctrine payload change.

**The eight key design decisions** (full rationale in the body):

1. **Doctrine compiles; it is not copied.** One `core/` source of truth, rendered per-harness by the existing keystone engine (`tessctl render` already does template → `CLAUDE.md`; extend it to emit `AGENTS.md`, `.codex/`, `.gemini/` from the same source).
2. **Enforcement moves from model-compliance to deterministic code wherever a check is mechanical.** New portable spine: `tessctl gate` + git pre-commit/pre-push hooks + a CI action — harness-independent, works even for an assistant with no hook system at all.
3. **Contracts become schemas.** `brief.schema.json`, `crew-plan.schema.json`, `verdict.schema.json`, `return-manifest.schema.json` — validated deterministically; a schema-miss auto-classifies as *degraded output* and triggers the changed-brief retry. Weak agents can't "sound done."
4. **Adapters are capability-tiered, not feature-identical.** Tier A (native subagents: Claude Code with hooks; Gemini CLI's `.gemini/agents/`) runs the full orchestra in-session. Tier B (headless CLI, no subagent tool: Codex CLI) runs the same conductor loop via **process fan-out** (`codex exec` child processes as the dispatch primitive — which also serves every harness as the cross-model driver). Tier C (rules-file-only assistants: Cursor, Copilot) gets doctrine + the deterministic gate spine, no orchestra. Degradation is explicit and documented, never silent.
5. **Model-tier routing is a first-class module**: strong model conducts and verifies; cheap models execute. Cross-model verification (Codex verifies Claude's diff, or vice versa) becomes an adapter feature — the strongest form of independent review.
6. **Verification is the moat, so verification produces an artifact.** A signed verdict file at a contracted path is the *thing* the gate checks before anything ships — the same way `tess.lock` already makes framework integrity a checkable artifact.
7. **Install UX stays `npm create tess` + keystone updates** — already built and proven over-the-wire (v0.1.0→v0.1.1 signed-tag upgrade verified 2026-06-29). The wizard gains a "which assistants?" axis and installs the right adapters.
8. **Prove it or don't claim it:** the Proving Ground (Phase 3) runs seeded task suites with deliberately weak execution models, with/without the framework, and publishes verified-pass-rate deltas. This is both the QA harness and the marketing.

**Roadmap:** Phase 0 *Contracts-as-code* (~2 wks) → Phase 1 *Portable core + render targets* (~2-3 wks) → Phase 2 *Codex adapter + gate spine end-to-end* (~3 wks) → Phase 3 *Gemini/generic adapter + cross-model verification + Proving Ground* (~3-4 wks) → Phase 4 *Mission Control GUI + Navigator router* (scoped separately). Estimates carry Xavier's 1.5–3× padding rule.

---

## 2. Part A — Design Rationale (HISTORICAL; enhancement claims superseded 2026-07-07)

> **Reframing note.** This section was originally titled "Core Thesis: How
> Structure Compensates for Agent Quality" and argued that each mechanism
> below *raises* a weak agent's output quality. The 2026-07-07 benchmark
> (see the supersession notice at the top of this document) tested that
> claim directly — mounting this doctrine as context in a single agent's
> workdir — and it did not hold: zero improvement, a weak-tier regression,
> and a real cost premium. The mechanism descriptions below are kept as
> **design history**, not deleted, because the *mechanisms themselves*
> mostly remain accurate under a different description: they are
> **enforcement and containment rationale** (why the gate, the schemas,
> and the hard floors exist), not evidence that a model reading them
> writes better code. Read every "kills F_n" / "catches F_n" claim below
> as "was designed to address F_n," not as a measured result — the only
> sub-mechanisms actually exercised end-to-end by the ship-gate (A.3's
> mandatory verification, A.7's hard floors) are the ones the benchmark
> left untouched, because they are deterministic code at the git/CI
> boundary, not prompted behavior.

The "weak agent problem" decomposes into six specific failure modes. Each doctrine mechanism targets one or more of them. This section is the theory of the product; every mechanism cited exists today in `conductor/` and is production-tested.

### A.0 The weak-agent failure taxonomy

| # | Weak-agent failure mode | What it looks like |
|---|---|---|
| F1 | **Context starvation** — can't infer missing context | Wrong file, wrong convention, invented paths |
| F2 | **Scope drift** — wanders into adjacent work | "Also refactored your auth while I was there" |
| F3 | **Confabulation** — fills gaps with plausible fiction | Fabricated UUIDs, invented API fields, "tests pass" (no tests ran) |
| F4 | **Premature completion** — declares success on vibes | "Done!" with a half-written file |
| F5 | **Same-mistake loops** — retries without changing anything | Burns 10 attempts on the identical wrong approach |
| F6 | **Blast-radius blindness** — no sense of irreversibility | Happily drops a prod table to "clean up" |

### A.1 The Dispatch Brief Contract → kills F1, F2 (and starves F3)

**Mechanism** (`conductor/dispatch-brief.md`, six required fields): Objective (success for *this* agent) · Output schema (path + format + required sections) · Tools/sources/constraints **with the evidence requirement and primary-artifact pointers** · NOT-responsible-for boundary · Milestones with named acceptance evidence (mandatory >15 min or prod-touching) · Escalation trigger.

**How it catches a weaker agent's mistakes:**
- **F1:** A weak model's dominant failure is under-specified input. The brief is *self-contained by contract* — file paths, conventions, branch targets travel in the brief, so the agent never has to reconstruct context it can't reconstruct. The retry protocol's "context-gap" class exists precisely because this is the most common cause; the fix is always "inject the missing context into the brief," which only works because the brief is the unit of injection.
- **F2:** The NOT-responsible-for line is a *fence a weak model can follow* even when it can't exercise judgment. "Do not touch the migration files" is checkable; "use good judgment about scope" is not.
- **F3:** The evidence requirement — *every factual claim must trace to a primary artifact the agent itself read or a tool call it itself ran; inference must be labeled* — doesn't stop a weak model from confabulating, but it forces confabulations into a form the verifier can mechanically falsify (a claim with no artifact pointer is rejected on sight).
- **F6:** The decomposition rule (>15 min or prod-touching → milestones with acceptance evidence; destructive ops → mandatory 3-step verify/go/execute) means a weak agent's blast radius per dispatch is structurally bounded. It cannot one-shot a catastrophe because it is never handed a one-shot destructive brief.
- **Escalation trigger** converts a weak agent's flailing into a clean stop: "if X, stop and surface" is followable by any model; "know when you're stuck" is not.

**Productization delta:** today the brief is prose checked by a warn-mode validator hook. Phase 0 turns it into `brief.schema.json` + `tessctl brief check <file>` — deterministic validation any harness can run (§C1).

### A.2 Structured-output contracts + deterministic return validation → kills F4

**Mechanism:** field 2 of the brief ("a markdown file at [path] with sections [X, Y, Z]", never "a good analysis") plus the orchestra model's rule that the conductor *reads the returned primary artifact, never trusts the summary* (`orchestra-model.md` §4c).

**How it catches a weak agent:** a weak model's "I've completed the analysis" costs nothing to say. A file that must exist at a contracted path with contracted sections either exists or doesn't — **existence and shape are model-independent checks.** The planned `return-manifest.schema.json` (§C1) makes the return itself structured: artifact paths, claims list with evidence pointers, self-reported status. A schema-miss is auto-classified as *degraded output* → enters the retry loop with a changed brief. The weak agent's most dangerous move (sounding finished) becomes mechanically impossible to cash.

### A.3 Verification-before-anything-visible → the backstop for F3, F4, and everything the brief missed

**Mechanism** (`conductor/verification-routing.md`): mandatory — not discretionary — domain verifier for prod-touching / client-facing / externally-visible / irreversible-decision-informing outputs. Six named verifiers (Reid code, Quinn release, Cyra security, Verity research, Maialen evidence, Lysandra creative). Two load-bearing rules: (1) the verifier reads **primary artifacts, never the orchestrator's summary** ("a verifier that reads the orchestrator's summary inherits the orchestrator's confabulations and verifies nothing"); (2) verdicts follow `review-output-standards.md` — `[SEVERITY] area/file:line — finding — risk — fix` with a mandatory closing verdict (`BLOCK | APPROVE WITH SUGGESTIONS | APPROVE`).

**How it catches a weak agent:** this is the single highest-leverage mechanism, because of a fundamental asymmetry — **verifying is easier than generating.** A model too weak to write a correct tenant-isolation query is still often strong enough to *notice* a missing `where org_id =` when told exactly what to look for; and the verifier role can be staffed with a *strong* model at a fraction of total cost because verification reads more than it writes. The doctrine's proof point is negative: the one time review was discretionary (2026-05-10), five critical/high gaps including a cross-tenant leak shipped. Structure made review mandatory; no equivalent incident since.
- Against **F3**: the verifier reads the *actual diff/logs/sources*, so a confabulated claim collides with reality at the artifact level.
- Against **F4**: Quinn's standard requires *quoted test output* — "tests pass" without pasted output is a rejection.
- The severity grammar means even a mediocre verifier produces machine-readable output the gate can act on (BLOCK ⇒ pipeline stops).

**Productization delta:** verdicts become signed artifacts at contracted paths (`verdict.schema.json`), and the ship-gate (`tessctl gate pre-push`) refuses to let changes marked prod/client-facing leave the machine without a matching APPROVE verdict (§C2, §C8). Cross-model verification (§D5) upgrades independence further.

### A.4 Dependency gates → prevents whole *classes* of premature work

**Mechanism** (`conductor/doctrine.md`): intake-before-anything · research-before-build · crew-before-deploy · review-before-synthesis · **verification-before-externally-visible**. Gates are dependency edges, not a clock; independent nodes run parallel; "no gate may be skipped, waived, or satisfied retroactively." A Simple Task Path exists so trivial work doesn't pay the full ceremony — with an explicit ALL-must-hold criteria list, and "when in doubt, use the full doctrine."

**How it catches a weak agent:** gates operate *above* the agent, in the conductor loop — the weak agent never gets the chance to make the mistake. A build brief cannot be issued before research lands (so the weak builder isn't guessing at facts a researcher should have pinned); synthesis cannot run on unreviewed outputs (so a weak agent's error can't be laundered into the final memo); nothing externally visible exists without a verification predecessor **in the mission graph itself**. For weak conductors, the crew-plan contract (§A.6) carries `gate_in` per stage so the gate check is a mechanical field comparison, not judgment.

### A.5 Typed retry with a changed brief + 3-attempt cap → kills F5, bounds cost

**Mechanism** (`conductor/subagent-failure-protocol.md`): five failure states (empty / partial / degraded / timeout / error) × four cause classes (transient / context-gap / wrong-approach / wrong-task). **Same-brief retries forbidden for every non-transient cause** — the retry brief must specifically address the classified cause. Cap: 3 attempts, then STOP and escalate with the full per-attempt analysis log. Partial returns are salvaged (re-dispatch only the remainder). Systemic failures (multiple agents failing) are diagnosed as system issues and don't consume the cap.

**How it catches a weak agent:** weak models fail *more often*, so the retry loop is where framework quality compounds. Three properties matter:
1. **The changed-brief requirement converts each failure into information.** A weak agent that failed on context-gap gets a brief with the missing context injected — the *system* learns even though the model doesn't. This is the design rationale for why weak-agent output quality would rise across attempts instead of flatlining — **unmeasured**: the proving-ground benchmark's trials averaged ~1.0–1.1 attempts-to-pass, so it does not isolate or confirm a within-task, across-attempt improvement effect.
2. **The cap bounds the cost of weakness.** Weak agents inside the framework have a worst case: 3 attempts + escalation, narrated per-attempt. No silent budget bleed.
3. **Cause classification routes the fix to the right place.** "Wrong-task" reframes the Objective; "wrong-approach" names what failed; "context-gap" enriches sources. Untyped retries (the norm elsewhere) re-roll the dice; typed retries reshape the dice.

### A.6 Orchestrator-plans / conductor-dispatches (the orchestra model) → makes weak agents *composable*

**Mechanism** (`conductor/orchestra-model.md`): platform truth — in Claude Code a subagent cannot spawn subagents; dispatch is one level deep, always. So orchestrators are **routing brains that return a crew-plan** (structured YAML: stages, gates, per-task six-field briefs, per-task verifier + primary artifacts, one outcome owner, ≤4-guild cap), and the conductor (Tess or a Workflow) is the **sole dispatcher**, invoking the orchestrator twice — PLAN, then SYNTHESIS with collected artifacts. The conductor *rejects* plans violating the §3.2 rules (missing brief fields, unreal agent names, fake gates, missing verifiers on prod-touching tasks).

**How it catches a weak agent:** the crew-plan is a *dispatch program* — "structured data the conductor can execute mechanically." That is precisely the property that lets **each role be staffed by the cheapest model that clears its bar**: planning needs a strong model once; execution of a well-formed brief is weak-model work; the conductor loop itself (§4 of orchestra-model.md) is nearly mechanical and in Phase 2 becomes partly *actual code* (the workflow runner). Weak agents are safe to compose because they never coordinate with each other — all coordination is data flowing through the conductor, and state lives in the conductor, never in the (possibly unreliable) players.

### A.7 Guardrails + hard floors + deterministic guards → caps the worst case (F6)

**Mechanism** (`conductor/guardrails.md`): Rule Zero (conductor never executes solo — enforced by the block-mode `dispatch-guard.sh` PreToolUse hook with a canonical file whitelist and a 4h stale-lock safety); Rule 1a (single narrow incident-ops exception, conditions-or-it-doesn't-apply); Rule 18's **hard floor that survives all autonomy grants** — credentials, money movement, destructive prod data, client-external factual claims ALWAYS gate on the human; the anti-fabrication guard (completion-claim Telegram sends denied while a dispatch is in flight — forcing read-before-report); the clarification threshold (assume-and-state below 30-min/reversible, one question above).

**How it catches a weak agent:** the hard floor is the recognition that **some decisions must never depend on model judgment at all** — not weak, not strong. A weak agent inside the framework cannot rotate a credential, refund money, or truncate a prod table *by any path*, because those actions gate on a human regardless of what the model believes. The block-mode hooks demonstrate the deeper principle this plan generalizes in §C8: *when a rule is mechanically checkable, check it mechanically.* The dispatch guard doesn't ask the model to remember Rule Zero; it denies the tool call. Note the honest lesson already in memory: an earlier hardening attempt was reverted because block-mode was bypassable via first-token parsing and over-blocked legitimate work — deterministic guards must be engineered and adversarially tested (Cyra), not sprinkled.

### A.8 Adversarial/independent review culture → catches what checklists can't

**Mechanism:** Rule 5 (no blind agreement), review-before-synthesis with explicit challenge questions (contradictions, untested assumptions, what's missed), Eva's 6-condition agent-creation gate and naming discipline (routing errors are quality errors), review-output-standards' BLOCK power, and the practice — visible throughout the kb — of adversarial review rounds (the keystone write-gate's path-traversal RCE was caught in a 4-round fix→verify loop by a *security* reviewer, not by the author).

**How it catches a weak agent:** independence is the property that matters. The producer's blind spots are correlated with the producer; a *different* agent — with a different role prompt, different context, and (Phase 3) a different *model vendor* — has decorrelated blind spots. For weak producers this is the difference between "errors ship" and "errors are findings."

---

## 3. Part B — The Plug-and-Play Layer

### B.1 The landscape as it actually is (what the framework must absorb)

The portable framework targets three harness archetypes. (Details verified against current docs at design time; re-verify at build time — these products version fast.)

| Capability | **Claude Code** | **Codex CLI (OpenAI)** | **Gemini CLI** | **Cursor / Copilot-class** |
|---|---|---|---|---|
| Persistent instructions | `CLAUDE.md` (+ `~/.claude/CLAUDE.md`, `.local.md`) | `AGENTS.md` — hierarchical: nested AGENTS.md wins; prompt overrides file (verified: codex base instructions) | `GEMINI.md`; `context.fileName` in settings.json accepts `["AGENTS.md", ...]` (verified) | `.cursor/rules/*.mdc`, `.github/copilot-instructions.md` |
| Custom commands | `.claude/commands/*.md` (frontmatter + body) | `~/.codex/prompts/*.md` (slash prompts) | `.gemini/commands/*.toml` — prompt + `{{args}}` + `!{shell}` injection (verified) | limited/none |
| Subagents | **Yes** — Task/Agent tool, `.claude/agents/*.md` (name/description/model/tools frontmatter), one level deep | **No native subagent tool** in-session; parallelism via Codex cloud tasks / multiple `codex exec` processes | **Yes (recent)** — `.gemini/agents/*.md` with frontmatter (name/description/kind/tools/model/temperature/max_turns) per `docs/core/subagents.md` (verified) | Background/cloud agents (opaque), no user-composable subagents |
| Hooks / lifecycle | **Yes** — PreToolUse/PostToolUse/Stop/SessionStart/etc., permission decisions | No hook system; **approval policy + OS sandbox** (`approval_policy`, `sandbox_mode` = read-only / workspace-write / full-access in `config.toml`; verified) | No Claude-style permission-decision hooks; tool `exclude` allowlists + sandbox setting | None exposed |
| Tool extension | MCP (config + marketplace), skills | MCP (`mcp_servers` in `config.toml`) | MCP (`mcpServers` in settings.json), extensions | MCP (varies) |
| Structured output enforcement | None native (prompt + hook-side validation) | **`codex exec` accepts an output-schema file** (`outputSchemaFile` in the exec SDK; verified) — native JSON-schema-constrained returns | None native at CLI level | None |
| Headless / scriptable | `claude -p`, `--output-format stream-json` | `codex exec --experimental-json` (non-interactive, JSON event stream; verified) | `gemini -p` | No |

Five facts drive the architecture:

1. **AGENTS.md is the only cross-vendor instruction convention** with real adoption (Codex native with hierarchical precedence; Gemini reads it via `context.fileName`; many others). It is the lowest common denominator for doctrine delivery.
2. **Subagent primitives are converging but uneven.** Claude Code has the Task/Agent tool + `.claude/agents/*.md`; Gemini CLI recently shipped `.gemini/agents/*.md` subagents with near-identical frontmatter; **Codex still has none in-session** — its parallelism is cloud tasks or multiple `codex exec` processes. So the adapter layer needs *two* dispatch drivers: **native-subagent** (Claude Code, Gemini) and **process fan-out** (`codex exec` / any headless CLI). Process fan-out is not a hack — it is exactly the "Workflow conductor" the orchestra model already defines (`orchestra-model.md` §5), and it doubles as the driver for *cross-model* dispatch on every harness.
3. **Only Claude Code has permission-decision hooks.** Codex compensates with an OS-level sandbox + approval policy (a *stronger* containment story for weak agents, but not programmable per-rule); Gemini has allowlists. Deterministic *rule* enforcement everywhere must therefore live in **git hooks + CI + a CLI gate** — which conveniently also work *in* Claude Code as a second layer. Hence the §C8 enforcement spine: git is the one runtime every coding assistant shares.
4. **Structured output is natively enforceable on Codex** (`codex exec` output-schema file) and on no other CLI — one more reason the framework's own `verify-return` must be harness-side (deterministic CLI), with the Codex adapter additionally passing the schema natively.
5. **MCP is the common tool protocol.** Anything the framework exposes as a tool (vault JIT exec, gate checks, roster queries) should eventually be exposable as a small MCP server so all three harnesses can call it uniformly (Phase 3+; the CLI comes first because it's simpler and CI-usable).

### B.2 Architecture: portable core + adapters

```
tess-os/
├── core/                          ← THE single source of truth (new; extracted from today's live tree)
│   ├── doctrine/                  ← harness-neutral doctrine (today's conductor/*, de-Claude-ified:
│   │                                 "the Agent tool" → "the dispatch primitive (see adapter)")
│   ├── contracts/                 ← THE NEW HEART — machine-checkable schemas
│   │   ├── brief.schema.json          (six fields, typed)
│   │   ├── crew-plan.schema.json      (orchestra-model §3.1, typed)
│   │   ├── verdict.schema.json        (severity tiers + closing verdict, typed)
│   │   ├── return-manifest.schema.json(artifact paths + claims-with-evidence + status)
│   │   └── policy.schema.json         (hard floors, whitelists, gate map)
│   ├── roster/                    ← 144 persona specs + 6 orchestrators (150 dispatch-capable) + compiled agent defs (exists: agents/ + .claude/agents/)
│   ├── commands/                  ← 26 command bodies, harness-neutral markdown (exists: .tess/core/commands)
│   └── personas/                  ← conductor personas (exists: .tess/core/personas)
│
├── adapters/                      ← per-harness render targets + dispatch drivers (new)
│   ├── claude-code/               ← Tier A: renders CLAUDE.md, .claude/{agents,commands,hooks,settings}
│   ├── codex/                     ← Tier B: renders AGENTS.md, ~/.codex/prompts/*, config.toml fragment,
│   │                                 dispatch driver = `codex exec --json` fan-out (+ native output-schema)
│   ├── gemini/                    ← Tier A−: renders GEMINI.md, .gemini/agents/*.md (native subagents),
│   │                                 .gemini/commands/*.toml; fallback driver = `gemini -p` fan-out
│   └── generic/                   ← Tier C: renders AGENTS.md + docs/OPERATING.md only
│
├── .tess/                         ← the keystone engine (EXISTS — tessctl, core mirror, lock, keys)
│   └── bin/tessctl                ← grows: `render --target <adapter>`, `gate`, `brief`, `verify-return`
└── (rendered artifacts land at the paths each harness expects; tess.lock tracks them per-file,
    exactly as it tracks CLAUDE.md/.claude/** today — owned_globs in tess.manifest.json gains the
    new adapter output paths)
```

**What is common (the portable core):**
- The doctrine (gates, Rule Zero-equivalent, guardrails, hard floor, retry protocol, orchestra model) — as text for the model *and* as `policy.yaml` for the gate spine.
- The contracts (schemas above) and the artifact-directory convention: `missions/<id>/{plan.yaml, briefs/, returns/, verdicts/, record.md}` — the mission's file trail is harness-independent by design, so a mission can even be *started* in Claude Code and *verified* by Codex.
- The roster (persona specs are pure markdown; only the compiled dispatch format is harness-specific).
- The keystone engine + signed update channel + vault + wizard (all already harness-neutral Python/Node).
- The enforcement spine (`tessctl gate` + git hooks + CI action).

**What is adapter-specific (the shims):**

| Concern | Claude Code adapter (Tier A) | Codex adapter (Tier B) | Gemini adapter (Tier A−) | Generic (Tier C) |
|---|---|---|---|---|
| Doctrine entry | `CLAUDE.md` (rendered — exists) | `AGENTS.md` (rendered; ≤ ~2k words, links to `core/doctrine/`) | `GEMINI.md` (rendered) | `AGENTS.md` |
| Commands | `.claude/commands/*.md` (exists) | `.codex/prompts/*.md` render of the same 26 bodies | `.gemini/commands/*.toml` render | `docs/commands.md` (human-invoked) |
| Dispatch primitive | Agent/Task tool + `.claude/agents/*` | `tessctl dispatch --driver codex` → `codex exec` child procs, brief passed as prompt file + native output-schema, return-manifest required at contracted path | **native subagents**: roster rendered to `.gemini/agents/*.md`; process fan-out (`gemini -p`) as fallback/cross-model driver | none — single-agent mode; gates + briefs still apply to the one agent |
| Roster | compiled subagent defs (exists) | roster personas injected into the child-process prompt (role prompt = persona spec) | compiled `.gemini/agents/` defs (same frontmatter family as Claude Code) | persona picked manually |
| In-session guards | PreToolUse hooks (exist) | **none in-session** → `config.toml` fragment sets `approval_policy` + `sandbox_mode` (OS sandbox = strong containment); gate spine carries rule enforcement | tool-exclude allowlist + gate spine | gate spine only |
| Verification | verifier subagents | verifier = separate `codex exec` (or **cross-model**: `claude -p`) reading primary artifacts | verifier subagent, or cross-model via fan-out | human or CI-invoked verifier prompt |

**Degradation policy (explicit, printed by `tessctl doctor`):** Claude Code = full Tier A (subagents + hooks). Gemini = Tier A− (native subagents, no permission hooks — the gate spine carries rule enforcement). Codex = Tier B (no in-session subagents; process fan-out conducts, and the OS sandbox + `approval_policy` provide containment the others lack). Tier C loses orchestration entirely but keeps the three highest-value mechanisms — six-field briefs, verification-before-ship (gate-enforced), typed retry discipline (documented in AGENTS.md). This is honest plug-and-play: same doctrine, same contracts, same gate; orchestration depth scales with harness capability.

### B.3 Install / onboarding UX

Keep what's built and proven; extend, don't rebuild:

1. `npm create tess@latest` — the existing 5-axis wizard (name/vibe/squad/conductor/pathway) gains **axis 6: harnesses** — multi-select detected from the machine (`which claude codex gemini`), defaulting to what's installed. Wizard stages to temp, validates, promotes atomically (existing behavior — "cancel leaves zero state behind").
2. The wizard drives keystone: `roster apply → set-operator → rename → pathway → render --target claude-code --target codex ...` then `doctor` + `verify` (existing chain + new render targets).
3. `tessctl gate install` — writes the git pre-commit/pre-push hooks and the CI workflow stub (new; the vault already installs pre-commit/pre-push scanners, so the pattern and the plumbing exist — the gate extends the same hook files).
4. **Adopting an existing repo** (the case the current product underserves): `tessctl adopt` — init into a repo that already has code, merging with existing CLAUDE.md/AGENTS.md rather than clobbering (3-way machinery exists; the missing piece is treating a pre-existing user file as the "local" side of the merge).
5. Upgrades stay `tessctl update` — signed-tag verification against the pinned fingerprint in `tess.lock`, snapshot-first, conflict-halts, security-tier quarantine (exists, OTW-verified). Adapter outputs are `owned_globs` entries so **framework upgrades update every harness's rendered artifacts at once** — this is the plug-and-play *maintenance* story no competitor has, and it falls out of keystone for free.

---

## 4. Part C — Productized Components (module specs)

Each module: what exists → target interface → weak-agent function. All modules are Apache-2.0 core (per the locked licensing decision); no module depends on a specific harness.

### C1 — Dispatch Brief Contract module
- **Exists:** `conductor/dispatch-brief.md` (prose contract), warn-mode PreToolUse validator (Claude Code only).
- **Target:** `core/contracts/brief.schema.json`; briefs written as YAML front-matter + markdown body at `missions/<id>/briefs/<task>.md`. CLI: `tessctl brief check <file>` (schema + lint: primary-artifact pointers present? escalation trigger concrete? milestones present when `prod_touching: true`?), `tessctl brief new --template <task-type>` (starter templates per task type — research/build/review/destructive-3-step). The Claude Code hook validator becomes a thin wrapper over the same CLI check.
- **Weak-agent function:** §A.1. Additionally, templates encode the "strongest dispatch on record cites prior incidents" practice — `tessctl brief new` auto-suggests relevant `memory/feedback_*` lessons by tag.

### C2 — Verification Routing module
- **Exists:** `conductor/verification-routing.md` (routing table, mandatory scope), `review-output-standards.md` (severity grammar + verdicts), six verifier personas.
- **Target:** `core/contracts/verdict.schema.json`; routing table as data (`core/policy/verification-routing.yaml`: output-domain → verifier persona → required-primary-artifact kinds). Verdicts written to `missions/<id>/verdicts/<task>.verdict.md` (front-matter: verdict, severity counts, artifacts-read hashes; body: findings in the `[SEVERITY] file:line — finding — risk — fix` grammar). CLI: `tessctl verdict check` (schema), `tessctl gate ship-check` (is there an APPROVE verdict covering this diff's scope? — §C8).
- **Weak-agent function:** §A.3. The `artifacts_read` field with content hashes makes "the verifier actually read the primary artifact" itself checkable — closing the loop on summary-inheritance.

### C3 — Gate system module
- **Exists:** `conductor/doctrine.md` gates + Simple Task Path; crew-plan `gate_in` fields; enforcement = conductor-model compliance.
- **Target:** mission record as data: `missions/<id>/plan.yaml` (the crew-plan) + `missions/<id>/state.json` (which gates cleared, when, evidenced by which artifact). CLI: `tessctl gate status <mission>`, `tessctl gate clear <gate> --evidence <path>` (refuses without evidence). The five canonical gates ship as policy; operators can add custom gates in `policy.yaml`.
- **Weak-agent function:** §A.4 — gates become field checks a runner (or a weak conductor) performs mechanically.

### C4 — Typed Retry module
- **Exists:** `conductor/subagent-failure-protocol.md` (complete: states, causes, changed-brief rule, cap 3, escalation format).
- **Target:** retry ledger in the mission record: `missions/<id>/retries/<task>.attempt-N.md` (front-matter: failure state, cause class, what-the-brief-changed; enforced: attempt N+1's brief must differ from attempt N's when cause ≠ transient — a literal diff check). CLI: `tessctl retry log`, `tessctl retry check` (blocks a 4th attempt; blocks a same-brief non-transient retry).
- **Weak-agent function:** §A.5. The diff check is the productized "no same-brief retries" rule — currently pure model discipline, becomes deterministic.

### C5 — Guardrails / hard-floor module
- **Exists:** `conductor/guardrails.md` Rules 1/1a/18; two block-mode hooks (Claude Code only); vault pre-commit/pre-push scanners (portable, exist).
- **Target:** `core/policy/policy.yaml` — the machine-readable half of guardrails: hard-floor action classes (credentials / money / destructive-prod / client-external-claims) with detection patterns, the conductor file whitelist, mandatory-verification scope, gate map. Consumed by: Claude Code hooks (exists), the gate spine (new), and rendered into every harness's doctrine file as prose. Hard-floor language is rendered verbatim into `AGENTS.md`/`GEMINI.md` so even Tier C assistants carry it as instruction.
- **Weak-agent function:** §A.7 — the worst-case cap. Engineering note from the reverted hardening attempt: block-mode guards ship only with an adversarial bypass test suite (Cyra-style reverse-direction testing), warn-mode first, per the hook-testing protocol already in `conductor/hook-testing-protocol.md`.

### C6 — Orchestrator layer module
- **Exists:** `conductor/orchestra-model.md` (crew-plan contract §3.1, plan-validation rules §3.2, two-pass PLAN/SYNTHESIS, conductor loop §4), six orchestrator agents, integration/precedence doctrine.
- **Target:** `crew-plan.schema.json` + `tessctl plan check` (the §3.2 rules as code: six fields per task, real agent names against the installed roster, real gates, verifier-required inference from task flags, ≤4 guilds, one owner, parallel-implies-no-edges). Plus `tessctl run <plan>` — the **workflow conductor**: a runner that executes the conductor loop §4 mechanically (gate check → dispatch batch via the adapter's driver → collect returns → verify → typed retry → synthesis pass). On Tier A it can drive `claude -p`; on Tier B it drives `codex exec`/`gemini -p`. This single module is what makes the orchestra *portable*: the conductor loop stops being a thing only a strong Claude session can perform.
- **Weak-agent function:** §A.6. `tessctl run` is also the *overnight/autonomous* safety story: a deterministic loop cannot "decide" to skip a gate at 3am.

### C7 — Roster + lifecycle module
- **Exists and strong:** 144 persona specs + 6 outcome orchestrators (150 dispatch-capable); staged/installed roster with `tessctl roster apply / recruit / bench`; Eva's 6-condition creation gate + naming discipline (`agent-lifecycle.md`); starter squads (`founders` / `builders` / `operators`, plus — Goal #11 — a dedicated `coding-squad` path for coding-agent-only adopters: `roster-paths.json`).
- **Delivered (Goal #11, roster honesty — small slice of this line item):** per-persona `model_tier` frontmatter vocabulary (`strong` / `cheap`, mapped from role: conduct→strong, execute→cheap, verify→strong) is now defined and applied to the core coding squad's `agents/<name>/README.md` files (previously free-text in README, per the original note below) — see `agents/README.md` § Model Tier. **Still Target, deferred to a follow-up serial-`tessctl` change (explicitly out of this slice):** wiring `model_tier` into actual model selection (adapter drivers reading the field to set the harness alias); `tessctl recruit` rendering the persona into *every installed adapter's* format, not just `.claude/agents/`; a community registry namespace (`tessctl recruit @community/<agent>`) as the hub play from the moat strategy — gated behind the same signed-channel discipline as framework updates.
- **Weak-agent function:** role prompts are *quality prosthetics* — a persona spec like Leah's ("separate facts from inferences from assumptions") is designed to narrow (unmeasured) a weak model's behavior — no benchmark to date isolates a persona-prompt effect from the rest of the mounted doctrine payload, and the proving-ground result above found no net benefit from the payload as a whole. The lifecycle governance keeps the roster routable (naming discipline = fewer misroutes = fewer garbage dispatches).

### C8 — The Enforcement Spine (`tessctl gate`) — the new keystone-grade component
- **Exists as precedent:** vault's git pre-commit/pre-push guards; keystone's doctor/verify hard-gates; Claude Code block-mode hooks.
- **Target:** one deterministic surface, three mounting points:
  1. **Git hooks** (pre-commit: brief/verdict/return schema checks for changed mission files, secret scan [exists]; pre-push: *ship-check* — any commit touching paths declared prod/client-facing in `policy.yaml` requires a covering APPROVE verdict artifact; refuses otherwise).
  2. **CI action** (`tess-os/gate-action`): same checks + `tessctl verify` (framework integrity) on every PR — the harness-independent backstop that works even when a rogue/weak agent bypasses local hooks with `--no-verify`.
  3. **Harness hooks** where they exist (Claude Code PreToolUse wrappers over the same CLI).
- **Weak-agent function:** this is the bounded honest form of the requirement made real — *a change to a policy-flagged path cannot ship without a signed covering verdict, at git/CI, provided CI runs as a required check from a trusted engine.* Within that scope, the producing model's quality becomes irrelevant at the ship boundary: no covering verdict artifact, no push. Everything upstream (briefs, retries) improves the odds; the spine caps the downside for the paths it actually covers.

### C9 — The Proving Ground (conformance + benchmark harness)
- **Exists:** `proving-ground/` — built, and RUN, twice (2026-07-07). See
  `proving-ground/README.md` and `proving-ground/reports/2026-07-07.md` +
  `2026-07-07-fair.md`.
- **Target (as originally scoped):** a suite of seeded, verifiable tasks (bug-with-failing-test, small feature vs spec, research-with-checkable-facts, adversarial task with a planted trap e.g. tenant-isolation hole) each with a deterministic grader. Runner executes each task 4 ways: {weak model, strong model} × {bare harness, tess-os framework}, and reports **verified-pass rate, cost, attempts-to-pass**. Published as a versioned report per release. This shipped as designed.
- **Weak-agent function — outcome, not a plan anymore:** this WAS the
  thesis test, and the rule this bullet originally stated now binds:
  *"If `weak+framework ≥ strong+bare` doesn't hold on the suite, the
  framework isn't done — and the claim can't be marketed until it's
  measured."* It was measured. It doesn't hold — `weak+framework` lost to
  `strong+bare` by 11.1 points in the fair run (8/9 vs 9/9, n=9 — too
  small a sample for a rate; directional, not a precision claim). Per
  this document's own
  rule, the enhancement claim is now unmarketable, and every surface that
  stated or implied it has been corrected (this document, `README.md`,
  `proving-ground/README.md`). The harness's remaining jobs are
  regression CI for doctrine-payload changes and the enforcement-arena
  demonstration (untested by this run) described in the reports'
  recommendations.

---

## 5. Part D — Lower-Quality-Agent Robustness (the dedicated design)

The layered defense, in the order a weak agent's work flows through it.
Layers 1–3 were **hypothesized** to raise output quality — measured
2026-07-07: no measurable raise, weak-tier harm. Layers 4–8 (catch + cap)
are the product.

**D1. Tight, self-contained, small briefs (input control).** Everything a weak model needs travels in the brief: primary-artifact paths, conventions, constraints, the NOT-boundary, the escalation trigger. Decomposition keeps each dispatch small — small context beats big context for weak models on both attention and blast radius. *Product:* C1 templates + `brief check` lint that flags briefs whose scope smells >15 min without milestones.

**D2. Persona prosthetics + model-tier routing (worker selection).** Every task runs on the cheapest tier that clears its bar, wrapped in a persona spec that narrows behavior. The tiering already practiced live (orchestration=Opus-class, planning=strong, execution=Sonnet-class; elevate only for money/security/destructive) ships as roster metadata + adapter defaults. *Product:* C7 `model_tier`; adapter drivers map tiers to concrete models per harness.

**D3. Structured returns, validated deterministically (output shape control).** The return-manifest contract: artifacts at contracted paths, claims each carrying an evidence pointer, explicit status. `tessctl verify-return` runs before the conductor even reads prose. Schema-miss ⇒ automatic *degraded* classification ⇒ changed-brief retry. **A weak agent physically cannot hand back an unverifiable blob and have it accepted.** *Product:* C1/C4.

**D4. Mandatory independent verification (error detection).** Domain verifier, primary artifacts only, severity grammar, BLOCK power. Staffed strong even when execution is cheap — the asymmetry (reading < writing) makes this affordable. *Product:* C2.

**D5. Cross-model adversarial second opinion (decorrelated detection).** Tier B adapters make this nearly free: the verifier driver can be a *different vendor's* model (`codex exec` reviews a Claude-produced diff, or `claude -p` reviews Codex output). Same-model reviewers share failure modes with producers; cross-vendor reviewers don't share training-correlated blind spots. Reserve for the mandatory-verification scope (prod/client/external) to control cost. *Product:* C2 + adapter drivers; a `verification-routing.yaml` flag `cross_model: prefer`.

**D6. Typed retry with changed briefs (error correction).** The failure→classification→brief-improvement loop from §A.5, with the diff check making "changed" literal. Weak agents get *better inputs* on each retry instead of more chances to repeat themselves. *Product:* C4.

**D7. The ship gate (containment).** Nothing prod/client/external leaves the machine or merges without a covering APPROVE verdict artifact — enforced at git and CI, below the level any agent (or harness) can charm its way past. *Product:* C8.

**D8. Hard floors + human gates (worst-case cap).** Credentials, money, destructive prod data, client-external factual claims: always human-gated, in every adapter, in every autonomy mode. Destructive ops always 3-step (verify → go → execute). *Product:* C5.

**The economics, stated plainly:** weak agents fail more, so they consume more retries and more verification — but retries of cheap models plus strong verification of a *finished artifact* costs a fraction of running the strong model end-to-end, and the gate guarantees the failure cost is bounded (max 3 attempts, nothing unverified ships on the paths the gate covers). That is the product's promise in one sentence: **the gate bounds the *downside* of model quality — a covered path can't ship without a signed verdict — at a measured cost premium (1.7–2.7× when doctrine is mounted as context; the cost of enforcement living only at git/CI, with no doctrine mounted, has not itself been separately measured by this benchmark and is not asserted here as near-zero). The upside conversion claimed here previously ("the framework converts model quality from a correctness risk into a mere cost/latency variable") was disproven — see the supersession notice.**

---

## 6. Part E — Gap Analysis + Roadmap

### E.1 What Tess OS is today vs what "ultimate plug-and-play" requires

| Dimension | Today (verified) | Required | Gap severity |
|---|---|---|---|
| Doctrine quality | Excellent, production-hardened, incident-annotated (`conductor/`) | Same, as compilable source | — (asset) |
| Contracts | Prose + one warn-mode hook | JSON-schema'd brief/plan/verdict/return + CLI validation | **HIGH** — this is the weak-agent keystone |
| Enforcement | 2 Claude-Code hooks (+ vault git guards); everything else = model compliance | Deterministic gate spine at git/CI level, harness-independent | **HIGH** |
| Harness coverage | Claude Code only; zero AGENTS.md/Codex/Gemini anywhere in the public repo | Tier A/B/C adapters from one core | **HIGH** — the literal "plug and play for Codex and frontier models" ask |
| Orchestration | Doctrine + strong-model conductor; no runnable workflow conductor in the public product | `tessctl run` mechanical conductor loop | MEDIUM-HIGH |
| Install/upgrade | **Best-in-class and shipped**: create-tess wizard, keystone 3-way merge, signed OTW-verified update channel, roster staging, vault | Add harness axis + adopt-existing-repo + adapter render targets | LOW-MEDIUM (extend, don't build) |
| Verification of the thesis | **Tested, 2026-07-07, twice — negative and published** (see `proving-ground/reports/`) | Gate-arena demonstration (enforcement, not enhancement) | MEDIUM — the credibility asset is now the disclosure itself, not a pending number |
| Mission Control GUI | Designed only (2026-07-02 design doc: local 127.0.0.1 server over `claude -p` stream-json); this repo's SaaS dashboard is a separate, adjacent artifact | Optional surface, after the core | LOW (sequenced last) |
| Public-repo hygiene | dispatch-guard ships **warn-mode** in public (block-mode is the private instance's posture). **Roster-count drift fixed (Goal #11, 2026-07):** `agents/README.md`, `conductor/orchestra-model.md`, and `.tess/core/MANIFEST.md` all carried stale/conflated counts (165 "persona directories" that were actually 144 dirs + 21 guild docs; "42 dispatchable" predating the 2026-06-27 all-150-dispatch-capable fix); all three now state 144 persona specs + 6 orchestrators = 150 dispatch-capable, hand-verified against the tree (`find agents -mindepth 1 -maxdepth 1 -type d \| wc -l`), and explicitly distinguish "dispatch-capable" (has a core definition) from "installed" (live in `.claude/agents/`, as few as 7 by default) | Truthful per-mode docs; counts generated from the tree | LOW — counts now truthful and hand-verified; **generation-from-tree mechanism still not built** (would be a `tessctl` change, out of scope for a docs-only fix) |

### E.2 Roadmap

**Phase 0 — Contracts-as-code (~2 wks padded).** Ship `core/contracts/*.schema.json` (brief, crew-plan, verdict, return-manifest, policy) + `tessctl brief|plan|verdict|verify-return` checks + the `missions/<id>/` record convention. Wire the existing Claude Code brief validator to the CLI. Fix E.1 hygiene items. *Acceptance:* every schema round-trips a real historical mission from `kb/wiki/missions/`; pytest suite for each validator; `tessctl doctor` reports contract health.

**Phase 1 — Portable core + render targets (~2–3 wks).** Extract `core/doctrine/` (de-Claude-ify wording: "dispatch primitive" abstraction), add `tessctl render --target {claude-code,codex,gemini,generic}` producing CLAUDE.md / AGENTS.md+prompts / GEMINI.md+commands / AGENTS.md from one source; extend `tess.manifest.json` owned_globs + `tess.lock` to the new outputs so keystone upgrades all adapters atomically. Wizard axis 6 (harness multi-select). *Acceptance:* a fresh `npm create tess` on a machine with Codex-only produces a working AGENTS.md-driven install; `tessctl update` cleanly 3-way-merges a doctrine change into all rendered targets.

> **Honest re-scope (MED-2 + LOW-1, Fable Phase-1 review, PR #36):** what actually shipped under this Phase 1 line item is a SUBSET of the paragraph above — the `RenderTarget` seam (registry, per-install enablement, and doctor/verify/update wired to consult it — the part that makes the seam load-bearing rather than decorative) plus exactly **one** target, `claude-code` (the Tier A reference implementation), plus the deferred Phase 0 item (`core/contracts/**` wired into the managed set). Still **not done**, and explicitly Phase 2+ scope: the `codex` / `gemini` / `generic` targets themselves; the `core/doctrine/` extraction and de-Claude-ified wording; wizard axis 6 (harness multi-select); and `core/contracts/policy.schema.json` (the fifth schema named in §B.2's `core/contracts/` tree — hard floors, whitelists, gate map — never built; `CONTRACT_SCHEMAS` in `.tess/bin/tessctl` only has brief/crew-plan/verdict/return-manifest). The Phase 1 acceptance criteria above ("a fresh `npm create tess` on a machine with Codex-only produces a working AGENTS.md-driven install") is **not yet met** — it is Phase 2's acceptance bar once a Codex target exists. This note exists so the roadmap table above isn't read as a completed-work claim; see `CHANGELOG.md` `[Unreleased]` for the itemized delivered-vs-deferred list.

**Phase 2 — Codex adapter + enforcement spine end-to-end (~3 wks).** `tessctl dispatch --driver codex` (brief file → `codex exec --json` child → return-manifest validation); `tessctl run <plan>` mechanical conductor loop; `tessctl gate install` (pre-commit/pre-push ship-check + CI action). *Acceptance:* one real mission (plan authored by a strong model in any harness) executes end-to-end with Codex-driven workers, verifier rejection triggers a typed retry, and a push without an APPROVE verdict on a prod-flagged path is refused by both git hook and CI.

> **Honest re-scope (gate-spine build, this PR):** what shipped under this Phase 2 line item is the **enforcement-spine SLICE only** — `tessctl gate` (`pre-commit` / `pre-push` / `ci` / `install-hooks`), the fifth contract `core/contracts/policy.schema.json` + the `core/policy/policy.yaml` instance it validates against, the git-hook splice installer (a second, independently-implemented instance of the coexistence pattern `_vault_install_git_hooks` already proved), and a `workflow_dispatch`-only CI workflow template. This closes the acceptance bar's second half exactly: "a push without an APPROVE verdict on a prod-flagged path is refused by both git hook and CI" — proven end-to-end in `tests/test_gate_hooks.py` against real git repos and a real bare remote, including the documented `git push --no-verify` → CI-still-catches-it case. **Not done, and explicitly still Phase 2+ scope:** the Codex adapter (`tessctl dispatch --driver codex`, `codex exec` process fan-out) and `tessctl run <plan>` (the mechanical conductor loop over a crew-plan) — the acceptance bar's first half ("one real mission... executes end-to-end with Codex-driven workers, verifier rejection triggers a typed retry"). The gate spine does not depend on either — it operates on git diffs and on-disk contract instances regardless of what produced them — so it was buildable and independently testable first. See `README.md`'s "Status" section and `CHANGELOG.md` `[Unreleased]` for the itemized delivered-vs-deferred list.
>
> **Fable adversarial-review fixes (this PR, follow-on to the gate-spine build above):** Fable's review of the gate-spine slice found one BLOCK (HIGH-1: coverage was diff-unbound — a schema-valid APPROVE verdict anywhere in the working tree permanently cleared its `covers_paths` glob for every future push, `**` acted as a master key, and an uncommitted pre-push verdict counted) and two MEDIUMs. All three are closed: (a) `verdict.schema.json` gains `artifact_hashes` — the content-hash loop-closer this very document's §C2 already named but deferred ("the `artifacts_read` field with content hashes makes 'the verifier actually read the primary artifact' itself checkable") — binding `covers_paths` coverage to the git blob SHA of the content actually reviewed, so verification is per-change, not a permanent toll; (b) over-broad `covers_paths` globs (`**`, bare `*`, `**/*`, `**/**`) are now schema/lint-rejected outright; (c) covering-verdict discovery moved from an `rglob` over the on-disk working tree to `git ls-tree` over the actual pushed ref(s), so only committed verdicts on the branch being pushed count. Separately, **the `allowed_verifiers` field is now ENFORCED** — the previous sentence in this note ("declared but not yet ENFORCED... a deliberate, deferred tightening") is superseded; a covering verdict's `verifier` must be in the matched rule's `allowed_verifiers` or it does not clear the gate. The glob matcher itself (`path_matches_globs`) was also fixed: `**/x` now matches a root-level `x` (previously required a directory component — this is what made `core/policy/policy.yaml`'s own `**/*.env` credentials glob miss a top-level `.env`), and a bare `*` no longer spans `/` (previously identical to `**`). See `CHANGELOG.md` `[Unreleased]` → "Fixed" for the itemized list and the 11 new tests proving each fix.

**Phase 3 — Gemini + generic adapters, cross-model verification, Proving Ground (~3–4 wks).** Gemini driver + render target; generic Tier C docs; `cross_model` verifier routing; `proving-ground/` v1 (≥10 seeded tasks, 4-way matrix, published report). *Acceptance:* the report exists with real numbers; README claims are regenerated from it (evidence-discipline rule).

**Phase 4 — Surfaces (scoped separately, after core).** Mission Control GUI per the 2026-07-02 design (local, token-authed, thin over `claude -p`/`tessctl run`); decide the fate of *this* repo's SaaS dashboard (natural fit: the multi-tenant, client-facing skin over the same mission-record data model); The Navigator (provider router) folds into the adapter driver layer rather than a separate product.

**Sequencing rationale:** contracts before adapters (adapters render contracts; building adapters first would triple rework), Codex before Gemini (second harness forces the abstraction; third validates it), Proving Ground before any marketing claim (the repo's own evidence rule), GUI last (the 2026-07-02 design doc itself says the GUI is "a thin front end over primitives that already exist" — so the primitives come first).

### E.3 Open decisions for Xavier

1. **Ship-gate default posture** — advisory (warn) or enforcing (block) for new public installs? (Private instance history: block-mode was reverted once for over-blocking; recommend: enforcing at pre-push/CI where false positives are rare, advisory at pre-commit.)
2. **Cross-model verification default** — on for the mandatory scope (2 vendors' API costs) or opt-in flag? Recommend opt-in until Proving Ground quantifies the catch-rate delta.
3. **Community roster registry** — Phase 3 or later? It is the hub/moat play but carries curation and security surface (recruit = executable instructions).
4. **This repo (SaaS dashboard)** — park, or re-target in Phase 4 as hosted Mission Control for the framework's mission records? (Recommend: park until the framework's file-based record model is stable; the dashboard's schema predates the doctrine and would be rebuilt against `missions/<id>/` data.)

---

## 7. Appendix — Design-decision register (one line each)

| # | Decision | Rejected alternative | Why |
|---|---|---|---|
| 1 | One `core/` compiled per harness | Per-harness forks of doctrine | Fork drift killed every multi-target docs effort; keystone merge only works with one base |
| 2 | Deterministic gate spine at git/CI | Model-enforced doctrine everywhere | Weak models can't self-enforce; git is the only universal runtime |
| 3 | Schemas + artifact-file mission records | In-context/JSON-mode structured output | Files are harness-neutral, diffable, gate-checkable, survive session death |
| 4 | Capability tiers with explicit degradation | Identical feature promise everywhere | Codex has no in-session subagent tool and only Claude Code has permission hooks; pretending otherwise ships silent breakage |
| 5 | Two dispatch drivers: native-subagent + process fan-out | Wait for vendor convergence / fan-out everywhere | Claude Code + Gemini already have native subagents (use them); `codex exec` fan-out covers Codex and doubles as the cross-model driver on all harnesses |
| 6 | Verifier reads primary artifacts, verdict is an artifact | Verifier reads conductor summary / verbal approval | Summary-inheritance verifies nothing (doctrine's own words); artifacts are gateable |
| 7 | Cross-model verification as adapter feature | Same-model review only | Decorrelated blind spots; the multi-harness install makes it nearly free |
| 8 | Proving Ground before marketing claims | Claim "works with weak models" on theory | The repo's own evidence-discipline rule; ran 2026-07-07, came back negative — the strongest README asset is now the honesty itself (publishing the loss) plus the gate-arena numbers, not the disproven enhancement claim |
