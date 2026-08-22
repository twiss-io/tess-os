# Gate operation and custody

> **Technology-preview boundary:** the current Tess OS gate is fail-closed,
> and the live `twiss-io/tess-os` `main` ruleset now requires the App-bound
> `tessctl gate ci` check with strict up-to-date enforcement and no configured
> bypass (verified 2026-08-22). External policy-epoch/reset custody remains
> unresolved; a repository owner could also change that external ruleset.

This page explains how to read the gate safely. It intentionally does **not**
explain how to generate a verifier key, add a key to policy, or sign an
approval. Those actions are a human-owned Xavier key-custody ceremony, not an
operator setup step.

## What the gate checks

For a policy-governed path, `tessctl gate ci` checks required review evidence
against the candidate change and active policy. A valid artifact must be
committed, content-bound, signed by an already-authorized verifier, and still
valid for the policy rule.

The intended production design binds every trust input to immutable base/head
artifacts. This NO-MERGE proposal adds type/delete/rename-safe ingress and a
monotonic normal-PR policy floor. It does not implement the external
policy-epoch reset authority or the final attestation-only approval carrier.

The intended delivery path is:

```text
change -> policy match -> independent review evidence -> required CI -> protected branch
```

All five links matter. A local hook is useful feedback, but it is not a
substitute for required CI and branch protection.

## Safe diagnostics

In an isolated, non-production clone, these commands inspect the existing
state without creating trust material. For `gate ci`, use two existing
immutable refs; replace the placeholders only with the refs you are reviewing.

```bash
./tessctl doctor
./tessctl verify
./tessctl gate ci --base <BASE_REF> --head <HEAD_REF>
```

If an existing verdict file needs inspection, an authorized operator may verify
it without signing a new one:

```bash
./tessctl verdict verify path/to/existing.verdict.yaml
```

Do not use these commands alone to decide that a production branch is
protected. They report local or CI evidence only. For `twiss-io/tess-os`, the
required App-bound live ruleset is a separately verified external control; a
different repository must establish and verify its own ruleset.

## Expected fail-closed result

The current source policy registers Cyra's public verifier key and keeps the
sign-off registry empty. Fresh `create-tess` scaffolds reset both registries to
empty, and neither source nor scaffold ships a private key. A governed change
without an already-valid covering artifact can therefore block with a result
such as:

```text
no covering APPROVE verdict found
```

That result is correct. It means the gate has not found already-authorized,
covering evidence for the change.

Do not:

- generate a key;
- register a public key in policy;
- write or sign a verdict or sign-off;
- use a bypass to present the protected change as approved; or
- weaken policy to make the block disappear.

The candidate repository must never create the trust anchor that clears its own
change.

## What to do when blocked

1. Stop before treating the change as approved or ready for production.
2. Record the exact gate output, changed paths, base/head references, and CI
   run URL.
3. Ask the designated human custodian, Xavier, whether this is an authorized
   custody or policy decision.
4. If the issue is a code or evidence defect rather than custody, fix that
   defect in a normal pull request and re-run the diagnostics.

There is no self-service bootstrap path documented here. A future custody
runbook may describe the approved ceremony after the external policy-epoch and
trust-root design is in place.

## Current status

- Current source policy contains Cyra's public verifier registration;
  `signoff_keys` is empty. Fresh scaffolds reset both registries to empty.
- Any candidate change to `verifier_keys` or `signoff_keys`—addition,
  deletion, identity rename, fingerprint rotation, or public-key path
  change—returns `POLICY_EPOCH_RESET_REQUIRED`. No private key is shipped.
- The gate-arena scorecard on this NO-MERGE proposal is 15/15 scripted
  attempts blocked. A14's normal-PR attenuation path and A15's two-push
  trust-registry bootstrap are denied, but the
  external policy-epoch custody/reset path remains open.
- The live `twiss-io/tess-os` ruleset requires the App-bound ship gate, strict
  freshness, and has no configured bypass. Hostile owner-level ruleset changes
  remain outside what an in-repo corpus can prevent or prove.
- External policy-epoch/reset custody remains the production closure gap for
  legitimate security-floor attenuation.

For the broader support matrix and product boundaries, read
[Support and status](STATUS.md).
