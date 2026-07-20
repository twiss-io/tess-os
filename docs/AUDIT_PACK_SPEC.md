# The Auditor Pack

> **Status: v1 spec + reference implementation, shipped in this repository.**
> This wires two primitives this repository already ships — the
> ACCOUNTABILITY LEDGER (`tessctl log`, docs/STATE_LAYER.md) and the Agent
> Receipt (`core/contracts/agent-receipt.schema.json`,
> docs/AGENT_RECEIPT_SPEC.md) — into one exportable, offline-verifiable
> bundle. It is not a new trust mechanism, a certification, or a production
> admission control. See "What this is not" below and `docs/STATUS.md`.

## The pitch, in one paragraph

An insurer, client, or external auditor asking "show me what your agents
did, and who approved it" today has to be handed live access to this
instance's `.tess/state/ledger/` and told how to read it. `tessctl audit
export` instead selects a SCOPE — one task's history, a time range, or every
event — and writes a self-contained pack: a machine-checkable `manifest.json`
plus a human-readable `SUMMARY.md`. `tessctl audit verify` re-checks that
pack's internal integrity using ONLY its own bytes, with no live system
access at all. Handing someone the pack is handing them everything they need
to independently re-check it.

## Honesty is the point

This pack is **tamper-evident**, not **cryptographically non-repudiable**.
Those are different claims, and conflating them is exactly the kind of
overstatement this spec exists to avoid:

- The ledger events it exports carry an **unsigned hash chain**
  (`ledger-event.schema.json`, `docs/STATE_LAYER.md` "Trust boundary"). It
  detects a non-re-chained edit, a removed/reordered event, or (within an
  `export_kind: full` shard) a missing event. It does **not** detect a
  determined adversary who edits an event and consistently recomputes every
  downstream hash to match — that forgery would still verify OK. It carries
  no signer identity.
- Each event's `actor` (harness/model/session/persona) is **self-reported**
  by the writing process at append time, not cryptographically attested. The
  hash chain proves a recorded claim was not altered after the fact; it does
  not prove the claim was true when made.
- An Agent Receipt, where one is embedded, IS GPG-signed when produced — but
  `tessctl audit verify` only re-checks its **shape** and its
  **content-hash self-consistency** (that it was not edited after signing).
  It does **not** perform GPG signature verification; that requires a
  trusted public key the auditor supplies out of band, via the tool built
  for exactly that: `tools/receipt-verify/receipt_verify.py`.
- This repository ships with **empty `verifier_keys`/`signoff_keys`
  registries by design** (`conductor/verdict-signing.md`) — the human-owned
  key ceremony that would let any signature be checked against a registered
  trust anchor has not happened. No receipt in a pack, even one whose
  signature independently verifies, should be treated as tied to an
  operator-registered identity unless that registration is independently
  confirmed.
- A pack proves that what **is** included was not altered after being
  recorded. It does **not** prove that nothing matching the scope was
  **omitted** by whoever ran the export — a party controlling the export
  could leave real events out. Cross-check against `tessctl log verify` on
  the live instance, or request a `--all` export, for full-shard assurance.

Every exported pack states all five of these points in its own
`manifest.json["trust_boundary"]` object and at the top of its
`SUMMARY.md` — a reader does not have to find this document to see the
boundary; it travels with the pack.

## Scope

`tessctl audit export` requires exactly one of:

| Flag | Scope | `export_kind` per shard |
|---|---|---|
| `--task ID` | Every ledger event whose `refs.task == ID` | always `partial` |
| `--since TS` / `--until TS` (either or both) | Every event with `ts` inside the (inclusive) window | always `partial` |
| `--all` | Every event in every shard (optionally narrowed by `--origin`) | `full` |

`--origin ORIGIN` is combinable with any of the three and restricts which
shard(s) (i.e. which writer) are considered at all — it never filters
events *within* a shard, so it does not affect `export_kind`.

`export_kind: full` is a **completeness claim** the shard was exported from
its own genesis with nothing excluded; `tessctl audit verify` actively
checks it (the first included event's `prev_hash` must be genesis, and no
seq gap may exist). `export_kind: partial` makes no completeness claim at
all — a seq gap between two included events is expected (an out-of-scope
event sits there) and is reported informational, never as tamper.

Agent Receipts are **not** auto-discovered — there is no on-disk receipt
store in this repository today (`docs/AGENT_RECEIPT_SPEC.md` "Producing a
receipt"). Pass `--receipt PATH` (repeatable) to embed an already-signed
receipt file verbatim; it is schema-validated against
`agent-receipt.schema.json` before anything is written — an invalid shape,
or a missing file, refuses the WHOLE export (no partial pack is ever
written).

## Object shape

```jsonc
{
  "pack_schema": "tess-os.audit-pack/1",
  "pack_id": "<uuid4 hex>",
  "exported_at": "<UTC ISO-8601>",
  "exported_by": { "user": "<OS user>", "tess_os_commit": "<git HEAD, or null>" },

  "scope": { "kind": "task | range | all", "task": "...", "since": "...", "until": "...", "origin": "..." },

  "trust_boundary": {
    "ledger_integrity": "...", "actor_identity": "...",
    "completeness": "...", "receipts": "...", "key_ceremony": "..."
  },

  "shards": [
    {
      "origin": "<harness/writer origin>",
      "shard": "<YYYY-MM>.<origin>.jsonl",
      "export_kind": "full | partial",
      "event_count": 2,
      "events": [ /* verbatim ledger-event.schema.json instances, sorted by seq */ ]
    }
  ],

  "receipts": [ /* verbatim agent-receipt.schema.json instances, if any were supplied */ ],

  "artifacts": {
    "tasks": ["T-..."], "missions": ["M-..."],
    "receipt_actions": [ { "receipt_id": "...", "repo": "...", "ref": "...", "paths": ["..."] } ],
    "task_record_evidence": ["..."],
    "task_record_evidence_note": "..."
  },

  "counts": { "events": 2, "receipts": 0, "shards": 1 }
}
```

`events[]` and `receipts[]` are embedded **byte-for-byte identical** to
their live on-disk form — nothing is summarized, renamed, or restructured —
so `tessctl audit verify` can recompute every hash directly from the pack.

`artifacts` is deliberately built only from already-STRUCTURED fields
(ledger `refs.task`/`refs.mission`, a receipt's own
`proposed_action.repo`/`ref`/`paths`, and — best-effort, for a `--task`
scope only — the live task record's current `evidence` list), never from
free-text pattern-matching over `summary` strings, which would be fragile
and could mislead.

## Per-action attribution

Every exported ledger event already carries, verbatim: `ts` (when),
`actor.harness`/`model`/`session`/`persona` (who — self-reported, see
"Honesty is the point"), `event` (what class of action), `refs.task`/
`refs.mission` (what it was about), and `summary` (a human-readable
description). `SUMMARY.md` renders these as one chronological table.

Ledger events and Agent Receipts are **two separate, unlinked**
accountability trails in this codebase today — no field on a ledger event
points at a receipt, and no field on a receipt points at a ledger event
(`chain.journal_ref` on a receipt points at a *trace* log, not the ledger).
`SUMMARY.md` lists receipts in their own section and explicitly does not
attempt automatic cross-referencing; a human auditor correlates a receipt
with the events above it via a matching repo/ref/task id where present in
both.

## Verification algorithm (`tessctl audit verify <pack>`)

Runs entirely against the pack's own bytes — no `.tess/state/ledger/`,
`.tess/state/tasks/`, or any other live-instance file is read.

1. Load `manifest.json` (from a directory or a direct file path); confirm
   `pack_schema == "tess-os.audit-pack/1"`.
2. For each shard group, walk `events` in the order given, recomputing each
   event's `hash` via the SAME `_ledger_event_hash` function `tessctl log
   verify` uses — a mismatch is reported as content tamper.
3. For two seq-ADJACENT included events in the same shard, confirm the
   later one's `prev_hash` equals the earlier one's `hash` — a mismatch is a
   broken chain link.
4. For a `export_kind: full` shard: the first event's `prev_hash` must be
   genesis, and no seq gap may exist between any two included events —
   either failing is reported as a missing event. For a `partial` shard, a
   seq gap is expected and reported informational only.
5. For each embedded receipt: schema-validate its shape against
   `agent-receipt.schema.json`, then recompute `receipt_signature
   .signed_content_sha256` and (if present) `decision.signature
   .signed_content_sha256` against the same compact/key-sorted/minus-one-
   key canonicalization `verdict_canonical_bytes`/`signoff_canonical_bytes`
   already use — a mismatch means the receipt (or its embedded decision)
   was edited after signing.

Every failure is fail-closed: exit code 1, with an itemized reason per
problem. `--json` emits `{"ok": bool, "events_checked": N,
"receipts_checked": N, "problems": [...]}`.

**Not performed by this command** (delegated to `tools/receipt-verify/`
instead, so this logic is not duplicated): actual GPG signature
verification of an embedded receipt, and multi-receipt chain-link
verification (`receipt_verify.py verify` / `verify-chain`).

## Reference material

| Artifact | Path |
|---|---|
| Engine implementation | `.tess/bin/tessctl` (AUDIT PACK region) |
| Tests | `tests/test_audit_pack.py` |
| Ledger this builds on | `docs/STATE_LAYER.md`, `core/contracts/ledger-event.schema.json` |
| Agent Receipt this embeds | `docs/AGENT_RECEIPT_SPEC.md`, `core/contracts/agent-receipt.schema.json` |
| GPG signature verification (delegated, not duplicated) | `tools/receipt-verify/` |
| Claim-label table | `docs/STATUS.md` |

## What this is not

- **Not a new trust anchor.** A pack is only as trustworthy as the ledger
  and receipts it draws from — see "Honesty is the point" above.
- **Not a gate.** `tessctl gate` decides whether a change may proceed. An
  audit pack is a portable RECORD of what already happened, consumed by a
  human or an external auditor — it is not wired into `tessctl gate`.
- **Not new signing infrastructure.** No new key type, no new GPG call, no
  change to verdict/sign-off signing or their trust boundary. This adds a
  new, independent read/export/re-check path only.
- **Not a claim of completeness.** See "Honesty is the point" — a pack
  proves what's in it was not altered, not that nothing was left out.
- **Not a production admission control.** See `docs/STATUS.md`'s claim-label
  table before deciding whether this fits a particular workflow.
