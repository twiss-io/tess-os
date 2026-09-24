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
guide, operator — and a crew of nine roles plus a library of about 140 expertise lenses, all
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

A real, unedited terminal recording of the `create-tess` v0.2.0 wizard, not a mockup.
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
3. **The gate is a non-authoritative preview.** The P0 type-swap gate
   bypass (#71 lineage; its fix #181 is deferred to v0.2.1) and the A14
   multi-push policy-reduction case are still open, and the merge-admission
   topology (#76) is undecided.
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
differs, and this table is the claim. It is not a parity claim.

- **Enforced:** the runtime loads the Tess doctrine natively and runs Tess's
  shipped hooks, so a blocking hook stops the tool call.
- **Partial:** the doctrine loads natively and some enforcement exists (the
  runtime's own sandbox or approval settings rendered by Tess, or Tess's
  Claude hooks read by a compatible runtime), with documented gaps or
  fail-open cases.
- **Advisory:** the runtime can read the doctrine as text. Nothing Tess
  ships can block a tool call there.

A level covers in-session enforcement only. The ship gate runs in git (the
pre-push hook, once installed) and in CI, outside every runtime, so it
applies whichever tool made the change. The levels match
[adapter conformance](adapters/CONFORMANCE.md), which records the evidence
and documentation links for each runtime.

| Runtime | Enforcement | How Tess OS reaches it | Main limits |
|---|---|---|---|
| Claude Code | **Enforced** | Reference `claude-code` target: `CLAUDE.md`, `.claude/agents`, `.claude/commands`, and the Tess hooks in `.claude/settings.json`. | The shipped hooks run natively (`dispatch-guard` only warns, by design). The merge gate is still a preview (see [Important limits today](#important-limits-today)). |
| Codex CLI | **Partial** | `codex` target: `AGENTS.md`, `.codex/config.toml`, and the Tess commands as `.agents/skills/tess-*` skills (`$tess-<command>`). | Enforcement is Codex's own sandbox and approval settings from the rendered `.codex/config.toml`, which Codex loads only for a trusted project. No Tess hook runs inside Codex in 0.2.0. The `AGENTS.md` chain is capped at 32 KiB. |
| Gemini CLI | **Advisory** | `gemini` target: `GEMINI.md`, which imports `AGENTS.md`, and the Tess commands as `/tess:<command>`. | The doctrine and commands load natively, but only in a trusted folder. Nothing Tess ships can block a tool call in Gemini: no Tess hook, setting or policy is rendered for it in 0.2.0, so the ship gate in git and CI is the only enforcement. No live model run was part of the v0.2.0 checks. |
| GitHub Copilot CLI, Cursor | **Partial** (through the Claude-compatible files) | No dedicated target. Both read `CLAUDE.md`, `AGENTS.md`, `.claude/agents`, and the Claude hooks. | Not tested by Tess OS. Copilot hook timeouts fail open; Cursor fails open on hook crashes and timeouts. Both load the doctrine twice. |
| Other `AGENTS.md` tools (for example OpenCode, Amp, Devin Desktop, Jules, Aider, Kiro, Qwen Code) | **Advisory** | The `AGENTS.md` doctrine text (Aider needs `read: [AGENTS.md]` in its config). | Nothing Tess ships can block a tool call there. |
| Cline, Roo Code, and any runtime not listed here | **unverified** | — | Not verified for this release. Using a frontier model, MCP, or an OpenAI-compatible API does not make a runtime supported. |

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
**name**, a **starter path** (`founders` / `builders` / `operators`; every path installs the same ten roles and only changes the suggested lenses), your
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
  installed (9):
    ada  clio  cyra  iris  leah
    morwenna  quinn  reid  vega

  staged / benched (0):
    (none)
```

`doctor` checks every managed file against expected state and flags
security-tier drift; `verify` checks `.tess/core` bytes against their
recorded `base_sha` and flags tampering. Neither one makes a branch
protected — see [Important limits today](#important-limits-today).
`recruit`/`bench` move a role between staged and installed — see
[The roster](#the-roster-ten-roles-and-a-lens-library) next.

## The roster: ten roles and a lens library

The roster is the same for every use case (personal, agency, organisation):
**ten roles, defined by permissions, model tier and isolation, not by
expertise.** Every starter path installs all of them.

| # | Role | Name | Permissions | Model tier |
|---|---|---|---|---|
| 1 | Conductor | Tess (you rename it in the wizard) | The main session: plans, loads lenses, dispatches. Not an agent file. | session model |
| 2 | Builder | Ada | Full tools; commits on a feature branch; no push or merge | default |
| 3 | Explorer | Morwenna | Read-only search and mapping | cheaper (haiku) |
| 4 | Researcher | Leah | Read-only plus web; cites every source | strong |
| 5 | Code reviewer | Reid | Read-only; mandatory verifier for diffs | strong |
| 6 | QA | Quinn | Runs tests; no source edits, no push or merge | strong |
| 7 | Security + approval signer | Cyra | Read-only review; signs verdicts with `tessctl verdict sign` | strong |
| 8 | Scribe | Clio | Writes only to the brain paths; every claim links to its source | default |
| 9 | Release / devops | Vega | Push, tag, publish — only behind the gate | default |
| 10 | Designer | Iris | Frontend and design, with the design skills attached | default |

Every dispatched role carries the line *"You are a dispatched specialist:
execute directly, never re-delegate or spawn agents."* Only the conductor
dispatches. Claude Code reads the nine role files from `.claude/agents/`; the
Codex render target compiles the same files to `.codex/agents/<name>.toml`
(with a `sandbox_mode` taken from each role).

### Lenses

The roster used to be 150 dispatchable personas. About 140 of them
(strategists, the six outcome orchestrators, Eva, Verity, Maialen, Lysandra
and the guild specialists) are now **lenses** in `conductor/lenses/` — short
expertise briefs the conductor adds to a role's dispatch when a task needs
them (`Lens: conductor/lenses/naomi.md`). A lens never widens a role's
permissions, and lenses are never registered as agents. Full index:
[docs/LENSES.md](docs/LENSES.md). The long-form persona specs stay under
`agents/<name>/` as the lens source.

The starter path only changes which lenses the conductor suggests first:

| Path | Suggested lenses |
|---|---|
| `founders` | Founder's Office, Revenue, Athena, Apolline, Naomi, Sienna, Zélie |
| `builders` | Product and Delivery, Elena, Freya, Petra, Selene, Joséphine |
| `operators` | Operational Reliability, Client Experience, Adrienne, Evangeline, Joséphine, Corinne |

Seats in your organisation (a CFO, a client lead) are brain entities, never
agents. Doctrine: `conductor/roster.md`.

### Staged vs. installed

`tessctl roster apply <path>` installs the nine roles. `tessctl bench <name>`
stages one (removing its live file) and `tessctl recruit <name>` brings it
back. Benching Reid, Quinn or Cyra removes a mandatory verifier, so do it
only with a reason.

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
