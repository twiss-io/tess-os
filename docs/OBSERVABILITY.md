# Observability — mission trace log + OTel GenAI export (Goal #8)

> Engine: `.tess/bin/tessctl`, the isolated `TRACE` region (search `Goal #8` in
> the file). CLI: `tessctl trace export`. Spec context:
> `docs/ULTIMATE_FRAMEWORK_PLAN.md`.

Tess OS shipped with zero observability: `tessctl gate` and `tessctl validate`
made pass/block decisions that left no record anywhere except a one-off
terminal print. This closes that gap with two pieces:

1. **A local-first JSONL trace** — every `gate`/`validate` invocation appends
   one structured event to disk. No daemon, no buffering, no network.
2. **An on-demand OTLP-JSON export** (`tessctl trace export --format
   otlp-json`) that maps the JSONL to [OTel GenAI semantic-convention][genai]
   agent spans — the same `gen_ai.*` shape Datadog, Honeycomb, New Relic, and
   the OTel Collector already ingest natively, and the same shape CrewAI/
   LangGraph instrumentations emit for their own agent frameworks. Feed the
   export to any OTLP/JSON-compatible collector or file-based ingest path and
   Tess OS becomes legible to that tool's existing GenAI dashboards — without
   Tess OS itself ever making a network call.

[genai]: https://github.com/open-telemetry/semantic-conventions-genai

## What's captured today

Exactly two code paths are instrumented, because exactly two deterministic
decision points exist in the engine today:

| Command | `phase` | `action` |
|---|---|---|
| `tessctl gate pre-commit` | `gate` | `gate.pre-commit` |
| `tessctl gate pre-push` | `gate` | `gate.pre-push` |
| `tessctl gate ci` | `gate` | `gate.ci` |
| `tessctl validate <type> <file>` | `validate` | `validate` |

**Not instrumented yet:** `tessctl run` exists as a sequential mechanical
conductor loop, but it does not currently emit the trace events documented on
this page. Its future instrumentation can use the same recorder and schema; it
does not require a telemetry redesign.

Every invocation of the four call-sites above appends **exactly one** event,
whether the outcome is a clean pass, a deterministic block, or a fail-closed
infrastructure error (a bad git ref, a missing/invalid policy file, an
unreadable contract instance). The trace is a record of what the gate/
validator DECIDED, not a verbose execution log — it is not a substitute for
`--json`'s already-rich per-invocation output, it is what persists after that
output scrolls off a terminal.

### Event shape (`TRACE_EVENT_SCHEMA`, `schema: "tess.trace.v1"`)

```json
{
  "schema": "tess.trace.v1",
  "event_id": "d2d5317f4a8f420386a3dde170896b48",
  "timestamp": "2026-07-07T10:31:10.273090Z",
  "run_id": "f437a6d0df1648cf9f851631e6234ced",
  "mission_id": "m1",
  "phase": "validate",
  "action": "validate",
  "outcome": "block",
  "exit_code": 1,
  "duration_ms": 3.201,
  "subject": {"contract_type": "brief", "file": "missions/m1/briefs/task1.brief.md"},
  "counts": {"violations": 2},
  "reasons": ["$.milestones: expected type array, got NoneType"]
}
```

- **`outcome`** is one of `pass` / `block` / `error` — `block` is a
  deterministic refusal (a schema-miss, a ship-gate rule with no covering
  verdict); `error` is a fail-closed infrastructure failure (git command
  failed, policy file missing/invalid, instance file unreadable) — the same
  distinction `GateSpineError` vs. an ordinary `{"blocked": true}` result
  already draws inside the engine, now surfaced in the trace too.
- **`mission_id`** is inferred from the `missions/<id>/...` path convention
  (`core/contracts/README.md`, `GATE_CONTRACT_PATH_PATTERNS`) already used by
  `tessctl gate`'s own contract-type inference — never invented, never a
  fallback UUID.
