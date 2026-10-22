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

# 3. Re-baseline integrity (only after a reviewed change to .tess/core).
#    Run it in your own shell or in CI: `lock --regen` refuses to run inside
#    Claude Code or Codex (with or without --yes). Without --yes it asks you
#    to type `re-baseline tess.lock` at the terminal.
python3 .tess/bin/tessctl lock --regen --yes

# 4. Regenerate the create-tess template LAST, then check
(cd create-tess && node scripts/build-template.mjs)
python3 -m pytest -q
(cd create-tess && npm test)
python3 .tess/bin/tessctl doctor
python3 .tess/bin/tessctl verify
python3 .tess/bin/tessctl lock --check

# 4b. Security audit of the candidate (see "Security audit before tagging"
#     below). Both validators must pass and no confirmed critical/high may
#     remain before the release PR is opened.
python3 .tess/bin/tessctl audit validate ~/security-audit-skill/tess-os/run-<N>

# 5. Push the branch and open the PR (not a draft)
git push -u origin release/v<new-semver>
gh pr create -R twiss-io/tess-os --base main --title "Tess OS v<new-semver>" --body "..."

# 6. If the gate reports protected paths: the independent verifier drafts
#    reviews/verdicts/<date>-<slug>.cyra.verdict.md; then, in YOUR terminal (it
#    shows the verdict and asks you to type `sign as Cyra`; it refuses a key
#    with no passphrase and any key not registered for Cyra in policy.yaml):
export GPG_TTY=$(tty)
python3 .tess/bin/tessctl verdict sign reviews/verdicts/<date>-<slug>.cyra.verdict.md \
  --key-id <registered verifier fingerprint>
git add reviews/verdicts && git commit -m "review: sign <slug> verdict" && git push
SIGNED_SHA=$(git rev-parse HEAD)

# 7. When all six checks are green on SIGNED_SHA, merge exactly that SHA
gh pr merge <pr-number> --merge --match-head-commit "$SIGNED_SHA"
git fetch origin && M=$(git rev-parse origin/main)

# 8. Sign BOTH release tags on the SAME merge commit M, in YOUR terminal, with
#    the maintainer tool scripts/release/sign-release-tag.sh (tess-os only; it
#    is not shipped to installs). Each run builds one annotated tag carrying
#    two signatures from the release key: the SSH signature in the tag message
#    (checked by .github/scripts/verify_release_ssh_sig.sh and by installs
#    without gpg) and the OpenPGP signature on the tag (Gate 1). release.yml
#    refuses a v<new-semver> tag lacking either; publish-npm.yml checks the
#    OpenPGP signature on create-tess-v<new-semver> and both signatures on
#    v<new-semver>. Do not use `git tag -s`: it makes the OpenPGP signature only.
#    Each run shows two Keychain prompts (SSH, then gpg): click "Allow",
#    never "Always Allow".
#
#    Run the helper from a HASH-VERIFIED COPY, never from the working tree
#    (security review round 2, M-5): it runs while the release keys are
#    unlocked, and a working-tree file can be edited by anything running as
#    you. Take the bytes from the reviewed merge commit M, and check their
#    sha256 against the copy in the LAST SIGNED release (checked first). If
#    the two differ, the helper changed in this release: read
#    `git diff v<previous-semver> "$M" -- scripts/release/` (the path is
#    security tier and CODEOWNERS-gated, so the change was reviewed in the PR),
#    and only then set WANT to the new sha256 by hand. Record the sha256 you
#    ran in the GitHub release notes, so the next release checks against it.
#    First release that ships the helper (v1.0.0; v0.2.0 has none): set WANT
#    to the sha256 the verifier recorded in the signed verdict for the PR.
PREV=v<previous-semver>
git verify-tag --raw "$PREV" 2>&1 | grep -q 'VALIDSIG EBEABC618C11B6A7340A7D1601DD637667B8CC89' \
  || { echo "STOP: $PREV is not signed by the release key"; exit 1; }
