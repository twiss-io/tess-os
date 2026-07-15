# Memory and Orchestration Contract

> **Status: PROPOSED — non-executable architecture contract.** This document
> does not add a memory store, task-graph runtime, receipt format, capability
> enforcement, Cloud service, or Vault service. It neither changes policy nor
> grants authority to an agent, adapter, repository, or service.

## Purpose

Tess OS is a local governance and review harness, not a model-improvement
product. This proposed contract defines the boundaries an eventual portable
memory and orchestration layer must preserve while working with multiple agent
hosts. It is deliberately narrower than a claim to support every frontier
model: platform support is earned per versioned adapter and evidence level.

The contract has two jobs:

1. make durable context, task coordination, and secret handling composable;
   and
2. ensure none of those conveniences can become a substitute for independent
   approval, the signed ship gate, or protected VCS enforcement.

## Current foundations

The following are **current repository foundations**, with the limits stated
here. They are not proof that the proposed system below is implemented.

| Foundation | Current evidence and limit |
|---|---|
| Mission and crew-plan records | `tessctl mission` and the `missions/` contracts create file-backed mission records, gates, and retry records. The crew-plan schema expresses ordered stages, tasks, dependency references, and verifier requirements. |
| Local conductor loop | `tessctl run` validates a plan, dispatches through Claude, Codex, or fake drivers, reads contracted return artifacts, invokes required verification, applies typed retries, and records escalation. Its v1 execution is sequential; `parallel: true` is plan validation, not concurrent process execution, and synthesis is out of scope. |
| Return-manifest discipline | The existing return-manifest contract separates an agent's self-report from status, artifacts, claims, and evidence pointers. The conductor reads an artifact at a fixed path rather than trusting a final-message summary. |
| Local vault primitive | The repository contains a local, ref-only vault primitive using age/X25519 encrypted material. `tessctl vault exec` performs just-in-time child-environment injection. It is not the planned Tess Vault service or a general secret-capability control plane. |
| Adapter support labels | The current advisory adapter contract only permits C0–C3. Claude Code is C3 preview; Codex and generic `AGENTS.md` hosts are C2; Perplexity is C0. C4 cannot be self-asserted in a local manifest. |

## Non-goals

This proposal does **not**:

- claim that memory or orchestration improves a model's reasoning or output;
- turn prompts, MCP, local hooks, adapter manifests, or model APIs into a
  trust boundary;
- change the current signed gate, key custody, policy, verdict, or branch
  protection model;
- claim a multi-agent task-graph runtime, runtime receipt enforcement,
  advanced retrieval memory, Cloud, or a future Vault service exists today;
- claim C4 certification, protected delivery, or universal provider support;
- require Cloud or a future Vault service for local Tess OS use.

## Contract invariants

These are requirements for any future implementation. They must be enforced by
the relevant independent component before that component can make a production
claim.

1. **Memory is not authority.** A memory entry, retrieval result, summary,
   task graph, or receipt may inform work but may never approve a verdict,
   alter policy, satisfy a required gate, or establish a trust anchor.
2. **Secrets never become context.** Secret values must never enter an agent
   prompt, memory plane, trace, evidence receipt, task output, or Tess Cloud.
   A secret reference or opaque handle is not a secret value.
3. **Delegation only narrows authority.** A child work unit cannot expand its
   capability ceiling, issue an approval, approve its parent, or create its
   own trust material. It can request a separately evaluated action.
4. **Cloud is optional and not a trust root.** Tess Cloud may synchronize
   eligible records only after explicit privacy controls; it cannot silently
   upload prompts, issue approvals, hold the only evidence record, or replace
   a locally/verifiably enforced gate.
5. **Receipts are evidence, not verdicts.** A receipt records what a component
   declared or observed. It does not itself authorize shipping or prove a
   platform's certification.
6. **Adapters are capability-bounded.** An adapter may describe, preflight,
   execute within an allowed envelope, observe, and finalize. It may not mint
   keys, verdicts, approvals, or secret values.

## Proposed four-plane model

The following is a **proposed** data model. It replaces neither the current
memory-classification doctrine nor the current mission files until separately
implemented and reviewed.

| Plane | Proposed purpose | Explicit exclusion |
|---|---|---|
| Ephemeral work context | Bounded task-local inputs, workspace references, and expiry metadata used while a work unit runs. | No durable authority, secret values, or automatic promotion to long-lived memory. |
| Durable scoped knowledge | Opt-in facts, decisions, and playbooks with owner, scope, provenance, retention, and deletion fields. | No silent cross-project retrieval, default prompt retention, or policy mutation. |
| Immutable evidence ledger | Append-only references to artifacts, checks, decisions, and hashes that support later review. | No approval authority, raw secrets, or substitute for the independently enforced ship gate. |
| Secret-capability boundary | Opaque secret handles and the allowed result of a separately authorized secret operation. | No raw values in the other three planes, model context, receipts, traces, or Cloud. |

