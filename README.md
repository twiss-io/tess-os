# Tess OS

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
- The **engine's integrity layer**: snapshot-first updates, the `doctor`
  hard-gate, conflict-halts-the-update, security-tier quarantine, hash-based drift
  detection, and atomic staging swap.
- The **vault** as described above — encrypted-at-rest store, `vault://` refs, JIT
  `exec`, and the pre-commit/pre-push backstop (a risk reducer, not a guarantee).

What is **in progress** and should not be assumed working:

- The network **FETCH** that pulls a new framework version over the wire, and
  `tessctl self-update`.
- A real **two-tag upgrade has not yet been exercised end-to-end** on a live
  update. Treat the upgrade engine as architecturally complete but unproven on a
  real over-the-wire update until that path is exercised.

The test suite is portable and green (Python: engine, vault, render, merge, hook
coexistence; Node: the wizard). It does not yet stand in for a verified live
upgrade.

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
