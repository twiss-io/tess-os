# Platform support

Tess OS is model-neutral at its governance boundary: the gate evaluates
repository changes and review evidence, regardless of which tool wrote the
files. That does **not** mean every model host has a native Tess OS adapter.

## Current support

| Platform or route | Status | What works | What is not claimed |
|---|---|---|---|
| Claude Code | **Tested/native preview (C3)** | Reference instruction renderer, prompt artifacts, configuration fragment, and local process driver. It is the only render target enabled by default in a new install. | Production certification, protected delivery, or perfect control of the host. |
| OpenAI Codex | **Experimental primary integration (C2)** | Opt-in `AGENTS.md`, prompt, and project-configuration rendering plus a local `codex exec` process driver. | Live native-event conformance, native feature parity, or default enablement. |
| Generic `AGENTS.md` hosts | **Repository-file compatibility (C2)** | Opt-in portable instructions and plain prompt files. | Native tools, permissions, commands, subagents, process control, or a driver. |
| Perplexity | **Git/CI route only; no adapter (C0)** | If a person or external workflow commits resulting files, the normal repository gate can evaluate those files. | A Perplexity renderer, driver, provenance proof, native workflow, or coding-agent integration. |
| Cursor, Copilot, and other coding tools | **Git/CI route only unless separately evidenced** | Their committed repository changes can enter the same policy-and-review path. | Native adapter support or control of work that never reaches the governed repository. |
| Gemini and future model hosts | **Planned only when named evidence exists** | No registered target or driver exists today. | Support based only on model popularity, MCP, or an API-compatible endpoint. |

The internal C0-C4 labels describe adapter evidence, not authority. They cannot
approve a change, register a verifier, alter policy, or protect a branch. The
canonical records live in [`adapters/manifests/`](../adapters/manifests/) and
their vocabulary is defined in
[`adapters/CONFORMANCE.md`](../adapters/CONFORMANCE.md).

## Three different kinds of compatibility

1. **Native adapter:** Tess OS intentionally renders host-specific files or
   runs a bounded local process driver for that host.
2. **Repository-file compatibility:** the host can read portable files such as
   `AGENTS.md`, but its permissions and execution model remain its own.
3. **Git/CI compatibility:** the host's output becomes an ordinary committed
   repository change, so Tess OS can evaluate the change without controlling
   or certifying the host.

These labels should never be collapsed into “supports all models.” A model can
change while the governance contract stays stable, but each native host adapter
still needs its own versioned implementation and evidence.

## What remains host-specific

Tess OS does not normalize every provider's authentication, tool calls,
sandbox, event stream, billing, retention policy, or subagent semantics. Those
differences are security boundaries. An adapter must translate only declared
capabilities and fail closed when a required capability cannot be represented.

For the full production boundary, read [Support and status](STATUS.md). For the
render-target implementation contract, read [Adapters](../adapters/README.md).
