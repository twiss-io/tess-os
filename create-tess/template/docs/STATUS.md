# Support and status

This page is the public claim boundary for Tess OS. It separates what is in the
repository today from pilot work and product plans. It describes v0.2.0, and
its facts were re-verified on 2026-09-24.

## Claim labels

| Label | Meaning |
|---|---|
| **Available** | Present in the reviewed repository and described with its known limits. It is not automatically production-ready. |
| **Preview** | Present but incomplete, unverified against a real provider lifecycle, or not certified for protected delivery. |
| **Planned** | A direction, not a shipped product or promise. |
| **Unsupported** | No Tess OS adapter, driver, or conformance evidence exists. |

## Runtime enforcement levels

Tess OS runs natively on Claude Code, Codex and Gemini CLI, plus any
AGENTS.md-compatible tool. That is coverage, not parity: the runtimes enforce
different amounts of Tess. The enforcement level says how much of the Tess
hook set a runtime can actually apply.

| Level | Meaning |
|---|---|
| **Enforced** | The full Tess session hook set runs inside the runtime. |
| **Partial** | The runtime loads the Tess doctrine and commands natively, but runs few or none of the Tess session hooks, or runs them with fail-open cases. |
| **Advisory** | The runtime reads the `AGENTS.md` doctrine text only: no Tess commands and no session hooks. |
| **unverified** | Not assessed. |

At every level, the repository's git hooks (once installed) and the CI gate
still apply to changes. They are outside the runtime.

| Runtime | Enforcement | Basis and limits |
|---|---|---|
| Claude Code | **Enforced** | Reference target and driver. The Tess hooks in `.claude/settings.json` run natively. The merge gate is still a preview (see below). |
| Codex CLI | **Partial** | `codex` target: `AGENTS.md`, `.codex/config.toml`, and the Tess commands as `.agents/skills/tess-*` skills (`$tess-<command>`). No Tess session hook runs inside Codex in 0.2.0. Codex reads `.codex/config.toml` only in a trusted project and caps the `AGENTS.md` chain at 32 KiB. |
| Gemini CLI | **Partial** | `gemini` target: `GEMINI.md`, which imports `AGENTS.md`, plus the Tess commands as `/tess:<command>`. No Tess session hook runs inside Gemini CLI in 0.2.0. Gemini loads these files only in a trusted folder. No live model run was part of the v0.2.0 checks. |
| GitHub Copilot CLI, Cursor | **Partial** | No dedicated target. Both read `CLAUDE.md`, `AGENTS.md`, `.claude/agents`, and the Claude hooks. Not tested by Tess OS. Copilot hook timeouts fail open; Cursor fails open on hook crashes and timeouts. Both load the doctrine twice. |
| Other `AGENTS.md` tools (for example OpenCode, Amp, Jules, Kiro) | **Advisory** | Doctrine text only. |
| Any runtime not listed here | **unverified** | Not assessed. |

The per-runtime evidence is in [Adapter conformance](../adapters/CONFORMANCE.md).
The C0–C4 labels in the matrix below are a separate scale: they grade how much
lifecycle evidence exists for an adapter, not how much it enforces.

## Current matrix

