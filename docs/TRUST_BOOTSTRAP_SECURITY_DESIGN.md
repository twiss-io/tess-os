# Trust bootstrap security design

## Current boundary

Tess OS is a signed, fail-closed review gate. A verifier key is a trust
anchor, not ordinary project configuration.

For every pull request, the gate accepts only verifier and hard-floor signoff
registrations that were already present in the base revision, and imports each
registered public key's bytes from that same immutable Git tree. Verifier
registrations may point only below `.tess/keys/verifiers/`; operator sign-off
registrations may point only below the separate `.tess/keys/signoffs/`
namespace. A candidate
cannot add, replace, delete, symlink, or roll back a key file and use it to
authenticate a verdict or hard-floor clearance for that same revision. If the
base registry is empty, no ordinary APPROVE verdict can clear a protected
change. This is intentional fail-closed behavior.

Both namespaces are governed by the security-tier policy rule. The policy and
schema that enforce that rule are mirrored and security-pinned in
`.tess/tess.lock`; public-key assets themselves are locked to their committed
immutable BASE Git blobs rather than copied into the framework mirror. This
distinction is deliberate: candidate checkout bytes are never trust input.

Verifier-review and human hard-floor authority must use two distinct primary
keys. Normalized fingerprints and immutable public-key bytes are unique within
each registry and disjoint across both registries; aliases and cross-role key
reuse fail closed. This remains true when one person is the only repository
owner. A solo owner may perform both custody roles with two separately held
primary keys, but that owner's own approval is not independent review and Tess
OS must not label it as such.

Accordingly, `tessctl verdict keygen` is disabled. It exits with
`TRUST_BOOTSTRAP_REQUIRED` before it invokes GPG or writes a key, policy
file, or lockfile. It is not a normal onboarding path.

Hard-floor sign-offs add a second independent constraint: schema v2 binds a
short-lived operator signature to immutable BASE repository identity, the
exact reviewed payload parent, the effective hard-floor rule, and every
matched path/blob id. The attestation HEAD is a single-parent, signoff-only
child of the reviewed payload. It is distinct from any CI event/evaluation
merge commit, whose parent and tree topology must be validated separately.
This avoids an impossible self-reference (a file inside a commit cannot also
contain that same commit's hash) while ensuring any extra or subsequent commit
invalidates the sign-off. Signature verification imports only the established
public-key bytes from immutable BASE, including any revocation material.

For the same reason, an ordinary verdict committed in the payload cannot hash
the future sign-off blob without creating a second cycle. Only after all
BASE-derived required v2 sign-offs validate does the gate exempt those exact
regular-file paths from ordinary verdict matching. The exemption is never a
glob or directory rule and is never derived from candidate policy or caller
input. A partial, candidate-added, extra, renamed, symlinked, or invalid
attestation publishes no exemption.

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

The Trust Center must also treat the payload/signoff split as one protected
operation: present the exact repository, BASE, payload commit, rule, paths,
blob hashes, and expiry to the human custodian; then create a signoff-only
child. It must restart the review if the payload changes and must never hide an
extra file in the attestation commit.

The Trust Center must not claim that it has enabled protection until the
repository host enforces the gate as a source-bound required workflow and the
merge settings match [the exact merge-wrapper contract](GITHUB_MERGE_TOPOLOGY.md).
A green local command or an advisory GitHub Actions run is not enforcement.

## Deliberately undecided

The following require a user-present key-custody design and Xavier's decision;
they are not implemented by this change:

- verifier identity proof and private-key storage;
- recovery, rotation, revocation, and multi-administrator quorum;
- the trusted ceremony that introduces a first verifier registration;
- GitHub ruleset configuration and administrator bypass policy.

Until those decisions exist, the safe outcome is an explicit blocked state.
