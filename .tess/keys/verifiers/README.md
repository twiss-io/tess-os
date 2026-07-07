# Verifier public keys — Phase 2b (verdict signing)

This directory holds each verifier's bundled **PUBLIC** key, ASCII-armored,
one file per verifier: `<name-lowercase>.asc` (e.g. `reid.asc`, `cyra.asc`).
Mirrors `.tess/keys/twiss-release-key.asc`'s existing bundled-public-key
pattern — same idea, applied per-verifier instead of per-release.

Full trust model, onboarding steps, and `tessctl verdict sign`/`verify` usage:
[`conductor/verdict-signing.md`](../../../conductor/verdict-signing.md).

## What goes here vs. what does NOT

- **Goes here:** a verifier's PUBLIC key only (`gpg --export --armor
  <fingerprint>`), committed to the repo. Reading this file is how
  `tessctl gate` verifies a verdict's signature — it never trusts an ambient
  system keyring for this check (unlike release-tag verification, which
  intentionally requires an out-of-band `gpg --import` first — see
  `conductor/release-process.md`'s trust model). Verdict verification
  imports straight from this repo file into an isolated, throwaway GNUPGHOME
  per check, so CI needs no manual bootstrap step.
- **NEVER goes here (or anywhere in this repo):** a verifier's PRIVATE key.
  Private key custody stays with the verifier, exactly like the release
  signing key's private half (`release-process.md`: "must stay on the
  maintainer's machine only").

## Registration

A public key file alone does nothing — it must also be registered in
`core/policy/policy.yaml`'s `policy.verifier_keys.<Name>` map (fingerprint +
path to this file). `core/policy/policy.yaml` ships with `verifier_keys: {}`
(deliberately empty — see that file's own comment block for why: an
unregistered verifier's verdicts can never cover any path, fail-closed, not a
silent bypass).

## Currently registered

None yet. This is a disclosed, deferred onboarding step — not an oversight.
See `core/policy/policy.yaml`'s `verifier_keys` comment block.