| Capability or surface | Label | Current boundary |
|---|---|---|
| Local policy and gate CLI | **Preview** | The engine can validate policy/evidence and fail closed. The live `main` ruleset requires the App-bound gate and CI checks. The gate is still a non-authoritative preview: see [v0.2.0 trust and custody facts](#v020-trust-and-custody-facts). |
| Agent Receipt spec + standalone verifier + emit CLI + demo (System B — GPG, `verdict`/`signoff`) | **Available** | `core/contracts/agent-receipt.schema.json`, `tools/receipt-verify/`, `tools/receipt-emit/`, and `examples/receipt-demo/` (see `docs/AGENT_RECEIPT_SPEC.md`) are present, tested, and runnable with real GPG signatures — including `tools/receipt-emit/`, which actually PRODUCES a real, chained, self-verified receipt from an already-signed verdict or hard-floor sign-off (not just the demo's illustrative walkthrough). Not wired into `tessctl gate`; not a claim of external adoption. This repository's policy registers one verifier key (Cyra); `signoff_keys` remains empty. A receipt is not independently trusted merely because it is signed: custody, signer identity, artifact binding, and the applicable gate path still have to verify. |
| Agent Receipt emission from a codegen run (System A — local HMAC, `decision_kind: local_approval`) | **Available** | `orchestrator.pipeline.run_pipeline()` (`orchestrator/mission_receipt.py`, Hop 7) now emits a real, locally HMAC-signed, independently re-verifiable `local_approval` Agent Receipt for a successful codegen run, wired directly into the pipeline — opt-in only (off unless a caller supplies `receipt_path`; most callers never do). `tools/receipt-verify/hmac_verify.py` (the standalone `local_approval` counterpart to `gpg_verify.py`) and `core/contracts/agent-receipt.schema.json`'s `$defs.LocalApprovalArtifact` verify/validate it. Deliberately WEAKER, and structurally distinct, evidence than the GPG-backed row above — verifiable only by a holder of the same local secret key, never a public key; see `docs/AGENT_RECEIPT_SPEC.md`'s "★ Trust levels are not interchangeable." Always a single genesis receipt to one JSON file per run — durable, cross-run JSONL-chain persistence is still a disclosed, scoped follow-up, not built here. The full idea→route→approve→boots→receipt-verify (+ rejection, + mid-kill unhappy-path) DoD B.9 end-to-end proof now EXISTS and passes: `tests/orchestrator/test_e2e_wedge_loop.py`, driven entirely through `run_pipeline()`, Node hard-required (not silently skipped) in CI — see `orchestrator/README.md`'s "Wedge-loop epic addition" section. |
| Auditor pack export + verify (`tessctl audit export`/`verify`) | **Available** | Exports the accountability ledger (+ any caller-supplied Agent Receipts) for a scope into a self-contained, offline-verifiable bundle (`docs/AUDIT_PACK_SPEC.md`). Tamper-evident via the ledger's unsigned hash chain, not cryptographically non-repudiable; does not perform GPG signature verification (delegated to `tools/receipt-verify/`); a `full`-scope export's tail anchor (`.tip`) is asserted so a dropped tail is detected, but a `task`/range-scoped (partial) export still cannot prove no matching event was omitted by the exporter. |
| Claude Code target and driver | **C3 — managed-adapter preview** | Reference integration; enforcement level **Enforced**. It remains an uncertified preview for protected delivery. |
| Codex target and driver | **C2 — manual-gated compatibility** | Enforcement level **Partial**. The renderer emits `AGENTS.md`, `.codex/config.toml`, and the Tess commands as `.agents/skills/tess-*` skills (Codex does not load a project `.codex/prompts/` directory). The driver is not live-tested against native event samples and does not have native-parity certification. |
| Gemini CLI target | **C2 — manual-gated compatibility** | Enforcement level **Partial**, with no live model run. The renderer emits `GEMINI.md` (which imports `AGENTS.md`) and the Tess commands as `/tess:<command>`. It renders no Gemini hooks, settings or policies. There is no Gemini dispatch driver. |
| Generic `AGENTS.md` target | **C2 — manual-gated compatibility** | Enforcement level **Advisory** in the host tool. Emits instructions and plain prompts only. Host-specific orchestration, tool permissions, and command behavior are not implied. |
| `tessctl run` conductor | **Available** | Validates plans, gates, artifacts, retries, and escalation in a sequential execution model. Parallel execution and synthesis remain future work. |
| MCP server | **Available** | Provider-neutral stdio JSON-RPC with limited read/check tools. MCP connects tools and context; it is not a review or trust-enforcement mechanism. |
| Adopting an existing, hand-built Tess instance | **Unsupported** | 0.2.0 has no adopt command. Start from a fresh `create-tess` install. |
| Perplexity adapter/driver | **C0 — not supported** | Tess OS has no Perplexity repository adapter. A future read-only research-worker role is only a proposal. |
| All frontier models | **Unsupported as a blanket claim** | A model name, OpenAI-compatible API, or MCP support is not adapter conformance. Only the runtimes in the enforcement table above are covered, each at its stated level. |
| AEC governance defaults and advisory template | **Available** | The accepted, non-enforcing contract and offline validator are in `docs/AEC_GOVERNANCE_DEFAULTS.md` and `adapters/support-policy/`. This does not grade a real execution. |
| AEC runtime assurance grading and enforcement | **Planned** | AEC-C0-AEC-C4 completeness and T0-T3 source-trust defaults are accepted, but no runtime assigns or enforces those levels today. Adapter C0-C4 capability labels are separate and cannot satisfy AEC assurance. |
| Advanced retrieval memory | **Planned** | Current `kb/` conventions and memory doctrine are not a proven retrieval, lifecycle, ACL, or privacy system. |
| Tess Cloud | **Planned** | Optional cloud synchronization/coordination product, separate from the local core and not present here. |
| Tess Vault | **Planned** | Separate agent-era secret-capability product. It must never expose secrets to agent prompts, evidence, or memory. |

## v0.2.0 trust and custody facts

Re-verified on 2026-09-24 against the live repository, its GitHub ruleset,
and the build machine's keyring.

1. **v0.2.0 approvals were signed with an agent-held verifier key.** The
   registered verifier key is Cyra, fingerprint `F9321F92…76E8`. It has no
   passphrase and is stored on the build machine, where the build agents can
   use it. For each protected change, an agent that did not build it
   reviewed the full diff, and that review's verdict was signed with this
   key. No key was rotated for this release.
   **Custody hardening is the first v0.2.1 item:** a passphrase-protected or
   hardware-held key, a human sign-off on each verdict, and a decision on the
   merge-admission topology (#76).
2. **Enforcement is by process, not by GitHub.** The `main` ruleset requires
   six status checks (`tests (py3.9)`, `tests (py3.12)`,
   `create-tess tests (node 18)`, `create-tess tests (node 24)`,
   `secret scan (gitleaks)` and the App-bound `tessctl gate ci`), with strict
   up-to-date branches and no bypass actors. It requires 0 approving
   reviews, and the GitHub token the build agents use has admin rights on
   the repository. "Only a reviewed change merges" therefore holds because
   the maintainers follow that process, not because GitHub prevents
   anything else.
3. **The P0 type-swap gate bypass (the #71 lineage) remains open in v0.2.0.**
   Its fix, #181, is deferred to v0.2.1. #181 would freeze the verifier and
   sign-off registries with no reset authority, which would lock in the
   agent-held key described above.
4. **The gate is a non-authoritative preview.** A14, the multi-push
   policy-reduction case, is OPEN. The merge-admission topology (#76) is
   undecided. The committed `gate-arena` scorecard reports 12/12 attacks
   blocked; A14 is not part of that score.
5. **Gemini CLI is Partial, with no live model run.** The v0.2.0 checks
   cover the rendered files and Gemini CLI commands that need no sign-in.
   No Gemini model session was run against a Tess install.

## Production-gate status

**Not ready as a universal production claim.** The remaining production
requirements are:

1. independent, human custody of the registered verifier key and of every
   covering approval, without candidate self-authorization (today the key is
   agent-held; see fact 1);
2. an external, human-owned sign-off trust anchor (`signoff_keys` is empty);
3. a candidate policy and evidence path that cannot authorize its own key or
   approval, with the type-swap bypass and A14 closed;
4. admission enforced by the host rather than by process (see fact 2);
5. policy coverage for the actual runtime, installer, release, dependency,
   and trust-state surfaces; and
6. an honest adversarial-corpus result with every open case disclosed.

The current repository does not meet those conditions. A fresh
`npm create tess` scaffold starts with empty `verifier_keys` and
`signoff_keys`; this repository registers Cyra's public key and has an empty
sign-off registry.

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
