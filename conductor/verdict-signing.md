# Signed review evidence and custody boundary

Tess OS can verify a review artifact only when it is bound to the reviewed
content and signed by an already-authorized verifier. A valid review artifact
is not a claim that a model is correct; it is evidence that an authorized
review identity approved the exact governed artifact under the active policy.

## What the verifier check rejects

The gate fails closed for an unsigned, malformed, stale, wrong-key,
unregistered, tampered, or non-covering review artifact. A review artifact must
be committed, match the relevant repository content, identify a verifier
allowed by the rule, and validate against that verifier's already-trusted public
key.

## Current custody boundary

The shipped verifier and sign-off registries are intentionally empty. A block
such as **"no covering APPROVE verdict found"** is therefore expected for a
governed change until an authorized external trust anchor exists.

This repository must not bootstrap that authority from the candidate content it
is evaluating. Do not generate a verifier or sign-off identity, add a public
key to policy, or sign a review artifact in order to clear the gate. Those are
Xavier-only key-custody actions and are outside normal contributor or operator
setup.

The required trust design must establish the first authority outside the
candidate repository, define recovery/revocation and rotation, and then bind
all later changes to currently trusted authority. It also requires GitHub to
make the actual gate and CI checks required before a branch can be called
protected.

## Safe inspection

An operator may inspect existing state without creating authority:

```bash
tessctl gate ci
tessctl verdict verify path/to/existing.verdict.yaml
```

These commands are diagnostics. They do not establish a production admission
control or replace branch-protection configuration.

For the operator path, read [Gate operation and custody](../docs/GATE_QUICKSTART.md).
For current limits, read [Support and status](../docs/STATUS.md).
