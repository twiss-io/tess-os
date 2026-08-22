# Agent Execution Contract governance defaults

> **Decision status: accepted. Implementation status: planned.** These are
> the defaults a future Agent Execution Contract (AEC), memory layer, routing
> runtime, Tess Cloud, and Tess Vault integration must satisfy. This document
> does not implement runtime enforcement, enable a provider, upload data,
> change the ship gate, or grant approval authority.

## Decision

Tess OS will remain local-only, zero-spend, and non-routing by default. Future
execution evidence will be graded on two independent axes:

- **AEC-C (completeness)** asks how much of an execution can be reconstructed.
- **T (source trust)** asks how independently the evidence can be trusted.

A complete self-report can still be untrusted. A signed approval can still be
incomplete. Neither axis substitutes for the independently enforced ship gate.
The `AEC-C0`-`AEC-C4` namespace is deliberately distinct from the adapter
capability levels `C0`-`C4`. An adapter's `C3` label never implies or satisfies
`AEC-C3/T2`. The AEC `T0`-`T3` namespace is also separate from the
connector-manifest trust tier with the same shorthand.

### Assurance defaults

| Security tier | Minimum AEC assurance | Status | Meaning |
|---|---:|---|---|
| Unclassified/default | AEC-C0/T0 | **Available** as the declared fallback; runtime grading is **planned** | Missing or unrecognized evidence receives no inferred assurance. |
| Local informational | AEC-C1/T0 | **Planned** | Basic producer-declared identity and outcome; informational use only. |
| Auditable, non-protected work | AEC-C2/T1 | **Planned** | Structured local evidence with bounded inputs, outputs, tools, and results. |
| Protected repositories | AEC-C3/T2 | **Planned** | Reconstructable execution plus independently issued, artifact-bound receipts. |
| Release or high-security work | AEC-C4/T3 | **Planned** | Complete conformance evidence plus externally enforced admission and a human-owned trust anchor. |

The default is always **AEC-C0/T0**. A same-user host or adapter cannot exceed
**T1** unless independent receipts bind the claimed execution to immutable
artifacts. A producer receipt is evidence, never an APPROVE verdict. It cannot
register its own key, authorize itself, or satisfy a human sign-off.

## Data and privacy defaults

- Execution, metadata, and policy evaluation stay local by default.
- Cloud synchronization, remote indexing, and automatic external-model
  routing are disabled by default.
- `clients/**`, `kb/**`, `.tess/state/**`, `operator/**`, and every vault,
  key, sign-off, or secret-bearing path are ineligible for automatic indexing.
- Raw prompts, raw tool results, secret values, credentials, private keys,
  tokens, session material, and unredacted client content are excluded from
  durable AEC evidence by default.
- Secret credential material must never enter prompts, receipts, evidence,
  memory, traces, logs, or Tess Cloud. A narrowly scoped opaque reference may
  identify an operation without exposing its value.
- Provider execution is opt-in for each run. The request must declare the
  endpoint, region or an explicit `unknown`, provider retention mode, and tool
  profile before dispatch. Missing declarations deny the request.

## Retention defaults

No durable raw AEC content is allowed until storage, tenant isolation, and
verified deletion are implemented. A future conforming local implementation
may keep only minimal redacted metadata for **7 days** by default. This is a
normative future contract, not a claim that the current runtime performs
automatic expiry.

Permanent evidence requires an explicit operator setting naming the scope and
retention purpose. Expiry or deletion must not erase a required approval
artifact while a protected release still depends on it; that lifecycle must be
defined by the future storage implementation before it can be marked available.

## Credentials and cost defaults

- Ambient environment-variable inheritance is denied.
- A run may request only an explicitly allowlisted credential name and class,
  through a short-lived, scoped reference. Secret material is never returned
  to the model or stored in AEC evidence.
- The default model and tool budget is **USD 0.00**, enforced as a hard stop.
- Any non-zero budget must be explicitly set by the owner for that run and
  name the cost scope. Silence, a provider default, or an adapter default is
  not authorization to spend.

## Tess Cloud and Tess Vault admission

Both products remain **planned and disabled**.

Tess Cloud cannot become available until tenancy, encryption and custody,
data classification, residency, retention, verified deletion, incident
response, and export controls are implemented and approved.

The future Tess Vault service cannot become available until tenancy, custody,
recovery, rotation, revocation, scoped reference resolution, audit, verified
deletion, and incident response are implemented and independently reviewed.
The repository's current local encrypted-vault primitive is not the Tess Vault
service.

## Machine-readable template

The advisory template is
[`adapters/support-policy/aec-support-policy.template.json`](../adapters/support-policy/aec-support-policy.template.json),
with its documentation schema in
[`adapters/contracts/aec-support-policy.schema.json`](../adapters/contracts/aec-support-policy.schema.json).
Validate it without changing the checkout or contacting a provider:

```sh
python3 -m tools.validate_aec_support_policy --root . --json
```

The validator and schema are documentation controls. They do not enforce a
runtime, certify an adapter, alter policy, or approve a repository change.

## Promotion rule

Use only these public support labels:

| Label | Meaning |
|---|---|
| **Available** | Present and testable in the repository, with its limits stated. |
| **Preview** | Implemented in part but not certified for the protected use claimed. |
| **Planned** | An accepted direction or contract that is not implemented. |
| **Unsupported** | No conforming implementation or evidence exists. |

AEC-C3, AEC-C4, T2, or T3 may not be advertised as available merely because the
template names the target. Promotion requires the evidence declarations in the
machine-readable contract, repository-local artifacts for those declarations,
independent review, and the external controls appropriate to the tier.
