# Telemetry — activation/retention instrumentation, the privacy contract

> Engine: `telemetry/` (Python package). Wired into: `orchestrator.pipeline.
> run_pipeline()`, one call, right after a governed mission's
> `generate_app()` succeeds. CLI: `python -m telemetry.cli`. See
> `telemetry/README.md` for the module architecture.

This is a **local-first, OPT-IN** measurement of one thing: whether a
real human ever gets a real governed mission — a human approval,
independently re-verified, -> a finalized spec -> a generated app — all
the way through the pipeline (**activation**), and whether they come
back and do it again (**retention**). It exists because that is the
precondition for any wider claim about whether Tess is worth depending
on, and because a governance product cannot make that claim credibly
while shipping silent telemetry of its own.

## Is it on by default?

**No.** Telemetry is OFF for every fresh clone, every fresh install, and
every machine that has never explicitly run:

```bash
python -m telemetry.cli enable
```

Until that command (or the equivalent `telemetry.consent.enable()` call)
runs, `orchestrator.pipeline.run_pipeline()` completing a governed
mission records **nothing** — no file is created, no timestamp is read,
no count is incremented. There is no environment variable, config
default, first-run prompt-that-defaults-to-yes, or "opt out instead of
opt in" mechanism anywhere in this repo. The ONE way telemetry ever
starts recording is a human explicitly running `enable`.

## What is captured

Exactly two event types, each containing exactly these seven fields —
see `telemetry/schema/telemetry-event.schema.json` for the machine-
enforced contract (`additionalProperties: false` — a code change that
tries to add an eighth field fails validation immediately, before it
fails a human review):

| Field | Example | What it is |
|---|---|---|
| `schema` | `"tess.telemetry.v1"` | Contract version tag. |
| `event_id` | `"a1b2c3..."` | A random id for the event record itself — not a person, not a plan, not a spec. |
| `event_type` | `"activation"` or `"retention"` | Which of the two things this is. |
| `timestamp` | `"2026-07-18T09:12:00.123Z"` | UTC, when this mission completed. |
| `install_id` | `"fcfcc7c3..."` | A random id generated ONCE by `enable()`, identifying this opted-in install — not you. |
| `mission_ordinal` | `1`, `2`, `3`, ... | This is the Nth governed mission this install has completed. A count. Nothing else. |
| `days_since_last_mission` | `null` (first mission) or `2.4103` | The gap since the previous one, in days. `null` for the very first (`activation`) event. |

That is the **entire** field set. Nothing else is ever included.

## What is NEVER captured

- **No spec text, plan text, or app content** — not a title, not a
  description, not a field name, not a generated file's contents.
- **No entity or user names** — not `approved_by`, not an app's data
  model, not a company or project name.
- **No file paths, URLs, or environment details.**
- **No identity beyond the anonymous `install_id`** — no OS username, no
  hostname, no MAC address, no IP address, no email. `install_id` is
  produced by `uuid.uuid4()` — a random number, not derived from
  anything about your machine or account.
- **No cross-request/cross-mission content correlation** — an event
  cannot be joined back to the plan/spec that produced it; `mission_id`,
  `plan_id`, and `spec_id` are never written here, on purpose (a
  content-derived slug — e.g. a spec title-derived id — could itself
  leak a fragment of what a mission was about; this contract avoids
  that question entirely rather than trying to sanitize it).

This is enforced technically, not just documented: every event is
validated against `telemetry/schema/telemetry-event.schema.json`
BEFORE it is written, and `additionalProperties: false` means an event
carrying any field outside the table above is rejected
(`telemetry.consent.TelemetryError`), never silently written. See
`tests/telemetry/test_events_privacy.py` for the adversarial proof.

## Where it's stored

`~/.tess-os/telemetry/` — a plain directory on your own machine, home-dir
scoped the same way `spec_engine.gate_identity`'s approval-identity key
already is:

- `~/.tess-os/telemetry/consent.json` — whether telemetry is enabled,
  the `install_id`, and when consent was first given. Nothing else.
- `~/.tess-os/telemetry/events.jsonl` — one JSON object per line, one
  line per completed governed mission, append-only.

Both are plain-text JSON — `cat`, `jq`, or any text editor reads them
directly; no proprietary format, no encryption, no compression.

## How to inspect it

```bash
python -m telemetry.cli status     # is it on? what's the install_id? where's the log?
python -m telemetry.cli summary    # local activation/retention view
cat ~/.tess-os/telemetry/events.jsonl | jq .   # read every raw event yourself
```

## How to disable it

```bash
python -m telemetry.cli disable
```

Stops all future recording immediately. Existing local events are kept
on disk (so a later re-enable doesn't silently fabricate a fresh
`install_id`, which would otherwise make your own local retention math
across the gap look wrong to you) — see "How to delete it" below to
erase them too.

## How to delete it

```bash
python -m telemetry.cli delete
```

Permanently removes the entire `~/.tess-os/telemetry/` directory —
`consent.json` AND `events.jsonl`, `install_id` included. A future
`enable()` after this generates a brand-new `install_id`, exactly as if
telemetry had never been used on this machine before. You can also just
`rm -rf ~/.tess-os/telemetry/` yourself — this CLI command does exactly
that, nothing more.

## No phone-home (v1)

Nothing in `telemetry/` ever opens a socket. It does not import
`socket`, `http.client`, `urllib.request`, `requests`, `httpx`, or any
other networking library — every function in this package reads and
writes ONLY the local JSON/JSONL files described above. There is no
background process, no daemon, no scheduled upload, and no "phone home
on first run" behavior. Getting this data anywhere else — a dashboard,
an aggregation service, anything — would require a **separate, explicit,
human-invoked export action that does not exist in this version.** If a
future version adds one, it will be its own opt-in, documented here
alongside this exact sentence being updated to describe it truthfully —
not a silent addition to what `enable()` already covers.

## Where this fires in the product lifecycle

`orchestrator.pipeline.run_pipeline()` — freeform input -> intent-router
classify/route -> spec-engine intake/plan -> a REAL, authenticated human
approval gate -> spec-engine finalize -> `spec_engine.codegen.
generate_app()` — calls `telemetry.events.record_mission_completion()`
exactly once, immediately after `generate_app()` succeeds (see
`orchestrator/pipeline.py`'s own docstring, "Hop 6", and
`orchestrator/README.md`'s "Telemetry" section). A rejected approval or
an unresolved ambiguous route never reaches this point, so neither ever
emits an event — only a genuinely completed governed mission does.

## Relationship to `tessctl trace` (`docs/OBSERVABILITY.md`)

Different system, different layer, different purpose — not to be
confused:

|  | `tessctl trace` | `telemetry/` (this doc) |
|---|---|---|
| What it observes | The ship-gate engine's own `gate`/`validate` decisions | The product's governed-mission pipeline completing |
| Default state | Always on (an engineering observability log) | **OFF — opt-in only** |
| Contains | Contract types, violation reasons, exit codes | Event type, timestamp, coarse counts only |
| Lives under | `.tess/**` / `missions/**` | `~/.tess-os/telemetry/` |
| Network | Never (proved by `tests/test_trace_otel.py`) | Never in v1 (proved by `tests/telemetry/test_no_network.py`) |

Both share the same underlying discipline (local-first JSONL, schema-
validated before write, no network call) because that discipline is
this repo's own, not because the two systems are related. Telemetry
never reads, writes, or depends on anything under `.tess/**`.
