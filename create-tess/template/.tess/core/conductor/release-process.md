# Tess OS — Signed Release Process

This document describes the release process for Tess OS framework maintainers.
All releases are signed with an ed25519 GPG key. The public key is bundled at
`.tess/keys/twiss-release-key.asc` and the pinned fingerprint is committed to
`framework.trusted_key_fingerprint` in `tess.lock`.

---

## Trust Model

Every `tess update` and `tess self-update` call performs the following security checks
before extracting any files from the upstream:

1. **Annotated tag object** — the ref must resolve to a git tag object (not a branch
   tip or raw commit SHA). Branches and lightweight tags are rejected.
2. **Signature verification** — `git verify-tag --raw` is run inside an isolated
   GNUPGHOME seeded exclusively with the key exported by the pinned fingerprint.
   The ambient `~/.gnupg` keyring is never consulted after the pin is set.
3. **Exact fingerprint match** — the 40-hex signing fingerprint from `VALIDSIG` must
   match `framework.trusted_key_fingerprint` exactly (no short-ID matching).

A single check failure aborts the update with no files extracted.

---

## Maintainer Release Steps

### Prerequisites

- GPG release key imported and the fingerprint pinned in `tess.lock`
- `gh` CLI authenticated with `twiss-io` write access

### Releasing a new version

```bash
# 1. Make and commit your changes
git add -A && git commit -m "feat: ..."

# 2. Update version fields in .tess/tess.lock
#    framework.version  = <new-semver>
#    framework.upstream_ref = v<new-semver>

# 3. Re-baseline integrity
python3 .tess/bin/tessctl lock --regen --yes

# 4. Verify doctor + verify are green
python3 .tess/bin/tessctl doctor
python3 .tess/bin/tessctl verify

# 5. Commit the lock update
git add .tess/tess.lock && git commit -m "chore: bump version to v<new-semver>"

# 6. Create a signed annotated tag
FINGERPRINT="EBEABC618C11B6A7340A7D1601DD637667B8CC89"
git tag -s v<new-semver> -u "$FINGERPRINT" -m "Tess OS v<new-semver>"

# 7. Push branch + tag
git push origin main
git push origin v<new-semver>

# 8. Create GitHub release
gh release create v<new-semver> --title "Tess OS v<new-semver>" --notes "..."

# 9. Verify adopters can upgrade
git clone https://github.com/twiss-io/tess-os.git /tmp/upgrade-test
cd /tmp/upgrade-test
gpg --import .tess/keys/twiss-release-key.asc
python3 .tess/bin/tessctl update --ref v<new-semver>
```

### Key management

The release key private key must stay on the maintainer's machine only. The
macOS Keychain entry `'Twiss Release Signing Key passphrase'` (account:
`twiss-release-key`) holds the passphrase for the encrypted backup.

Encrypted private-key backup location: recorded in the maintainer's key
management runbook (never committed to the repository).

---

## Adopter: upgrading

```bash
# Import the release key once (if not already in your keyring)
gpg --import .tess/keys/twiss-release-key.asc

# Upgrade to a specific signed release
python3 .tess/bin/tessctl update --ref v0.1.1

# Verify after upgrade
python3 .tess/bin/tessctl doctor
python3 .tess/bin/tessctl verify
```
