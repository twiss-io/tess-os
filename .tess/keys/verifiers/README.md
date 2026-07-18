# Verifier public keys — Phase 2b (verdict signing)

This directory holds each verifier's bundled **PUBLIC** key, ASCII-armored,
one file per verifier: `<name-lowercase>.asc` (e.g. `reid.asc`, `cyra.asc`).
Mirrors `.tess/keys/twiss-release-key.asc`'s existing bundled-public-key
pattern — same idea, applied per-verifier instead of per-release.

## What goes here vs. what does NOT

- **Goes here:** a custody-controlled verifier's PUBLIC key only, committed
  to the repo by an independently authorized ceremony. Reading this file is how
  `tessctl gate` verifies a verdict's signature — it never trusts an ambient
  system keyring for this check (unlike release-tag verification, which
  intentionally requires an out-of-band `gpg --import` first — see
  `conductor/release-process.md`'s trust model). During a ship-gate run,
  verdict verification imports the exact public-key blob from the immutable
  base Git tree into an isolated, throwaway GNUPGHOME; candidate checkout
  bytes never affect that trust decision.
- **NEVER goes here (or anywhere in this repo):** a verifier's PRIVATE key.
  Private key custody stays with the verifier, exactly like the release
  signing key's private half (`release-process.md`: "must stay on the
  maintainer's machine only").

## Trust-bootstrap boundary

A public key file alone never authorizes a verdict. The ship-gate accepts
only registrations and public-key bytes that already existed in its base
revision. A candidate cannot add, replace, delete, symlink, or roll back a
key here, add it to policy, and use it to approve the same pull request.

This repository currently has no registered verifier keys. That produces the
explicit `TRUST_BOOTSTRAP_REQUIRED` state for protected changes: normal
APPROVE verdicts remain impossible until an independently anchored base
revision contains a registration.

Bootstrap, registration, recovery, rotation, and the first trust anchor are
Xavier-owned, user-present custody decisions. Do not use this directory,
`tessctl verdict keygen`, a manual policy edit, or a lockfile re-pin to
bootstrap authority. The command is disabled and makes no key, policy, or
lock change.

See [the trust-bootstrap security design](../../../docs/TRUST_BOOTSTRAP_SECURITY_DESIGN.md)
for the current boundary and the future Trust Center error-state contract.
