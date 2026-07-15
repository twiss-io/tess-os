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

The public `create-tess` package is currently **0.1.0** and lags repository
`main`; it is not production onboarding for the signed gate. The package can
still scaffold a local Tess OS instance, but it does not solve the custody or
required-check prerequisites above.

For exact source behavior, use a reviewed GitHub tag or commit and read its
release notes. A future npm release will be documented only after a
reproducible release rehearsal and the production prerequisites are complete.

## Where to start

- [Support and status](docs/STATUS.md) — capability labels and current limits.
- [Gate operation and custody](docs/GATE_QUICKSTART.md) — safe diagnostics and
  the boundary around the human-owned key ceremony.
- [Adapters](adapters/README.md) — render targets and their limits.
- [Mission and orchestration model](missions/README.md) — current conductor
  contracts and evidence model.
- [Observability](docs/OBSERVABILITY.md) — local trace/export behavior.
- [Comparison and roadmap](docs/COMPARISON.md) — factual current-state
  comparison rather than unsupported feature claims.
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
