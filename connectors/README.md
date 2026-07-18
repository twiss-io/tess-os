# Connectors — the external-service seam

> Status: **v1 — three provider connectors, in-repo registry, real
> codegen seam.** Anthropic, OpenAI, and Google Gemini are registered,
> schema-valid, `T0` (declared-only). Zero business-app connectors, zero
> `T3`-audited connectors, zero distribution beyond `git pull`. Full
> architecture and honest vision-vs-v1 gap:
> [`docs/design/connectors-architecture.md`](../docs/design/connectors-architecture.md)
> (design doc — read it first; this file is the shipped-v1 pointer into
> it, not a restatement).

## Vocabulary — "connector", not "adapter"

`adapters/**` is a DIFFERENT seam: harness render targets (Claude Code,
Codex, generic — C0–C4 conformance). A **connector** is a declared,
versioned integration with an EXTERNAL SERVICE (Anthropic, OpenAI,
Gemini, …). Never call one the other; see design doc §2.

## Layout

```
connectors/
├── README.md                              this file
├── contracts/
│   └── connector-manifest.schema.json     advisory schema — outside core/contracts/,
│                                           never a gate/policy input (same fenced-off
│                                           treatment adapters/** and docs/** get)
├── manifest_validator.py                  offline, dependency-free structural checker
│                                           (same harness pattern as
│                                           tools/adapter_manifest_validator.py)
├── validate_connector_manifests.py        CLI wrapper
└── registry/
    ├── anthropic/  connector.json + README.md + fixtures/
    ├── openai/     connector.json + README.md + fixtures/
    └── gemini/     connector.json + README.md + fixtures/
```

Declaration = a directory with a schema-valid manifest. Discovery =
reading the directory (deterministic, offline, no network, no index
service). Installation = nothing — v1 connectors ship in-repo, so
"install" is `git pull`. `connectors/**` takes the exact same fenced-off
treatment `adapters/**`/`docs/**` get: prose + advisory artifacts, no
core→live compiled split, nothing here can ever be mistaken for a gate,
policy, or approval input.

## Validate the registry (checkout-local, read-only)

```sh
python3 -m connectors.validate_connector_manifests --root . --json
```

Checks (per manifest, and across the whole registry): `manifest_version`
pin, `id` matches its directory name, `version` is semver, `aliases`
never collide across connectors, `auth.scheme` is `"env"` (v1's only
supported scheme — `"vault-capability"` is reserved in the design doc but
fails validation until a real implementation lands), `auth.env` entries
are env-var-**NAME**-shaped (`^[A-Z][A-Z0-9_]*$`) — **a manifest carrying
an actual secret VALUE anywhere fails validation**, not just in the auth
block (see "No secrets, ever" below) — `limits.max_retries == 0`,
`error_map` values are recognized typed-error classes, and
`trust.tier` self-assertion never exceeds `T1` (`T2` requires a dated
evidence entry; `T3` is unconditionally rejected — see "Trust tiers"
below). Zero network, zero credentials, zero subprocess, zero write path.

## No secrets, ever

Every string in a manifest — not just `auth.env` — is scanned for
known provider-key shapes (`sk-…`, `sk-ant-…`, `AIza…`, `ghp_…`, `xox…`,
`AKIA…`, a bare `Bearer <token>`, or any generic 20+-char mixed-
case/digit run that isn't a name/URL/UUID/date) and rejected if found.
`auth.env` additionally requires every entry to be
SCREAMING_SNAKE_CASE — a real secret value essentially never satisfies
that shape, so the two checks overlap deliberately (defense in depth,
not two independent hopes).

## Trust tiers (T0–T3)

| Tier | Name | Who can assert it | Evidence |
|---|---|---|---|
| T0 | Declared | The manifest author | Schema-valid manifest, offline validator passes |
| T1 | Contract-tested | The repo's CI | T0 + a fixture suite covering every operation/error_map row, passing offline |
| T2 | Live-verified | The operator who ran it | T1 + a dated, operator-run live smoke recorded in the manifest's own `trust.evidence` |
| T3 | Audited | Only a registered verifier key | T2 + a signed ship-gate verdict + a published audit summary |

**`T3` is currently unreachable, mechanically, not just by policy.**
`core/policy/policy.yaml`'s `verifier_keys`/`signoff_keys` ship empty —
this repo's standing rule — and no agent may self-provision one. The
validator rejects `trust.tier: "T3"` on ANY manifest unconditionally;
this is enforcement, not a request. All three v1 connectors ship at
`T0`.

## The codegen seam — the through-line

`spec_engine.connector_resolver.resolve_connectors()` matches a spec's
`how_it_works.integrations` entries against this registry **at PLAN
time** — exact `id`/`alias` slug equality only, never fuzzy — and the
result rides through the approval gate bound into
`spec_engine.content.plan_content_hash()` (PR #82's existing HMAC
mechanism; no new trust machinery). `spec_engine.codegen.generate_app()`
then reads ONLY that frozen, approved snapshot — it never re-reads this
directory itself. A resolved integration gets a real, vendored `fetch()`
client (`generation_status: "generated-connector"`); an unresolved one
keeps today's honest, unchanged labeled `501` stub. Full design:
[`docs/design/connectors-architecture.md` §6](../docs/design/connectors-architecture.md).

## Out of scope for v1 (Xavier's calls, not built here)

The hosted/paid marketplace, third-party connector submission, and `T3`
activation (needs Xavier to register real verifier keys — never
agent-provisioned). See the design doc §11 for the full decision list.
