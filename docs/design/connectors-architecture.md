# Connectors + Marketplace — Architecture Design

> **Status: DESIGN.** Nothing in this document is built. No connector code,
> no schema file, no registry directory, and no codegen change exists yet —
> this is the blueprint for the build epic, written for Xavier's direction
> first. Where this document sketches an interface or a directory layout,
> that is a **proposal**, not a description of the repository. In
> `docs/STATUS.md` claim-label vocabulary, everything below is **Planned**
> except where a section explicitly cites something that already exists.
>
> Grounding: TESS-VISION-AND-BUILD-SPEC.html Phase 1 Epic E3 ("Model Router
> + Boilerplate Connectors v1"), Phase 3 Epic E8 ("Connector Registry +
> Audited Marketplace v1"), the "Marketplace — the honest version" callout
> in its Section B, and — in this repo — `spec_engine/codegen.py`'s
> `integration` module kind (today an honestly-labeled HTTP 501 stub),
> `orchestrator/`'s content-hash-bound approval gate, and
> `adapters/CONFORMANCE.md`'s evidence-tier discipline.

---

## 1. Why this document

The spine already runs end to end: freeform text → `intent_router` →
`spec_engine` intake/plan → an authenticated, content-hash-bound approval →
`spec_engine.codegen.generate_app()` → a real, runnable Node app
(`orchestrator/README.md` has the full flow). One module kind in that
pipeline is deliberately not real yet:

> `integration` → `src/integrations/<slug>.js` — a labeled connector STUB
> that always throws, wired to a route that returns HTTP 501.
> *"Deterministic codegen cannot produce a working third-party integration
> without real credentials/API contract details the spec does not carry."*
> — `spec_engine/codegen.py`

That stub label is exact, and it names its own cure. The spec cannot carry
a third party's API contract — but a **registered connector can**. A
connector is a versioned, reviewable artifact that carries precisely the
two things codegen is missing: the provider's API contract (endpoints,
request/response shapes, error taxonomy) and the auth *declaration* (which
env var names, never values). With that artifact present, the `integration`
module kind stops being a 501 stub and becomes generated, working client
code — deterministically, without codegen ever fabricating anything.

This document designs:

1. the connector contract (manifest + invoke surface + typed errors),
2. the codegen seam that turns the 501 stub into a real integration,
3. the first three provider connectors (Anthropic, OpenAI, Gemini),
4. the registry and its trust tiers, and the audit pipeline that would
   one day justify the word "marketplace",
5. the honest gap between the vision's marketplace language and what v1
   actually ships, and
6. a phased rollout with Xavier's decisions called out explicitly.

---

## 2. Vocabulary — "connector", not "adapter"

This repo already uses **adapter** for a different seam: `adapters/**` and
`adapters/CONFORMANCE.md` describe **harness render targets** (Claude Code,
Codex, generic `AGENTS.md` hosts) with C0–C4 conformance levels. That
vocabulary is taken and must not be overloaded.

Therefore, in tess-os:

| Term | Means | Lives at |
|---|---|---|
| **Adapter** | A harness render target / dispatch driver (C0–C4 vocabulary) | `adapters/**`, `.tess/bin/tessctl` |
| **Connector** | A declared, versioned integration with an external service (Anthropic, Slack, Stripe, …) | `connectors/**` (proposed — does not exist yet) |

The vision doc's E3 phrase "provider adapters for Anthropic/OpenAI/Google"
maps to **provider connectors** in this repo's vocabulary. Same intent,
non-colliding name. Trust tiers for connectors get their own scale (T0–T3,
§7) rather than reusing C0–C4, because the two measure different things:
C-levels measure *harness lifecycle conformance*; T-tiers measure
*integration trust evidence*.

---

## 3. Where connectors sit in the spine

Two consumers, one contract:

```
                       connectors/registry/<id>/connector.json
                       (the contract artifact — §4)
                              │
              ┌───────────────┴────────────────────┐
              ▼                                    ▼
   (a) GENERATION-TIME BINDING          (b) RUNTIME CONSUMERS (later)
   spec_engine.codegen resolves         The E3 model-router service
   spec.how_it_works.integrations       (per-step model choice, spend
   against the registry and emits       caps, usage ledger) consumes
   a REAL generated client into         the SAME manifests as its
   the app — v1 scope (§5)              provider substrate — later
                                        phase, not v1 (§9)
```