An implementation must make scope explicit: tenant/project, repository,
mission, work unit, principal, classification, retention rule, and provenance.
Retrieval is eligible only when the requesting work unit's declared scope and
capability ceiling permit it. A model's request alone is never sufficient.

## Proposed task graph and work units

The existing crew-plan and mission contracts are useful foundations, but this
is a **proposed** runtime model, not a statement that a graph scheduler exists.

```text
mission
  -> task graph (nodes + typed dependency edges)
      -> work unit (one bounded objective)
          -> adapter invocation
              -> artifacts and proposed execution receipt
```

Each proposed work unit should declare:

- stable mission, graph-node, work-unit, and parent identifiers;
- an immutable input/artifact reference set and workspace revision;
- intended adapter, host version, model identifier when available, and
  declared capabilities;
- a capability ceiling, budget/time limits, and isolation expectations;
- an output contract, evidence classification, and escalation path; and
- explicit state: planned, runnable, running, complete, blocked, failed,
  cancelled, or escalated.

Edges should be typed rather than inferred from prose: `requires-artifact`,
`requires-review`, `requires-decision`, `blocks-on-policy`, and
`may-run-after`. A scheduler must fail closed on unknown dependencies,
ambiguous ownership, invalid state transitions, or absent required artifacts.
It must not treat an agent's completion message as a graph transition.

### Proposed delegation ceiling

```text
parent capability ceiling
  -> child receives an equal-or-narrower, time-bounded subset
      -> child emits evidence or an action request
          -> independent policy/review path decides any protected action
```

This contract does not authorize autonomous nested delegation. Existing host
constraints still apply; for example, the documented orchestra model uses one
conductor as the sole dispatcher. Any future graph runtime must preserve that
host-specific control boundary or explicitly declare a different, independently
verified execution model.

## Proposed execution receipts

There is no implemented universal runtime receipt format. The current
return-manifest is a related foundation, not this proposed replacement.

A future receipt should contain no secrets and should be canonicalizable for
integrity checks. Its minimum shape is:

```yaml
receipt_version: "proposed-v1"
receipt_id: <stable identifier>
mission_id: <identifier>
work_unit_id: <identifier>
parent_work_unit_id: <identifier-or-null>
adapter:
  id: <adapter id>
  version: <adapter version>
  provider: <provider label>
  model: <reported model identifier or unavailable>
inputs:
  workspace_ref: <commit/tree/reference>
  artifact_hashes: [<hash>]
authority:
  declared_capabilities: [<capability>]
  granted_capability_ceiling: [<capability>]
execution:
  started_at: <timestamp>
  ended_at: <timestamp>
  result: complete|blocked|failed|cancelled|escalated
evidence:
  artifact_hashes: [<hash>]
  redaction_classification: <label>
  policy_reference: <identifier-or-null>
  review_reference: <identifier-or-null>
```

The `policy_reference` and `review_reference` fields are pointers only. They
cannot contain approval material, alter a policy, or convert a receipt into a
signed verdict. Receipt signing, timestamping, provenance attestation, storage
authority, and retention are deferred decisions.

## Adapter ceiling and promotion

The following levels are the **current documented ceiling** for the advisory
adapter vocabulary. They do not confer authority.

| Level | Meaning | Contract position |
|---|---|---|
| C0 | No adapter or driver exists. | Not supported. |
| C1 | Bounded read-only research worker may return cited material. | Future research-only role; no repository-action authority. |
| C2 | Instructions/local artifacts can support a manual gate; an unproven local driver may exist. | Compatibility preview; no protected-delivery claim. |
| C3 | Managed/reference adapter with lifecycle evidence beyond C2. | Preview only; never protected delivery. |
| C4 | Certified protected workflow. | **Deferred.** It requires independent conformance and external admission controls; it cannot be declared by an adapter manifest. |

A future adapter contract should require explicit capability discovery,
preflight, declared input/output boundaries, version-drift handling, denied
action reporting, and a self-test that proves its stated limits. An adapter is
not trusted merely because it supports MCP, has a compatible API, or names a
frontier model.

## Cloud and Vault boundaries

### Tess OS

Tess OS remains the local governance kernel. The baseline must continue to
work without Tess Cloud or a future Vault service. Its durable evidence must be
portable and independently inspectable rather than held only by a hosted
service.