SIGNER_DIR="$(mktemp -d)"; SIGNER="$SIGNER_DIR/sign-release-tag.sh"
git show "$M:scripts/release/sign-release-tag.sh" > "$SIGNER"
WANT=$(git show "$PREV:scripts/release/sign-release-tag.sh" | shasum -a 256 | cut -d' ' -f1)
GOT=$(shasum -a 256 "$SIGNER" | cut -d' ' -f1)
test "$GOT" = "$WANT" || { echo "STOP: helper differs from $PREV (see above)"; exit 1; }
export TESS_RELEASE_SSH_KEY=<path to the SSH release private key, outside any repo>
bash "$SIGNER" v<new-semver> "$M"
bash "$SIGNER" create-tess-v<new-semver> "$M"
rm -rf "$SIGNER_DIR"
for t in v<new-semver> create-tess-v<new-semver>; do
  git cat-file -t "$t"                          # must print: tag
  test "$(git rev-parse "$t^{commit}")" = "$M"  # both tags on M
  git verify-tag --raw "$t" 2>&1 | grep VALIDSIG # must show EBEABC618C11B6A7340A7D1601DD637667B8CC89
  bash .github/scripts/verify_release_ssh_sig.sh "$t"  # the SSH release signature
done
# Push the framework tag only. create-tess-v<new-semver> stays local until the
# pre-publish gate below is green.
git push origin v<new-semver>

# 9. release.yml runs on the tag push: restores the annotated tag, verifies the
#    signature (Gate 1), runs the test suite, gitleaks over the tag's history,
#    the secret-path scrub, and publishes the GitHub release with the curated
#    CHANGELOG summary as notes. If it cannot run, publish by hand and say so:
gh release create v<new-semver> --verify-tag --latest \
  --title "Tess OS v<new-semver>" --notes-file <curated summary>
```

### Security audit before tagging (v1.0.0+)

Tess OS audits itself with the method it ships: the `security-audit` skill
(Cloudflare's open-source method, `.tess/core/skills/security-audit/`; read its
`TESS.md` for how the roles map). Run it on the release candidate before step 5.

- **Scope.** Major and minor releases: a full audit of the candidate. Patch
  releases: a scoped audit of `git diff v<previous-release>..<candidate>`, with
  every surface outside the diff recorded as `out_of_scope`, never `covered`.
- **Reuse the last run.** Start from the previous release's run folder
  (`~/security-audit-skill/tess-os/run-<N-1>`): the new run reads its
  `coverage-ledger.json` and `findings.json`, re-checks carried findings, and
  turns its blocked, deferred and needs_validation units into current work.
- **Required to tag:**
  1. `tessctl audit validate <run-dir>` passes: both upstream validators accept
     `findings.json` and `coverage-ledger.json`.
  2. `run_status` is `complete`, or the release notes state the exact
     `incomplete_reason` and the maintainer accepts it in writing on the PR.
  3. Zero `confirmed` findings of severity critical or high. Fix them (smallest
     fix plus regression test, checked by a fresh verifier) and re-run the
     affected units first.
  4. Every `needs_validation` item is listed in the release notes by fingerprint
     and the missing fact, in words that do not describe how to exploit it.
- **Keep the artifacts out of the public repo.** The run folder stays on the
  maintainer's machine, outside the repository. The release notes carry only a
  summary: the reviewed commit, profile and scope, counts per verdict and
  severity, validator result, the needs_validation list above, and the sha256
  of `findings.json` so the run can be matched later. Details of an unfixed
  finding go to the private reporting channel in SECURITY.md, never to an
  issue, PR, commit or release note.

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
3. **Tag check:** for both `v<new-semver>` and `create-tess-v<new-semver>`,
   `git verify-tag --raw` shows the pinned VALIDSIG and
   `.github/scripts/verify_release_ssh_sig.sh` accepts the SSH signature, and both
   tags point at M.

Then configure the npm trusted publisher if needed, and push the npm tag you
signed on M in step 8 (never cut a new, unsigned one here: publish-npm.yml
refuses it):

```bash
git push origin create-tess-v<new-semver>
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
agent-held verifier key: the registered Cyra key (`F9321F92…76E8`)
has no passphrase and is reachable by automated agents on the maintainer's machine, so
"an independent verifier signed it" was process, not enforcement. From v1.0.0,
SECURITY.md states the trust model plainly: a verifier signature is an automated
review attestation, not a human approval, and the release signing key is the single
root of trust. Since the v1.0 security audit, `tessctl verdict sign` also needs the
maintainer at a terminal (typing `sign as Cyra`) and refuses a key with no
passphrase, so an agent cannot sign through it: give the Cyra key a passphrase with
`gpg --passwd <fingerprint>` before the first signature.

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
