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

Fifteen scripted attack classes against a fixture repo running the REAL
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

**Result: 13/15 attacks BLOCKED** after the A13 fix in this PR. The expansion
added A13–A15 and each surfaced a real gap; the finding run first recorded them
at **12/15** (preserved in the commit history and `bypass/FINDINGS.md` — the
finding is committed *before* the fix on purpose). A13's blob→symlink type-swap
is closed by the engine fix in this PR's second commit; A14 + A15 remain open,
disclosed findings. Full write-up of the three new classes: `bypass/FINDINGS.md`.

The original 10-attack corpus (A1–A10) ran 8/10 at first pass, with two real,
disclosed gaps — both since closed:

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

The gate-arena expansion (2026-07-15) added three NEW classes probing the
evaluate-then-swap (TOCTOU), split-payload, and dependency/supply-chain
families the original corpus never exercised. Each surfaced a real gap.
Full detail: `bypass/FINDINGS.md`.

| # | Attack | Status |
|---|---|---|
| A13 | **Evaluate-then-swap.** (a) content-swap (blob→blob) is BLOCKED — the engine is stateless and re-validates the merged head's content, so a swapped-in malicious commit is independently re-blocked. (b) **type-swap (blob→symlink)** was a ★BYPASS: `_gate_diff_paths` uses `git diff --diff-filter=ACMR`, which EXCLUDES git type-changes (status `T`), and `_gate_git_ls_tree` drops mode-120000 symlinks (LOW-1) — so converting a governed file to a symlink pointing at ungoverned content shipped green with zero verdict. Fixed in this PR (separate commit): `--diff-filter=ACMR` → `--diff-filter=ACMRT`, so a type-swap is classified and fails closed. | **CLOSED** (fix in this PR) |
| A14 | **Multi-commit split-payload across merges.** A3 blocks weaken-policy-then-exploit in ONE push, but not when split into two independently-merged pushes: an approved "cleanup" PR that removes a rule (push 1, correctly gated — needs a real Reid verdict) permanently lowers the baseline, so a later unreviewed prod change (push 2) ships green with no flag. A3's baseline is only the immediately-preceding merge. NOT key-free (depends on push 1 being approved) — a confused-deputy erosion, not a clean bypass. | **OPEN** (disclosed; fix design in FINDINGS.md) |
| A15 | **Dependency / supply-chain injection.** The gate governs `.github/workflows/**` (MEDIUM-1) but NOT the dependency manifests those governed workflows install-and-execute (`requirements-dev.txt`, `package-lock.json`, …). This repo's real `ci.yml` runs `pip install -r requirements-dev.txt` + `pytest` and `npm ci`; an unreviewed manifest edit (typosquat/malicious pin) ships green and executes in CI with zero verdict. Key-free. | **OPEN** (disclosed; fix = add manifest globs to policy, a coverage decision for Tess+Xavier — FINDINGS.md) |

Full detail, mechanism-by-mechanism: `results/bypass-scorecard.md` /
`.json` (committed — see the honesty capstone audit's R10: a security
number that only lives in a PR description, not a committed artifact,
doesn't count).

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
neutered artifact is what actually executes. 12/15 (13/15 after the A13 fix
commit) is a corpus score, not a proof of unbypassability — it means precisely
these 15 pre-registered attacks were run and these were the outcomes, and A14 +
A15 remain OPEN, disclosed findings. See `RESULTS.md`'s must-not-claims and
`bypass/FINDINGS.md`.

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