- **`reasons`** is capped at 20 entries (`TRACE_MAX_REASONS`) with a
  `"...and N more (truncated for the trace log)"` marker, so one huge
  violation list can never blow up a JSONL line.
- Every event is validated against `TRACE_EVENT_SCHEMA` (the same generic
  `schema_validate()` engine `core/contracts/*.schema.json` already use)
  **before** it is written — a tracer bug raises `TraceError` loudly inside
  `_trace_append_event`'s own tests, but at the real gate/validate call-sites
  that same failure is caught by `_trace_record` and downgraded to a
  non-fatal stderr `WARNING`. A trace-log write failure must never flip the
  exit code of the security-critical command it is merely observing.

### Where it's written

- **Mission-scoped** — `missions/<id>/trace.jsonl`, appended, when at least
  one path in the gate/validate call is `missions/<id>/...`-shaped. This is a
  normal working-tree file in the SAME bucket as
  `missions/<id>/{briefs,verdicts,returns}/**` — committing it (or not) is the
  mission owner's call, same as any other mission record. `trace.jsonl`
  itself is deliberately placed at the mission root, not inside `briefs/` /
  `verdicts/` / `returns/`, so the gate's own contract-type inference never
  mistakes it for a brief/verdict/return-manifest instance.
- **Fallback (no mission id)** — `.tess/trace/runs/<run_id>.jsonl`, one file
  per process invocation. This is local runtime state, the same
  never-core-managed, gitignored bucket `.tess/snapshots/**` and
  `.tess/staging/**` already occupy (see `tess.manifest.json`'s
  `never_touch` and `.gitignore`) — it is never written through
  `guarded_write` / the manifest write-gate, and `tessctl doctor` / `verify`
  / `lock --check` have no opinion on it.

## Exporting — `tessctl trace export --format otlp-json`

```bash
./tessctl trace export --format otlp-json                       # every trace.jsonl this repo has, to stdout
./tessctl trace export --format otlp-json --mission-id m1        # just missions/m1/trace.jsonl
./tessctl trace export --format otlp-json --in some/file.jsonl   # explicit file(s) (repeatable), overrides discovery
./tessctl trace export --format otlp-json --out /tmp/spans.json  # write to disk instead of stdout
```

Discovery (no `--in` given): every `missions/*/trace.jsonl` plus every
`.tess/trace/runs/*.jsonl`, sorted for deterministic ordering. A line that
fails to parse as JSON, or parses but fails `TRACE_EVENT_SCHEMA`, is skipped
(reported to stderr as `SKIPPED: <file>:<line>: <reason>`) rather than
aborting the whole export — a single corrupt line never blocks exporting
every other valid one.

### The OTel GenAI mapping

Each event becomes one [`invoke_agent` **internal** span][agent-spans] — the
same span kind and shape the upstream semantic conventions document for
in-process agent frameworks ("Examples: LangChain agents, CrewAI agents"),
which is exactly what a deterministic engine invocation like `tessctl gate`/
`tessctl validate` is, structurally: a local, in-process operation with a
clear pass/fail outcome, no remote model call.

[agent-spans]: https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md

| `gen_ai.*` attribute | Value | Requirement level (upstream) |
|---|---|---|
| `gen_ai.operation.name` | `"invoke_agent"` | Required |
| `gen_ai.agent.name` | `tessctl.<action>` (e.g. `tessctl.gate.ci`) | Conditionally required when available — always populated |
| `gen_ai.agent.id` | `tessctl:<action>` | Conditionally required if applicable — always populated |
| `gen_ai.agent.description` | Human-readable one-liner per action | Conditionally required when available — always populated |
| `gen_ai.conversation.id` | the event's `mission_id`, when present | Conditionally required when available — a mission IS the "session" a sequence of gate/validate calls belongs to |
| `error.type` | `"tess.<outcome>"` | Conditionally required if the operation ended in an error — set whenever `outcome` is `block` or `error` |

