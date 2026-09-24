# Tess OS — Signed Release Process

This document describes the release process for Tess OS framework maintainers.
All releases are signed with an ed25519 GPG key. The public key is bundled at
`.tess/keys/twiss-release-key.asc` and the pinned fingerprint is committed to
`framework.trusted_key_fingerprint` in `tess.lock`.

---

## Trust Model

Every `tessctl update` and `tessctl self-update` call performs the following security
checks before extracting any files from the upstream:

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

- GPG release key on the maintainer's machine, fingerprint pinned in `tess.lock`
  (`EBEABC618C11B6A7340A7D1601DD637667B8CC89`)
- `gh` CLI authenticated with `twiss-io` write access
- Repository secret `TESS_SIGNING_PUBKEY` set to the armored PUBLIC key
  (`.tess/keys/twiss-release-key.asc`); `release.yml` Gate 1 fails without it

### Rules that apply to every step

- **Everything reaches `main` by pull request.** Ruleset 18248530 requires a PR and
  six green status checks (including `tessctl gate ci`) and has no bypass actors.
  A direct push to `main` is refused; never try it.
- **Protected paths need a covering verdict.** A PR that touches a path matched by
  `core/policy/policy.yaml` (engine, policy, workflows, security-tier doctrine) is
  blocked by `tessctl gate ci` until a signed APPROVE verdict covers it. The verdict
  is drafted by an independent verifier (Cyra) after reviewing the FULL diff, never
  by the author of the change.
- **Set `GPG_TTY` in the terminal that signs.** `tessctl verdict sign` and
  `git tag -s` call gpg, and pinentry is TTY-only. Start every signing command with
  `export GPG_TTY=$(tty)`.
- **Passphrase rule:** type a passphrase only for a signing command you started
  yourself, seconds ago.
- **Merge the signed SHA, nothing else.** After the verdict commit is pushed, record
  the head SHA and merge only that SHA with a merge commit.

### Releasing a new version

```bash
# 1. Work on a release branch; never on main
git fetch origin && git switch -c release/v<new-semver> origin/main

# 2. Version fields
#    .tess/tess.lock: framework.version = <new-semver>, framework.upstream_ref = v<new-semver>
#    create-tess/package.json version (then: cd create-tess && npm install --package-lock-only)
#    package.json and pyproject.toml version

# 3. Re-baseline integrity (only after a reviewed change to .tess/core)
python3 .tess/bin/tessctl lock --regen --yes

# 4. Regenerate the create-tess template LAST, then check
(cd create-tess && node scripts/build-template.mjs)
python3 -m pytest -q
(cd create-tess && npm test)
python3 .tess/bin/tessctl doctor
python3 .tess/bin/tessctl verify
python3 .tess/bin/tessctl lock --check

# 5. Push the branch and open the PR (not a draft)
git push -u origin release/v<new-semver>
gh pr create -R twiss-io/tess-os --base main --title "Tess OS v<new-semver>" --body "..."

# 6. If the gate reports protected paths: the independent verifier drafts
#    reviews/verdicts/<date>-<slug>.cyra.verdict.md; then, in YOUR terminal:
export GPG_TTY=$(tty)
python3 .tess/bin/tessctl verdict sign reviews/verdicts/<date>-<slug>.cyra.verdict.md \
  --key-id <registered verifier fingerprint>
git add reviews/verdicts && git commit -m "review: sign <slug> verdict" && git push
SIGNED_SHA=$(git rev-parse HEAD)

# 7. When all six checks are green on SIGNED_SHA, merge exactly that SHA
gh pr merge <pr-number> --merge --match-head-commit "$SIGNED_SHA"
git fetch origin && M=$(git rev-parse origin/main)

# 8. Signed annotated tag on the merge commit M, tagger = the release key's identity
export GPG_TTY=$(tty)
git -c user.name='Twiss Release Signing Key' -c user.email=legal@twiss.io \
  tag -s v<new-semver> -u EBEABC618C11B6A7340A7D1601DD637667B8CC89 \
  -m "Tess OS v<new-semver>" "$M"
git cat-file -t v<new-semver>          # must print: tag
git verify-tag --raw v<new-semver>     # must show VALIDSIG EBEABC618C11B6A7340A7D1601DD637667B8CC89
git push origin v<new-semver>

# 9. release.yml runs on the tag push: restores the annotated tag, verifies the
#    signature (Gate 1), runs the test suite, gitleaks over the tag's history,
#    the secret-path scrub, and publishes the GitHub release with the curated
#    CHANGELOG summary as notes. If it cannot run, publish by hand and say so:
gh release create v<new-semver> --verify-tag --latest \
  --title "Tess OS v<new-semver>" --notes-file <curated summary>
```

### Pre-publish gate (before ANY `create-tess-v*` tag)

`publish-npm.yml` publishes to npm when a `create-tess-v*` tag is pushed. Push that
tag only after all three of these pass against the real GitHub tag:

1. **Over-the-wire upgrade:** scaffold with the previous published create-tess, then
   in the scaffold run `self-update` and `update` (order below) against the real tag.
   `doctor` and `verify` report OK, local edits are preserved, and the negative cases
   hold: a tag signed by another key gives `SECURITY REJECT`, and a lightweight tag is
   rejected.
2. **Fresh install:** `npm pack` at M, then scaffold from that tarball; `doctor` and
   `verify` report OK and `tess.lock` pins the new version.
3. **Tag check:** `git verify-tag --raw v<new-semver>` shows the pinned VALIDSIG.

Then configure the npm trusted publisher if needed, and push the npm tag on M:

```bash
git tag create-tess-v<new-semver> "$M" && git push origin create-tess-v<new-semver>
```

If the gate is not green, do not publish; the GitHub release stands on its own and the
release notes say when npm follows.

### Key management

The release key private key must stay on the maintainer's machine only. The
macOS Keychain entry `'Twiss Release Signing Key passphrase'` (account:
`twiss-release-key`) holds the passphrase for the encrypted backup.

Encrypted private-key backup location: recorded in the maintainer's key
management runbook (never committed to the repository).

**Verifier-key custody (v0.2.0):** the v0.2.0 approvals were signed with an
agent-held verifier key: the registered Cyra key (`F9321F92B4E2DF36304CB6BAA53B9C5A1F5876E8`)
has no passphrase and is reachable by automated agents on the maintainer's machine, so
"an independent verifier signed it" was process, not enforcement. Custody hardening
(passphrase or hardware key, human sign-off, the #76 topology) is the first v0.2.1 item.

---

## Adopter: upgrading

Run these from your project root, in this order. `self-update` replaces the engine
first, so the new engine performs the update.

```bash
# Import the release key once (if not already in your keyring)
gpg --import .tess/keys/twiss-release-key.asc

# 1. Upgrade the engine to the signed release
python3 .tess/bin/tessctl self-update --ref v0.2.0

# 2. Upgrade the framework files to the same release
python3 .tess/bin/tessctl update --ref v0.2.0

# Verify after upgrade
python3 .tess/bin/tessctl doctor
python3 .tess/bin/tessctl verify
```
