# Tess OS

[![License: Apache-2.0](https://img.shields.io/github/license/twiss-io/tess-os)](LICENSE)
[![create-tess on npm](https://img.shields.io/npm/v/create-tess?label=create-tess)](https://www.npmjs.com/package/create-tess)
[![Latest release](https://img.shields.io/github/v/release/twiss-io/tess-os)](https://github.com/twiss-io/tess-os/releases)
[![CI](https://img.shields.io/github/actions/workflow/status/twiss-io/tess-os/ci.yml?label=CI)](https://github.com/twiss-io/tess-os/actions/workflows/ci.yml)

> **Technology preview:** do not use the current release or `main` to protect
> production merges.

Tess OS is a **signed, fail-closed review gate** and a **model-neutral
governance harness** for code produced by AI agents.

In plain English: an agent can propose a repository change, but Tess OS checks
the repository's policy and review evidence before that change is allowed to
move toward delivery. If required proof is missing or invalid, the gate blocks.

Tess OS does not improve a model's intelligence, prove its reasoning, or turn
an unsupported product into a trusted integration. It governs artifacts that
reach a repository; it does not certify the model that created them.

## The 30-second mental model

```text
coding agent writes files
          |
          v
Git records the proposed change
          |
          v
Tess OS checks policy + signed review evidence
          |
          +---- missing or invalid proof ----> BLOCK
          |
          +---- valid covering proof --------> required CI may pass
                                                   |
                                                   v
                                      protected Git rule decides delivery
```

The final Git rule matters. A prompt, local hook, adapter, or passing command is
not branch protection by itself.

## What is here today

- `tessctl`, a local CLI for policy checks, contract validation, integrity
  checks, mission records, traces, rendering, and a sequential conductor loop.
- A signed-review gate that fails closed when a governed change lacks valid,
  covering approval evidence.
- A Claude Code reference target and local process driver at
  **C3 — Managed-adapter preview**.
- A Codex pilot at **C2 — Manual-gated compatibility**. Its durable repository
  surfaces are `AGENTS.md` and trusted-project `.codex/config.toml`; its local
  `codex exec` driver still lacks live native-event evidence. It also preserves
  legacy `.codex/prompts` mirrors that Codex does not discover from a project.
- A generic `AGENTS.md` target for tools that can consume repository
  instructions without claiming native feature parity.
- File-backed mission, crew-plan, retry, and return-artifact contracts.
- A local age-encrypted vault primitive and an experimental local GUI. Neither
  is the future Tess Vault product or a production control plane.

The current conductor runs stages sequentially. The repository's knowledge-base
and memory doctrine are useful conventions, not a finished advanced retrieval
or cross-agent memory system.

## Platform support, without the marketing fog

Tess OS is model-neutral because its core evaluates repository artifacts, not
because every model or host has a native adapter.

| Surface | Public status | Evidence-based meaning |
|---|---|---|
| Claude Code | **C3 — Managed-adapter preview** | Reference renderer and local driver. Protected delivery is not certified. |
| OpenAI Codex | **C2 — Manual-gated compatibility** | `AGENTS.md`, trusted-project `.codex/config.toml`, and a local `codex exec` driver exist. Project `.codex/prompts` mirrors are legacy artifacts, not native prompt integration. |
| Generic `AGENTS.md` hosts | **Compatible through repository files** | Tess can render portable instructions and prompts. Tool discovery, permissions, commands, and subagents remain host-specific. |
| Cursor, Copilot, Perplexity, and other tools | **Compatible through Git/CI only when output becomes a governed repository change** | The gate can evaluate committed files regardless of their author. This is not a native adapter, provider control, or proof of provenance. Perplexity's adapter level is currently C0. |
| Gemini or a future frontier model | **Planned only when named evidence exists** | A compatible API or MCP connection is not adapter support. New hosts need a bounded adapter and conformance evidence. |

See the concise [platform support guide](https://github.com/twiss-io/tess-os/blob/main/docs/PLATFORM_SUPPORT.md)
and the detailed [status boundary](https://github.com/twiss-io/tess-os/blob/main/docs/STATUS.md).

## Why a fresh install blocks

Tess OS ships with empty verifier and sign-off registries on purpose. A new
repository therefore has no pre-authorized reviewer key that can approve a
governed change.

If you see:

```text
no covering APPROVE verdict found
```

the gate is doing what it was designed to do. Do not create a key, register a
public key, sign a verdict, weaken policy, or bypass the hook merely to make the
message disappear. The repository being reviewed must not create the authority
that approves itself.

Real activation requires an owner-held custody decision and independently
required Git checks. That ceremony is intentionally not a one-click agent
action. Read [Trust setup, in plain English](https://github.com/twiss-io/tess-os/blob/main/docs/TRUST_SETUP.md)
and the more technical [gate operation guide](https://github.com/twiss-io/tess-os/blob/main/docs/GATE_QUICKSTART.md).

## Safe evaluation

Use a non-production clone. The checks below inspect state; they do not create
approval authority or protect a branch. For `gate ci`, use two existing
immutable refs that you are actually reviewing.

```bash
git clone https://github.com/twiss-io/tess-os.git
cd tess-os
./tessctl doctor
./tessctl verify
./tessctl gate ci --base <BASE_REF> --head <HEAD_REF>
```

Do not use this example as a trust bootstrap or release procedure.

## Tess OS, Tess Cloud, and Tess Vault

```text
Tess OS       local governance core and review evidence
    |
    +-- Tess Cloud   future optional sync and coordination layer
    |
    +-- Tess Vault   future scoped credential-capability service
```

Tess Cloud and Tess Vault are product directions, not services available from
this repository. Both are intended to build on stable Tess OS contracts. Cloud
must remain optional and must not become the trust root. Vault must keep raw
secrets out of prompts, memory, traces, evidence, and Cloud.

The current local `tessctl vault` primitive is not the future Tess Vault
service. Read the [product-family architecture](https://github.com/twiss-io/tess-os/blob/main/docs/PRODUCT_FAMILY.md)
for the exact current-versus-planned boundary.

## Orchestration and memory

Tess OS contains substantial governance doctrine and a working sequential
`tessctl run` loop. It validates plans, mission gates, return artifacts,
bounded retries, and escalation. It does not yet ship a parallel task-graph
scheduler, universal execution receipts, or an advanced retrieval-memory
runtime.

The design boundary is documented in the
[memory and orchestration contract](https://github.com/twiss-io/tess-os/blob/main/docs/MEMORY_AND_ORCHESTRATION_CONTRACT.md):
memory can inform work, but it can never approve a change, mint authority, or
carry secret values.

## npm status

- [`create-tess`](https://www.npmjs.com/package/create-tess) exists, but the
  registry's live `create-tess@0.1.0` is a legacy release that predates these
  support and custody corrections. Repository source is newer and remains
  unreleased until an owner-authorized publication.
- `tess-os` is **not published on npm**. The root `package.json` is an
  unpublished documentation/metadata-only manifest for release rehearsal; it
  does not contain the runtime tree and there is no current npm install path
  for Tess OS.

Neither the legacy `create-tess` release nor the unpublished root manifest
completes key custody, required checks, Cloud, Vault, or production onboarding.

## Learn more

- [Local development quickstart](https://github.com/twiss-io/tess-os/blob/main/docs/LOCAL_DEV_QUICKSTART.md)
- [Platform support](https://github.com/twiss-io/tess-os/blob/main/docs/PLATFORM_SUPPORT.md)
- [Trust setup](https://github.com/twiss-io/tess-os/blob/main/docs/TRUST_SETUP.md)
- [Adapter evidence](https://github.com/twiss-io/tess-os/tree/main/adapters)
- [Mission and orchestration model](https://github.com/twiss-io/tess-os/blob/main/missions/README.md)
- [Product family](https://github.com/twiss-io/tess-os/blob/main/docs/PRODUCT_FAMILY.md)
- [Framing migration notes](https://github.com/twiss-io/tess-os/blob/main/docs/FRAMING_MIGRATION.md)
- [Recommended GitHub description and topics](https://github.com/twiss-io/tess-os/blob/main/docs/GITHUB_METADATA_RECOMMENDATION.md)
- [Security policy](https://github.com/twiss-io/tess-os/blob/main/SECURITY.md)

## Production-readiness boundary

Current `main` is not a production admission control. Production use still
requires, at minimum, an external human-owned first trust anchor, prevention of
candidate self-authorization, required VCS checks, complete policy coverage,
and an honest adversarial-corpus result with open cases disclosed.

A green local command is engineering evidence. It is not certification.

## Contributing and license

Contributions are welcome. Changes to the gate, policy, trust material,
workflows, release path, or provider integrations require especially careful
review. See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).

Apache-2.0. Forks must follow the [trademark policy](TRADEMARK.md).