**v1 builds (a) only.** The codegen seam is the smallest change that makes
a generated app's integration genuinely work, it exercises the whole
contract, and it is dogfood-able the day it lands (a spec that says
"integrations: [Anthropic]" produces an app that can actually call
Anthropic). The router service, spend caps, and metering are E3's own
epic and are **not** smuggled in here — but the manifest is designed so
the router can sit on it without a breaking change (§5.4, §9).

A deliberate v1 design decision follows from this: **generation-time
binding, not runtime plugin loading.** The connector's client code is
generated *into* the app (vendored, deterministic, reviewable in the app's
own repo), not fetched or dynamically loaded at runtime. Runtime plugin
loading is a supply-chain surface the registry has not earned yet; a
vendored generated client is auditable with `git diff` and drift-checkable
like every other generated file. Runtime *mounting* (the MCP-compatible
tier, §8) is a later phase with its own trust story.

---

## 4. The connector contract

A connector is a directory in the registry containing a manifest, docs,
and contract-test fixtures. The manifest is the load-bearing artifact.

### 4.1 Manifest — `connector.json` (proposed schema `connector-manifest.v1`)

Advisory-schema posture, copied deliberately from
`adapters/contracts/adapter-manifest.schema.json`: the schema lives at
`connectors/contracts/connector-manifest.schema.json`, **outside**
`core/contracts/`, is not accepted by `tessctl validate`, and can never
grant authority, approval, or policy standing. It is validated by an
offline, dependency-free checker (same harness pattern as
`tools/validate_adapter_manifests.py`), which proves structural
consistency only — never provider behavior.

Fields (illustrative sketch — the build epic writes the real JSON Schema):

```jsonc
{
  "manifest_version": "connector-manifest.v1",
  "id": "anthropic",                  // stable slug, registry key
  "version": "0.1.0",                 // semver, bumped on ANY contract change
  "display_name": "Anthropic (Claude)",
  "aliases": ["claude"],              // resolver matches ONLY id + aliases (§6.2)
  "provider": {
    "base_url": "https://api.anthropic.com",
    "api_version_pin": { "header": "anthropic-version", "value": "2023-06-01" }
  },
  "auth": {
    "scheme": "env",                  // v1: the ONLY scheme. Reserved: "vault-capability"
    "env": ["ANTHROPIC_API_KEY"],     // names ONLY — a value here fails validation
    "header": { "name": "x-api-key" } // how the key is presented to the provider
  },
  "operations": [
    {
      "name": "generate",
      "description": "Single-turn or multi-turn text generation.",
      "side_effect": "spend",         // "read" | "write" | "spend" (§4.3)
      "idempotent": false,
      "http": { "method": "POST", "path": "/v1/messages" },
      "input_schema":  { /* normalized input — §5.2 */ },
      "output_schema": { /* normalized output — §5.2 */ }
    }
  ],
  "data_flows": [
    "Prompt/message content is sent to the provider.",
    "No data is sent anywhere other than provider.base_url."
  ],
  "error_map": { /* provider status/code -> typed error class — §4.4 */ },
  "limits": { "timeout_ms": 60000, "max_retries": 0 },
  "trust": {
    "tier": "T0",                     // T0–T3, §7 — self-declared at T0/T1 only;
                                      // T2/T3 require evidence artifacts (§7.2)
    "evidence": []
  }
}
```

Three non-negotiable properties, enforced by the offline validator:

- **No secrets, ever.** `auth.env` carries variable *names*. Any
  high-entropy or value-shaped string in an auth block fails validation.
  This is the same "keys in env/keychain only, never in specs or repos"
  rule E3 states, made mechanical.
- **Declared data flows.** E8's packaging requirement ("a manifest
  declaring permissions, data flows, and secret requirements") lands here:
  `data_flows` + `auth` + per-operation `side_effect` are the audit
  pipeline's grep surface (§7.3).
- **Version pinning.** The provider API version is pinned in the manifest
  (header or URL segment). Provider drift then has exactly two honest
  outcomes: fixture tests fail at registry CI time, or the generated
  client raises `ConnectorContractError` at runtime — never a silent
  behavior change.

### 4.2 Invoke surface

Uniform across every connector and every operation. Sketch of the
generated client's shape (v1 target stack `node-http-minimal`, Node core
`fetch()` only — zero npm dependencies, preserving codegen's existing
discipline):

```js
// src/integrations/anthropic.js  (GENERATED — illustrative shape only)
// generation_status: "generated-connector" (§6.3)
// Auth: reads process.env.ANTHROPIC_API_KEY at CALL time — never at boot,
// never logged, never echoed into any error message.

async function call(operation, input) {
  // 1. operation must be declared in the manifest -> else ConnectorInvocationError
  // 2. env var present?                           -> else ConnectorConfigError
  // 3. build request from the manifest's http + input mapping
  // 4. fetch() with AbortController timeout (limits.timeout_ms)
  // 5. map provider status via error_map           -> typed error, or
  // 6. validate + normalize response               -> { output, usage, raw }
}

module.exports = { call, OPERATIONS, CONNECTOR: { id, version, manifest_hash } };
```

