# A14 policy epochs and revision-bound approval

**Status: NO-MERGE security proposal.** The normal-PR attenuation detector in
this branch is executable. The external policy-epoch reset and revision-bound
approval carrier described below are interfaces only: no reset verifier, key,
verdict, GitHub rule, or custody path is created here.

## Attack

A14 splits one payload across separately evaluated ranges:

1. push/PR 1 removes, narrows, disables, or otherwise weakens an established
   security rule and obtains an otherwise valid review;
2. after that policy becomes the new base, push/PR 2 changes the path that is
   no longer governed;
3. an immediate-base-only union sees no violation in push 2 because the old
   rule has already disappeared from history's current tip.

This is not signature forgery. Every per-change signature can be valid while
the policy history is being attenuated.

## Adopted normal-PR rule

Security coverage is monotonic in the ordinary PR path. Existing
`require_verdict` rules and hard floors may be retained or strengthened, but
an ordinary candidate range may not:

- delete a governed rule or hard floor;
- turn off `require_verdict`;
- remove or rewrite an established glob;
- remove a security classification;
- add an allowed verifier to an established rule;
- change a hard-floor category; or
- add, remove, rename, or rotate an entry in `verifier_keys` or
  `signoff_keys`, including its fingerprint or public-key path; or
- delete the policy, policy schema, gate engine/wrapper/workflow, or trusted
  lock that defines or executes the enforcement boundary.

The engine compares the candidate policy committed at the exact immutable
HEAD with the policy committed at BASE. A detected reduction returns
`POLICY_EPOCH_RESET_REQUIRED` regardless of any candidate verdict. Exact glob
retention is intentional: the gate does not guess that two different patterns
are semantically equivalent.

An authoritative range must also contain a readable, schema-valid policy at
its immutable BASE. Missing or malformed BASE policy fails closed rather than
silently disabling the comparison. Git's explicit empty-tree object is the
only policy-less bootstrap subject; a real commit with no valid policy is not
treated as a fresh project and cannot create its own weaker baseline.

Additive rules, additional globs, additional classifications, and a narrower
allowed-verifier set remain normal PR changes (and remain subject to the
existing gate rules that protect policy files). Trust registries are not
ordinary additive policy: exact BASE-to-candidate equality is required because
even an apparently additive key becomes approval authority for the next push.

## Policy-epoch reset interface (not implemented)

A legitimate reduction requires a new policy epoch anchored outside the
ordinary candidate payload. A future reset attestation must bind all of:

- stable repository identity;
- previous policy epoch and new policy epoch;
- immutable merge-base/base commit;
- payload commit and payload tree;
- exact BASE policy blob and trusted BASE gate-engine blob;
- a unique review attempt identifier;
- an explicit machine-readable list of every removed or weakened protection;
- expiry and anti-replay data;
- an independently governed reset-authority signature.

The reset authority must not be a verifier key introduced by the same PR, and
the ordinary candidate branch must not be able to establish or rotate it. No
fallback to a normal covering verdict is permitted. Until that separate
custody path exists, attenuation is intentionally unsatisfiable.

## Revision-bound approval carrier

An in-tree signed artifact cannot literally contain the final commit/tree hash
that contains the artifact itself; doing so requires a cryptographic
fixed-point. The safe carrier is therefore an **attestation-only final HEAD**:

1. `payload_head` is the exact reviewed commit;
2. the signed approval binds repository, merge base, `payload_head`, payload
   tree, BASE policy blob, BASE gate blob, and attempt id;
3. the current attestation HEAD has exactly one parent (`payload_head`);
4. its delta is strictly allowlisted to regular, committed verdict artifacts;
5. any later commit, type change, symlink, delete, extra path, base mismatch,
   or policy/gate mismatch invalidates the approval.

That carrier is the approved implementation direction, but it is not activated
by this branch. Activating it requires schema migration, GitHub event/App
provenance, and independent custody review. Existing `artifact_hashes` remain
the live per-file binding until then.

## Honest closure status

The normal two-PR attenuation route is denied at push 1 by the executable
monotonic rule. A13b regular-to-symlink type changes are also included in gate
diff discovery by this branch. **A14 remains OPEN as a complete production
claim** until the external policy-epoch verifier/custody path and the
attestation-only approval carrier are implemented and independently verified.
No arena total should describe those unimplemented paths as closed.
