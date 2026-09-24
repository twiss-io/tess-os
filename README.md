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
doesn't take Tess OS's own word for it. That verifier runs today. This
repository's policy registers one verifier key (Cyra). For v0.2.0 that key
was held by an agent on the build machine, not by a human custodian, and the
sign-off registry is still empty. See
[Important limits today](#important-limits-today) before treating a receipt
as a production trust guarantee.

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
- A Codex render target (enabled by default) that produces `AGENTS.md`,
  `.codex/config.toml`, and the Tess commands as `.agents/skills/tess-*`
  skills (invoked as `$tess-<command>`); a Codex driver also exists.
- A Gemini CLI render target (enabled in new installs) that produces a
  `GEMINI.md` importing `AGENTS.md`, and the Tess commands as
  `/tess:<command>` custom commands.
- An opt-in generic target that produces `AGENTS.md` and plain prompt files.
- A local, sequential `tessctl run` conductor loop with mission gates, return
  artifact validation, bounded retries, and escalation.
- Local JSONL traces for selected gate and validation commands, with an
  operator-run OpenTelemetry JSON export.

These are current repository capabilities, not equivalent provider support
claims. Each runtime gets a different enforcement level; see
[Runtimes and enforcement](#runtimes-and-enforcement) and the
[support and status guide](docs/STATUS.md) before deciding whether an
integration fits a particular workflow.

## See it

![Tess OS -- create-tess wizard and Agent Receipt demo](docs/demo/tess-demo.svg)

A real, unedited terminal recording of `create-tess` 0.1.x, not a mockup.
It runs `npm create tess`'s five-axis wizard end to end — vibe, operator
name, starter squad, conductor name, pathway — through the actual post-bake
`tessctl doctor`/`tessctl verify` checks and the conductor's in-voice arrival
greeting, then the Agent Receipt "show me the receipt" demo (propose →
approve → sign → journal → verify, plus a tamper rejection). How it was
recorded, and how to reproduce it, is in [docs/demo/](docs/demo/README.md).

## Important limits today

Tess OS is deliberately fail-closed when no covering approval exists. This
repository's policy registers one verifier key (Cyra); `signoff_keys` remains
empty. A fresh `npm create tess` scaffold starts with both registries empty. A
message such as **"no covering APPROVE verdict found"** is an expected block,
not an invitation to create a key, sign the candidate's own work, or work
around the gate.

Facts for v0.2.0, re-verified on 2026-09-24:

1. **The v0.2.0 approvals were signed with an agent-held key.** The Cyra
   verifier key has no passphrase and sits on the build machine. An agent
   that did not build the change reviewed each protected change and signed
   the verdict with that key. No key was rotated for this release. Moving
   the key to human custody is planned for v0.2.1.
2. **"Only reviewed changes merge" is a process rule, not a GitHub
   guarantee.** The `main` ruleset requires six status checks, including the
   App-bound `tessctl gate ci`, with strict up-to-date branches and no bypass
   actors. It requires 0 approving reviews, and the GitHub token the build
   agents use has admin rights on the repository.
3. **The gate is a non-authoritative preview.** The P0 type-swap bypass
   (the #71 hardening) and the A14 multi-push policy-reduction case are
   still open, and the merge-admission topology (#76) is undecided.
4. **The human sign-off registry is empty**, so Rule-18 hard-floor actions
   remain unavailable through repository evidence alone.

Until those are resolved, a passing local command or GitHub Action is useful
engineering evidence, not a production admission control. The committed
`gate-arena` scorecard on `main` reports **12/12 attacks blocked**. A14 is a
disclosed but untested case and is not included in that score. The score is
disclosed evidence, not a production-readiness certificate. Full detail:
[Support and status](docs/STATUS.md).

Do **not** generate, register, or sign an additional verifier or sign-off key
to clear a gate, and never use the registered verifier to approve its own
candidate. Key custody belongs to a designated human custodian. See
[Gate operation and custody](docs/GATE_QUICKSTART.md).

## Runtimes and enforcement

Tess OS runs natively on Claude Code, Codex and Gemini CLI, plus any
AGENTS.md-compatible tool. How much of Tess each runtime can actually enforce
differs, and this table is the claim. It is not a parity claim. **Enforced**
means the full Tess session hook set runs inside the runtime. **Partial**
means the runtime loads the Tess doctrine and commands natively but runs few
or none of the Tess session hooks. **Advisory** means it reads the doctrine
text only. In every case the repository's git hooks (once installed) and
the CI gate still apply. The levels match
[adapter conformance](adapters/CONFORMANCE.md), which records the evidence
for each.

| Runtime | Enforcement | How Tess OS reaches it | Main limits |
|---|---|---|---|
| Claude Code | **Enforced** | Reference `claude-code` target: `CLAUDE.md`, `.claude/agents`, `.claude/commands`, and the Tess hooks in `.claude/settings.json`. | The session hooks run natively; the merge gate is still a preview (see [Important limits today](#important-limits-today)). |
| Codex CLI | **Partial** | `codex` target: `AGENTS.md`, `.codex/config.toml`, and the Tess commands as `.agents/skills/tess-*` skills. | No Tess session hook runs inside Codex in 0.2.0; the gate runs at git pre-push and in CI. Codex reads `.codex/config.toml` only in a trusted project, and caps the `AGENTS.md` chain at 32 KiB. |
| Gemini CLI | **Partial** | `gemini` target: `GEMINI.md`, which imports `AGENTS.md`, and the Tess commands as `/tess:<command>`. | No Tess session hook runs inside Gemini CLI in 0.2.0; the gate runs at git pre-push and in CI. Gemini loads these files only in a trusted folder. No live model run was part of the v0.2.0 checks. |
| GitHub Copilot CLI, Cursor | **Partial** (through the Claude-compatible files) | No dedicated target. Both read `CLAUDE.md`, `AGENTS.md`, `.claude/agents`, and the Claude hooks. | Not tested by Tess OS. Copilot hook timeouts fail open; Cursor fails open on hook crashes and timeouts. Both load the doctrine twice. |
| Other `AGENTS.md` tools (for example OpenCode, Amp, Jules, Kiro) | **Advisory** | The `AGENTS.md` doctrine text only. | No Tess commands or session hooks in the tool. The git hooks and CI gate still apply to the repository. |
| Any runtime not listed here | **unverified** | — | Not assessed. Using a frontier model, MCP, or an OpenAI-compatible API does not make a runtime supported. |

## Other surfaces

| Surface | Status | What that means |
|---|---|---|
| Perplexity | **Unsupported** | There is no repository adapter or driver. A future bounded, read-only research-worker role is under consideration; it is not a coding-harness integration. |
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

The default flow copies a template bundled inside the npm package; it does
not clone anything. See [npm and source status](#npm-and-source-status) for
which version npm serves.

### Option B — clone the source

```bash
git clone https://github.com/twiss-io/tess-os.git
cd tess-os
cp .env.example .env        # fill in real values; .env is gitignored, never committed
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements-dev.txt
./tessctl init
```

`tessctl init` restores the managed tree from `.tess/core`, renders the
enabled targets (for example `CLAUDE.md`, `AGENTS.md` and `.codex/`) from
templates, and creates the working
`.tess/state/` directories — same command documented in full, with the test
suite, in [docs/LOCAL_DEV_QUICKSTART.md](docs/LOCAL_DEV_QUICKSTART.md).

### Everyday `tessctl` commands

Example output from a fresh clone. File and agent counts change between
versions:

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

This README describes Tess OS **v0.2.0**. On 2026-09-24, when this section
was last checked, npm served `create-tess` **0.1.4**. `create-tess` 0.2.0 is
published only after the release checks pass: a real over-the-wire upgrade
from the signed `v0.2.0` tag, a fresh install from that tag, and
`git verify-tag`. Run `npm view create-tess version` to see what npm serves
now.

Since `0.1.4`, `create-tess` bundles the scaffold template inside the npm
package, and the default flow copies that bundle instead of running
`git clone`. `--template-source <git-url>` remains an explicit opt-in for a
live git fetch. `create-tess/template/` is a mirror of this repository's
tree, rebuilt before every `npm pack`/`npm publish`. For an exact state, use a
reviewed, signed GitHub tag or the source-checkout path above.

## Upgrading

Upgrades come from a signed git tag. `tessctl` checks the tag against the
release key pinned in `.tess/tess.lock`
(`framework.trusted_key_fingerprint`), inside an isolated keyring.

1. Import the release public key once. `tessctl` reads the pinned key from
   your keyring:

   ```sh
   gpg --import .tess/keys/twiss-release-key.asc
   ```

2. Update the engine first, then the framework, then check the result:

   ```sh
   ./tessctl self-update --ref v0.2.0
   ./tessctl update --ref v0.2.0
   ./tessctl doctor
   ./tessctl verify
   ```

`update` writes only paths that your `tess.manifest.json` owns. An install
made with `create-tess` 0.1.4 lists `.agents/**` under `never_touch`, so
`update` skips the new Codex skills as `skipped:not-owned` and prints the glob
to add. To opt in, add these lines to `owned_globs` in `tess.manifest.json`:

```text
".agents/skills/tess-*/**",
".gemini/commands/tess/**",
"GEMINI.md"
```

The first line is for the Codex skills. The other two are for the Gemini CLI
target, which also needs `"gemini"` in `render_targets.enabled`. Then run
`./tessctl render`. A render output you edited by hand is not overwritten;
`tessctl` reports it as skipped and names the reason.

Adopting an existing Tess instance that was not installed by `create-tess`
is not supported in 0.2.0. Start from a fresh install.

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
