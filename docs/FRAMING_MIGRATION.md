# Public framing migration

Tess OS began with Claude Code-shaped “agent operating system” language. The
repository now has a broader and more accurate public description:

> **A signed, fail-closed review gate for coding-agent output and a
> model-neutral governance harness.**

This is a documentation and product-language migration. It does not rename the
CLI, change trust behavior, or claim that every model host is supported.

## Terminology

| Older shorthand | Preferred wording | Why |
|---|---|---|
| “agent OS for Claude Code” | “model-neutral governance harness, with a Claude Code reference integration” | Separates the core policy/evidence boundary from one host adapter. |
| “makes agents better” | “adds review discipline and verifiable delivery evidence” | Internal benchmarking did not establish model-quality improvement. |
| “supports all frontier models” | Name the exact native adapter, repository-file route, or Git/CI route | Model neutrality is an architecture property, not universal conformance. |
| “multi-agent orchestration framework” | “sequential conductor and file-backed mission contracts” | Parallel scheduling, advanced synthesis, and provider-neutral execution receipts remain incomplete. |
| “memory system” | “knowledge-base conventions and memory contract” | Advanced retrieval, ACLs, lifecycle management, and privacy enforcement are roadmap work. |
| “vault” | “local encrypted vault primitive” or “Tess Vault (planned)” | Prevents the current helper from being mistaken for the future product. |
| “production gate” | “technology-preview gate” until external custody and required checks are complete | A local pass is not protected delivery. |

## Compatibility promise

Stable Tess OS contracts should allow future models and hosts to be added
without rewriting policy. Every native integration still needs a named adapter,
bounded capabilities, negative-path tests, version-drift handling, and
conformance evidence. Until that evidence exists, documentation should say
“Git/CI compatibility” rather than “native support.”

## Package and migration boundary

The `tess-os` npm package remains a light metadata/documentation package;
runtime delivery remains repository-based. `create-tess` remains a local
scaffolder with a Claude Code-oriented default. This framing change does not
silently enable Codex or generic targets in existing installations and does not
introduce Tess Cloud or Tess Vault services.

For current facts, use [Platform support](PLATFORM_SUPPORT.md),
[Support and status](STATUS.md), and [Product family](PRODUCT_FAMILY.md).
