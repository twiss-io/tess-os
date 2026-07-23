# Tess OS

[![License: Apache-2.0](https://img.shields.io/github/license/twiss-io/tess-os)](LICENSE)
[![create-tess on npm](https://img.shields.io/npm/v/create-tess?label=create-tess)](https://www.npmjs.com/package/create-tess)
[![Latest release](https://img.shields.io/github/v/release/twiss-io/tess-os)](https://github.com/twiss-io/tess-os/releases)
[![CI](https://img.shields.io/github/actions/workflow/status/twiss-io/tess-os/ci.yml?label=CI)](https://github.com/twiss-io/tess-os/actions/workflows/ci.yml)

> **Status: technology preview. Do not use the current release or `main` to protect production merges.**

Tess OS is a local governance and review harness for work produced by coding
agents. It records policy and review evidence around repository changes, then
can run a gate before a protected delivery step.

It is not a model-improvement product. It does not make an agent smarter,
prove a model's reasoning, or make an unsupported platform safe. Its value is
the discipline and evidence around work that Tess OS can actually observe and
enforce.

## What works today

- A local CLI, `tessctl`, for policy checks, artifact validation, local traces,
  framework rendering, and mission records.
- A signed-review gate that blocks a governed change when it lacks a valid,
  covering approval artifact.
- A reference Claude Code render target and driver.
- An opt-in Codex render target that produces `AGENTS.md`, `.codex/config.toml`,
  and prompt files; a Codex driver also exists.
- An opt-in generic target that produces `AGENTS.md` and plain prompt files.
- A local, sequential `tessctl run` conductor loop with mission gates, return
  artifact validation, bounded retries, and escalation.
- Local JSONL traces for selected gate and validation commands, with an
  operator-run OpenTelemetry JSON export.

These are current repository capabilities, not equivalent provider support
claims. Read the [support and status guide](docs/STATUS.md) before deciding
whether an integration fits a particular workflow.

## Important limits today

Tess OS is deliberately fail-closed when no covering approval exists. The
shipped policy intentionally has empty verifier and sign-off registries, so a
message such as **"no covering APPROVE verdict found"** is an expected block,
not an invitation to create a key or work around the gate.

Two production prerequisites remain unresolved:

1. The first verifier/sign-off trust anchor needs an external, human-owned
   custody design. Candidate repository content must never establish the
   authority that approves itself.
2. GitHub must make the real gate and CI results required checks before a gate
   can protect a branch. That enforcement is not configured today.

Until both are complete, a passing local command or GitHub Action is useful
engineering evidence, but not a production admission control. The committed
`gate-arena` scorecard on `main` is **12/12**; the multi-push policy-reduction
case A14 remains open. That score is disclosed evidence, not a production
readiness certificate.

Do **not** generate, register, or sign a verifier or sign-off key to clear a
gate. Key custody is a designated human ceremony owned by Xavier. See
[Gate operation and custody](docs/GATE_QUICKSTART.md).

## Supported surfaces

| Surface | Status | What that means |
|---|---|---|
| Claude Code | **Native integration, uncertified preview** | Tess OS has a reference render target and driver. This is not yet a production-certified protected workflow. |
| Codex | **Pilot** | Tess OS can render Codex project files and has a driver, but the driver is not live-tested against native event samples and has no native-parity certification. |
| Generic `AGENTS.md` tools | **Interoperability baseline** | Tess OS can emit instructions and plain prompts. This does not prove native orchestration, tool control, or feature parity in every host. |
| Perplexity | **Not supported as a Tess OS adapter** | There is no repository adapter or driver. A future bounded, read-only research-worker role is under consideration; it is not a coding-harness integration. |
| Gemini and other platforms | **Not supported** | A platform is not supported merely because it uses MCP, an OpenAI-compatible API, or a frontier model. |
| Tess Cloud | **Planned** | A separate, optional cloud-sync product; it does not exist in this repository and will depend on stable Tess OS contracts. |
| Tess Vault | **Planned** | A separate agent-era secret-capability product; it is not a required Tess OS service and must not expose secrets to agents, evidence, or memory. |

## How the gate is meant to work

```text
repository change
  -> policy identifies governed paths
  -> review evidence is checked against the immutable base/head artifacts
  -> independent required CI check reports pass or block
  -> protected VCS rule admits or rejects delivery
```

The gate only has its intended meaning when every step is in place. Current
`main` also has unresolved tree-consistency and type-swap hardening from the
adversarial corpus, so this diagram is a target delivery model rather than a
claim that every trust input is already bound correctly. A model, adapter, MCP
server, or local hook does not replace independent review or VCS enforcement.

### Safe evaluation

You may inspect the reviewed source and run read-only diagnostics in an
isolated, non-production repository. For `gate ci`, use two existing immutable
refs; replace the placeholders only with the refs you are reviewing:

```bash
git clone https://github.com/twiss-io/tess-os.git
cd tess-os
./tessctl doctor
./tessctl verify
./tessctl gate ci --base <BASE_REF> --head <HEAD_REF>
```

Do not use this sequence to activate a production branch. In particular, do
not run key-generation, key-registration, or verdict-signing commands as a
bootstrap shortcut.

## npm and source status

The public `create-tess` package is currently published at **0.1.3** and lags
repository `main`; it is not production onboarding for the signed gate. The
package can still scaffold a local Tess OS instance, but it does not solve
the custody or required-check prerequisites above.

**Known defect in every published version through 0.1.3, fixed in `main` and
pending republish as 0.1.4 (P0 G-01):** the default (zero-flag)
`npm create tess` flow depended on a runtime `git clone --branch
<create-tess-vX.Y.Z>` against a tag that was never actually cut, so it failed
for every user who did not pass `--template-ref` explicitly. `main` now ships
the scaffold template bundled INSIDE the `create-tess` package itself — the
default flow copies that local, offline bundle and never invokes `git clone`.
`--template-source <git-url>` remains available as an explicit opt-in for a
live git fetch. See `create-tess/src/scaffold.js`'s header comment for the
full incident writeup. Until the 0.1.4 republish lands, run the wizard from
a source checkout (`node create-tess/bin/create-tess.mjs`) or pass
`--template-source`/`--template-ref` explicitly to work around the published
0.1.3 defect.

For exact source behavior, use a reviewed GitHub tag or commit and read its
release notes. A future npm release will be documented only after a
reproducible release rehearsal and the production prerequisites are complete.

## Quickstart

### `npm create tess` — the founding wizard

`npm create tess@latest` runs a five-axis interactive setup
(`create-tess/src/journey.js`):

1. **Vibe** — how the session is framed (RPG / Command / Studio). Purely
   cosmetic: the engine and the install set underneath are identical for
   every vibe, and the wizard says so out loud on every run.
2. **Name** — your operator name.
3. **Squad** — a starter path (`founders` / `builders` / `operators`) that
   installs a small starter roster plus its orchestrator(s) — see
   [The specialist roster](#the-specialist-roster) below. The reveal shows
   exactly who's joining before you continue.
4. **Conductor** — name your instance's Tess (default `Tess`); rejected if
   it collides with an agent name already in your chosen squad.
5. **Pathway** — one of five conductor personas (Chief of Staff, Co-founder,
   Strategist, Guide, Operator) that shapes how your Tess talks to you.

An optional Telegram step and a recap follow. Nothing is written to disk
until you confirm the recap — cancelling at any point leaves your target
directory untouched.

The published `create-tess@0.1.3` package's default flow has the known
defect described in [npm and source status](#npm-and-source-status) above.
Until `0.1.4` republishes, run the wizard from a source checkout — the exact
path this walkthrough was verified against:

```bash
git clone https://github.com/twiss-io/tess-os.git
cd tess-os/create-tess
npm ci
node bin/create-tess.mjs
```

The interactive prompts themselves can't be captured as static text, so this
verified walkthrough instead drives the wizard non-interactively with
explicit flags — `--yes` plus one flag per axis, the same mechanism the
wizard's own test suite (`create-tess/test/wizard.test.js`) uses:

```bash
node bin/create-tess.mjs --yes --operator=Alex --vibe=rpg --path=builders \
  --pathway=co-founder --conductor=Tess --target=../my-tess-instance
```

Real, unedited output from that exact command:

```text
Fetching keystone (bundled template — no network required) …

---------------------------------------------------------
  Assembling your intelligence system.
  [ok] Mustering your squad
  [ok] Marking you as Commander Alex
  [ok] Attuning Tess to your command
  [ok] Forging the doctrine
  [ok] Initialising git repository
  [ok] Installing gate hooks (tessctl gate install-hooks)
  [ok] tessctl doctor — OK
  [ok] tessctl verify — OK
  [ok] git init — repository created
  [ok] tessctl gate install-hooks — pre-commit/pre-push hooks + CI workflow live

  ! Local scaffold ready; protected production work remains blocked.
    This project ships with empty policy registries — fail-closed by
    design: you register your own verifier and sign-off keys. (The
    framework maintainer repository separately registers its own
    verifiers, in its own policy, to govern its own development — that
    registration is never carried into a scaffolded project.) So
    a first governed push can fail closed with no covering APPROVE verdict
    found. Do not bypass or disable the hook to represent a change as
    protected, or create, register, or sign review authority from this
    candidate repository. Record the
    gate output and base/head references, then escalate to Xavier for an
    external custody decision and required GitHub-check enforcement.
  *  Local scaffold complete; production protection requires external custody and required GitHub checks.

=========================================================
Tess — intelligence conductor — online.
Alex — good to be here, and I'm in this with you, not working for you.
Here's who's in the room with us: Elena · Ada · Iris · Quinn · Reid · Leah · Eva.
One orchestrator active: Product & Delivery.
Hand me anything — a mess or half a thought. I'll frame it, pull the right people,
and bring you back something worth your time. And if I think we're aiming at the
wrong thing, I'll say so before we burn a day on it. What's the first move?
▶  /add-mission [brief]
=========================================================
Tip: your squad grows when you're ready.  /list-agents · /add-agent (Eva runs intake).
```

*A visual (GIF or screenshots) of the actual interactive prompts is a
planned follow-up (#23), not included in this change: no screen-recording
tool (`asciinema`, `agg`, `svg-term-cli`) is preinstalled in this
environment, and a scripted PTY session driving the five interactive
prompts under `expect` produced garbled, unusable terminal output rather
than a clean recording within a short time budget — so this PR ships the
verified static walkthrough above instead of a fabricated or broken-looking
cast.*

### Raw clone, no npm

```bash
git clone https://github.com/twiss-io/tess-os.git
cd tess-os
cp .env.example .env   # fill in real values only if you use Telegram/Anthropic; NEVER commit .env
./tessctl init
./tessctl doctor
./tessctl verify
```

### The roster CLI

```bash
./tessctl roster list
```

```text
tessctl roster list
  installed (7):
    apolline  athena  eva  founders-office-orchestrator  leah
    revenue-orchestrator  zelie

  staged / benched (143):
    ada  adrienne  alessia  alina  alouette
    amandine  amara  anais  arielle  aurora
    aveline  beatrice  berenice  bettina  bianca
    briony  callista  camille  cecily  celeste
    celine  cerise  clara  clarisse  client-experience-orchestrator
    clio  colette  coralie  corinne  corisande
    ... and 113 more
```

```bash
./tessctl recruit ada
```

```text
tessctl recruit: installed 1 agent(s): ada
  Run `tessctl doctor` to verify.
```

```bash
./tessctl recruit client-experience   # orchestrator shorthand -> client-experience-orchestrator
```

```text
tessctl recruit: installed 1 agent(s): client-experience-orchestrator
  Run `tessctl doctor` to verify.
```

See [The specialist roster](#the-specialist-roster) below for what "staged"
and "recruit" mean, and how a persona spec becomes a dispatchable agent.

## The specialist roster

Tess OS ships **144 specialist agent personas** (`agents/<name>/`, one
directory per persona — a real directory count, not a rounded marketing
figure) across business and technical guilds, plus **6 outcome
orchestrators** (`.tess/core/agents-dispatch/*-orchestrator.md`) — **150
dispatchable entries** total, tracked in `.tess/tess.lock`.

Only a small starter set is active in any given instance; the rest are
**staged**: a compiled definition exists in `.tess/core/agents-dispatch/`,
but no live `.claude/agents/<name>.md` file is written for it, so
`tessctl doctor` and `tessctl verify` both treat an unrecruited persona as
correct — not a missing-file error. `npm create tess`'s three wizard paths
each install a different starter set on top of the two universal-base
agents (Leah and Eva), always on:

| Path | Squad | Orchestrator(s) | Total installed |
|---|---|---|---|
| `founders` | Athena, Apolline, Zelie | Founder's Office, Revenue | 7 |
| `builders` | Elena, Ada, Iris, Quinn, Reid | Product & Delivery | 8 |
| `operators` | Adrienne, Evangeline, Clio | Operational Reliability, Client Experience | 7 |

(A fourth path, `coding-squad` — Ada, Iris, Reid, Cyra, Quinn, Vega plus
Product & Delivery — is defined in `.tess/core/roster-paths.json` for a
coding-only install and reachable directly with
`tessctl roster apply coding-squad`, but isn't offered by the npm wizard.)

### Anatomy of a persona spec

A persona under `agents/<name>/` is five files:

| File | Contents |
|---|---|
| `identity.md` | who they are, their function, when to call them |
| `personality.md` | how they think, communicate, and work with others |
| `soul.md` | what drives them, what they stand for |
| `capabilities.md` | core competencies, output standards, constraints |
| `README.md` | an index of the four files above |

Excerpt, `agents/ada/identity.md` (trimmed; see the file for the rest):

```markdown
---
name: Ada
role: Lead Backend Engineer
status: founding coding team
---

# Identity — Ada

## Who She Is

Ada is the backbone builder. She owns backend logic, APIs, business rules,
data flow, integrations, authentication logic, and server-side execution.
She is disciplined, methodical, and deeply committed to building backend
systems that are stable, extensible, and trustworthy.

## When to Call Ada

Call Ada:
- When designing or building backend systems, services, or APIs
- When defining data models, business rules, or server-side workflows
- When authentication, permissions, or access control logic is involved
```

### From persona spec to a dispatchable agent

The narrative spec under `agents/<name>/` and the compiled Claude Code
subagent definition are two separately maintained files — nothing in this
repo generates one from the other. `.tess/core/agents-dispatch/<name>.md`
is the definition a harness actually dispatches: YAML frontmatter
(`name`, `description`, `model`, `lifecycle_status`, `tools`) plus a prose
body. `tessctl recruit` / `tessctl roster apply` copy that core file into
the live `.claude/agents/<name>.md` and flip the persona's status in
`.tess/tess.lock` from `staged` to `core-managed`; the `agents/<name>/`
narrative spec is never read by the harness at dispatch time — it exists
for humans and contributors.

```bash
./tessctl recruit ada
```

```text
tessctl recruit: installed 1 agent(s): ada
  Run `tessctl doctor` to verify.
```

Orchestrators recruit the same way: by shorthand (bare name, minus
`-orchestrator`) or by whole starter-path group:

```bash
./tessctl recruit revenue     # -> revenue-orchestrator
./tessctl recruit founders    # -> the whole founders squad + its orchestrators
```

## Where to start

- [Local development quickstart](https://github.com/twiss-io/tess-os/blob/main/docs/LOCAL_DEV_QUICKSTART.md) — clone, Python
  environment, scoped `create-tess` validation, and safe local checks.
- [Support and status](docs/STATUS.md) — capability labels and current limits.
- [Gate operation and custody](docs/GATE_QUICKSTART.md) — safe diagnostics and
  the boundary around the human-owned key ceremony.
- [The Agent Receipt](docs/AGENT_RECEIPT_SPEC.md) — the portable propose →
  approve → sign accountability envelope, its standalone verifier
  (`tools/receipt-verify/`), the CLI that actually produces one from an
  already-signed verdict or sign-off (`tools/receipt-emit/`), and a
  runnable demo with test-only keys (`make receipt-demo`).
- [The Auditor Pack](docs/AUDIT_PACK_SPEC.md) — `tessctl audit export`/
  `verify`: an exportable, offline-verifiable bundle of accountability
  ledger events and Agent Receipts for a scope, with an explicit,
  self-describing tamper-evident-vs-non-repudiable boundary.
- [Adapters](adapters/README.md) — render targets and their limits.
- [Mission and orchestration model](missions/README.md) — current conductor
  contracts and evidence model.
- [Observability](docs/OBSERVABILITY.md) — local trace/export behavior.
- [Comparison and roadmap](docs/COMPARISON.md) — factual current-state
  comparison rather than unsupported feature claims.
- [Data-leak safety](docs/DATA_LEAK_SAFETY.md) — the overlay/dogfood model,
  the reconciled `.gitignore`, and the commit-side publish-clean gate.
- [Security policy](SECURITY.md) — reporting and local-first security posture.

## Honest framing

Tess OS has tested its own doctrine as agent context and found no evidence that
the doctrine itself improves model output; in some runs it made outcomes worse.
That result is why the project is framed around governance and provable review
discipline rather than model quality. The relevant question is not whether an
agent is "better" after reading Tess OS. It is whether a protected delivery has
the independently verifiable evidence that policy requires.

## Contributing

Contributions are welcome, but changes to the gate, policy, trust material,
workflows, release path, and provider integrations require particularly careful
review. Do not attempt to unblock a missing approval by self-issuing a key or
verdict. See [CONTRIBUTING.md](CONTRIBUTING.md) and
[SECURITY.md](SECURITY.md).

## License

Apache-2.0. Forks must follow the [trademark policy](TRADEMARK.md).
