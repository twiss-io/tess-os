# The Gate Arena

## Addendum (2026-07-15) — corpus expanded to 15, reconciled to 14/15

**Superseded by the fixes below; the pre-2026-07-15 12/12 write-up is
preserved unmodified further down this file, per this repo's own
"no goalpost-moving after seeing the numbers" discipline.** Three NEW
attack classes (A13, A14, A15) were added, targeting families the original
12-attack corpus never exercised: TOCTOU/evaluate-then-swap, multi-push
split-payload, and dependency/supply-chain injection. Full detail,
mechanism-by-mechanism, is in each attack's own returned `mechanism` string
(see `bypass/attacks.py`) and `results/bypass-scorecard.md`/`.json`
(committed, regenerated every run).

| # | Attack | Result | Status |
|---|---|---|---|
| A13 | **Evaluate-then-swap (TOCTOU).** Three sub-probes: (a) content-swap after a green check (CONTROL — the engine is stateless and correctly re-validates); (b) a governed prod file converted blob→symlink was a git TYPE change (T) EXCLUDED by the diff-filter, making the swap invisible to the classifier; (c) `_gate_load_policy`, contract-shape validation, and hard-floor sign-off validation all read the ON-DISK working tree instead of the committed `--head` ref — disk state at check time has no enforced correspondence to the ref actually being evaluated (an ordinary `pull_request` checkout, by `actions/checkout`'s own documented default, checks out a synthetic MERGE commit, not `pull_request.head.sha`). (c) defeated even A11's "trusted, base-ref-extracted engine" CI fix — pinning the engine binary does not pin the data it reads. **Both (b) and (c) were REAL, FOUND bypasses.** Fixed: diff-filter is now `ACMRT`; policy/contract/sign-off validation now resolve content via the committed head ref's own git tree (the same `git ls-tree`/`git cat-file` primitive covering-verdict discovery already used), never disk. | 5/5 sub-probes BLOCKED | **CLOSED** |
| A14 | **Multi-commit split-payload across separately-merged pushes.** Splits a weaken-policy-then-exploit tamper (which A3 correctly blocks in ONE push) into two independently-gated merges: push 1 gets a real, validly-signed Reid verdict for a policy "cleanup" that narrows/removes a rule; push 2 ships an unreviewed prod change against the now-legitimately-weakened baseline. Push 2 is **NOT blocked** — A3's baseline-union is scoped to the immediately-preceding push only, so it does not (and is not designed to) compose across a sequence of separately-reviewed pushes. **This is NOT a forgery/technical bypass** — every cryptographic/signature/artifact-hash check held; push 1 required and got a real, key-custodied signature from an approving reviewer. It is a disclosed, real limitation of any human-verdict system: once a narrowing is legitimately reviewed and approved, it becomes the trusted baseline going forward, and the gate has no mechanism (nor claims one) for flagging a sequence of individually-approved changes that cumulatively erode coverage. | SLIPPED THROUGH (push 2) | **OPEN — disclosed, design fix proposed, not implemented** |
| A15 | **Dependency/supply-chain injection.** The gate's classification model is purely path-glob-based with no built-in notion that a dependency manifest/lockfile is prod_touching. FOUND: as shipped before this PR, neither the arena's fixture nor this repo's own real, live `core/policy/policy.yaml` had any rule for `uv.lock`/`pyproject.toml`/`package.json`/`requirements*.txt` etc. — a real, live gap, not just a fixture artifact — even though this repo's own governed CI workflows install and execute exactly what those files declare. Fixed (enumerated): a new `dependency-manifests` rule now covers every manifest/lockfile format this repo actually uses. Disclosed, NOT fixed: an unlisted format or non-lockfile supply-chain vector (proven via a Dockerfile base-image-tag probe) remains invisible — an enumeration fix, not a general capability. | BLOCKED (enumerated format); residual gap confirmed open by design | **PARTIALLY CLOSED — enumerated instance fixed, general limitation disclosed** |

**Result: 14/15 scripted attacks BLOCKED.** One real, disclosed, non-forgery
finding remains open (A14) — reported honestly, not papered over, with a
proposed (not yet implemented) design fix in `RESULTS.md`'s addendum below
and A14's own `mechanism` string in `results/bypass-scorecard.md`.

---

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
