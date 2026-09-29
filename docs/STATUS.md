# Support and status

This page is the public claim boundary for Tess OS. It separates what is in the
repository today from pilot work and product plans. It describes v1.0.0, and
its facts were re-verified on 2026-09-29.

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
different amounts of Tess. These levels follow
[Adapter conformance](../adapters/CONFORMANCE.md).

| Level | Meaning |
|---|---|
| **Enforced** | The runtime loads the Tess doctrine natively and runs Tess's shipped hooks natively; a hook that blocks stops the tool call. |
| **Partial** | The doctrine loads natively. Some enforcement exists (the runtime's own sandbox or approval settings rendered by Tess, or Tess's Claude hooks read by a compatible runtime), with documented gaps or fail-open cases. |
| **Advisory** | The runtime can read the doctrine as text. Nothing Tess ships can block a tool call there. |
| **unverified** | Not verified against the runtime's documentation for this release. No level is claimed. |

A level covers in-session enforcement only. The ship gate runs in git (the
pre-push hook, once installed) and in CI, outside every runtime, so it applies
to a change whatever tool produced it.

| Runtime | Enforcement | Basis and limits |
|---|---|---|
| Claude Code | **Enforced** | Reference target and driver. The hooks in `.claude/settings.json` run natively (`dispatch-guard` only warns, by design). Since v1.0 Tess's PreToolUse safety gate (`.claude/hooks/tess-gate.py`, sha-pinned, run through `run-pinned.py --on-fail block`) runs on every `Bash`, `Edit`, `Write`, `MultiEdit` and `NotebookEdit` call and blocks edits to Tess's security-tier and enforcement files, attempts to skip or re-point Tess's git hooks, `gh auth token`, secret-shaped values in commands, and a push of brain/ or clients/ data to a public or unverifiable remote; force pushes, remote changes and visibility changes ask you first (denied in `bypassPermissions`/`dontAsk` mode, which cannot ask). Checked live with Claude Code 2.1.284 in a fresh install on 2026-09-29: a commit that skips the git hooks and an Edit to `conductor/guardrails.md` were blocked by the Tess gate (its decision log recorded both). The hooks also run in `claude -p` in a folder that was never trusted, but the project's tool allow list does not (see docs/brain/ONBOARDING.md). The shell checks read the command text (an interpreter one-liner is not seen); the ship gate in git and CI stays the wall. The merge gate is still a preview (see below). |
| Codex CLI | **Enforced** | `codex` target: `AGENTS.md`, `.codex/config.toml`, and the Tess commands as `.agents/skills/tess-*` skills (`$tess-<command>`). Enforced once the project is trusted and Tess hooks are approved in `/hooks`: from then on Tess's PreToolUse safety gate (`.claude/hooks/tess-gate.py`, sha-pinned) runs on every shell command, file edit, subagent spawn and MCP call and blocks what it refuses; approval is pinned to the hook's hash, so re-approve after a Tess update. Until then only Codex's own sandbox and approval settings apply. The shell checks read the command text (an interpreter one-liner is not seen); the ship gate in git and CI stays the wall. The `AGENTS.md` chain is capped at 32 KiB. |
| Gemini CLI | **Advisory** | `gemini` target: `GEMINI.md`, which imports `AGENTS.md`, plus the Tess commands as `/tess:<command>`. The doctrine and commands load natively, but only in a trusted folder. Nothing Tess ships can block a tool call in Gemini: no Tess hook, setting or policy is rendered for it in this release, so the ship gate in git and CI is the only enforcement. No live Gemini model run has been part of the release checks. |
| GitHub Copilot CLI, Cursor | **Partial** | No dedicated target. Both read `CLAUDE.md`, `AGENTS.md`, `.claude/agents`, and the Claude hooks. Not tested by Tess OS. Copilot hook timeouts fail open; Cursor fails open on hook crashes and timeouts. Both load the doctrine twice. |
| Other `AGENTS.md` tools (for example OpenCode, Amp, Devin Desktop, Jules, Aider, Kiro, Qwen Code) | **Advisory** | Doctrine text only (Aider needs `read: [AGENTS.md]` in its config). |
| Cline, Roo Code, and any runtime not listed here | **unverified** | Not verified for this release. |

The per-runtime evidence is in [Adapter conformance](../adapters/CONFORMANCE.md).
The C0–C4 labels in the matrix below are a separate scale: they grade how much
lifecycle evidence exists for an adapter, not how much it enforces.

## Current matrix

