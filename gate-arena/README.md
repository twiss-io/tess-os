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

Twelve scripted attack classes against a fixture repo running the REAL
`.tess/bin/tessctl` engine (copied verbatim from this checkout), real `git`,
real `gpg`, and a policy **forked verbatim from this repo's own shipped
`core/policy/policy.yaml`** (not a synthetic toy — the self-gating rule that
protects `core/policy/**` and `.github/workflows/**` — and, as of the
honesty-capstone-audit-2026-07-08 §3-c/§3-d fix, `.tess/bin/**`, `tessctl`,
and `.tess/gate/signoffs/**` — is the actual rule this repo ships, with real
generated keys registered so it's testable at all).

Run it: `python3 gate-arena/bypass/run_bypass_corpus.py` (no API calls, no
cost — pure deterministic software testing, requires `git` + `gpg` on
PATH).

**Result: 12/12 attacks BLOCKED.** The original 10-attack corpus (A1–A10)
ran 8/10 at first pass, with two real, disclosed gaps — both since closed:

| # | Finding | Status |
|---|---|---|
| A3 | A policy-tamper that DELETES policy.yaml's own self-gating rule, committed in the SAME push as the unreviewed payload. Fixed: `tessctl gate` now classifies against the UNION of what the newly-pushed policy requires and what the pre-push BASELINE policy already required (`_gate_load_policy_at_base` + `_gate_union_baseline_matches`) — a requirement true at the baseline cannot be silently switched off by the same push that needed it. | **CLOSED** |
| A10c | The signature check did not inspect GPG key expiry/revocation status — only cryptographic validity and exact fingerprint match. Fixed: `_gpg_signing_key_validity_reason` scans gpg's own EXPKEYSIG/REVKEYSIG status classification at verification time; either is now rejected fail-closed. | **CLOSED** |

The honesty capstone audit (2026-07-08) found two FURTHER, NEW bypass
classes not covered by the original corpus — the same self-protection class
as A3/A8 (the thing governing a push isn't protected from that push),
applied to two surfaces MEDIUM-1/A3 never reached:

| # | Attack | Status |
|---|---|---|
| A11 | **Same-push ENGINE tamper** (§3-c). `.github/workflows/tess-gate.yml` ran `python3 .tess/bin/tessctl gate ci` FROM THE PUSHED CHECKOUT, and `.tess/bin/**` was in NO policy glob — an attacker editing `_gate_run_ship_check` itself to self-attest clean, in the same push as an unreviewed payload, kept the required check green against a tampered engine (A8's disclosure covered the workflow FILE; this is the ENGINE that file invokes). Fixed: `.tess/bin/**` + the root `tessctl` wrapper are now policy-covered, AND the CI workflow (v3) extracts and runs the engine AS IT EXISTED AT THE PUSH'S BASE REF, never the pushed tree's own copy. | **CLOSED** |
| A12 | **Hard-floor sign-off forgery** (§3-d). `.tess/gate/signoffs/<rule-id>.signoff.json` was validated by JSON SHAPE ALONE (five non-empty fields) — no signature, no authentication — and the directory was not policy-covered; any agent able to write a file could forge a hard-floor clearance. Fixed: a sign-off must now carry a signature verifying against a registered key in `policy.signoff_keys`, AND `.tess/gate/signoffs/**` is now policy-covered (a governed artifact, not just an authenticated one). | **CLOSED** |

Full detail, mechanism-by-mechanism: `results/bypass-scorecard.md` /
`.json` (committed — see the honesty capstone audit's R10: a security
number that only lives in a PR description, not a committed artifact,
doesn't count).

### A13 path-ingress expansion (separate, no-key score)

The complete raw-diff path-ingress regression is intentionally measured
separately from the historical GPG-backed A1-A12 corpus:

```bash
python3 gate-arena/bypass/run_path_ingress_corpus.py
```

**Result: 48/48 tests passed; 0 failures, 0 errors, 0 skips.** It covers
deletion, rename-away, mode/type changes, symlinks, gitlinks/submodules,
newline/tab/Unicode/NFC path handling, NFD and non-UTF-8 denial, malformed raw
records (including captured U/X/B states), and full SHA-1/SHA-256 IDs at raw
Git ingress. It exercises the local staged diagnostic, explicit-ref ship-check,
pre-push stdin, installed local hook, locally invoked CI phase, and MCP surface.
It also contains reverse controls proving `100644` additions and same-mode
regular edits still reach normal review, while new governed `100755` files are
unavailable without mode-bound signed evidence. SHA-256 approval is not claimed:
the current blob-verdict schema is SHA-1-only and the governed SHA-256 fixture
must fail closed.

This run performs no key generation, registration, verdict signing, sign-off
signing, or trust bootstrap. Its committed record is
`results/path-ingress-scorecard.md` / `.json`. The score is **not** added to
12/12 and is not a claim that the gate is unbypassable.

Ref deletion is denied at pre-push, but A14's multi-ref/multi-push policy is not
adopted by this corpus and remains Xavier's open topology decision.

Two boundaries this layer cannot test (disclosed, not new — the reckoning
doc already names them): **key custody** (whoever holds a verifier's or
sign-off-authorizer's private key can sign as them) and **repo-admin power**
(branch protection + required status checks are the actual enforcement
anchor on GitHub; a repo admin can remove them — the gate binds agents and
contributors, not owners). A8's and A11's blocks are real but partial for
the same reason: they prove the CONTENT/ENGINE checks refuse to clear a
neutered `.github/workflows/tess-gate.yml` / a tampered `.tess/bin/tessctl`
in the same push; they cannot prove, from inside this arena, that a real
GitHub required-status-check would still refuse to go green if that
neutered artifact is what actually executes. 12/12 is a corpus score, not a
proof of unbypassability — see `RESULTS.md`'s must-not-claims.

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
