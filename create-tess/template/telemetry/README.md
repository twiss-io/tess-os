# telemetry — local-first, opt-in activation/retention instrumentation

> Follow-up to `orchestrator/` (the wired spine: intent-router ->
> spec-engine -> approval gate -> codegen). This package answers one
> question honestly: does a real human ever get a real governed mission
> (a human approval -> a finalized spec -> a generated app) all the way
> through the pipeline, and do they come back and do it again? That is
> the precondition for any wider claim about whether Tess is
> indispensable — measuring it requires instrumentation, and a
> governance product cannot ship that instrumentation as silent
> telemetry without contradicting its own premise.
>
> **Status: Buildable-Now.** OFF by default. OPT-IN via
> `python -m telemetry.cli enable`. Local-first — writes to a single
> JSONL file on this machine, nothing else, ever, in v1. See
> `docs/TELEMETRY.md` for the full plain-English privacy contract.

## What this is

Two structured, schema-validated events, both fired from exactly one
place in this repo — `orchestrator.pipeline.run_pipeline()`, immediately
after `spec_engine.codegen.generate_app()` succeeds (see that module's
own docstring, "Hop 6"):

- **`activation`** — this install's FIRST completed governed mission
  (`mission_ordinal == 1`). The accountability chain (human approval,
  independently re-verified -> finalized spec -> generated app) firing
  once, end to end, for the first time.
- **`retention`** — every governed mission completed after the first
  (`mission_ordinal >= 2`), carrying `days_since_last_mission` so a
  week-N-return / repeat-use view is computable later from the ordinal +
  gap sequence alone (`telemetry.summary.build_summary()` computes
  exactly this, locally, on demand).

```
orchestrator.pipeline.run_pipeline()
     │
     ▼  (only after status == "generated")
telemetry.events.record_mission_completion()
     │
     ▼  telemetry.consent.is_enabled()?
     │       │
     │      NO  -> return MissionCompletionEvent(recorded=False); NOTHING
     │             else happens -- no read, no write, no timestamp.
     │
     ▼  YES
count prior events in events.jsonl -> mission_ordinal, event_type,
days_since_last_mission -> validate against schema/telemetry-event.
schema.json (additionalProperties: false) -> append one JSON line
```

## Module map

| File | Role |
|---|---|
| `consent.py` | The opt-in gate. `is_enabled()`, `enable()`, `disable()`, `status()` — reads/writes `~/.tess-os/telemetry/consent.json`. |
| `store.py` | Append-only JSONL event log + schema validation before every write. `append_event()`, `read_events()`, `delete_all()`. |
| `events.py` | `record_mission_completion()` — the ONE function `orchestrator.pipeline` calls. Builds the event record, self-gates on consent, computes `mission_ordinal` / `days_since_last_mission`. |
| `summary.py` | `build_summary()` — the local activation/retention reader (what `python -m telemetry.cli summary` prints). |
| `schema_check.py` + `schema/telemetry-event.schema.json` | This component's own minimal, dependency-free validator (mirrors `intent_router.schema_check` / `spec_engine.spec_check` — deliberately duplicated, not imported, so this component has zero import dependency on any sibling top-level component) + the schema whose `additionalProperties: false` is the technical enforcement of "no PII, no content, ever." |
| `cli.py` | `python -m telemetry.cli {status,enable,disable,summary,delete}`. |

## The opt-in mechanism, precisely

Consent lives in one local JSON file: `~/.tess-os/telemetry/consent.json`
(mirrors the exact `~/.tess-os/<thing>` local-state convention
`spec_engine.gate_identity.default_identity_dir()` already established
for the approval-identity key). Its ABSENCE — the state of every fresh
clone, every fresh install, and every machine that has never run
`python -m telemetry.cli enable` — means telemetry is OFF.
`telemetry.consent.is_enabled()` is the ONE gate every event-emitting
call site checks, and it is checked FIRST, before anything else: no
consent file, no counting, no timestamp read, nothing written, nothing
read. There is no environment variable, config default, or first-run
heuristic that flips this on automatically — see `consent.py`'s own
module docstring for the complete statement.

