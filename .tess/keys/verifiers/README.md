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

`tessctl verdict keygen --verifier <Name>` does both the key-file half
(generate + export here) and the registration half (both copies of
`policy.yaml`, comment-preserving, re-pinned) in one command — see
`conductor/verdict-signing.md`'s "Onboarding a verifier" section and
`docs/GATE_QUICKSTART.md` for the full walkthrough. The manual
`gpg --export --armor` path documented there still works unchanged for a
verifier who already has a keypair or wants full control over key
parameters.

## Currently registered

None yet, for THIS repo's own real Reid/Cyra trust anchors. This is a
disclosed, deferred onboarding step — not an oversight, and not something
`tessctl verdict keygen`'s existence changes: generating a real key for this
repo's own `tess-os-security-tier-doctrine` rule is a maintainer
private-key-custody decision, not fabricated here. See
`core/policy/policy.yaml`'s `verifier_keys` comment block.
