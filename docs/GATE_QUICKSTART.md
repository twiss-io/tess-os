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

The ship-gate derives changed paths from Git's byte-safe, NUL-delimited raw
diff, retaining status, modes, and full object IDs through policy
classification. Raw ingress accepts full SHA-1 and SHA-256 object IDs, but the
current blob-verdict approval schema remains SHA-1-only: `artifact_hashes`
requires a 40-hex blob ID. A governed SHA-256 blob therefore cannot receive a
covering approval and fails closed. The gate disables rename detection so a
rename-away is represented as deletion plus addition, and fails closed on
malformed, unmerged/unknown, non-UTF-8, or non-NFC path records.

Review artifacts bind regular blobs, not pathname transitions. A governed
non-executable regular addition (`100644`) or same-mode regular content edit can
continue to normal verdict/sign-off checks. A new governed executable
(`100755`) is unavailable because current signed evidence does not bind Git
status/mode. A governed deletion, rename-away, executable-bit transition, type
change, symlink, or gitlink/submodule state is categorically blocked before
authorization artifacts are consulted:

```text
GOVERNED_TRANSITION_UNSUPPORTED
```

This prevents a blob-only verdict from being reused as authority for absence,
mode, symlink-target, or submodule-commit semantics.

The proposed production design binds every trust input to an immutable BASE,
attestation HEAD, and exact two-parent evaluation merge. The topology and its
required repository settings are documented in
[GitHub merge topology](GITHUB_MERGE_TOPOLOGY.md). It remains a protected
NO-MERGE proposal until the parent security stack and GitHub ruleset are
independently completed.

Verifier verdicts and human hard-floor sign-offs require distinct primary key
material. The gate rejects normalized fingerprint reuse, identical immutable
BASE public-key bytes, and aliases within either registry. Even in solo-owner
mode, use two separately held primary keys; owner approval by itself is not
independent review and must never be presented as one.

The intended delivery path is:

```text
change -> policy match -> independent review evidence -> required CI -> protected branch
```

All five links matter. A local hook is useful feedback, but it is not a
substitute for required CI and branch protection.

The local pre-commit diagnostic classifies staged transitions with policy read
from immutable `HEAD`, not the staged/working candidate, and universally denies
new symlink/gitlink additions. Regular additions and same-mode modifications
remain advisory there; pre-push/CI performs the actual verdict check. Pre-push
stdin explicitly rejects ref deletions because path/blob evidence does not bind
ref topology. Multi-ref and multi-push policy semantics are unchanged: A14
remains an open Xavier-owned adoption decision.

## Hard-floor sign-off v2: exact revision binding

Credentials, money movement, destructive production-data operations, and
client-external factual claims need a distinct operator sign-off in addition
to any ordinary verifier verdict. The gate accepts only sign-off schema v2.
Legacy v1 or unversioned JSON is replayable and is rejected.

A sign-off file cannot contain the commit id of the same commit whose tree
contains that file: Git computes the commit id from the tree, which would make
the value self-referential. Tess OS resolves this with a two-commit invariant:

```text
event BASE
  -> one or more reviewed payload commits
  -> payload HEAD
  -> exactly one signoff-only attestation commit (attestation HEAD)
```

The attestation HEAD must have exactly one parent, and that parent must equal the
signed `payload_head_sha`. Its complete diff must be exactly the canonical
`.tess/gate/signoffs/<rule-id>.signoff.json` path set required by the payload;
no code, policy, key, verdict, rename, deletion, symlink, type swap, or extra
file may share the commit. If two hard-floor rules match, both sign-offs must
be introduced or updated atomically in that same child. The authoritative CI
evaluation commit is a separate exact two-parent merge wrapper whose second
parent and tree are that attestation HEAD. A different tree, later candidate
commit, multi-head push, or editing a sign-off in another child invalidates
the attestation.

The shipped ordinary security rule also covers `.tess/gate/signoffs/**`.
Requiring a separate payload-committed verdict for the final v2 sign-off blob
would create another impossible cycle: the verdict must hash the future
sign-off, while the sign-off must contain the commit id that includes the
verdict. The engine therefore removes only the exact BASE-derived required
sign-off paths from ordinary verdict coverage, and only after the complete
child passes topology, schema, binding, time, immutable-key, and signature
checks. This is atomic: one invalid sign-off yields no exemption. Candidate
rules, keys, globs, directory prefixes, extra signoff-looking files, and
caller input cannot add exempt paths. Governed payload files and every other
security-tier path still require their ordinary covering verdicts.

Before GPG verification, each signed artifact must exactly match:

- `schema_version: 2`;
- `repository_id` from immutable BASE policy;
- the effective rule id, category, and canonical rule SHA-256;
- the exact immutable `base_sha` and reviewed `payload_head_sha`; and
- the complete matched path set and each regular file's Git blob id.

`authorized_at` and `expires_at` use strict UTC RFC3339 timestamps. The signing
command supplies a one-hour expiry when it is omitted; the gate permits no
more than 24 hours, allows at most five minutes of future clock skew, and
rejects expired attestations. Signature keys and their exact public bytes
still come only from immutable BASE policy/tree state. Verifier keys are
restricted to `.tess/keys/verifiers/`; human sign-off keys are restricted to
the separate `.tess/keys/signoffs/` namespace. Candidate path redirection,
key replacement, or rollback cannot substitute candidate bytes for BASE
authority or erase a BASE revocation.

This topology is intentionally strict and currently technical. A future Trust
Center may make the user-present ceremony easier, or use a separately secured
external-attestation channel, but it must preserve these bindings. Git notes
and candidate-controlled storage are not trusted by the current design.

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
- The historical GPG-backed gate-arena scorecard is 12/12. The separate
  no-key A13 path-ingress scorecard is 48/48; neither score proves
  unbypassability and they are not combined. A14, the multi-push
  policy-reduction case, remains open.
- The key bootstrap and GitHub admission-control gaps mean Tess OS must not
  yet protect production merges.

For the broader support matrix and product boundaries, read
[Support and status](STATUS.md).