## What is (and is never) in an event

See `schema/telemetry-event.schema.json` for the enforced, exhaustive
field list — `schema`, `event_id`, `event_type`, `timestamp`,
`install_id`, `mission_ordinal`, `days_since_last_mission` — and nothing
else, ever; `additionalProperties: false` means `telemetry.store.
append_event()` raises `TelemetryError` rather than writing a record
carrying an undocumented field (proved adversarially in
`tests/telemetry/test_events_privacy.py`). No spec text, plan content,
entity/user names, file paths, or IP address — `install_id` is a locally
generated `uuid.uuid4()`, never derived from hostname, MAC address, or
OS username. See `docs/TELEMETRY.md` for the full plain-English
statement of this contract.

## Local-first, no phone-home (v1)

Every function in this package reads and writes ONLY the local
filesystem (`~/.tess-os/telemetry/` by default, or
`$TESS_OS_TELEMETRY_DIR` if set). Nothing here imports `socket`,
`http.client`, `urllib.request`, or any HTTP client library, and nothing
here ever makes a network call — see `docs/TELEMETRY.md`'s "No
phone-home" section and `tests/telemetry/test_no_network.py` for the
same style of proof `docs/OBSERVABILITY.md`'s tessctl trace already
carries for itself. Aggregating events ACROSS installs, or exporting
them anywhere, is explicitly out of scope for v1 and would be a
SEPARATE, EXPLICIT opt-in action if ever built — never automatic.

## Running it

```bash
python -m telemetry.cli status      # show consent state + where events live
python -m telemetry.cli enable      # explicit opt-in
python -m telemetry.cli summary     # local activation/retention view
python -m telemetry.cli disable     # explicit opt-out (events kept)
python -m telemetry.cli delete      # erase ALL local telemetry state
```

Programmatically:

```python
from telemetry import consent
from telemetry.events import record_mission_completion

consent.enable()                 # explicit opt-in, once
event = record_mission_completion()
# event.recorded, event.event_type, event.mission_ordinal,
# event.days_since_last_mission
```

## Running the tests

```bash
python -m pytest tests/telemetry     # this component's suite only
python -m pytest tests/orchestrator  # includes the run_pipeline() integration test
python -m pytest                     # full repo suite
```

`tests/telemetry/_telemetry_paths.py` is this component's own sys.path
bootstrap helper, following the exact naming discipline
`tests/orchestrator/_orchestrator_paths.py` / `tests/spec_engine/
_spec_engine_paths.py` / `tests/intent_router/_paths.py` document for
themselves (a unique basename per test directory — pytest's default
"prepend" import mode requires it). Every test in this suite passes an
explicit `telemetry_dir=tmp_path/...` — none of it ever reads or writes
the real `~/.tess-os/telemetry/` on the machine running the tests.

## Integration status — what this module does and does not wire up

**Built, tested, working standalone:** consent (opt-in/opt-out/status),
the schema-validated local event log, `record_mission_completion()`,
the local summary reader, the CLI, and the ONE wired integration point
(`orchestrator.pipeline.run_pipeline()`, Hop 6).

**Deliberately NOT built here** (same disclosed-scope-boundary
discipline `orchestrator/README.md` and `spec-engine/README.md` already
apply to themselves):

- Any network egress, export, or cross-install aggregation — v1 is
  local-only by design; a future export path would be a SEPARATE,
  EXPLICIT opt-in action, never automatic.
- A retention/activation event for anything other than
  `orchestrator.pipeline.run_pipeline()` reaching `"generated"` — a
  rejected or ambiguous-and-unresolved run emits nothing, on purpose
  (see `events.py`'s own docstring for exactly why).
- Cross-process file locking for `mission_ordinal` — a disclosed,
  accepted v1 scope boundary (see `events.py`'s "Known limitation"
  section).
- Any change to `.tess/**`, `core/policy/**`, `.github/workflows/**`, or
  `.tess/bin/tessctl` — this is a product-layer concern, entirely
  separate from the ship-gate engine's own `tessctl trace`
  instrumentation (`docs/OBSERVABILITY.md`).
