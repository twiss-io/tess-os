# GitHub merge topology for authoritative admission

> **NO-MERGE bootstrap proposal:** this control changes the ship-gate trust
> model. It must remain a draft until the protected parent stack is rebuilt,
> independently reviewed, and the repository owner applies the matching
> GitHub ruleset. A candidate branch cannot make its own check authoritative.

Tess OS production admission uses one deliberately narrow topology: an exact
two-parent merge commit whose tree is identical to the reviewed branch head.
This gives the gate three distinct immutable objects:

```text
event BASE -----------\
  \                     evaluation merge (tree equals attestation HEAD)
   payload ... attestation HEAD /
```

The merge wrapper is required for every authoritative change, including an
ordinary documentation pull request. A hard-floor sign-off is required only
when policy classifies the payload into a hard-floor category.

## Pull-request check contract

For `pull_request`:

- BASE is exactly `pull_request.base.sha` and the base branch is `main`;
- attestation HEAD is exactly `pull_request.head.sha`;
- evaluation HEAD is exactly `GITHUB_SHA`;
- `GITHUB_REF` is exactly `refs/pull/<event-number>/merge`;
- evaluation parents are exactly `[BASE, attestation HEAD]`, in that order;
- `tree(evaluation HEAD) == tree(attestation HEAD)`; and
- BASE is the exact merge-base/ancestor of attestation HEAD.

The policy delta and all ordinary verdict/blob checks evaluate BASE to the
evaluation merge. If a hard-floor rule matches, sign-off topology is evaluated
on the attestation HEAD, whose parent is the signed `payload_head_sha`. The
merge wrapper never substitutes for the signoff-only attestation commit.

## Main-push check contract

For `push`:

- both the event ref and `GITHUB_REF` are exactly `refs/heads/main`;
- BASE is exactly event `before` and is not all-zero;
- evaluation HEAD is exactly event `after` and `GITHUB_SHA`;
- evaluation HEAD has exactly two ordered parents;
- parent 1 is exactly event `before`;
- parent 2 is the attestation HEAD; and
- the evaluation and attestation trees are byte-identical.

A hard-floor sign-off must bind `base_sha` to event `before`. A later push,
changed payload, changed sign-off, conflict-resolution tree, or different
first parent invalidates the evidence.

## Workflow supply-chain contract

The authoritative workflow pins checkout and Python setup actions to exact
reviewed commit SHAs and disables checkout credential persistence. It selects
CPython 3.13.7 exactly. Its only Python runtime package is PyYAML 6.0.3 from a
binary wheel whose SHA-256 is recorded in
.tess/ci/ship-gate-requirements.txt. Installation requires hashes, refuses
dependencies and source distributions, and does not upgrade pip.

The workflow extracts that requirements file from immutable event BASE into a
temporary path before installation. It never installs a requirements file
from the candidate checkout. The policy security tier covers .tess/ci/** so a
future dependency-pin change also needs ordinary review evidence before it can
become trusted BASE state.

## First-adoption bootstrap

A repository whose BASE predates either the trusted engine or the pinned
ship-gate requirements receives TRUST_BOOTSTRAP_REQUIRED. The workflow must
not fall back to candidate engine or dependency bytes.

The first adoption therefore needs an externally reviewed, owner-controlled
bootstrap commit and matching repository ruleset. That out-of-band adoption
must be disclosed as bootstrap; it cannot be described as having passed the
gate it is introducing. Once the stack exists in BASE, every later
authoritative run uses only that established engine and requirements file.

## Required GitHub repository settings

The owner must apply all of these together. The workflow cannot safely or
honestly claim that it applied them itself.

1. Allow **merge commits only**. Disable squash merge and rebase merge.
2. Require branches to be up to date before merging (strict mode).
3. Do not require linear history; it conflicts with the required merge commit.
4. Disable merge queue/`merge_group` until Tess OS ships and tests an explicit
   queue topology. The current engine returns `MERGE_GROUP_UNSUPPORTED`.
5. Disable auto-merge. Admission must observe the final current merge preview,
   not an asynchronously replaced preview.
6. Require the `tessctl gate ci` job from
   `.github/workflows/tess-gate.yml`. Prefer a ruleset-required workflow,
   which binds the workflow source. If a named status check is used, bind it
   to the expected GitHub Actions source application rather than accepting an
   arbitrary check with the same name.
7. Require the other release/CI checks defined by the release runbook.
8. Do not grant routine bypass. Repository administrators and automation must
   be subject to the ruleset; emergency bypass must be exceptional,
   user-present, time-bounded, and auditable.
9. Keep force pushes and branch deletion disabled on `main`.

After configuration, test the reverse direction in a disposable branch:
squash, rebase, fast-forward, stale-base, reordered-parent, octopus,
tree-mismatch, tag-ref, manual-dispatch, and merge-queue attempts must not
produce authoritative admission.

## Why other merge methods are rejected

- A squash commit discards the reviewed attestation commit identity.
- A rebase rewrites the signed revision and parent relationship.
- A fast-forward has no merge wrapper proving the event BASE/HEAD pair.
- An octopus or reordered merge makes the protected first-parent transition
  ambiguous.
- A merge result with a different tree introduces bytes outside the attested
  head, commonly through conflict resolution.
- A caller-selected ref, tag, workflow, or event payload is not the protected
  GitHub merge-preview context.

Local `tessctl gate ci`, pre-push, and MCP gate checks remain diagnostics. They
cannot manufacture GitHub's protected event provenance or satisfy this
external admission contract.
