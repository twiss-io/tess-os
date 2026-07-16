# Trust setup, in plain English

This page explains why a fresh Tess OS install blocks and what a repository
owner must decide before production use. It intentionally contains no commands
for creating keys, registering reviewers, or signing approvals.

> **Current boundary:** Tess OS is a technology preview. The first external
> trust anchor and required Git checks are not yet packaged as safe production
> onboarding.

## Why the gate starts locked

A new Tess OS repository contains no authorized verifier or sign-off keys. This
is deliberate. Shipping a default reviewer key would mean anyone who received
the repository also received the power to approve it.

So a governed change may stop with:

```text
no covering APPROVE verdict found
```

That message means “required independent evidence is absent.” It is not a
broken installation and it is not permission for an agent to create its own
reviewer identity.

## What safe activation eventually requires

```text
repository owner chooses an external custodian
                    |
                    v
custodian protects the private signing material outside the candidate change
                    |
                    v
only pre-authorized public identity is recognized by policy
                    |
                    v
independent CI checks the exact immutable change
                    |
                    v
the Git host requires that check before delivery
```

The person or system proposing a change must not also create the authority that
approves that same change. Keeping the private signing material outside the
repository is necessary, but not sufficient: branch protection and required CI
must also be configured independently.

## What an easy user experience may automate

A future setup assistant may safely:

- explain whether the repository is in exploration or protected mode;
- run read-only diagnostics;
- detect missing required checks and show exact remediation status;
- guide the owner to a platform-backed or hardware-backed custody option;
- display the public identity for the owner to confirm; and
- verify that an existing approval covers the exact immutable change.

It must never silently create authority, store raw private keys in the project,
self-sign an approval, weaken policy, or mark a branch protected when the Git
host does not enforce it. Simplicity should remove confusing steps, not merge
the proposer and reviewer roles.

## What to do today

For local evaluation, use an isolated, non-production clone and the read-only
diagnostics in [Gate operation and custody](GATE_QUICKSTART.md).

For a governed change that stops because no covering approval exists:

1. Leave the block in place.
2. Record the immutable base and head references, changed paths, gate output,
   and CI run URL.
3. Escalate the custody and required-check decision to the designated
   repository owner.
4. Fix ordinary code or evidence defects in a normal pull request, but do not
   turn a custody decision into an engineering workaround.

There is currently no safe self-service production bootstrap. The technical
guide deliberately omits key-generation, key-registration, and signing steps
until the external custody design and Git enforcement are ready.
