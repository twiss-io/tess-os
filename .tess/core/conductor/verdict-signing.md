# Review evidence and external custody

> **Technology-preview boundary:** Tess OS is a fail-closed review gate, not
> a self-service production-access system. Its external first-trust-anchor
> design and GitHub required-check enforcement are unresolved.

## What this guide covers

A protected change needs independent, already-authorized review evidence that
is committed, content-bound, and valid for the active policy. The gate rejects
missing, malformed, unregistered, stale, or changed evidence. That fail-closed
result is intentional.

This guide deliberately does not describe how to create a verifier identity,
add authority to policy, or produce approval evidence. Those actions would
alter the trust boundary and are not operator onboarding.

There is no self-service bootstrap path in this guide.

## Safe inspection

An authorized operator may inspect an already-existing artifact without
creating new authority:

```bash
tessctl verdict verify path/to/existing.verdict.yaml
```

Verification reports whether the artifact is valid against the currently
available trust material. It does not make a candidate branch approved or a
production branch protected.

## Expected fail-closed state

The shipped policy deliberately has empty verifier and sign-off registries. A
protected candidate can therefore report:

```text
no covering APPROVE verdict found
```

That is a correct result. It means there is no already-authorized, covering
review artifact for the candidate content. A candidate repository must never
create or register the trust anchor that clears its own change.

## When a protected change blocks

1. Stop before treating the change as approved or production-ready.
2. Record the exact gate output, changed paths, immutable base/head references,
   and CI run URL.
3. Escalate to Xavier, the human custodian, for the external custody decision.
4. If the problem is a code or evidence defect rather than custody, correct it
   in a normal pull request and re-run inspection.

A future custody runbook may describe an approved ceremony only after the
external trust-root design and required GitHub enforcement are in place.

## What this does not claim

Local hooks, a rendered workflow, or a successful local verification do not
establish production branch protection. This guide does not claim that the
unresolved first-key bootstrap or adversarial hardening gaps are fixed.

Security-governed policy, key-registry, and workflow surfaces remain outside
this operator guide. Changing those paths requires a separately reviewed
NO-MERGE proposal and Xavier custody; it is not a bootstrap action for a
candidate repository.