Contract points, independent of language:

- `call(operation, input) → { output, usage, raw }` on success. `raw` is
  the provider's response passthrough — normalization is deliberately
  minimal (§5.2) and never destroys information.
- Every failure is a **typed error** (§4.4) that names the connector, the
  operation, and the remedy — and never contains a secret.
- Config is read lazily at call time. A generated app with three declared
  integrations and zero configured keys still boots, serves `/health`,
  and serves every non-integration route — the existing "it MUST actually
  run" guarantee is untouched. The generated server logs one loud boot
  WARNING per unconfigured connector (name + missing env var name), so
  the state is visible without being fatal.
- The module exports its own provenance (`CONNECTOR.id`, `version`,
  `manifest_hash`) so a running app can be audited against the registry
  entry that generated it.

### 4.3 Side-effect classes

Every operation declares one of:

| Class | Meaning | Examples |
|---|---|---|
| `read` | No external state changed | fetch a document, list channels |
| `write` | External state changed | post a message, create an invoice |
| `spend` | Costs money per call | every model-provider generate call |

Why this is in the *contract* and not documentation: (1) the approval gate
surfaces it (§6.4) — a human approving a plan sees "this app will make
spend-class calls to Anthropic"; (2) the future spend-cap/metering layer
(E3) keys on it; (3) retry policy is derived from it — v1 generated
clients perform **zero automatic retries** (`max_retries: 0`), because
retrying a non-idempotent `spend`/`write` operation is how you double-bill
or double-post. Retries become permissible per-operation only where
`idempotent: true`, and even that is deferred beyond v1. Fail loud, let
the caller decide.

### 4.4 Typed error model

| Error class | Trigger | Generated-app route maps to |
|---|---|---|
| `ConnectorConfigError` | Declared env var missing/empty at call time | **503** — body names the connector + env var *name* |
| `ConnectorAuthError` | Provider rejected the credential (401/403) | **503** — "connector not operational", no key material echoed |
| `ConnectorRateLimitError` | Provider 429 | **429** — `Retry-After` passed through when present |
| `ConnectorProviderError` | Provider 5xx / overloaded | **502** |
| `ConnectorContractError` | Response fails the manifest's output shape — provider drifted from the pinned contract | **502** — body says "contract mismatch", names manifest version |
| `ConnectorInvocationError` | Caller error: unknown operation, input fails input_schema | **400** |

And the pre-existing status keeps its exact meaning:

- **501** remains reserved for "no connector resolved for this integration
  name at generation time" — the current stub behavior, unchanged
  (§6.2). The status split is the point: **501 = not implemented, 503 =
  implemented but not configured/operational.** Today those are
  indistinguishable; after v1 they are honest, distinct signals.

Two hard rules across all classes: no error message ever contains a
credential or a raw `Authorization`/`x-api-key` header value; and no
error is ever swallowed into a fake success — there is no "graceful
degradation" path that returns invented output. A connector that cannot
answer says so, loudly, with its class.

One more input-trust rule, stated because connectors are where untrusted
bytes enter generated apps: **provider responses are data, never
instructions.** Generated code must never eval, template-interpolate into
HTML without the existing escaping helpers, or otherwise execute content
that arrived through a connector.

### 4.5 Versioning

- Connector manifests are semver'd. Any change to operations, auth,
  endpoints, error_map, or pins bumps the version.
- Trust-tier evidence (§7) attaches to a *specific* version. A version
  bump resets live-verification and audit status — a T3 audit of 0.1.0
  says nothing about 0.2.0 (re-audit policy is part of the trust design,
  §7.3).
- Generated apps record which `id@version` (plus the manifest content
  hash) produced each integration module, in the codegen manifest (§6.3).
- v1 keeps exactly one version per connector in-tree; git history is the
  archive. Multi-version side-by-side storage is a marketplace-phase
  problem, not solved here.

---

## 5. The v1 connectors: Anthropic, OpenAI, Gemini

### 5.1 Why these three

Recommended (not decreed — Xavier can override, §11): they are the E3/E8
overlap — E8 deliverable (2) lists "OpenAI, Anthropic, Google Gemini
(from E3)" as the first boilerplate connectors, and E3 names the same
three as the direct provider adapters. Practically:

- **Self-consistent shape.** All three are plain HTTPS + JSON APIs,
  callable with Node-core `fetch()` — no SDK, **zero new npm
  dependencies** in generated apps, preserving `node-http-minimal`'s
  entire reason for existing.
- **Well-documented, stable, versioned** public contracts — the cheapest
  possible first exercise of the manifest's api-version-pin machinery.
- **Dogfood-able immediately.** The operator already holds keys for all
  three; a generated app that calls a model is the single most useful
  integration for every app the spec-engine is likely to generate.
- One shared normalized operation (`generate`) proves the contract's
  normalization posture on a real, non-trivial case (§5.2) — three
  providers, three different auth headers, three different body shapes,
  one invoke surface.

### 5.2 Provider mapping onto the contract

| | Anthropic | OpenAI | Gemini |
|---|---|---|---|
| Endpoint | `POST /v1/messages` | `POST /v1/chat/completions` | `POST /v1beta/models/{model}:generateContent` |
| Base URL | `api.anthropic.com` | `api.openai.com` | `generativelanguage.googleapis.com` |
| Auth header | `x-api-key` | `Authorization: Bearer` | `x-goog-api-key` |
| Env var | `ANTHROPIC_API_KEY` | `OPENAI_API_KEY` | `GEMINI_API_KEY` |
| Version pin | `anthropic-version` header | URL path (`/v1/`) | URL path (`/v1beta/`) |
| System prompt | top-level `system` field | `system`/`developer` role message | `systemInstruction` field |
| Usage fields | `usage.input_tokens` / `output_tokens` | `usage.prompt_tokens` / `completion_tokens` | `usageMetadata.promptTokenCount` / `candidatesTokenCount` |

(The table is orientation, not the contract — each manifest carries the
authoritative mapping, and the build epic verifies every row against the
live provider docs at build time rather than trusting this document.)

Normalized `generate` operation, all three connectors:

```jsonc
// input (normalized)
{ "model": "…", "messages": [{ "role": "user|assistant|system", "text": "…" }],
  "max_tokens": 1024, "temperature": 0.7 }

// output (normalized)
{ "text": "…", "stop_reason": "end|max_tokens|other",
  "usage": { "input_tokens": 0, "output_tokens": 0 },
  "raw": { /* full provider response, untouched */ } }
```

**Normalization posture — minimal and honest.** The normalized surface is
the common denominator only (text in, text + usage out). Everything
provider-specific rides in `raw`, unmapped. This layer is explicitly
**not** a universal LLM abstraction — no tool-use normalization, no
streaming, no multimodal in v1. Pretending otherwise is how connector
layers rot; the router epic (E3) is where richer cross-provider semantics
belong, and it can read `raw`. The `usage` block is normalized *now*,
though, precisely so E3's ledger has a stable substrate later (§9).

Known contract hazards to encode in manifests rather than discover in
production: OpenAI's `max_tokens` → `max_completion_tokens` migration on
newer models (the manifest's input mapping owns this translation);
Gemini's `v1beta` path (pin it and let fixture tests catch a forced
migration); Anthropic's `529 overloaded` (maps to
`ConnectorProviderError`). OpenAI's newer Responses API
(`POST /v1/responses`) is noted and deliberately **not** chosen for v1 —
`chat/completions` is the stable, universally documented surface;
revisiting is a one-line manifest version bump later, which is exactly
what the versioning model is for.

### 5.3 Contract tests — how a connector proves itself without keys

Per connector, two test layers (design; built in the build epic):

1. **Fixture tests (always run, CI, offline).** Recorded request/response
   pairs in `connectors/registry/<id>/fixtures/`. Prove: request
   construction from normalized input, response normalization, every
   `error_map` row, and the no-secret-in-errors rule. These run on every
   PR with zero keys and zero network — same offline discipline as the
   adapter-manifest harness.
2. **Live smoke (operator-run, key-gated).** A minimal real round-trip
   per provider, run only when the operator's own env carries the key;
   **skipped loudly, never silently**, when it does not (the skip message
   states what was not proven). A passing live run — with its date — is
   what T2 evidence (§7.2) records. CI stays green without keys *and*
   without pretending live verification happened.

### 5.4 What these three explicitly do NOT deliver

To keep E3's honest scope visible: no per-step model routing, no spend
caps, no usage ledger, no aggregator for long-tail models, no streaming.
Those are the router service's deliverables, on top of this substrate.
Anyone reading "Tess has Anthropic/OpenAI/Gemini connectors" should hear
"generated apps can make real, typed, fail-loud calls to three model
providers with BYO keys" — nothing more.