### Tess Cloud — proposed and optional

Tess Cloud is a **future optional** synchronization and coordination layer
built against stable Tess OS contracts. Before any implementation can claim
sync, it needs approved tenancy, encryption, data-classification, residency,
retention, deletion, and incident-response designs.

Cloud may receive only explicitly eligible, redacted records. It must not
silently upload prompts, workspace contents, raw traces, secret handles that
could be resolved remotely, or secret values. It is not a verifier registry,
approval service, or trust root.

### Tess Vault — future service distinct from the local primitive

The current repository's local age-encrypted vault primitive is not Tess Vault
as a service. A **future Tess Vault** may offer scoped secret capabilities only
after independent cryptography, custody, recovery, revocation, audit, and
threat-model decisions. Tess OS and agents should receive an opaque handle,
the requested operation class, a policy decision, and an auditable outcome—no
raw secret value.

The future service must not expose secret values to memory, receipts, traces,
prompts, task outputs, or Cloud. It also must not become an approval shortcut
for protected repository changes.

## Adoption gates

The order below is a **proposal for future implementation**, not a claim that
these gates are met today.

| Gate | Required evidence before promotion |
|---|---|
| 1. Boundary specification | Versioned schemas and threat model for scope, redaction, capability narrowing, and graph state; negative tests for secret and authority leakage. |
| 2. Local reference implementation | Deterministic local behavior with contained paths, crash/retry semantics, and tests that denied dependencies, capability expansion, self-approval, and cross-scope retrieval fail. |
| 3. Receipt integrity | Canonical receipt encoding, artifact provenance rules, redaction verification, retention semantics, and a decision on attestation/custody. |
| 4. Adapter conformance | Versioned adapter evidence for capability mapping, isolation, denied actions, version drift, and provider-specific lifecycle behavior. C0–C3 labels remain exact until the evidence exists. |
| 5. Cloud admission | Explicit operator opt-in plus approved privacy, tenancy, encryption, residency, retention, deletion, and incident-response controls. |
| 6. Vault admission | An independently reviewed secret-capability design with custody, recovery, rotation, revocation, audit, and failure-mode evidence. |
| 7. Protected-workflow claim | External human-owned trust anchor, candidate-self-authorization prevention, required VCS checks, honest adversarial results, and independent C4 conformance evidence. |

Every gate must test its reverse direction: an unauthorized retrieval, secret
exposure attempt, capability expansion, self-approval attempt, unapproved
Cloud upload, or unsupported-adapter claim must be denied and leave an
auditable result.

## Deferred decisions for the operator

These are deliberately not decided by this document or an agent implementation:

- scope and tenancy model, including who may read, retain, export, or delete
  durable memory;
- retrieval eligibility, default retention, promotion from work context, and
  deletion/expiry semantics;
- Cloud data residency, encryption/custody, synchronization topology, and
  incident-response commitments;
- future Vault custody, recovery/escrow, revocation, rotation, and break-glass
  design;
- receipt provenance, attestation/signing, ledger storage, and audit access;
- graph scheduler isolation, budget accounting, cancellation, and delegation
  depth; and
- the independent evidence and external controls needed for a C4 claim.

## Claim audit

This document uses present tense only for repository foundations and their
published limits. It uses **proposed**, **future**, or **deferred** for every
advanced-memory, graph-runtime, receipt-runtime, capability-enforcement,
Cloud, future-Vault, and C4 statement.

| Current statement in this document | Primary source |
|---|---|
| Mission/crew-plan contracts and their limits | [`missions/README.md`](../missions/README.md), [`core/contracts/crew-plan.schema.json`](../core/contracts/crew-plan.schema.json) |
| Sequential `tessctl run`, artifact reading, verifier/retry limits | [`docs/STATUS.md`](STATUS.md), [`.tess/bin/tessctl`](../.tess/bin/tessctl) |
| Existing return-manifest boundary | [`core/contracts/return-manifest.schema.json`](../core/contracts/return-manifest.schema.json) |
| Local ref-only age/X25519 vault primitive | [`conductor/vault.md`](../conductor/vault.md), [`tests/test_m5_vault.py`](../tests/test_m5_vault.py) |
| C0–C3 ceiling and C4 exclusion | [`adapters/CONFORMANCE.md`](../adapters/CONFORMANCE.md), [`docs/STATUS.md`](STATUS.md) |
| Existing memory terminology and its non-automatic promotion rule | [`conductor/memory-model.md`](../conductor/memory-model.md) |
| One-conductor/one-level orchestration doctrine | [`conductor/orchestra-model.md`](../conductor/orchestra-model.md) |
