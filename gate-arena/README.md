# The Gate Arena

An honest, adversarial test of the ONE claim `proving-ground/` never tested:
not "does the doctrine make agents produce better output" (tested twice,
disproven — see `proving-ground/reports/2026-07-07.md` and
`2026-07-07-fair.md`), but **"can unverified/bad output ship anyway?"** —
the ship-gate's actual claim.

This directory is built per the design in
`kb/wiki/synthesis/... tess-os-honest-reckoning-2026-07-07.md` §3 (G4), read
in full before anything here was written. Its own words, restated: *"Layer
A proves the lock works, not that the lock is on the right door."* Two
layers, two different epistemics — conflating them would be a fresh version
of the mistake the proving-ground benchmark just punished.

## Layer A — the bypass corpus (deterministic, `bypass/`)

Ten scripted attack classes against a fixture repo running the REAL
`.tess/bin/tessctl` engine (copied verbatim from this checkout), real `git`,
real `gpg`, and a policy **forked verbatim from this repo's own shipped
`core/policy/policy.yaml`** (not a synthetic toy — the self-gating rule that
protects `core/policy/**` and `.github/workflows/**` is the actual rule this
repo ships, with real generated keys registered so it's testable at all).

Run it: `python3 gate-arena/bypass/run_bypass_corpus.py` (no API calls, no
cost — pure deterministic software testing, requires `git` + `gpg` on
PATH).

**Result: 8/10 attacks BLOCKED, 2 slipped through — both disclosed as real
findings, not smoothed over:**

| # | Finding |
|---|---|
| A3 | A policy-tamper that DELETES policy.yaml's own self-gating rule, committed in the SAME push as the unreviewed payload, is **not caught**. `_gate_load_policy` reads `core/policy/policy.yaml` straight off the checked-out working tree with no base-ref pin and no diff against the previous policy — if the attacker is willing to also weaken the rule protecting the file they're editing, in the same commit, nothing left standing flags it. |
| A10c | The signature check does not inspect GPG key expiry/revocation status at all — only cryptographic validity (`VALIDSIG`) and exact fingerprint match. A verdict signed with an already-expired key still verifies. Mitigation today is manual: remove a compromised/expired verifier's entry from `policy.verifier_keys`. |

Full detail, mechanism-by-mechanism: `results/bypass-scorecard.md` /
`.json`.

Two boundaries this layer cannot test (disclosed, not new — the reckoning
doc already names them): **key custody** (whoever holds a verifier's
private key can sign as them) and **repo-admin power** (branch protection +
required status checks are the actual enforcement anchor on GitHub; a repo
admin can remove them — the gate binds agents and contributors, not
owners). A8's block is real but partial for the same reason: it proves the
CONTENT check refuses to clear a neutered `.github/workflows/tess-gate.yml`
in the same push; it cannot prove, from inside this arena, that a real
GitHub required-status-check would still refuse to go green if that
neutered workflow is what actually executes.

## Layer B — the enforcement metric (probabilistic, `enforcement/`)

A seeded corpus of diffs (some correct, some subtly wrong — a planted bug,
a security hole, a spec violation), each run through a VERIFIER (a fresh,
task-scoped `claude -p` call — NOT the tess-os doctrine payload; the
proving-ground benchmark is exactly why this matters) that must return a
schema-valid verdict, which then goes through the same real gate mechanics
as Layer A.

**Read `PRE_REGISTERED_CAVEAT.md` first** — it was committed before any
Layer B run, and its terms are binding: no goalpost-moving after seeing the
numbers.

Results: `results/enforcement-metrics.md` / `.json`.

## The honest synthesis

`RESULTS.md` at the top of this directory states the numbers from both
layers plainly, including cost, and does not launder "the gate enforces a
review" into "the gate makes output good" — those are different claims and
this arena is built specifically not to blur them.
