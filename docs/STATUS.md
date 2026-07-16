# Support and status

This page is the public claim boundary for Tess OS. It separates what is in the
repository today from pilot work and product plans.

For a shorter, nontechnical comparison, start with
[Platform support](PLATFORM_SUPPORT.md). The matrix below remains the canonical
evidence boundary.

## Claim labels

| Label | Meaning |
|---|---|
| **Verified current state** | Present in the reviewed repository and described with its known limits. It is not automatically production-ready. |
| **Pilot** | Present but incomplete, unverified against a real provider lifecycle, or not certified for protected delivery. |
| **Planned** | A direction, not a shipped product or promise. |
| **Not supported** | No Tess OS adapter, driver, or conformance evidence exists. |

## Current matrix

| Capability or surface | Label | Current boundary |
|---|---|---|
| Local policy and gate CLI | **Verified current state** | The engine can validate policy/evidence and fail closed. It is not a production admission control until first-key custody and GitHub required checks are fixed. |
| Claude Code target and driver | **C3 — managed-adapter preview** | Reference integration. It remains an uncertified preview for protected delivery. |
| Codex target and driver | **C2 — manual-gated compatibility** | The renderer emits `AGENTS.md`, `.codex/config.toml`, and prompt files. The driver is not live-tested against native event samples and does not have native-parity certification. |
| Generic `AGENTS.md` target | **C2 — manual-gated compatibility** | Emits instructions and plain prompts only. Host-specific orchestration, tool permissions, and command behavior are not implied. |
| `tessctl run` conductor | **Verified current state** | Validates plans, gates, artifacts, retries, and escalation in a sequential execution model. Parallel execution and synthesis remain future work. |
| MCP server | **Verified current state** | Provider-neutral stdio JSON-RPC with limited read/check tools. MCP connects tools and context; it is not a review or trust-enforcement mechanism. |
| Perplexity adapter/driver | **C0 — not supported** | Tess OS has no Perplexity repository adapter. A future read-only research-worker role is only a proposal. |
| Gemini adapter/driver | **C0 — not supported** | No registered render target or dispatch driver exists. |
| All frontier models | **Not supported as a claim** | A model name, OpenAI-compatible API, or MCP support is not adapter conformance. |
| Advanced retrieval memory | **Planned** | Current `kb/` conventions and memory doctrine are not a proven retrieval, lifecycle, ACL, or privacy system. |
| Tess Cloud | **Planned** | Optional cloud synchronization/coordination product, separate from the local core and not present here. |
| Tess Vault | **Planned** | Separate agent-era secret-capability product. It must never expose secrets to agent prompts, evidence, or memory. |

## Production-gate status

**Not ready.** A production claim requires all of the following:

1. an external, human-owned first verifier/sign-off trust anchor;
2. a candidate policy that cannot authorize its own first key or approval;
3. required GitHub gate and CI checks on the protected branch;
4. policy coverage for the actual runtime, installer, release, dependency, and
   trust-state surfaces; and
5. an honest adversarial-corpus result with every open case disclosed.

The current repository does not meet those conditions. In particular, the
committed `gate-arena` scorecard reports 12/12 while A14 remains open, and the
shipped verifier/sign-off registries are intentionally empty.

## Product boundaries

Tess OS is the local governance core. A future Tess Cloud service may sync
verified records only with an approved privacy, tenancy, encryption, retention,
and deletion design. It must not become the trust root or silently upload
prompts.

A future Tess Vault must issue scoped secret capabilities rather than put secret
values into model context. Tess OS should see only an opaque capability request,
the policy decision, and an auditable outcome.

These are architectural directions, not available products, pricing promises,
or data-processing commitments.

## Evidence before claims

A platform can advance from pilot to a protected-workflow claim only after a
versioned adapter passes a conformance suite covering capability mapping,
artifact provenance, denied actions, version drift, isolation, and independent
required-check enforcement. Until then, Tess OS will describe the exact adapter
surface and its limits rather than advertise universal support.

The current advisory records and the C0–C4 vocabulary are in
[Adapter conformance](../adapters/CONFORMANCE.md). They are deliberately not
gate, policy, approval, signing, key, verifier, or branch-protection inputs.
