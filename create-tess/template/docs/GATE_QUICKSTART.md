# Gate operation and custody

> **Technology-preview boundary:** the current Tess OS gate is fail-closed,
> but it is not yet a production branch-protection control. The external
> first-key design and GitHub required-check enforcement are still unresolved.

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
artifacts. Current `main` still has unresolved tree-consistency and type-swap
hardening identified by the adversarial corpus, so it must not be treated as
that completed design.

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

Do not use these commands to decide that a production branch is protected.
They report local or CI evidence only; GitHub required-check enforcement is a
separate prerequisite.

## Expected fail-closed result

Fresh policy registries intentionally contain no verifier or sign-off key. A
governed change can therefore block with a result such as:

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
runbook may describe the approved ceremony after the external trust-root design
and required GitHub enforcement are in place.

## Current status

- `verifier_keys` and `signoff_keys` are intentionally empty in the shipped
  policy.
- The committed gate-arena scorecard on `main` is 12/12; A14, the multi-push
  policy-reduction case, remains open.
- The key bootstrap and GitHub admission-control gaps mean Tess OS must not
  yet protect production merges.

For the broader support matrix and product boundaries, read
[Support and status](STATUS.md).