---

## 6. The codegen seam — from 501 stub to real integration

The through-line of this whole design. Everything in this section is a
**proposed change to `spec_engine.codegen` and `spec_engine.plan_builder`**
(build epic; nothing changed today).

### 6.1 Today (verified current state)

`spec.how_it_works.integrations` is a `List[str]` of free-text names
(`spec-engine/schema/spec.schema.json`). For each, codegen emits
`src/integrations/<slug>.js` — a labeled stub that always throws — and a
route returning 501. Manifest row: `generation_status: "stub"`. This is
honest and correct: the spec genuinely does not carry an API contract.

### 6.2 Resolution — integration name → registered connector

A resolver (proposed `spec_engine/connector_resolver.py`) maps each
integration name against the registry:

- **Match rule: exact slug or manifest-declared alias only.** Slugified
  integration name must equal a connector `id` or one of its `aliases`.
  Deliberately *stricter* than `_match_entity_by_name`'s substring
  heuristic: a false negative costs a labeled stub (safe, today's
  behavior); a false positive would wire real external calls to the wrong
  provider. No fuzzy guessing across that line.
- **No match → today's behavior, unchanged**, with one improvement: the
  stub's manifest note also states which connector ids *were* registered,
  so "why is Stripe still a 501?" is answerable from the artifact alone.
- **Resolution is deterministic**: a pure function of (spec, registry
  contents). The registry directory joins spec + scaffold plan as codegen
  inputs; determinism now reads "same spec + same plan + same registry →
  byte-identical output," and the manifest hash it records (§6.3) is what
  makes "same registry" checkable.

### 6.3 Generation — a fourth generation status

`GENERATION_STATUSES` grows one value (additive, mirroring the documented
additive path for target stacks):

| `generation_status` | Meaning |
|---|---|
| `generated` | Real, working code (unchanged) |
| `generated-stub-logic` | Real wiring, TODO business logic (unchanged) |
| `stub` | Labeled placeholder, not functional (unchanged — now only for *unresolved* integrations) |
| **`generated-connector`** *(new)* | Real client generated from a registered connector manifest; operational once its declared env var is configured |

The codegen-manifest row for a resolved integration records: connector
`id`, `version`, manifest content hash, the operations wired, the declared
env var names, and the side-effect classes. The generated app's README
section "What's real vs. stub" gains a third honest category: *"real
connector client — configure `ANTHROPIC_API_KEY` to make it operational;
until then its route returns 503 (not 501)."*

`generated-connector` is deliberately **not** `generated`: the code is
real, but operability depends on runtime configuration the repo cannot
carry. Collapsing that distinction would be exactly the overstatement the
per-module manifest exists to prevent.

### 6.4 The approval gate must see the connector surface

