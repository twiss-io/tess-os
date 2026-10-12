# A14 policy-attenuation decision

**Status:** proposal only; no policy, engine, workflow, key, CODEOWNERS, or
release behavior is adopted by this document.

**Scope:** request a Xavier-owned decision about A14, a fixture-modeled
policy-attenuation threat across two separately evaluated local commit ranges.
This record is written against current `main`
[`61a916e`](https://github.com/twiss-io/tess-os/tree/61a916e9a07ed1341e936dec45895461faaac33d)
and deliberately does not claim that the unmerged A13/A15 work is live.

## Decision requested

Decide whether a policy change that removes or narrows coverage is a distinct
high-risk change class, and, if so, select the human approval and branch
enforcement requirements before any implementation is proposed. The current
repository states that A14 remains open and that its 12/12 arena score is not
a production-readiness certificate. [S1]

## Evidence: the fixture model and the current immediate-base mechanism

PR #59's A14 artifact is a local corpus fixture, not a record of two GitHub
PRs. It creates a throwaway repository, then evaluates two committed ranges:

1. **Local range `b0..p1`.** The fixture removes its `prod-src` rule from its
   forked policy, signs the policy-edit verdict with the fixture's `Reid`
   identity, commits the result as `p1`, and calls `gate ci` over `b0..p1`.
   [F1]
2. **Local range `p1..p2`.** The same fixture writes an unreviewed production
   change, commits it as `p2`, and calls `gate ci` over `p1..p2`. It also runs
   a one-range `b0..combined` control. [F1]

The fixture creates real but disposable GPG identities per run, registers
their public halves only in its forked policy, and tears their temporary GPG
homes down after each fixture. Its `Reid` name is therefore a test identity,
not evidence of a live GitHub reviewer, Xavier-held key, Xavier custody, or
human approval. [F2]

Current `main`'s pull-request workflow passes the PR event's exact
`base.sha` and `head.sha` to `tessctl gate ci`. [M1] The current engine loads
the baseline policy from `base_shas` and unions it with the candidate policy
only for that ship-check evaluation. [M2] The residual A14 statement is thus
an inference from the fixture and that immediate-base behavior: if a future,
properly authorized policy attenuation becomes the PR base, the next range is
evaluated against that attenuated base rather than an older policy floor. This
document does not claim that sequence has occurred in GitHub. [F1] [M1] [M2]

## What A14 is not

- It is **not** a same-push policy self-tamper claim. The current corpus's A3
  record concerns a policy change and payload in the same commit/range; the
  A14 fixture separates them into `b0..p1` and `p1..p2`. [S3] [F1]
- It is **not** a verifier-key or verdict forgery claim. The A14 fixture's
  signature is made with its generated, registered-for-test `Reid` key. [F1]
  [F2]
- It is **not** an A13 type-swap or evaluate-then-swap claim. PR #59 records
  A13 and A14 as separate attack classes with different proposed responses.
  [S2] [F1]
- It is **not** evidence of two live GitHub PRs, Xavier custody, or human
  approval. The reproduction is explicitly a disposable local fixture. [F1]
  [F2]
- It is **not** proof that current `main` admits an A14 sequence today. This
  document makes no such claim; shipped policy registries are intentionally
  empty and current project documentation says GitHub required gate/CI
  enforcement is not configured. [S1] [S5]
- It is **not** an adopted mitigation. The PR #59 A14 artifact labels its
  listed design choices as unimplemented and for the security owner to decide.
  [S6]

## Current limitations and deployment posture

Current `main` discloses a 12/12 committed arena score while A14 remains open.
[S1] Current documentation also says that production admission control still
needs a human-owned trust anchor and required GitHub gate/CI checks. [S1] The
shipped `verifier_keys` registry is empty by design, so a verifier verdict
cannot satisfy a rule until a separately governed custody ceremony registers a
real public key. [S5]

PR #59 is closed with `mergedAt: null`; its proposed A13/A15 hardening and its
14/15 A14-expanded arena record are therefore unmerged artifacts, not controls
this memo credits to `main`. [S2] [S6] No deployment claim is made from that
PR state.

## Non-adopted options and trade-offs

The following are alternatives recorded for decision, not commitments:

| Option | Potential effect | Trade-off / unresolved design work |
|---|---|---|
| Explicit attenuation classification | Add a `narrows_coverage` declaration, or infer narrowing from a policy diff, then require a stricter review bar such as both designated reviewers. [S6] | A voluntary field can be omitted; inference needs a complete, reviewable definition of “narrowing,” including deletes, glob edits, rule reordering, and hard-floor changes. |
| Longer-lived trusted floor | Compare a candidate policy with a configurable durable floor (for example, a release tag), rather than only the immediately prior push. [S6] | Resists slow erosion but introduces trusted-floor lifecycle, rollback, bootstrap, and exception semantics. |
| Independent repository process | Require a GitHub/CODEOWNERS review gate for `rules[]` or `hard_floor_rules[]` attenuation, independent of cryptographic verdicts. [S6] | Depends on repository-administrator enforcement and does not by itself define the semantic boundary of attenuation. |
| Keep disclosure-only status | Leave A14 openly documented while no new mechanism is adopted. [S1] | Preserves present behavior but leaves the documented policy-history risk unresolved. |

## Recommendation for Xavier

Approve the *governance intent* first, not an engine patch: treat policy
attenuation as a named high-risk change class. Prefer deterministic diff-based
classification over a self-declared marker, because the condition being
controlled is the semantic removal or narrowing of protection. Require two
independent human approvals for an attenuation PR and make that review
repository-enforced before considering a longer-lived trusted-floor mechanism.

This recommendation does **not** authorize implementation, change key custody,
or weaken fail-closed behavior. It deliberately separates the decision that a
policy may be attenuated from the later decision to adopt any particular
engine or GitHub configuration.

## Explicit decision gates

1. **Custody and branch-enforcement gate:** Xavier confirms the external
   trust-anchor design and required GitHub gate/CI enforcement prerequisites
   documented for production admission control. [S1]
2. **Semantic gate:** Xavier approves a written definition of attenuation that
   covers at least rule deletion, glob narrowing, removal of a hard-floor
   category, and disabling of a verdict requirement. The definition must state
   how intentional replacement, rename, emergency rollback, and expansion are
   distinguished.
3. **Authority gate:** Xavier selects the required approvers, their
   independence requirement, and the escalation path. No candidate policy may
   establish its own first authority; current documentation expressly rejects
   that bootstrap pattern. [S1] [S5]
4. **Mechanism-selection gate:** Xavier chooses one initial enforcement design
   (diff classification, durable floor, or repository process) and its
   compatibility with the first three gates. This is a design decision, not an
   authorization to merge a policy change.
5. **Adversarial-verification gate:** A future implementation must add a
   reproducible A14 corpus case that proves the unauthorized fixture-modeled
   two-range sequence is denied, and must also prove the authorized exception
   path has the chosen independent approvals. It must report the aggregate
   corpus score honestly, including any remaining failure.
6. **Independent-review and release gate:** A security reviewer verifies the
   implementation and its reverse-direction test from primary artifacts; only
   then may Xavier make a separate merge/release decision.

## Primary-artifact claim/source appendix

| ID | Claim supported | Primary source |
|---|---|---|
| S1 | Current `main` says A14 remains open, reports 12/12, and lists missing trust-anchor and required-check prerequisites. | [`README.md` at `61a916e`, lines 45–61](https://github.com/twiss-io/tess-os/blob/61a916e9a07ed1341e936dec45895461faaac33d/README.md#L45-L61) |
| S2 | PR #59 title, head, closed state, and `mergedAt: null`; its submitted scope includes A13/A14/A15. | [GitHub pull-request API record for #59](https://api.github.com/repos/twiss-io/tess-os/pulls/59) and [PR #59](https://github.com/twiss-io/tess-os/pull/59) |
| S3 | Current main's 12-case scorecard records A3 as the same-range policy self-tamper control. | [`bypass-scorecard.md` at `61a916e`, lines 1–11](https://github.com/twiss-io/tess-os/blob/61a916e9a07ed1341e936dec45895461faaac33d/gate-arena/results/bypass-scorecard.md#L1-L11) |
| F1 | The A14 harness creates `b0..p1`, `p1..p2`, and a same-range control; it signs only inside the fixture and tears the fixtures down. | [`attacks.py` at PR #59 head `5b70a5d`, lines 1044–1133](https://github.com/twiss-io/tess-os/blob/5b70a5d355475289607fdfea41e4ff973e2c5c5d/gate-arena/bypass/attacks.py#L1044-L1133) |
| F2 | Fixture identities are generated per run in isolated temporary GPG homes, registered in a forked policy, and removed on teardown. | [`lib.py` at PR #59 head `5b70a5d`, lines 120–188 and 327–342](https://github.com/twiss-io/tess-os/blob/5b70a5d355475289607fdfea41e4ff973e2c5c5d/gate-arena/bypass/lib.py#L120-L188), [`lib.py`, lines 433–485](https://github.com/twiss-io/tess-os/blob/5b70a5d355475289607fdfea41e4ff973e2c5c5d/gate-arena/bypass/lib.py#L433-L485) |
| M1 | Current main's PR workflow resolves `github.event.pull_request.base.sha` and `.head.sha`, then passes them to `tessctl gate ci`. | [`tess-gate.yml` at `61a916e`, lines 87–128](https://github.com/twiss-io/tess-os/blob/61a916e9a07ed1341e936dec45895461faaac33d/.github/workflows/tess-gate.yml#L87-L128) |
| M2 | Current main's ship-check loads a policy from supplied `base_shas` and unions it with candidate classification for that evaluation. | [`tessctl` at `61a916e`, lines 9630–9662](https://github.com/twiss-io/tess-os/blob/61a916e9a07ed1341e936dec45895461faaac33d/.tess/bin/tessctl#L9630-L9662) and [`tessctl`, lines 10173–10202](https://github.com/twiss-io/tess-os/blob/61a916e9a07ed1341e936dec45895461faaac33d/.tess/bin/tessctl#L10173-L10202) |
| S5 | Current main's security rule covers policy/gate artifacts and the shipped verifier registry is intentionally empty. | [`core/policy/policy.yaml` at `61a916e`, lines 100–136 and 153–192](https://github.com/twiss-io/tess-os/blob/61a916e9a07ed1341e936dec45895461faaac33d/core/policy/policy.yaml#L100-L192) |
| S6 | PR #59's submitted A14 description lists the higher-review-bar, durable-floor, and CODEOWNERS/process alternatives as unimplemented. | [`gate-arena/RESULTS.md` at PR #59 head `5b70a5d`, lines 31–52](https://github.com/twiss-io/tess-os/blob/5b70a5d355475289607fdfea41e4ff973e2c5c5d/gate-arena/RESULTS.md#L31-L52) |

No Actions run is cited as evidence that A14 is mitigated. No mitigation is
claimed adopted by this proposal.
