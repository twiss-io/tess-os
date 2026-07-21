# Trust bootstrap security design

## Current boundary

Tess OS is a signed, fail-closed review gate. A verifier key is a trust
anchor, not ordinary project configuration.

For every pull request, the gate accepts only verifier and hard-floor signoff
registrations that were already present in the base revision, and imports each
registered public-key bytes from that same immutable Git tree. A candidate
cannot add, replace, delete, symlink, or roll back a key file and use it to
authenticate a verdict or hard-floor clearance for that same revision. If the
base registry is empty, no ordinary APPROVE verdict can clear a protected
change. This is intentional fail-closed behavior.

Accordingly, `tessctl verdict keygen` is disabled. It exits with
`TRUST_BOOTSTRAP_REQUIRED` before it invokes GPG or writes a key, policy
file, or lockfile. It is not a normal onboarding path.

## Why this is necessary

An automated candidate can otherwise generate a private key, add its public
key to policy, sign its own approval, and claim to have passed review. That is
self-issued trust, not independent verification.

The base revision is the only trust source available to the candidate gate.
Trust changes must therefore be established outside the candidate revision,
under separately controlled custody and repository enforcement.

## Future Trust Center contract

A future Trust Center must surface this as a blocking state, not as a setup
wizard that silently creates authority.

| Field | Contract |
| --- | --- |
| State code | `TRUST_BOOTSTRAP_REQUIRED` |
| User-facing message | “Review protection is waiting for an administrator-held verifier key. No review key has been created.” |
| Primary action | “Contact your repository administrator” |
| Permitted local action | Read-only explanation and verification of an already-established public registration |
| Forbidden action | Generate a verifier private key, register a public key, sign a verdict, edit policy, or re-pin a lockfile |
| Candidate-gate result | Protected changes remain blocked until an independently anchored base revision contains the verifier registration |

The Trust Center must not claim that it has enabled protection until the
repository host enforces the gate as a required status check. A green local
command or an advisory GitHub Actions run is not enforcement.

## Deliberately undecided

The following require a user-present key-custody design and Xavier's decision;
they are not implemented by this change:

- verifier identity proof and private-key storage;
- recovery, rotation, revocation, and multi-administrator quorum;
- the trusted ceremony that introduces a first verifier registration;
- GitHub ruleset configuration and administrator bypass policy.

Until those decisions exist, the safe outcome is an explicit blocked state.
