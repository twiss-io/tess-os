# Tess product family

Tess OS, Tess Cloud, and Tess Vault are intended to share contracts without
collapsing into one security boundary.

```text
                           optional, verified records
                  +--------------------------------------+
                  |                                      v
agent output -> Tess OS local governance core      Tess Cloud (planned)
                  |
                  | opaque, scoped capability request
                  v
             Tess Vault (planned)
```

## Tess OS — available as a technology preview

Tess OS is the local, open-source core in this repository. Its current purpose
is to apply policy, validate evidence, render bounded host integrations, and
fail closed before a protected delivery step.

It also contains a sequential conductor loop, mission contracts, local traces,
an experimental GUI, and a small age-encrypted local vault primitive. Those
pieces are not a production cloud control plane, a mature parallel
orchestration runtime, or the future Tess Vault service.

## Tess Cloud — planned optional coordination

Tess Cloud is a future product direction for synchronizing permitted mission
state, verified records, and coordination metadata across installations. It is
not implemented in this repository and no current command silently uploads
Tess OS content to it.

Cloud must remain optional. A local gate must not need Cloud to know which
public identities or policy are trusted, and a Cloud outage must not become a
reason to fail open. Any implementation needs explicit tenancy, consent,
encryption, retention, deletion, regional, and audit boundaries before public
production claims.

## Tess Vault — planned credential capabilities

Tess Vault is a future agent-era credential-capability service built on stable
Tess OS policy and evidence contracts. It should issue a narrowly scoped,
time-bounded capability to perform an allowed action instead of handing a raw
secret to a model.

Raw credentials must stay out of prompts, model context, memory, traces, review
evidence, return artifacts, logs, and Tess Cloud. Tess OS should observe only
the opaque request, the policy decision, and a redacted audit outcome.

The current local `tessctl vault` primitive encrypts local values with `age`.
It is an implementation primitive, not the planned Tess Vault product, hosted
service, approval system, or guarantee that a downstream tool cannot expose a
secret.

## Dependency direction

- Tess Cloud and Tess Vault may depend on versioned Tess OS contracts.
- Tess OS must not require either service for local governance.
- Neither service may mint review authority for a candidate change.
- Memory and orchestration may consume redacted facts, never raw credentials
  or implicit approval.

These are architectural constraints and roadmap directions, not launch dates,
pricing, availability, or data-processing commitments.
