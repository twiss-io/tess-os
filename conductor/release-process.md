# Tess OS — Signed Release Process

This document describes the release process for Tess OS framework maintainers.
All releases are signed with an ed25519 GPG key. The public key is bundled at
`.tess/keys/twiss-release-key.asc` and the pinned fingerprint is committed to
`framework.trusted_key_fingerprint` in `tess.lock`.

For what a version number *means* (SemVer policy, what bumps MAJOR/MINOR/
PATCH, how the four version-bearing files below relate to each other), see
[`docs/VERSIONING.md`](../docs/VERSIONING.md). This document covers the
mechanics of cutting a release; that one covers the numbering policy.

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
- Decide the version number using [`docs/VERSIONING.md`](../docs/VERSIONING.md)'s
  MAJOR/MINOR/PATCH rule — do this before step 1, it determines the release
  notes' framing

### Releasing a new version

```bash
# 1. Make and commit your changes
git add -A && git commit -m "feat: ..."

# 2. Bump ALL FOUR version-bearing files to the same <new-semver>
#    (see docs/VERSIONING.md — this is the step release-process.md v1
#    omitted, which is why pyproject.toml/package.json drifted behind
#    two tagged releases; do not repeat that gap):
#      .tess/tess.lock      framework.version = <new-semver>
#                            framework.upstream_ref = v<new-semver>
#      pyproject.toml        [project].version = <new-semver>
#      package.json (root)   .version = <new-semver>
#      create-tess/package.json  .version = <new-semver>   (MAJOR.MINOR must
#                                match; see VERSIONING.md if create-tess is
#                                already ahead on PATCH from its own release)

# 3. Move CHANGELOG.md's [Unreleased] section to a new dated version heading
#    ## [<new-semver>] — YYYY-MM-DD
#    and start a fresh, empty [Unreleased] above it. Cross-check every entry
#    that documented a since-merged PR is actually merged (not still open).

# 4. Re-baseline integrity
python3 .tess/bin/tessctl lock --regen --yes

# 5. Verify doctor + verify are green, plus the full test matrix CI runs
python3 .tess/bin/tessctl doctor
python3 .tess/bin/tessctl verify
python -m pytest
(cd create-tess && npm test)

# 6. Commit the version bump + changelog move
git add .tess/tess.lock pyproject.toml package.json create-tess/package.json CHANGELOG.md
git commit -m "chore: bump version to v<new-semver>"

# 7. Create a signed annotated tag (triggers .github/workflows/release.yml,
#    which re-verifies the signature + reruns the full gate suite before
#    publishing the GitHub Release — see Gates 1-5 in that workflow)
FINGERPRINT="EBEABC618C11B6A7340A7D1601DD637667B8CC89"
git tag -s v<new-semver> -u "$FINGERPRINT" -m "Tess OS v<new-semver>"

# 8. Push branch + tag
git push origin main
git push origin v<new-semver>

# 9. Confirm the Release workflow published (it runs automatically on the
#    v<new-semver> push above — do not create the release manually unless
#    that workflow fails and you've diagnosed why)
gh run list -R twiss-io/tess-os --workflow=release.yml --limit 1
gh release view v<new-semver> -R twiss-io/tess-os

# 10. Publish create-tess to npm — tag its OWN namespace to trigger
#     .github/workflows/publish-npm.yml (Trusted Publishing/OIDC, fails
#     closed if create-tess/package.json's version doesn't match this tag —
#     see docs/VERSIONING.md's "already wired" section). REQUIRES npm's
#     Trusted Publisher to be configured for this repo+workflow on
#     npmjs.com first (one-time, dashboard-only, not a git operation) —
#     confirm that's done before tagging or this step fails closed with an
#     auth error.
git tag create-tess-v<new-semver>
git push origin create-tess-v<new-semver>
gh run list -R twiss-io/tess-os --workflow=publish-npm.yml --limit 1

# 11. Verify adopters can upgrade
git clone https://github.com/twiss-io/tess-os.git /tmp/upgrade-test
cd /tmp/upgrade-test
gpg --import .tess/keys/twiss-release-key.asc
python3 .tess/bin/tessctl update --ref v<new-semver>

# 12. Verify the npm publish landed
npm view create-tess version   # should print <new-semver>
npm create tess@latest         # smoke test the published wizard
```

### Release checklist

Copy this into the release tracking issue/PR before tagging:

- [ ] Version decided per `docs/VERSIONING.md` (MAJOR/MINOR/PATCH rationale
      stated, not just picked)
- [ ] `.tess/tess.lock` — `framework.version` + `upstream_ref` bumped
- [ ] `pyproject.toml` — `[project].version` bumped to match
- [ ] `package.json` (root) — `.version` bumped to match
- [ ] `create-tess/package.json` — `.version` bumped to match (MAJOR.MINOR)
- [ ] `CHANGELOG.md` — `[Unreleased]` moved under a new dated `##
      [<semver>] — YYYY-MM-DD` heading; every entry double-checked against
      what's actually merged to `main` (no entry for a still-open PR)
- [ ] `tessctl lock --regen --yes` run; `doctor` + `verify` both `OK`
- [ ] `python -m pytest` green; `(cd create-tess && npm test)` green
- [ ] Version-bump commit pushed to `main`
- [ ] Signed annotated tag `v<semver>` created and pushed
- [ ] `.github/workflows/release.yml` run succeeded (Gates 1-5) and the
      GitHub Release is published
- [ ] `create-tess-v<semver>` tag pushed (only after npm's Trusted
      Publisher is confirmed configured for this repo)
- [ ] `.github/workflows/publish-npm.yml` run succeeded; `npm view
      create-tess version` shows `<semver>`
- [ ] Adopter upgrade path smoke-tested (`tessctl update --ref
      v<semver>` against a fresh clone at the prior tag)
- [ ] `npm create tess@latest` smoke-tested against the newly published
      package

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