The governance-critical seam. `orchestrator/`'s approval gate signs a
**content hash of the plan** (PR #82's hardening), precisely so an
approval cannot be replayed against different content. Connectors expand
what an approval *means* — approving a plan now approves real external
calls, real data flows, and spend-class operations. Therefore:

- **Resolution runs at plan time, before the gate** — not at generate
  time. The plan carries the resolved connector set: per integration,
  either `connector id@version + manifest_hash + env vars + side-effect
  classes` or an explicit `unresolved → will be a labeled 501 stub`.
- `plan.summary_for_approval` states it in plain language: *"This app
  will call Anthropic (spend-class) using the key in ANTHROPIC_API_KEY.
  'Stripe' has no registered connector and will be generated as a
  non-functional labeled stub."*
- Because the resolved set is **inside the plan content hash**, swapping
  a registry entry (or the registry itself) between approval and
  generation invalidates the approval — codegen's existing
  plan-vs-approval verification catches it with no new mechanism.
  Generate-time resolution re-runs and **fails loud** on any mismatch
  with the approved set; it never silently re-resolves.

This is the connector layer inheriting the spine's existing trust
discipline instead of bolting a parallel one on beside it — and it is
also the marketing-honesty backstop: nobody approves "integrations" in
the abstract; they approve a named list of providers, env vars, and
side-effect classes.

### 6.5 v1 acceptance criteria (for the build epic)

1. A spec with `integrations: ["Anthropic"]` generates
   `src/integrations/anthropic.js` with `generation_status:
   "generated-connector"`; with `ANTHROPIC_API_KEY` configured, `POST
   /api/integrations/anthropic` round-trips a real prompt (operator-run,
   key-gated live test).
2. Without the key: the route returns **503** with a body naming the
   connector and the missing env var *name* — never 200, never invented
   output, never the key echoed.
3. A spec with `integrations: ["Stripe"]` (unregistered) behaves exactly
   as today — labeled stub, 501 — with the manifest note listing the
   registered connector ids.
4. Determinism: same spec + plan + registry → byte-identical generated
   files across runs (extends the existing determinism test).
5. The approval summary lists the resolved connector surface; a registry
   entry mutated after approval causes generation to refuse (verified by
   an adversarial test in the spirit of
   `tests/orchestrator/test_pipeline_adversarial.py`).
6. Secret scan of the generated app and of `connectors/**` finds zero
   credentials; generated code contains env var **names** only.
7. All three providers' fixture tests pass offline in CI; live smokes
   pass when the operator supplies keys, and skip loudly when not.

---

## 7. Registry and trust tiers — the architecture the word "marketplace" has to earn

### 7.1 v1 registry: a directory, not a service

```
connectors/
├── README.md                    # this seam's prose, adapters/README.md-style
├── contracts/
│   └── connector-manifest.schema.json    # advisory — outside core/contracts/
└── registry/
    ├── anthropic/
    │   ├── connector.json
    │   ├── README.md            # human-facing: what it does, data flows, limits
    │   └── fixtures/            # recorded contract-test request/response pairs
    ├── openai/…
    └── gemini/…
```

Declaration = a directory with a schema-valid manifest. Discovery =
reading the directory (deterministic, offline, no network, no index
service). Installation = nothing: v1 connectors ship in-repo, so "install"
is `git pull`. Versioning = the manifest's semver + git history (§4.5).
Trust verification = the tier system below. An offline validator (the
adapter-manifest harness pattern) checks every registry entry's structural
consistency in CI.

`connectors/**` takes the same fenced-off manifest treatment as
`adapters/**` and `docs/**` (prose + advisory artifacts; no core→live
render split), which also means: nothing in the registry can ever be
mistaken for a gate, policy, or approval input. Distribution beyond
in-repo — a hosted index, fetch-with-lockfile installs, third-party
submissions — is Phase C3, and mostly Xavier's call (§11).

### 7.2 Trust tiers T0–T3

Evidence-based, per connector **per version**, self-assertable only at
the bottom — the same philosophy as `adapters/CONFORMANCE.md`'s C-levels
(where a self-authored manifest cannot assert C4), applied to
integrations:

| Tier | Name | Evidence required | Who can assert it |
|---|---|---|---|
| **T0** | Declared | Schema-valid manifest; offline validator passes | The manifest author |
| **T1** | Contract-tested | T0 + fixture suite covering every operation and every error_map row, passing in CI | The repo's CI |
| **T2** | Live-verified | T1 + a dated, operator-run live smoke against the real provider, recorded in the registry entry | The operator who ran it |
| **T3** | Audited | T2 + a ship-gate review with a **signed verifier verdict** + a **published audit summary** (permission surface, data flows, secret handling, failure modes, injection surface) | Only a verifier whose key is registered in `core/policy/policy.yaml` |

Rules that make the tiers mean something:

- A manifest's own `trust.tier` field can claim at most T1; T2/T3 exist
  only as evidence artifacts (dated live-smoke records; signed verdicts)
  that the validator checks for presence and internal consistency. A
  self-authored JSON file cannot promote itself — same fail-closed stance
  as sign-offs and verdicts everywhere else in this repo.
- **T3 is currently unreachable, by design.** The shipped
  `verifier_keys`/`signoff_keys` registries in `core/policy/policy.yaml`
  are deliberately empty, and this design does not change that — a real
  human operator registers real keys (never self-provisioned by an
  agent; that rule is absolute). Until that operator step happens, the
  honest maximum for any connector is T2. This document *designs* the T3
  pipeline; it cannot and does not activate it.
- Version bump → tier evidence resets to whatever re-runs (T1 re-proves
  itself in CI automatically; T2/T3 require fresh human/verifier acts).
  Re-audit cadence for T3 (every version? every minor?) is an audit-
  pipeline policy decision flagged for the C2 phase.

**Non-conflation note** (the same one `orchestrator/README.md` draws for
its approval gate): the T3 audit *uses* the ship-gate machinery — signed
verdicts from registered verifier keys — but a connector audit verdict is
a new artifact class about a registry entry. It is not a spec-approval,
not a repo-merge verdict, and never a policy input. One engine, three
clearly-separated meanings; this document adds the third without blurring
the first two.

### 7.3 What a T3 audit actually contains

Designed now so C2 has a checklist rather than a vibe:

1. **Permission surface**: every endpoint the connector can touch, every
   side-effect class, enumerated and matched against the manifest — an
   undeclared capability fails the audit (E8's own fail-closed acceptance
   criterion).
2. **Secret handling**: key material appears in exactly one place
   (outbound auth header construction); provably absent from logs,
   errors, and generated output. Mechanical grep + adversarial fixture.
3. **Data flows**: what content leaves, to where, matched against
   `data_flows` declarations.
4. **Failure honesty**: every error_map row exercised; no path returns
   invented success.
5. **Injection surface**: provider responses handled as data (§4.4);
   escaping verified on every path into generated HTML.
6. **Red-team pass**: an adversarial reviewer (the standing Codex
   red-team pattern) attacks 1–5.
7. **Published summary**: the audit result — including anything open —
   published in the registry entry. An audit that can't be published
   isn't a trust asset.

### 7.4 Marketplace — what the word is allowed to mean, when

"Marketplace" = registry + trust tiers + **distribution** + **third-party
supply** + (possibly) commerce. v1 ships the first two only, in-repo.
There is no submission flow, no hosted index, no billing, no third-party
anything in v1 — and no design in this document depends on them existing.
The MCP-compatible mount tier (§8) is the honest v1 answer to breadth.
Everything beyond that is C3 phase and majority-Xavier-decision (§11).

---

## 8. The MCP-compatible tier — breadth without overclaiming

The vision's honest formulation is *"thousands compatible (MCP), dozens
audited, every audit published."* Architecture mapping:

- **Compatible** = any existing MCP server an operator mounts into their
  harness themselves. This is an operator configuration act, not a
  registry artifact; tess-os neither vets, ships, nor takes credit for
  it. v1 does exactly one thing here: documents the counting rule —
  mounted MCP servers are *never* counted as Tess connectors, mirroring
  the vision's Section A correction that ambient MCP config "must not be
  represented as" a Tess-engineered connector layer.
- **Audited** = T3 registry entries, of which v1 has **zero** (§7.2).
- A future `kind: "mcp-bridge"` connector — a manifest that *describes*
  an external MCP server, carries its trust tier, and lets the resolver
  target it — is sketched as the C3 mechanism for pulling mounted servers
  into the governed world one at a time. Design only; nothing in v1
  depends on it.

---

## 9. Relationship to the E3 router service (explicitly out of scope)

E3's router (TypeScript service: per-step model choice, fail-closed spend
caps, usage ledger, aggregator for long-tail models) is a **runtime
consumer** of these manifests, not a competitor to them. The contract
prepares for it in exactly three ways, none of which build any router
machinery: normalized `usage` in every generate output (the ledger's
substrate), the `spend` side-effect class (the cap's trigger), and
manifest-declared provider pins (the router's provider table). The
aggregator adapter E3 mentions (e.g. OpenRouter-style breadth) is an
**external paid dependency and therefore a Xavier decision** — nothing
here assumes it.

---

## 10. Honest reality check — vision vs. v1

Stated plainly, because this section is the one most likely to be quoted:

| Vision language | What it actually is | v1 reality |
|---|---|---|
| "Thousands of integrations" | The MCP ecosystem, mountable by an operator — *compatible*, not built, not vetted | **3 connectors** (Anthropic, OpenAI, Gemini), in-repo |
| "Enterprise-audited" / "audited marketplace" | A **trust process** (T3 pipeline, §7.3) requiring registered verifier keys, per-connector audit labor, re-audits per version, published summaries | **0 audited connectors.** T3 is designed but unreachable until the operator registers real verifier keys — deliberately not a switch anyone can flip, least of all an agent |
| "Connector marketplace" | Registry + trust + distribution + third-party supply + commerce | **Registry skeleton only**, in-repo; no distribution, no submissions, no commerce |
| "Boilerplate connectors v1" (E3/E8) | Model providers + ~20 business apps | Model providers only; business apps are the C2 phase and a Xavier prioritization call |
| "Model router, spend caps, hundreds of models" | E3's own service epic | **None of it** — this design only lays the substrate (§9) |

What "enterprise-audited" would actually require, spelled out once:
registered human-owned verifier keys (an operator ceremony, per
`conductor/verdict-signing.md`'s model — never agent-provisioned); the
§7.3 checklist exercised per connector per version, with real hours of
review and red-team labor each time; a published-audit norm including
open findings (the repo already practices this — the gate-arena scorecard
discloses its open A14 case, and `docs/STATUS.md` cites it as a reason
the production gate is **Not ready**); a re-audit and revocation policy;
and a disclosure channel. That is an operating cost that scales linearly
with the catalog, which is precisely why "dozens audited" is the honest
ceiling of the vision and "thousands audited" appears nowhere in this
design.

The defensible v1 claim, in full: *"Generated apps get real, typed,
fail-loud connector clients for Anthropic, OpenAI, and Gemini, resolved
from a versioned registry, with BYO keys, an approval gate that shows the
human exactly which external calls they're approving, and a designed —
not yet exercised — audit tier."* Anything grander waits for the evidence.

---

## 11. Phased rollout and the decisions that are Xavier's

### Phase C1 — v1 (the build epic this document feeds)

Contract schema + offline validator; `connectors/registry/` with the
three provider connectors at T1 (T2 once the operator runs live smokes);
the resolver + plan-time binding + approval-surface change; codegen's
`generated-connector` status; fixture + adversarial tests; acceptance
criteria in §6.5. Zero new runtime dependencies anywhere (Python stdlib
in the spine, Node core in generated apps).

### Phase C2 — first expansion + first audits

The first business-app connectors (category priority: **Xavier's call**,
§ below); the T3 audit pipeline exercised end-to-end on the existing
three (gated on verifier-key registration: **Xavier**); re-audit policy;
spend-cap/ledger substrate handshake with the E3 router epic as it lands.

### Phase C3 — distribution and the marketplace question

MCP-bridge connector kind; any registry distribution beyond in-repo;
third-party submission + review flow; commerce, if ever. Every item here
is majority-decision, not engineering-default.

### Decisions reserved for Xavier — none of these are made in this document

1. **v1 connector set confirmation** — Anthropic/OpenAI/Gemini is the
   recommendation (§5.1); he may swap or add.
2. **Post-provider category priority** — which business connectors come
   first in C2 (the vision's candidate list: Sheets/Docs, Slack, Notion,
   Airtable, HubSpot, email/SMS, GitHub, Supabase, Vercel, Telegram).
3. **Verifier-key provisioning for the T3 tier** — whose keys, when.
   Without this act the audited tier stays designed-but-empty, and this
   document says so rather than working around it.
4. **The marketplace/trust model itself** — in-repo registry only vs.
   hosted index; whether third-party connectors are ever accepted; who
   audits at scale; whether audits are a paid service.
5. **Any paid/external dependency** — explicitly including an aggregator
   (OpenRouter-style) for long-tail model breadth, and any hosted
   registry infrastructure. Nothing in C1 requires any.
6. **Repo placement** — recommendation: `connectors/**` lives in tess-os
   (v1 registry is small, and the codegen seam wants atomic co-review);
   a split into its own repo is a reversible later call.
7. **Tess Vault interplay** — the manifest reserves `auth.scheme:
   "vault-capability"` (§4.1) to match `docs/STATUS.md`'s Vault
   direction (scoped secret capabilities, never secret values in model
   context); whether/when Vault becomes the recommended scheme is his
   product call.

### Open flags — where this design is least certain

- **Plan-time vs. generate-time resolution** (§6.4): plan-time binding is
  the governance-correct choice, but it makes the registry an input to
  the *plan* content hash — a registry edit between plan and approval
  invalidates in-flight plans. Believed correct (that invalidation is the
  feature), but it is the design decision most worth a second opinion.
- **Normalization depth** (§5.2): the minimal `generate` surface is
  deliberately thin; if the E3 router epic starts before C1 lands, the
  two should co-design the normalized shapes rather than inherit these.
- **OpenAI surface choice** (§5.2): `chat/completions` over the Responses
  API for v1 stability — a judgment call, cheap to revisit via version
  bump, flagged for the build epic to re-verify against current provider
  docs.

---

## 12. Non-goals (v1)

No runtime plugin loading; no MCP proxy/bridge machinery; no router,
spend caps, metering, or ledger; no streaming or multimodal
normalization; no automatic retries; no hosted registry, submission flow,
or commerce; no third-party connectors; no audited-tier activation; no
change to `core/policy/**`, `core/contracts/**`, the ship-gate engine, or
the approval-gate mechanism (the seam *feeds* the existing gate richer
content; it does not modify it).

---

*Design doc only — see the Status banner. Cross-references:
`spec_engine/codegen.py` (the stub this design retires),
`spec-engine/schema/spec.schema.json` (`how_it_works.integrations`),
`orchestrator/README.md` (approval gate + non-conflation precedent),
`adapters/CONFORMANCE.md` + `adapters/README.md` (evidence-tier and
advisory-manifest patterns copied here), `docs/STATUS.md` (claim labels;
Vault direction), TESS-VISION-AND-BUILD-SPEC.html (E3, E8, Pillar 04,
"Marketplace — the honest version").*
