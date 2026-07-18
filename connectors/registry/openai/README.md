# Connector — OpenAI

> Registry entry for `connectors/registry/openai/connector.json`
> (`connector-manifest.v1`). See [`connectors/README.md`](../../README.md)
> and [`docs/design/connectors-architecture.md`](../../../docs/design/connectors-architecture.md)
> for the full architecture this entry plugs into.

## What it does

One operation, `generate` — single-turn or multi-turn text generation via
the STABLE Chat Completions surface (`POST /v1/chat/completions`), not
the newer Responses API (`POST /v1/responses`) — a deliberate v1
stability choice, cheap to revisit later via a version bump.
`side_effect: "spend"` — every call costs money; v1 performs zero
automatic retries (`max_retries: 0`).

## Auth

- **Scheme:** `env` (v1's only supported scheme).
- **Env var:** `OPENAI_API_KEY` — read at CALL time, never at boot.
- **Header:** `Authorization: Bearer <value of OPENAI_API_KEY>`.
- **Base URL override (testing/self-hosted-proxy only):**
  `OPENAI_API_BASE_URL`, if set, replaces `https://api.openai.com`. Not a
  secret — a network target override. **https-pinned at runtime:** a
  non-`https://` value is refused with a `ConnectorConfigError` (503)
  before any network call — this override cannot be used to downgrade the
  manifest's https-only guarantee to cleartext.

## Data flows

`input.messages` (a `"system"`-role entry rides in as an ordinary chat
message) and `input.model`/`max_tokens`/`temperature` are sent, as JSON,
to `provider.base_url` over HTTPS. Nothing goes anywhere else. The
provider's full raw response comes back to the caller in `output.raw`,
untouched.

## Errors

| Provider status | Typed error | Generated route status |
|---|---|---|
| 401 / 403 | `ConnectorAuthError` | 503 |
| 400 | `ConnectorInvocationError` | 400 |
| 429 | `ConnectorRateLimitError` (Retry-After passed through) | 429 |
| 500 / 502 / 503 | `ConnectorProviderError` | 502 |

Missing/empty `OPENAI_API_KEY` at call time → `ConnectorConfigError` →
**503**, never a silent failure, never `200`.

## Known v1 limitation — o-series reasoning models

This connector sends the normalized `max_tokens` field as the request
body's `max_tokens`. OpenAI's o-series reasoning models (`o1`/`o3`/
`o4-mini`) reject `max_tokens` and require `max_completion_tokens`
instead. This connector does NOT special-case model family — the
normalized input carries no model-family signal to key on. Calling
`generate` with an o-series model name surfaces the provider's own `400`
as a typed `ConnectorInvocationError` (see error map above), never a
silent failure or a guessed-parameter retry. Fixing this properly (a
model-family-aware input mapping) is a manifest version bump, not a v1
scope item — see `connectors-architecture.md` §5.2's own "known contract
hazards" list.

## Trust tier

`T0` (declared — schema-valid manifest only). See
[`docs/design/connectors-architecture.md` §7.2](../../../docs/design/connectors-architecture.md)
for the T0–T3 scale; `T3` is unreachable until Xavier registers a real
verifier key in `core/policy/policy.yaml` (currently empty by design —
this entry does not and cannot change that).

## Fixtures

[`fixtures/`](fixtures/) — hand-authored, representative request/response
pairs (success + 401/429/500) matching OpenAI's own published API shape
as of 2026-07-18. Not captured real traffic; no credential of any kind
appears in any fixture file.
