# Tess OS

[![License: Apache-2.0](https://img.shields.io/github/license/twiss-io/tess-os)](LICENSE)
[![create-tess on npm](https://img.shields.io/npm/v/create-tess?label=create-tess)](https://www.npmjs.com/package/create-tess)
[![Latest release](https://img.shields.io/github/v/release/twiss-io/tess-os)](https://github.com/twiss-io/tess-os/releases)
[![CI](https://img.shields.io/github/actions/workflow/status/twiss-io/tess-os/ci.yml?label=CI)](https://github.com/twiss-io/tess-os/actions/workflows/ci.yml)

> **Status: technology preview. Do not use the current release or `main` to protect production merges.**

**Your own AI, not a subscription to someone else's assistant. It keeps a
plain record of what happened — and can prove what a change went through
before it shipped.**

Run the wizard and you get a local instance: a conductor you name, one of
five pathways for how it shows up — Chief of Staff, co-founder, strategist,
guide, operator — and a crew drawn from a roster of 150 specialists, all
running on your own machine, in your own git repo, under an Apache-2.0
license. Every mission and gate decision leaves a plain-file, hash-chained
trail under `.tess/state/` that you can read yourself, no proprietary memory
store to trust blindly. And when a change needs a "prove it," Tess OS can
hand you a real [Agent Receipt](docs/AGENT_RECEIPT_SPEC.md) — signed,
chain-linked, and designed to be checked by a standalone verifier that
doesn't take Tess OS's own word for it. That verifier runs today; the current
policy registers Cyra's public verifier key, while private-key custody and
covering approval remain external to the repository and the sign-off registry
is still empty. See [Important limits today](#important-limits-today) before
treating a receipt as a production trust guarantee.

None of that makes the underlying model smarter. Tess OS is a local
governance and review harness for work produced by coding agents. It records
policy and review evidence around repository changes, then can run a gate
before a protected delivery step.

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

## See it

![Tess OS -- create-tess wizard and Agent Receipt demo](docs/demo/tess-demo.svg)

A real, unedited terminal recording, not a mockup. It runs `npm create
tess`'s five-axis wizard end to end — vibe, operator name, starter squad,
conductor name, pathway — through the actual post-bake `tessctl
doctor`/`tessctl verify` checks and the conductor's in-voice arrival
greeting, then the Agent Receipt "show me the receipt" demo (propose →
approve → sign → journal → verify, plus a tamper rejection). How it was
recorded, and how to reproduce it, is in [docs/demo/](docs/demo/README.md).

## Important limits today

Tess OS is deliberately fail-closed when no covering approval exists. The
current policy registers Cyra's public verifier key; `signoff_keys` remains
empty. A message such as **"no covering APPROVE verdict found"** is an
expected block, not an invitation to create a key, sign the candidate's own
work, or work around the gate.

The live GitHub `main` ruleset now requires the App-bound `tessctl gate ci`
check and the repository's CI checks with strict up-to-date-branch enforcement
(verified 2026-08-22). That external rule is an active control, not a remaining
setup step.

Production limitations remain:

1. The registered verifier's private-key custody and every covering approval
   must remain independent of candidate repository content; a producer still
   cannot clear its own work.
2. The human sign-off registry is empty, so Rule-18 hard-floor actions remain
   unavailable through repository evidence alone.
3. Multi-push policy reduction remains a disclosed, untested adversarial case.

Until both are complete, a passing local command or GitHub Action is useful
engineering evidence, but not a production admission control. The committed
`gate-arena` scorecard on `main` reports **12/12 attacks blocked**.
Multi-push policy reduction is a disclosed but untested case, and is not
included in that score. The score is disclosed evidence, not a
production-readiness certificate.

Do **not** generate, register, or sign an additional verifier or sign-off key
to clear a gate, and never use the registered verifier to approve its own
candidate. Key custody is a designated human ceremony owned by Xavier. See
[Gate operation and custody](docs/GATE_QUICKSTART.md).

## Supported surfaces

| Surface | Status | What that means |
|---|---|---|
| Claude Code | **Preview** | Tess OS has a reference render target and driver. This is not yet a production-certified protected workflow. |
| Codex | **Preview** | Tess OS can render Codex project files and has a driver, but the driver is not live-tested against native event samples and has no native-parity certification. |
| Generic `AGENTS.md` tools | **Preview** | Tess OS can emit instructions and plain prompts. This does not prove native orchestration, tool control, or feature parity in every host. |
| Perplexity | **Unsupported** | There is no repository adapter or driver. A future bounded, read-only research-worker role is under consideration; it is not a coding-harness integration. |
| Gemini and other platforms | **Unsupported** | A platform is not supported merely because it uses MCP, an OpenAI-compatible API, or a frontier model. |
| Agent Execution Contract governance defaults | **Planned** | The C/T assurance, local-data, zero-spend, credential, retention, Cloud, Memory, and Vault defaults are accepted as a non-enforcing contract; runtime grading and enforcement are not implemented. See [AEC governance defaults](docs/AEC_GOVERNANCE_DEFAULTS.md). |
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

## Quickstart

### Option A — `npm create tess`

```bash
npm create tess@latest my-os
cd my-os
```

This runs the interactive wizard through five axes: a **vibe** (Guild /
Tactical / Studio — reskins the language, not the power underneath), your
**name**, a **starter squad** (`founders` / `builders` / `operators`), your
**conductor's name**, and how it should **show up in the room** (Chief of
Staff / Co-founder / Strategist / Guide / Operator). It then bakes the
instance, runs `tessctl doctor`/`tessctl verify`, and the conductor greets
you by name — see [See it](#see-it) above for the real recording.

For CI or a non-interactive setup, pass every axis as a flag:

```bash
npm create tess@latest my-os -- --yes \
  --operator="Alex" --vibe=studio --path=builders \
  --conductor="Atlas" --pathway=co-founder
```

**Verified 2026-07-23:** the P0 zero-flag `git clone` bug (present through
`0.1.3`) is fixed and published as `0.1.4` — see
[npm and source status](#npm-and-source-status) for the full incident
writeup.

### Option B — clone the source

```bash
git clone https://github.com/twiss-io/tess-os.git
cd tess-os
cp .env.example .env        # fill in real values; .env is gitignored, never committed
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements-dev.txt
./tessctl init
```

`tessctl init` restores the managed tree from `.tess/core`, renders
`CLAUDE.md`/`AGENTS.md`/`.codex/` from templates, and creates the working
`.tess/state/` directories — same command documented in full, with the test
suite, in [docs/LOCAL_DEV_QUICKSTART.md](docs/LOCAL_DEV_QUICKSTART.md).

### Everyday `tessctl` commands

Real output, from a fresh clone:

```console
$ ./tessctl doctor
tessctl doctor — 1033 files checked
  ok          .tess/core/MANIFEST.md
  ok          .tess/core/personas/chief-of-staff.md
  ...
============================================================
pristine: 890  |  staged (benched): 143  |  uncaptured drift: 0  |  captured: 0  |
quarantined: 0  |  core tamper: 0  |  security alerts: 0

doctor: OK

$ ./tessctl verify
============================================================
ok: 1033  |  staged warns: 0  |  core tampers: 0  |  security drifts: 0  |
live drifts: 0  |  missing live files: 0  |  quarantined: 0  |  doctrine leaks: 0

verify: OK — core integrity confirmed; no security-tier tampering; live matches core

$ ./tessctl roster list
  installed (7):
    apolline  athena  eva  founders-office-orchestrator  leah
    revenue-orchestrator  zelie

  staged / benched (143):
    ada  adrienne  alessia  alina  alouette
    amandine  amara  anais  arielle  aurora
    ... and 113 more

$ ./tessctl recruit reid
tessctl recruit: installed 1 agent(s): reid
  Run `tessctl doctor` to verify.
```

`doctor` checks every managed file against expected state and flags
security-tier drift; `verify` checks `.tess/core` bytes against their
recorded `base_sha` and flags tampering. Neither one makes a branch
protected — see [Important limits today](#important-limits-today).
`recruit`/`bench` move an agent between the bench and installed — see
[The specialist roster](#the-specialist-roster) next.

## The specialist roster

`npm create tess` doesn't hand you an empty framework — it hands you a crew.
**150 dispatchable specialists in this repository: 144 individual personas**
(`agents/`) **plus 6 outcome orchestrators**
(`conductor/outcome-orchestrators/`) that route work across them. Nobody runs
with all 150 active — each starter path installs a small squad plus a
universal base (Leah — research, Eva — talent/recruiting) and stages
everyone else on the bench:

| Path | Squad | Orchestrators |
|---|---|---|
| `founders` | Athena — Chief Strategy Officer · Apolline — Chief Sales Strategist · Zélie — Presentation & Deck Design | Founder's Office · Revenue |
| `builders` | Elena — Product Engineer · Ada — Lead Backend Engineer · Iris — Lead Frontend Engineer · Quinn — QA & Reliability Architect · Reid — Code Quality & Standards | Product & Delivery |
| `operators` | Adrienne — Chief of Staff & Executive Operations · Evangeline — Chief Customer Experience Strategist · Clio — Session Scribe | Operational Reliability · Client Experience |

### From spec to dispatch

139 of 144 personas live as a 5-file spec under `agents/<name>/`:
`README.md`, `identity.md`, `personality.md`, `soul.md`, `capabilities.md`.
That's a floor, not a ceiling: the other 5 carry one or more additional
files — Leah and Eva each add a `governance.md`, Eva also adds
`hiring-framework.md` and `agent-profile-template.md`, and Clio, Petra, and
Reid run leaner (1-2 files each). Once recruited, every persona compiles
down to a single `.claude/agents/<name>.md` dispatch file: YAML frontmatter
(`name`, `description`, `model`, `lifecycle_status`, `tools`) plus the
merged spec body Claude Code actually reads at dispatch time.

Take Leah, the universal-base researcher installed on every path, as a real
example. Here's the spec:

```
agents/leah/
├── README.md         "Leah ensures the team never operates on incomplete,
│                       shallow, or unchallenged information."
├── identity.md        who she is, her function, when to call her
├── personality.md     how she thinks, communicates, works with others
├── soul.md            what drives her, what she stands for
├── capabilities.md    the 9-section research-output format, hard constraints
└── governance.md      core mandate, research protocol, and escalation rules —
                        the one extra file beyond the 5-file floor (202 lines)
```

compiles to `.claude/agents/leah.md`:

```yaml
---
name: leah
description: Senior Researcher & Intelligence Lead. Invoke at the start of
  every mission, before any other specialist moves. Use whenever the team is
  operating on thin or untested information...
model: sonnet
lifecycle_status: core
tools: Read, Write, Glob, Grep, WebSearch, WebFetch
---
```

Ada, Lead Backend Engineer on the `builders` squad, is the opposite case: her
spec under `agents/ada/` is just as complete, but there's no
`.claude/agents/ada.md` in a fresh `founders`-path install. She's on the
bench until you recruit her.

### Bench vs. active

```console
$ ./tessctl recruit reid
tessctl recruit: installed 1 agent(s): reid
  Run `tessctl doctor` to verify.

$ ./tessctl roster list
  installed (8):
    apolline  athena  eva  founders-office-orchestrator  leah
    reid  revenue-orchestrator  zelie
```

`recruit` accepts an exact name (`ada`), an orchestrator shorthand (`revenue`
→ `revenue-orchestrator`), or a whole path group (`founders` → squad +
orchestrators). `bench` reverses it — moves an agent back to staged and
removes its live dispatch file. Either way, the underlying spec under
`agents/<name>/` is untouched; only the compiled, dispatchable copy changes.

## npm and source status

The public `create-tess` package is published at **0.1.4** (2026-07-21),
matching this repository's `create-tess/package.json`.

**Fixed and verified (2026-07-23), P0 G-01:** every published version
through `0.1.3` had the default (zero-flag) `npm create tess` flow depend on
a runtime `git clone --branch <create-tess-vX.Y.Z>` against a tag that was
never actually cut — it failed for every user who didn't pass
`--template-ref` explicitly. `0.1.4` bundles the scaffold template inside the
`create-tess` package itself; the default flow now copies that local,
offline bundle and never invokes `git clone`. Confirmed by running both
`npx create-tess@latest` and `npm create tess@latest` fresh against the live
npm registry — no flags, no workaround needed. `--template-source
<git-url>` remains available as an explicit opt-in for a live git fetch. See
`create-tess/src/scaffold.js`'s header comment for the full incident
writeup.

`create-tess/template/` — what actually gets copied into a scaffolded
project — is a full mirror of this repository's tree, rebuilt automatically
before every `npm pack`/`npm publish`. It can still move a little ahead of
whatever the last publish captured (as of this writing, two commits have
touched the bundled template since the `0.1.4` publish, both mirroring
unrelated orchestrator/receipt-hardening work, not the wizard itself). For
the exact current state, use a reviewed GitHub tag or commit, or the
source-checkout path above.

This publish is documented here because its specific, previously-broken
behavior was independently re-verified against the live registry, not
asserted from the changelog alone. Future releases will be documented the
same way.

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
- [Demo recording](docs/demo/README.md) — how the terminal recording above was
  made and how to reproduce it.
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