| Capability or surface | Label | Current boundary |
|---|---|---|
| Local policy and gate CLI | **Preview** | The engine can validate policy/evidence and fail closed. The live `main` ruleset requires the App-bound gate and CI checks. The gate is still a non-authoritative preview: see [v1.0.0 trust facts](#v100-trust-facts). |
| Agent Receipt spec + standalone verifier + emit CLI + demo (System B — GPG, `verdict`/`signoff`) | **Available** | `core/contracts/agent-receipt.schema.json`, `tools/receipt-verify/`, `tools/receipt-emit/`, and `examples/receipt-demo/` (see `docs/AGENT_RECEIPT_SPEC.md`) are present, tested, and runnable with real GPG signatures — including `tools/receipt-emit/`, which actually PRODUCES a real, chained, self-verified receipt from an already-signed verdict or hard-floor sign-off (not just the demo's illustrative walkthrough). Not wired into `tessctl gate`; not a claim of external adoption. This repository's policy registers one verifier key (Cyra); `signoff_keys` remains empty. A receipt is not independently trusted merely because it is signed: custody, signer identity, artifact binding, and the applicable gate path still have to verify. |
| Agent Receipt emission from a codegen run (System A — local HMAC, `decision_kind: local_approval`) | **Available** | `orchestrator.pipeline.run_pipeline()` (`orchestrator/mission_receipt.py`, Hop 7) now emits a real, locally HMAC-signed, independently re-verifiable `local_approval` Agent Receipt for a successful codegen run, wired directly into the pipeline — opt-in only (off unless a caller supplies `receipt_path`; most callers never do). `tools/receipt-verify/hmac_verify.py` (the standalone `local_approval` counterpart to `gpg_verify.py`) and `core/contracts/agent-receipt.schema.json`'s `$defs.LocalApprovalArtifact` verify/validate it. Deliberately WEAKER, and structurally distinct, evidence than the GPG-backed row above — verifiable only by a holder of the same local secret key, never a public key; see `docs/AGENT_RECEIPT_SPEC.md`'s "★ Trust levels are not interchangeable." Always a single genesis receipt to one JSON file per run — durable, cross-run JSONL-chain persistence is still a disclosed, scoped follow-up, not built here. The full idea→route→approve→boots→receipt-verify (+ rejection, + mid-kill unhappy-path) DoD B.9 end-to-end proof now EXISTS and passes: `tests/orchestrator/test_e2e_wedge_loop.py`, driven entirely through `run_pipeline()`, Node hard-required (not silently skipped) in CI — see `orchestrator/README.md`'s "Wedge-loop epic addition" section. |
| Auditor pack export + verify (`tessctl audit export`/`verify`) | **Available** | Exports the accountability ledger (+ any caller-supplied Agent Receipts) for a scope into a self-contained, offline-verifiable bundle (`docs/AUDIT_PACK_SPEC.md`). Tamper-evident via the ledger's unsigned hash chain, not cryptographically non-repudiable; does not perform GPG signature verification (delegated to `tools/receipt-verify/`); a `full`-scope export's tail anchor (`.tip`) is asserted so a dropped tail is detected, but a `task`/range-scoped (partial) export still cannot prove no matching event was omitted by the exporter. |
| Ten-role roster + lens library (v0.2) | **Available** | Nine dispatchable role files (`.tess/core/agents-dispatch/`) plus the conductor, identical on every starter path; ~140 former personas are lenses in `conductor/lenses/` (index `docs/LENSES.md`). Role permissions are enforced by each runtime's tool list / sandbox mode; path restrictions such as Clio's brain-only writes and Vega's gate-only push are doctrine in the role text, not engine-enforced. |
| Claude Code target and driver | **C3 — managed-adapter preview** | Reference integration; enforcement level **Enforced**. It remains an uncertified preview for protected delivery. |
| Codex target and driver | **C2 — manual-gated compatibility** | Enforcement level **Enforced** once the project is trusted and Tess hooks are approved in `/hooks`. The renderer emits `AGENTS.md`, `.codex/config.toml`, the Tess commands as `.agents/skills/tess-*` skills (Codex does not load a project `.codex/prompts/` directory), and one `.codex/agents/<name>.toml` per installed role (sandbox mode from the role file). The driver is not live-tested against native event samples and does not have native-parity certification. |
| Gemini CLI target | **C2 — manual-gated compatibility** | Enforcement level **Advisory**, with no live model run. The renderer emits `GEMINI.md` (which imports `AGENTS.md`) and the Tess commands as `/tess:<command>`. It renders no Gemini hooks, settings or policies. There is no Gemini dispatch driver. |
| Generic `AGENTS.md` target | **C2 — manual-gated compatibility** | Enforcement level **Advisory** in the host tool. Emits instructions and plain prompts only. Host-specific orchestration, tool permissions, and command behavior are not implied. |
| `tessctl run` conductor | **Available** | Validates plans, gates, artifacts, retries, and escalation in a sequential execution model. Parallel execution and synthesis remain future work. |
| MCP server | **Available** | Provider-neutral stdio JSON-RPC with limited read/check tools. MCP connects tools and context; it is not a review or trust-enforcement mechanism. |
| Adopting an existing, hand-built Tess instance | **Unsupported** | There is no adopt command. Start from a fresh `create-tess` install. |
| Perplexity adapter/driver | **C0 — not supported** | Tess OS has no Perplexity repository adapter. A future read-only research-worker role is only a proposal. |
| All frontier models | **Unsupported as a blanket claim** | A model name, OpenAI-compatible API, or MCP support is not adapter conformance. Only the runtimes in the enforcement table above are covered, each at its stated level. |
| AEC governance defaults and advisory template | **Available** | The accepted, non-enforcing contract and offline validator are in `docs/AEC_GOVERNANCE_DEFAULTS.md` and `adapters/support-policy/`. This does not grade a real execution. |
| AEC runtime assurance grading and enforcement | **Planned** | AEC-C0-AEC-C4 completeness and T0-T3 source-trust defaults are accepted, but no runtime assigns or enforces those levels today. Adapter C0-C4 capability labels are separate and cannot satisfy AEC assurance. |
| Advanced retrieval memory | **Planned** | Current `kb/` conventions and memory doctrine are not a proven retrieval, lifecycle, ACL, or privacy system. |
| Tess Cloud | **Planned** | Optional cloud synchronization/coordination product, separate from the local core and not present here. |
| Tess Vault | **Planned** | Separate agent-era secret-capability product. It must never expose secrets to agent prompts, evidence, or memory. |

## v1.0.0 trust facts

Re-verified on 2026-09-29. The full trust model is in
[SECURITY.md](../SECURITY.md#trust-model).

1. **Verifier approvals are automated attestations.** The registered
   verifier key is Cyra, fingerprint `F9321F92…76E8`. By design it has no
   passphrase and is used by the review automation. An agent that did not
   build a protected change reviews it and signs the verdict, so a Cyra
   signature means the automated review passed, not that a person approved.
2. **Merges to `main` need no human review, by design.** The `main` ruleset
   requires six status checks (`tests (py3.9)`, `tests (py3.12)`,
   `create-tess tests (node 18)`, `create-tess tests (node 24)`,
   `secret scan (gitleaks)` and the App-bound `tessctl gate ci`), with strict
   up-to-date branches and no bypass actors, and 0 approving reviews. `main`
   is therefore not a release; only a signed tag is.
3. **The release signing key is the single human root of trust.** Nothing
   reaches users unless it comes from a tag signed with that key, and every
   use of the key needs the maintainer's explicit approval. `tessctl update`
   and `self-update` check the tag against the pinned keys (SSH, and OpenPGP
   when gpg is installed) on the user's machine before any file changes. The
   P0 type-swap gate bypass (#71 lineage) is closed: the gate sees type
   changes, deletions and renames of protected paths. A fresh install's
   first push passes the gate with no reviewer keys because it carries the
   signed release's proof; any protected file that differs from that release
   still needs a verdict.
4. **The gate is a merge check, not the release control.** The A14
   multi-push policy-reduction case is out of scope under the trust model:
   `main` protections are best-effort, and users are protected by the signed
   release and the pinned key when they update. The committed `gate-arena`
   scorecard reports 12/12 attacks blocked; A14 is not part of that score.
5. **Gemini CLI is Advisory, with no live model run.** The doctrine and
   the Tess commands load natively, but Tess renders no Gemini hook,
   setting or policy, so nothing Tess ships can block a tool call there; the
   ship gate in git and CI is the only enforcement.

## Production-gate status

**Not ready as a universal production claim.** The remaining production
requirements are:

1. independent, human custody of every covering approval where a project
   needs a person, not only the automated verifier, to approve (see fact 1);
2. an external, human-owned sign-off trust anchor (`signoff_keys` is empty);
3. a candidate policy and evidence path that cannot authorize its own key or
   approval (the type-swap bypass is closed; A14 is out of scope, see fact 4);
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
