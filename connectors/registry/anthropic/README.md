# Connector — Anthropic (Claude)

> Registry entry for `connectors/registry/anthropic/connector.json`
> (`connector-manifest.v1`). See [`connectors/README.md`](../../README.md)
> and [`docs/design/connectors-architecture.md`](../../../docs/design/connectors-architecture.md)
> for the full architecture this entry plugs into.

## What it does

One operation, `generate` — single-turn or multi-turn text generation via
Anthropic's Messages API (`POST /v1/messages`, pinned to
`anthropic-version: 2023-06-01`). `side_effect: "spend"` — every call
costs money; v1 performs zero automatic retries (`max_retries: 0`).

## Auth

- **Scheme:** `env` (v1's only supported scheme).
- **Env var:** `ANTHROPIC_API_KEY` — the connector reads this at CALL
  time, never at boot. The manifest names the env var; it never carries
  a value.
- **Header:** `x-api-key: <value of ANTHROPIC_API_KEY>` (no prefix).
- **Base URL override (testing/self-hosted-proxy only):**
  `ANTHROPIC_API_BASE_URL`, if set, replaces `https://api.anthropic.com`.
  Not a secret — a network target override, disclosed and versioned like
  everything else in the manifest. **https-pinned at runtime:** a
  non-`https://` value is refused with a `ConnectorConfigError` (503)
  before any network call — this override cannot be used to downgrade the
  manifest's https-only guarantee to cleartext.

## Data flows

`input.messages` (all roles, including any `"system"`-role entries) and
`input.model`/`max_tokens`/`temperature` are sent, as JSON, to
`provider.base_url` over HTTPS. Nothing goes anywhere else. The
provider's full raw response comes back to the caller in `output.raw`,
untouched.

## Errors

| Provider status | Typed error | Generated route status |
|---|---|---|
| 401 / 403 | `ConnectorAuthError` | 503 |
| 400 | `ConnectorInvocationError` | 400 |
| 429 | `ConnectorRateLimitError` (Retry-After passed through) | 429 |
| 500 / 502 / 503 | `ConnectorProviderError` | 502 |
| 529 (Anthropic-wide overload — distinct from the per-account 429) | `ConnectorProviderError` | 502 |

Missing/empty `ANTHROPIC_API_KEY` at call time → `ConnectorConfigError` →
**503**, never a silent failure, never `200`.

## Known v1 limitation

`max_tokens` is required by this endpoint (Anthropic has no server-side
default) and is forwarded exactly as given — this connector applies no
capping, clamping, or model-aware default of its own.

## Trust tier

`T0` (declared — schema-valid manifest only). See
[`docs/design/connectors-architecture.md` §7.2](../../../docs/design/connectors-architecture.md)
for the T0–T3 scale; `T3` is unreachable until Xavier registers a real
verifier key in `core/policy/policy.yaml` (currently empty by design —
this entry does not and cannot change that).

## Fixtures

[`fixtures/`](fixtures/) — hand-authored, representative request/response
pairs (success + 401/429/529) matching Anthropic's own published API
shape as of 2026-07-18. Not captured real traffic; no credential of any
kind appears in any fixture file.
