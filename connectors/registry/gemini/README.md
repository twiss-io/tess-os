# Connector — Google Gemini

> Registry entry for `connectors/registry/gemini/connector.json`
> (`connector-manifest.v1`). See [`connectors/README.md`](../../README.md)
> and [`docs/design/connectors-architecture.md`](../../../docs/design/connectors-architecture.md)
> for the full architecture this entry plugs into.

## What it does

One operation, `generate` — single-turn or multi-turn text generation via
`generateContent` (`POST /v1beta/models/{model}:generateContent`). The
model name rides in the URL PATH, not the body — this connector
substitutes `input.model` into the path at call time.
`side_effect: "spend"` — every call costs money; v1 performs zero
automatic retries (`max_retries: 0`).

## Auth

- **Scheme:** `env` (v1's only supported scheme).
- **Env var:** `GEMINI_API_KEY` — read at CALL time, never at boot.
- **Header:** `x-goog-api-key: <value of GEMINI_API_KEY>` (no prefix).
  Deliberately the header form, never the legacy `?key=` query-string
  form — a key never belongs in a URL that could end up in an access log.
- **Base URL override (testing/self-hosted-proxy only):**
  `GEMINI_API_BASE_URL`, if set, replaces
  `https://generativelanguage.googleapis.com`. Not a secret — a network
  target override.

## Data flows

`input.messages` (a `"system"`-role entry is sent separately as
`systemInstruction`, matching Gemini's own request shape) and
`input.model`/`max_tokens`/`temperature` are sent, as JSON, to
`provider.base_url` over HTTPS. Nothing goes anywhere else. The
provider's full raw response comes back to the caller in `output.raw`,
untouched.

## Errors

| Provider status | Typed error | Generated route status |
|---|---|---|
| 401 / 403 | `ConnectorAuthError` | 503 |
| 400 | `ConnectorInvocationError` | 400 |
| 429 | `ConnectorRateLimitError` | 429 |
| 500 / 502 / 503 | `ConnectorProviderError` | 502 |

Missing/empty `GEMINI_API_KEY` at call time → `ConnectorConfigError` →
**503**, never a silent failure, never `200`.

## Trust tier

`T0` (declared — schema-valid manifest only). See
[`docs/design/connectors-architecture.md` §7.2](../../../docs/design/connectors-architecture.md)
for the T0–T3 scale; `T3` is unreachable until Xavier registers a real
verifier key in `core/policy/policy.yaml` (currently empty by design —
this entry does not and cannot change that).

## Fixtures

[`fixtures/`](fixtures/) — hand-authored, representative request/response
pairs (success + 401/429/500) matching Gemini's own published API shape
as of 2026-07-18. Not captured real traffic; no credential of any kind
appears in any fixture file.