Everything Tess-OS-specific that is **not** part of the `gen_ai.*` registry
(changed-path counts, contract type, the capped `reasons` list, the run/event
ids, the exit code) is namespaced under `tess.*` — the upstream conventions
explicitly allow additional attributes alongside the required/recommended
set; nothing here repurposes a `gen_ai.*` key for a non-standard meaning.

**Span/trace ids** are derived deterministically (`sha256` of the run id /
event id, truncated to the correct length) rather than randomly — re-running
the export against the same JSONL always produces byte-identical OTLP-JSON,
which makes the output diffable and trivially testable. Every event within
one `tessctl` process invocation shares one `run_id` (and therefore one
`traceId`); a future multi-event command groups naturally under it.

**Structure**: a standard OTLP/JSON `TracesData` document
(`resourceSpans` → `scopeSpans` → `spans`), verified against the canonical
`examples/trace.json` in [`open-telemetry/opentelemetry-proto`][otlp-proto] —
`traceId`/`spanId` are lowercase hex (32/16 chars), `kind`/`status.code` are
the documented integers (`1` = `SPAN_KIND_INTERNAL`, `1`/`2` =
`STATUS_CODE_OK`/`STATUS_CODE_ERROR`), and 64-bit fields
(`startTimeUnixNano`, `endTimeUnixNano`, integer attribute values) are
JSON strings per protobuf's own JSON mapping for 64-bit integers.

[otlp-proto]: https://github.com/open-telemetry/opentelemetry-proto/blob/main/examples/trace.json

## The no-network guarantee

Nothing in the trace/export path ever opens a socket. Concretely:

- `.tess/bin/tessctl` never imports `socket`, `http.client`,
  `urllib.request`, `requests`, `httpx`, or `aiohttp` — anywhere in the file,
  not just in the trace region (`tests/test_trace_otel.py`'s
  `test_engine_source_never_imports_networking_libraries` scans the whole
  source and fails loud if that ever changes).
- `_trace_append_event` / `_trace_discover_jsonl_files` /
  `_trace_events_to_otlp_json` / `_cmd_trace_export` are pure local
  filesystem reads/writes and in-memory JSON reshaping — no subprocess, no
  DNS lookup, no HTTP client.
- `tests/test_trace_otel.py`'s `no_network` fixture monkeypatches
  `socket.socket`, `socket.create_connection`, and `socket.getaddrinfo` to
  raise, then calls `_cmd_gate_ci` / `_cmd_gate_pre_commit` / `cmd_validate`
  / `_cmd_trace_export` **directly** (not via subprocess, so the patch is
  guaranteed to be in the same interpreter these functions run in) and
  asserts they still complete normally — proving the entire call graph,
  including the new trace write and the OTLP export, never reaches for a
  socket.

Getting the data into Datadog/Honeycomb/New Relic/an OTel Collector is a
**separate, explicit, operator-run step**: pipe `tessctl trace export`'s
stdout (or the `--out` file) to whatever local OTLP/JSON ingestion path that
tool provides. Tess OS itself never phones home.

## What's deferred

- **Metrics / span events / links** — only spans are emitted today; no OTel
  metrics stream, no span events (e.g. per-reason events), no span links
  across a mission's briefs → verdict → returns chain. The JSONL already
  carries enough (`mission_id`, `run_id`) to build that later without a
  schema break.
- **`tessctl run`** — exists, but is not yet instrumented (see above).
- **Streaming / live tail** — the trace is append-only JSONL; there is no
  `tessctl trace tail` or watch mode. `tail -f missions/<id>/trace.jsonl |
  jq .` works today without any new tooling.
- **OTLP/protobuf (binary) export** — only `--format otlp-json` is
  implemented; the CLI's `choices=["otlp-json"]` is deliberately narrow so a
  future protobuf exporter is an additive `--format` value, not a breaking
  change.
