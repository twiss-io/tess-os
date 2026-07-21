# Support and status

This page is the public claim boundary for Tess OS. It separates what is in the
repository today from pilot work and product plans.

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
| Agent Receipt spec + standalone verifier + emit CLI + demo (System B — GPG, `verdict`/`signoff`) | **Verified current state** | `core/contracts/agent-receipt.schema.json`, `tools/receipt-verify/`, `tools/receipt-emit/`, and `examples/receipt-demo/` (see `docs/AGENT_RECEIPT_SPEC.md`) are present, tested, and runnable with real GPG signatures — including `tools/receipt-emit/`, which actually PRODUCES a real, chained, self-verified receipt from an already-signed verdict or hard-floor sign-off (not just the demo's illustrative walkthrough). Not wired into `tessctl gate`; not a claim of external adoption; a receipt emitted by this tool is genuinely signed and tamper/chain-evident but NOT trust-anchored — `verifier_keys`/`signoff_keys` ship empty by design, and key-ceremony registration is a separate, Xavier-gated decision this tool does not perform. |
| Agent Receipt emission from a codegen run (System A — local HMAC, `decision_kind: local_approval`) | **Verified current state** | `orchestrator.pipeline.run_pipeline()` (`orchestrator/mission_receipt.py`, Hop 7) now emits a real, locally HMAC-signed, independently re-verifiable `local_approval` Agent Receipt for a successful codegen run, wired directly into the pipeline — opt-in only (off unless a caller supplies `receipt_path`; most callers never do). `tools/receipt-verify/hmac_verify.py` (the standalone `local_approval` counterpart to `gpg_verify.py`) and `core/contracts/agent-receipt.schema.json`'s `$defs.LocalApprovalArtifact` verify/validate it. Deliberately WEAKER, and structurally distinct, evidence than the GPG-backed row above — verifiable only by a holder of the same local secret key, never a public key; see `docs/AGENT_RECEIPT_SPEC.md`'s "★ Trust levels are not interchangeable." Always a single genesis receipt to one JSON file per run — durable, cross-run JSONL-chain persistence is still a disclosed, scoped follow-up, not built here. The full idea→route→approve→boots→receipt-verify (+ rejection, + mid-kill unhappy-path) DoD B.9 end-to-end proof now EXISTS and passes: `tests/orchestrator/test_e2e_wedge_loop.py`, driven entirely through `run_pipeline()`, Node hard-required (not silently skipped) in CI — see `orchestrator/README.md`'s "Wedge-loop epic addition" section. |
| Auditor pack export + verify (`tessctl audit export`/`verify`) | **Verified current state** | Exports the accountability ledger (+ any caller-supplied Agent Receipts) for a scope into a self-contained, offline-verifiable bundle (`docs/AUDIT_PACK_SPEC.md`). Tamper-evident via the ledger's unsigned hash chain, not cryptographically non-repudiable; does not perform GPG signature verification (delegated to `tools/receipt-verify/`); a `full`-scope export's tail anchor (`.tip`) is asserted so a dropped tail is detected, but a `task`/range-scoped (partial) export still cannot prove no matching event was omitted by the exporter. |
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
