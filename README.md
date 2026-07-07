# Tess OS

[![License: Apache-2.0](https://img.shields.io/github/license/twiss-io/tess-os)](LICENSE)
[![create-tess on npm](https://img.shields.io/npm/v/create-tess?label=create-tess)](https://www.npmjs.com/package/create-tess)
[![Latest release](https://img.shields.io/github/v/release/twiss-io/tess-os)](https://github.com/twiss-io/tess-os/releases)
[![CI](https://img.shields.io/github/actions/workflow/status/twiss-io/tess-os/ci.yml?label=CI)](https://github.com/twiss-io/tess-os/actions/workflows/ci.yml)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![GitHub Discussions](https://img.shields.io/github/discussions/twiss-io/tess-os)](https://github.com/twiss-io/tess-os/discussions)

**Not an agent. A chief of staff with a staff.**

Tess OS is an orchestration-first **agent operating system** for Claude Code. Not
one assistant that grows with you — a *governed organization* of specialists. A
single conductor (**Tess**) takes in work, routes it through six outcome
orchestrators, and dispatches it to specialist subagents organized into guilds,
under enforced dependency gates, mandatory adversarial verification, and a typed
retry protocol.

It ships with an in-place **framework upgrade engine** (`tessctl`) so new
framework versions fold into an instance you — and your agents — have been
editing live, instead of being clobbered by a re-scaffold.

> Tess OS is a doctrine + roster + config scaffold plus an upgrade engine. It is
> not a running application — you bring Claude Code and your own credentials.

The framing: **Tess OS is the council *and* your trusted assistant** — the
conductor you talk to, backed by a staff you can grow. The wizard, the roster, the
upgrade engine, and the vault are the first pieces of that suite.

**Try it in one command** (full walkthrough in [Quickstart](#quickstart--npm-create-tess) below):

```bash
npm create tess@latest
```

⭐ **If Tess OS is useful to you, consider [starring the repo](https://github.com/twiss-io/tess-os)** — it helps other people find it.

<!--
  DEMO PLACEHOLDER — add a screenshot or GIF of the `npm create tess` first-run
  wizard here (the 5-axis gamified onboarding and the conductor's first greeting).
  Suggested asset path: docs/assets/wizard-demo.gif
  Do not commit a fake/placeholder image — wire in the real recording when ready.
-->

> **Official repository.** `github.com/twiss-io/tess-os` is the canonical,
> official home of Tess OS. Forks are welcome under Apache-2.0 — but a fork is
> **not** official, not endorsed, and must follow the [trademark
> policy](TRADEMARK.md): build on the code freely, but **rebrand** (you may say
> "built with Tess OS", you may not name your fork "Tess OS").

---

## Quickstart — `npm create tess`

The front door is a gamified first-run wizard. You don't fill in a config file —
you *arrive*:

```bash
npm create tess@latest
```

Five choices, then the conductor greets you in-voice with a first mission open:

| Axis | What you pick |
|---|---|
| **Name** | what the conductor calls you (the operator) |
| **Vibe** | the world / narrative skin — `rpg`, `command`, or `studio` |
| **Squad** | a starter crew of *real* agents — Founder, Builder, or Operator |
| **Conductor** | name your conductor (default: Tess) |
| **Pathway** | how the conductor speaks — chief-of-staff, co-founder, strategist, guide, or operator |

The wizard stages the template into a temp dir first, validates your choices
against the real roster, and only then promotes it into your target — **cancel
leaves zero state behind**. On confirm it drives the keystone (`roster apply →
set-operator → rename → pathway → render`), runs `doctor` + `verify`, and prints
the conductor's first greeting in the persona's voice.

Prefer it raw? The runtime artifact is just the git template — a fresh clone
works because Claude reads the doctrine directly and the engine is committed:

```bash
git clone https://github.com/twiss-io/tess-os.git mind && cd mind
./tessctl init        # write the lock + manifest + operator stubs, render CLAUDE.md
cp .env.example .env  # then fill in your own values
claude                # Tess reads CLAUDE.md as the entry point
```

---

## Why it's different

Two compounding ideas, each defensible on Tess OS's own architecture:

1. **Coordination depth under enforced governance.** The unit of work is not a
   prompt; it's a *mission* routed through an outcome orchestrator and dispatched
   to a crew. Every dispatch carries a six-field brief contract. Mission flow is
   governed by dependency gates (intake → research → crew → build → review →
   verification), never a fixed clock; independent work runs in parallel. Nothing
   externally visible ships without a mandatory verifier reading the primary
   artifacts. Failed work is retried with a *changed* brief, at most three times,
   then escalated.

2. **In-place upgradeability of the framework.** Most scaffold-first tools own
   generated files once and have no upstream merge — a re-run overwrites your
   edits. Tess OS keeps a committed pristine copy of the framework as a merge
   base (`.tess/core/`), records a per-file status in `tess.lock`, and a 3-way
   merge folds each new *framework* version into your live tree. The engine is
   snapshot-first, hard-gates on `tessctl doctor`, halts the whole update on a
   conflict (nothing is overwritten), and quarantines security-tier files.

---

## `tess update` — upgrade in place, non-destructively

```bash
./tessctl update      # snapshot → doctor gate → 3-way merge new framework → re-pin
```

The whole point: you can adopt Tess OS, edit it heavily for months, and still pull
a newer *framework* version without losing your edits. The engine snapshots first,
refuses to start if `doctor` isn't clean, 3-way-merges each framework file, and
**halts the entire update on the first conflict** — nothing is overwritten behind
your back. Security-tier files are quarantined for explicit approval.

> Scope, stated honestly: "upgrade in place" covers **framework files** —
> doctrine, agents, commands, hooks, skills, and the client *template*. It does
> not auto-migrate client folders you have already created; those are yours.

---

## The roster + orchestrators

- **144 specialist agents in the roster** — 141 fully specified, 3 stubs
  (petra/reid/clio) — across guilds: research, engineering, design, brand,
  client, ops, growth, and more. The permanent crew is **Leah** (research,
  informs first) and **Eva** (talent strategy).
- **Six outcome orchestrators** — a routing layer between Tess and the guilds:
  Founder's Office, Revenue, Product & Delivery, Client Experience, Strategic
  Growth, and Operational Reliability. Orchestrators are routing brains that
  return a crew-plan; Tess (or a workflow) is the sole dispatcher.

### `tessctl recruit` — grow your staff

A new instance starts with a small starter squad, not all 144. Bring more onto
the active roster as you need them:

```bash
./tessctl recruit vega cyra freya     # by name
./tessctl recruit revenue             # an orchestrator + its guild
./tessctl roster list                 # installed vs staged
```

Agents not on the active roster stay *benched* (present in core, out of the way)
until you recruit them — so the conductor's context stays focused.

### `tessctl vault` — a local-first secret store

```bash
./tessctl vault init                  # generate an age identity
./tessctl vault set github/token      # value read from prompt/stdin — never argv
./tessctl vault exec --ref github/token -- gh auth status   # JIT injection
```

The vault keeps secrets **encrypted at rest** (age / X25519 via `pyrage`, or an
`age`/`rage` CLI) and references them by `vault://` ref instead of pasting raw
values. It installs git **pre-commit and pre-push guards** that scan for secret
and vault material before anything leaves your machine.

> **Honest scope:** the vault is a **local-first store plus a backstop**, not a
> guarantee. The guards meaningfully reduce the chance of committing a credential,
> but no client-side scanner can promise a secret "cannot leak." Treat it as
> defense-in-depth: rotate real credentials, review what you commit, and don't
> grant production access you wouldn't grant a new hire.

### `tessctl validate` — contracts-as-code

```bash
./tessctl validate brief my-brief.md              # dispatch-brief.md's six fields
./tessctl validate crew-plan plan.yaml             # orchestra-model.md §3.1/§3.2
./tessctl validate verdict verdict.json --json     # review-output-standards.md
./tessctl validate return-manifest return.json
```

The five core contracts — `brief`, `crew-plan`, `verdict`, `return-manifest`,
`policy` — are JSON Schemas at `core/contracts/*.schema.json`, each grounded in
the exact doctrine text it encodes (see `core/contracts/README.md`). A contract
instance that fails validation is a **schema-miss**: `tessctl validate`
classifies it `degraded_output` (per `conductor/subagent-failure-protocol.md`'s
failure-state table) and exits non-zero, so a git hook or CI action can gate on
it deterministically — the point is that a weak agent's output either matches
the contracted shape or it doesn't; existence and shape are model-independent
checks. Instances can be `.json`, `.yaml`/`.yml`, or `.md` with a YAML
front-matter block.

### `tessctl gate` — the enforcement spine

```bash
./tessctl gate install-hooks           # install/upgrade the pre-commit + pre-push git hooks
                                        # + the CI workflow (now push/pull_request-triggered)
                                        # (idempotent; splices above any pre-existing hook —
                                        #  same coexistence pattern as `tessctl vault init`)
./tessctl gate pre-commit               # contract validation on STAGED files (fast, local)
./tessctl gate pre-push                 # THE SHIP-GATE — reads the git pre-push stdin protocol
./tessctl gate ci --base <ref> --head <ref>   # same ship-gate logic, explicit refs (CI entrypoint)

./tessctl verdict sign <file> --verifier <Name> --key-id <KEYID>   # sign a verdict (Phase 2b)
./tessctl verdict verify <file>                                    # check a verdict's signature
```

Phase 2 of `docs/ULTIMATE_FRAMEWORK_PLAN.md`, Design Decisions #2 ("enforcement
moves from model-compliance to deterministic code — a `tessctl gate` spine at
git pre-commit/pre-push + CI; git is the only runtime every assistant shares")
and #6 ("verification produces a gateable artifact — signed verdict files; the
ship-gate refuses pushes on prod/client-flagged paths without a covering
APPROVE verdict"). Three mounting points, one deterministic logic:

- **`pre-commit`** — validates any staged brief/crew-plan/verdict/
  return-manifest/policy file against its schema + lint (reuses
  `tessctl validate`'s engine directly). Fast, local, catches malformed
  contracts before they're even committed.
- **`pre-push` (the ship-gate)** — for every path changed in what's being
  pushed, classifies it against `core/policy/policy.yaml`. Any path matching a
  `require_verdict: true` rule is BLOCKED unless a COMMITTED verdict — part of
  the actual pushed ref(s), never an uncommitted working-tree file — is
  schema-valid, carries `disposition: APPROVE`, has a `covers_paths` glob
  matching that path, carries a valid cryptographic `signature` that verifies
  against `policy.verifier_keys[verifier]`'s registered key (Phase 2b — see
  `conductor/verdict-signing.md`), names a `verifier` the matched rule's
  `allowed_verifiers` actually permits, and records THIS path's current git
  blob SHA in `artifact_hashes` (a HIGH finding still forces `BLOCK` unless
  explicitly accepted — the Phase 0 verdict schema rule applies unchanged).
  Verification is per-change: a verdict clears the exact content it reviewed,
  never a permanent toll on the glob — re-editing a covered file, or adding a
  new file under the same `covers_paths` glob, requires its own covering
  verdict. `covers_paths` can never be a blanket 'master key' glob (`**`, bare
  `*`, `**/*`, `**/**`) — a verdict carrying one is schema/lint-invalid and
  covers nothing. An unsigned verdict, a signature from an unregistered or
  mismatched key, or a verdict edited after signing (tamper) is treated
  identically to "no covering verdict at all" — fail-closed. Any path
  matching a hard-floor rule (credentials / money movement / destructive prod
  data / client-external claims — `guardrails.md` Rule 18) is BLOCKED
  regardless of any verdict, unless an explicit human sign-off artifact
  exists at `.tess/gate/signoffs/<rule-id>.signoff.json` — a verifier's
  APPROVE (signed or not) can never clear a hard floor.
- **`ci`** — identical ship-gate logic over an explicit `--base`/`--head` ref
  range, the harness-independent backstop that still catches a push made with
  `git push --no-verify` (local hooks are advisory; CI is not).

**Fail-closed by design:** a missing/invalid policy file, a git command that
fails, or an unreadable verdict all count as a block, never a silent allow —
ambiguity resolves to refuse, not permit.

**Trust boundary (honest disclosure, updated for Phase 2b — verdict
signing):** a covering verdict must now carry a cryptographic `signature`
(GPG detached signature over the verdict's canonical content) that verifies
against the registered public key for its claimed `verifier` in
`core/policy/policy.yaml`'s `policy.verifier_keys` — an unsigned, hand-faked,
wrong-key, or tampered-after-signing verdict is rejected, fail-closed, and
can never cover a path. Signing ties to `allowed_verifiers`: a genuine
signature from a real, registered verifier who simply isn't permitted for
the matched rule still does not clear it. Together with HIGH-1's diff-binding
(`artifact_hashes`), a covering verdict now means: **the right verifier,
cryptographically authenticated, signed off on the exact content being
shipped** — hand-authoring a fake `disposition: APPROVE` no longer works.

The remaining boundary is **key custody, not the mechanism**: whoever holds
a verifier's private key can sign as them (the same boundary every signature
scheme has, including this repo's own release-tag signing — see
`release-process.md`). `tessctl` never generates or stores a verifier's
private key. Git hooks remain local and bypassable (`git push --no-verify`;
`ci` is the harness-independent backstop for exactly that reason, and now
triggers automatically on `push`/`pull_request` — see "CI auto-enforce"
below). Full trust model, key onboarding, and the disclosed/deferred piece
(this repo's own Reid/Cyra keys are not yet generated — `verifier_keys`
ships empty on purpose): `conductor/verdict-signing.md`.

**CI auto-enforce:** `.github/workflows/tess-gate.yml` now triggers on
`push` (protected branches) and `pull_request`, in addition to
`workflow_dispatch` — the ship-gate runs automatically rather than requiring
someone to remember to invoke it. A CI check alone is only advisory until
configured as a **required status check** in branch protection (required
check name: the job name `tessctl gate ci`) — see
`conductor/verdict-signing.md`'s "CI auto-enforce" section for the exact
setup steps (a repo-admin action, not automated by this change) and the
fresh-adopter bootstrap warning.

### `tessctl trace` — mission trace log + OTel GenAI export

```bash
./tessctl trace export --format otlp-json                     # every trace.jsonl this repo has, to stdout
./tessctl trace export --format otlp-json --mission-id m1      # just missions/m1/trace.jsonl
./tessctl trace export --format otlp-json --out spans.json     # write to disk instead of stdout
```

Every `gate`/`validate` invocation above already appends one structured JSONL
event — local-first, no daemon, no network — to `missions/<id>/trace.jsonl`
(when a mission id is inferable) or a per-run fallback under
`.tess/trace/runs/`. `trace export --format otlp-json` maps that JSONL to
[OTel GenAI semantic-convention][genai] agent spans (OTLP/JSON) — the same
`gen_ai.*` shape Datadog, Honeycomb, New Relic, and the OTel Collector
already ingest, and CrewAI/LangGraph instrumentations already emit — so
Tess OS becomes legible to any APM that understands `gen_ai.*` without a
single network call ever leaving the machine: the export is a pure local
file-to-file JSON reshape, and getting the result into a collector is a
separate, explicit, operator-run step. Full capture list, the exact
attribute mapping, and the no-network guarantee (including the socket-guard
tests that prove it): `docs/OBSERVABILITY.md`.

[genai]: https://github.com/open-telemetry/semantic-conventions-genai

---

## How a mission runs

Every task is dispatched — the conductor never executes specialist work itself.
Guard hooks enforce dispatch discipline, anti-fabrication, and channel formatting.
The gates are dependency-ordered, not lockstep:

```
intake → research (Leah) → crew (Eva) → build → review → verification → synthesis
```

No gate may be skipped, waived, or satisfied retroactively. The clarification
hard floor (credentials, money movement, destructive production operations,
external factual claims) always returns to the operator, even in autonomous mode.

---

## What's in the box

- **`conductor/`** — the doctrine layer: identity, guardrails, the dispatch-brief
  contract, verification routing, the failure/retry protocol, and the command
  system (wired `.claude/commands/`).
- **`core/contracts/`** — the four doctrine contracts (dispatch-brief, crew-plan,
  verdict, return-manifest) as JSON Schemas, checked via `tessctl validate`. The
  first piece of the portable `core/` the framework is growing into.
- **`agents/`** — the roster of specialist persona specs across guilds. The
  compiled, managed dispatch definitions live in `.claude/agents/`.
- **`.tess/`** — the upgrade engine: `bin/tessctl`, the pristine merge-base
  `core/`, and the committed `tess.lock`.
- **`.claude/`** — Claude Code configuration: managed agents, guard hooks, a
  permissions baseline, and generic design/processing skills.
- **`create-tess/`** — the `npm create tess` wizard.
- **`clients/_template/`** — a per-client mini-operating-system template you copy
  for each new client.
- **`kb/`** — a knowledge-base scaffold (`raw/`, `wiki/`, `lint/`).
- **`operator/`** — blank identity/profile/channel stubs you fill in; injected at
  `CLAUDE.md` render time, kept out of framework core.

---

## Status — read this before you trust it

This is an early public foundation. What is real and committed today:

- The **governed organization**: the full doctrine, the roster, the six
  orchestrators, the gates, the dispatch-brief contract, the verification routing,
  and the retry protocol.
- **Contracts-as-code (Phase 0, extended Phase 2)**: five core contracts
  (`brief`, `crew-plan`, `verdict`, `return-manifest`, `policy`) as JSON
  Schemas under `core/contracts/`, a dependency-free validator (`tessctl
  validate`), and the schema-miss → `degraded_output` classification wired to
  the retry protocol's signal. Full retry orchestration (dispatching the
  changed-brief retry itself) remains out of scope — this ships the
  deterministic check and the classification.
- **The gate spine (Phase 2, hardened post-adversarial-review; Phase 2b —
  verdict signing + CI auto-enforce)**: `tessctl gate` — deterministic
  pre-commit (staged contract validation), pre-push (the ship-gate: blocks
  prod/client/external changes without a covering, COMMITTED, content-bound,
  **cryptographically SIGNED** `disposition: APPROVE` verdict from an
  allowed verifier), and CI (`gate ci`) entrypoints, plus
  `tessctl gate install-hooks` to install/upgrade the git hooks and a CI
  workflow template that now triggers on `push`/`pull_request` (in addition
  to `workflow_dispatch`). `tessctl verdict sign`/`verdict verify` manage
  the signing key lifecycle. `core/policy/policy.yaml` is the policy-as-data
  instance the gate reads (now including `verifier_keys`, the allowed-key
  set); hard-floor categories (credentials/money/destructive-prod-
  data/client-external-claims) require an explicit human sign-off artifact and
  are never satisfiable by a verdict alone. Fable's adversarial review of the
  original Phase 2 found one BLOCK (HIGH-1 — coverage was diff-unbound: any
  schema-valid APPROVE verdict anywhere in the working tree permanently
  cleared its `covers_paths` glob for every future push, `**` acted as a
  master key, and an uncommitted pre-push verdict counted) plus two MEDIUMs
  (`allowed_verifiers` was advisory only; `**`/`*` glob semantics missed
  root-level files and let a single `*` span directories); that review also
  flagged the residual now closed by Phase 2b — verdicts were committer-
  authored plain files with no cryptographic signature. All closed: coverage
  is bound to the reviewed git blob SHA per path (`artifact_hashes`),
  master-key globs are schema/lint-rejected, only committed verdicts on the
  pushed ref(s) count, `allowed_verifiers` is enforced, the glob matcher is
  fixed, AND a covering verdict must now carry a valid signature tied to its
  claimed verifier's registered key — see this README's `tessctl gate`
  section, `conductor/verdict-signing.md`, and CHANGELOG.md for the full
  disclosure, including the residual trust boundary that remains (key
  custody, not the mechanism — see `conductor/verdict-signing.md`) and the
  disclosed, deferred piece (this repo's own Reid/Cyra signing keys are not
  yet generated/registered). Scope note: this phase does NOT include a Codex
  adapter, `.gemini`/generic render targets, or `tessctl run` (the mechanical
  conductor loop) — see `docs/ULTIMATE_FRAMEWORK_PLAN.md`'s Phase 2 honest
  re-scope note.
- **Observability (Goal #8)**: `tessctl gate`/`tessctl validate` now append a
  schema-valid JSONL trace event to `missions/<id>/trace.jsonl` (or a
  per-run fallback under `.tess/trace/runs/`) on every invocation, and
  `tessctl trace export --format otlp-json` maps that log to OTel GenAI
  semantic-convention agent spans — legible to any APM that understands
  `gen_ai.*`, with zero network calls (a pure local file-to-file transform,
  proven by a static import scan plus socket-guard tests). `tessctl run`
  (which does not exist yet) is not instrumented — see `docs/OBSERVABILITY.md`.
- The **engine's integrity layer**: snapshot-first updates, the `doctor`
  hard-gate, conflict-halts-the-update, security-tier quarantine, hash-based drift
  detection, and atomic staging swap.
- The **vault** as described above — encrypted-at-rest store, `vault://` refs, JIT
  `exec`, and the pre-commit/pre-push backstop (a risk reducer, not a guarantee).
- The **signed upgrade channel**: the FETCH, signature-verify, merge, version bump,
  and `tess self-update` paths are fully exercised and verified live over the wire —
  see below.

**Over-the-wire upgrade: VERIFIED** (v0.1.0 → v0.1.1, exercised 2026-06-29):

A fresh clone was checked out at v0.1.0. Running `tess update --ref v0.1.1`
performed the full upgrade chain:
1. **FETCH** — cloned v0.1.1 from `https://github.com/twiss-io/tess-os.git` over HTTPS
2. **Signature verification** — `git verify-tag --raw` in an isolated GNUPGHOME seeded
   only with the pinned key; output: `signature OK (isolated keyring) — fingerprint
   matches pinned key`
3. **Merge** — conductor/README.md fast-forwarded; conductor/release-process.md adopted
   via A2 (new-file adoption)
4. **Version bump** — `framework.version` → `0.1.1`, `upstream_ref` → `v0.1.1` (Step 8)
5. **`tess self-update --ref v0.1.1`** — verified signature, parse-checked new engine,
   backed up previous engine, installed, ran doctor: all clean

Post-upgrade `tess doctor` and `tess verify` both returned `OK`. The fingerprint pin
(`EBEABC618C11B6A7340A7D1601DD637667B8CC89`) is set in `tess.lock` and is enforced on
every future update; unsigned or wrong-key tags are rejected before any extraction.

The test suite is portable and green (Python: engine, vault, render, merge, hook
coexistence; Node: the wizard).

---

## Recommended model setup

Tess (the conductor) runs best on an Opus-class Claude model. Specialist subagents
run well on Sonnet-class models. Configure this per Claude Code's model settings.

## Bring your own secrets

This repo ships **zero secrets and zero client data** by design — no tokens, keys,
credentials, server addresses, or client records anywhere. Provision your own:

- Create a Telegram bot via [@BotFather](https://t.me/BotFather) for the channel.
- Supply API keys via the vault (`tessctl vault set …`), environment variables
  (`.env`, gitignored), or your own secrets manager — never commit them.
- Guard hooks reference `$CLAUDE_PROJECT_DIR`, so paths stay relative to wherever
  you clone.
- Review `conductor/guardrails.md` before granting the system any production access.

---

## Community / Get help / Training

- **Community, discussions & questions** — use [GitHub
  Discussions](https://github.com/twiss-io/tess-os/discussions) for questions,
  ideas, "how do I…", and community conversation. Please don't use the issue
  tracker for support.
- **Docs** — the in-repo doctrine under [`conductor/`](conductor/README.md) is
  the source of truth.
- **Bugs & features** — open an [issue](https://github.com/twiss-io/tess-os/issues)
  using the templates.
- **Security** — do **not** open a public issue; report privately per
  [SECURITY.md](SECURITY.md).
- **Training / managed setup** — want Tess OS installed and run for your team, or
  hands-on onboarding? Reach out: **legal@twiss.io**. (Offered separately; not
  part of the Apache-2.0 distribution.)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). In short: branch, keep the gates green
(`pytest`, the create-tess `node --test`, `tessctl doctor` + `verify`), never
commit a secret, and don't introduce AGPL-licensed code into this Apache-2.0 repo.
Contributions here are Apache-2.0 (inbound = outbound); no CLA is required for
Tess OS — see [CLA.md](CLA.md) for how the *future* AGPL standalone vault differs.

Please also read the [Code of Conduct](CODE_OF_CONDUCT.md).

### Attribution

If you build on Tess OS, **keep the [NOTICE](NOTICE) file** (Apache-2.0 §4(d)
requires it) and a short **"built with Tess OS"** credit is appreciated. That is
all the attribution Apache-2.0 asks for — nothing more is required. The project
**name and marks** are a separate matter: see the [trademark
policy](TRADEMARK.md).

## License

**Apache-2.0.** See [LICENSE](LICENSE) and the third-party attributions in
[NOTICE](NOTICE). The code is Apache-2.0; the **marks** are not licensed by it —
see [TRADEMARK.md](TRADEMARK.md).

**Open-core model:**

| Layer | What it is | License |
|---|---|---|
| **Tess OS** (this repo) | the permissive shell — build freely | **Apache-2.0** |
| **Embedded vault** (`tessctl vault`, in this repo) | the "lite" client | **Apache-2.0** |
| **Standalone Twiss Vault** (`twiss-io/vault`, future, separate repo) | the protected product | **AGPL-3.0 + CLA** |

> The vault embedded in this repository is part of Tess OS and is Apache-2.0. The
> *standalone* vault product is planned under **AGPL-3.0 + a CLA** (which enables
> dual-licensing for commercial use) in a **separate** repository. **No
> AGPL-licensed code is present in this Apache-2.0 repo.** Need it installed or
> managed for your team? **legal@twiss.io**.
