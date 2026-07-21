# Pre-registered caveat — Layer B (enforcement metric)

**Committed BEFORE any Layer B corpus, verifier call, or metric exists.**
Check the git history: this file's commit is a parent of every commit that
adds `enforcement/corpus/`, `enforcement/run_verifier.py`, or
`results/enforcement-metrics.*`. If it isn't, the pre-registration is
void — this document has no force retroactively.

This binds the write-up in `RESULTS.md`. No goalpost-moving after seeing
the numbers: this file's predictions and rules are fixed now, not
adjusted once results are known.

## What Layer B measures

A seeded corpus of diffs (~12), roughly half correct and half subtly wrong
(a planted bug, a security hole, or a spec violation — the kind of "the
obvious first implementation is confidently wrong" case the proving-ground
suite's tasks 11–19 were already built around), each sent to a VERIFIER (a
fresh `claude -p` call, given the diff + task brief + the verdict schema —
**not** the tess-os doctrine payload; the proving-ground benchmark already
showed mounting that payload does not help and can hurt a model, so Layer B
does not repeat that mistake by mounting it into the verifier either). The
verifier returns a schema-valid verdict; an APPROVE gets signed and run
through the same real gate mechanics Layer A exercises.

## The headline metric, defined now

**Bad-ship reduction** = the fraction of BAD diffs the gate+verifier
pipeline BLOCKS, versus a no-gate baseline that ships 100% of bad diffs by
construction. This number **is exactly the verifier's recall on this
corpus** — surfaced as such, not laundered into "the gate blocks bad
output." The gate contributes zero intelligence; it only converts "the
verifier said BLOCK" into "the diff cannot ship." All quality judgment
lives in the verifier call, not the deterministic gate code (that split is
the entire point of Layer A vs. Layer B being separate).

**Good-output friction** = the fraction of GOOD diffs the verifier wrongly
BLOCKs (1 − precision, on this corpus's positive class).

## Binding rules, fixed before any result exists

1. **If verifier recall is low** (this document does not pre-commit to a
   numeric threshold for "low" — but if a majority of seeded bad diffs
   ship), the honest conclusion is: *the gate reliably enforces a review
   that catches X% of this seeded bug corpus — the enforcement mechanism is
   real, the review it enforces is the bottleneck.* X is published exactly
   as measured, unrounded in the raw JSON, even if embarrassing. The gate's
   floor value at recall→0 is **not** zero — it still (a) blocks everything
   on hard-floor paths regardless of any verdict (Layer A, A2), (b) makes
   "nobody reviewed this" a state that cannot occur silently on a
   policy-flagged path, (c) leaves a signed, tamper-evident audit trail
   (Layer A, A4–A7) — but the *quality* value the pipeline delivers scales
   with X, and only X may be claimed, at exactly the size measured.
2. **Selection bias, disclosed in advance:** these are seeded bugs, chosen
   because this arena's author (and the proving-ground tasks they're partly
   drawn from) already knows the exact shape of the wrongness. That is
   plausibly EASIER for a verifier to catch than an organic, unplanted
   subtlety in real production code where nobody wrote the bug on purpose
   to be catchable. The measured recall is treated as an **upper-bound
   estimate** for this bug class, not a general promise about arbitrary
   real-world diffs.
3. **The counterfactual is not "no review at all" in most real shops** —
   it is "a disciplined team that already reviews everything." This arena's
   `bad-ship reduction` number is versus a *zero-review* baseline (0% bad
   diffs blocked, by construction, since nothing gates them). That is the
   gate's own claim's natural counterfactual (unverified output cannot
   ship — the counterfactual to a GATE is no gate, not a hypothetical
   perfect human reviewer). It is not evidence about how much bad output
   ships *at any specific already-disciplined organization* without this
   tool — that claim is not this arena's to make, and `RESULTS.md` will not
   make it.
4. **One verifier tier is the primary result.** If time/budget allow a
   second (cheaper or more expensive) model pass for cross-model
   decorrelation, it is reported as a secondary, clearly-labeled
   comparison — not blended into the headline number.
5. **Cost is reported in full**, including the real `claude -p` spend for
   every verifier call, unrounded, alongside the recall/precision numbers —
   per the task's own instruction that this is real spend, not a free
   simulation.
6. **If the numbers come back such that gate+verifier blocks little bad
   output and costs real money to do it, the write-up says so as the
   headline, not buried in a caveats section** — the same evidence
   discipline that killed the enhancement thesis in
   `proving-ground/reports/2026-07-07*.md` applies here with equal force.
   Nothing here is exempt because it is testing "our" mechanism instead of
   a rival's.

— Ada, Lead Backend Engineer, Tess AI coding team. Committed 2026-07-08,
before any Layer B corpus file, verifier call, or metric existed.
