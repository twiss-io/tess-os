# Tess OS — Architecture Overview

This is a map of the system, not a duplicate of it. Every section below
names the real files and points at the root [README](../README.md) section
that goes deeper — read this first to know where to look, then follow the
links for the actual detail and the current honest-status caveats (which
live in the README's "Status" section and are not repeated here, since a
second copy of a status claim is a second place for it to go stale).

## The shape of the system

Tess OS is two things layered together, not one:

1. **A doctrine + roster + config scaffold** an AI coding agent (today,
   Claude Code) reads to behave as a governed multi-agent organization
   rather than a single undifferentiated assistant.
2. **A deterministic enforcement layer** (the ship-gate) that does not
   depend on the agent reading or obeying anything — it blocks unverified
   output at the git pre-commit/pre-push/CI boundary regardless of which
   agent or tool produced the diff.

The README's intro states plainly why this split matters: Tess OS's own
benchmark of whether *reading* the doctrine makes a model produce better
output came back negative (see README "Honest results"). The gate does not
depend on that working — it enforces after the fact, on artifacts, not on
trusting the agent's process.

```
┌─────────────────────────────────────────────────────────────┐
│  Doctrine layer (conductor/, agents/)                        │
│  — read by the agent; governs HOW work is supposed to happen │
└───────────────────────────┬───────────────────────────────────┘
                             │ rendered by
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  tessctl engine (.tess/bin/tessctl)                          │
│  — upgrade engine, render targets, contracts validator,       │
│    vault, gate, mission records, trace export                 │
└───────────────────────────┬───────────────────────────────────┘
                             │ enforced by
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  Ship-gate (git hooks + CI, core/policy/policy.yaml)          │
│  — deterministic; blocks regardless of which agent produced   │
│    the diff; does not trust the agent's own summary            │
└─────────────────────────────────────────────────────────────┘
```

## Layer 1 — Doctrine (`conductor/`, `agents/`)

The prose layer: identity, guardrails, the six-field dispatch-brief
contract, verification routing, the typed retry protocol, and the command
system. `agents/` holds the roster of specialist persona specs (144
entries, 141 fully specified + 3 stubs) across guilds, with six outcome
orchestrators as a routing layer between the conductor and the guilds.

This is what an operator's own `CLAUDE.md`/`AGENTS.md` reads — it is prose
a model consumes, not code that runs. See README's "The roster +
orchestrators" and "How a mission runs" sections for the dependency-gated
flow (`intake → research → crew → build → review → verification →
synthesis`) and `tessctl recruit`/`roster apply` for growing the active
roster without loading all 144 personas into context at once.

## Layer 2 — The engine (`.tess/bin/tessctl`)

A single self-contained Python 3 file (stdlib + PyYAML; the vault adds
`pyrage`) that does five distinct jobs. Each is real, tested, independently
useful, and separately scoped in the README's "Status" section:

- **In-place upgrade engine** — pristine merge base at `.tess/core/`,
  per-file status in the committed `tess.lock`, snapshot-first 3-way merge,
  a `doctor` hard-gate, conflict-halts-the-update, security-tier
  quarantine, hash-based drift detection. `tess update --ref vX.Y.Z` is
  what an existing instance runs to pull a new framework version without
  being clobbered by a re-scaffold. See README "`tess update`".
- **Render targets** — compiles the doctrine into a harness-native artifact:
  `CLAUDE.md`/`.claude/settings.json` for Claude Code, `AGENTS.md` for the
  Codex/Cursor/Gemini-CLI/Zed/Devin-class of harnesses that read that
  standard. Determinism and idempotency (same core in → same bytes out,
  every time) are what let `doctor`/`verify` detect drift.
- **Contracts-as-code (`tessctl validate`)** — JSON Schemas at
  `core/contracts/*.schema.json` for the brief, crew-plan, verdict,
  return-manifest, policy, mission, and retry shapes doctrine already
  specifies in prose; a dependency-free validator checks an instance
  against its schema and classifies a failure as `degraded_output` per the
  retry protocol. See README "`tessctl validate`".
- **The vault (`tessctl vault`)** — a local-first, age/X25519
  encrypted-at-rest secret store (`vault://` refs, JIT `exec` injection,
  git pre-commit/pre-push guards as a leak backstop). Explicitly scoped in
  the README as "a risk reducer, not a guarantee a secret cannot leak."
- **Mission records + observability** — `tessctl mission`/`retry log|check`
  turn the doctrine's gates and retry protocol into file-backed, checkable
  state under `missions/<id>/`; `tessctl trace export --format otlp-json`
  maps the same trace log to OTel GenAI semantic-convention spans with zero
  network calls. See README "`tessctl mission`" and `docs/OBSERVABILITY.md`.

## Layer 3 — The ship-gate (`tessctl gate`, `core/policy/policy.yaml`)

The enforcement point, and the part of the system that does not require
trusting an agent's behavior. `core/policy/policy.yaml` (validated against
`core/contracts/policy.schema.json`) defines `require_verdict` rules keyed
on path globs; a push touching a matched path is blocked at pre-push/CI
without a **committed, content-bound (SHA-pinned), cryptographically
signed** `disposition: APPROVE` verdict from a verifier named in that
rule's `allowed_verifiers`. Four hard-floor categories (credentials, money
movement, destructive production data, client-external claims) are never
satisfiable by a verdict alone — they additionally require a separately
signed human sign-off artifact. See `docs/GATE_QUICKSTART.md` for the
copy-paste walkthrough and README's "`tessctl gate`" section for the full
disclosure of what Fable's adversarial review found and closed across
Phase 2 and 2b.

**Self-protection:** the policy file gates edits to itself, to the verifier
key registry, to the gate's own CI workflow, and to the engine file that
runs it (`.tess/bin/**`) — closing the "who guards the gate" loop a naive
implementation would leave open. See `core/policy/policy.yaml`'s own header
comments for the specific adversarial findings (HIGH-1, MEDIUM-1, and the
2026-07-08 honesty-capstone audit) each rule closes.

## Where the release-engineering docs fit

None of the three layers above are what version numbers or release process
govern directly — they're the same three layers at every version. What
changes release to release is covered separately:

- [`VERSIONING.md`](VERSIONING.md) — what a version number means here and
  which file is canonical.
- [`../conductor/release-process.md`](../conductor/release-process.md) —
  how a release is actually cut, signed, and published.
- [`../CHANGELOG.md`](../CHANGELOG.md) — what changed, release by release.

## What this document is not

It is not a substitute for the README's "Status" section, which is the
canonical, actively-maintained statement of what's real vs. in progress vs.
not built — that section changes more often than this one should, so this
document describes the *shape* of the system (which layers exist, how they
compose) rather than restating current build status. When in doubt, the
README's "Status" section wins.
