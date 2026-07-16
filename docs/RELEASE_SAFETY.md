# Release safety contract

Tess OS releases are intentionally fail-closed. A blocked release is not
automatically a broken release: it means one or more independently checkable
release facts has not been established.

## What a production release proves

A GitHub Release is reachable only when all of these statements are true:

1. The ref is a stable, annotated `vX.Y.Z` tag.
2. The tagged commit is exactly the fetched `origin/main` HEAD at release time.
3. The tag signature verifies under the one public key supplied by the
   protected GitHub `release` environment.
4. The signature's primary-key fingerprint exactly matches the fingerprint
   allowlisted in that same protected environment.
5. `package.json`, `create-tess/package.json`, both create-tess lockfile version
   fields, `.tess/tess.lock` `framework.version`, and its `upstream_ref` all
   agree with `X.Y.Z`.
6. The GUI's independent version agrees with its own lockfile, remains
   `private: true`, and no workflow adds a GUI npm publication command.
7. The existing upstream `secret scan (gitleaks)` GitHub Actions check has a
   successful latest result for the exact tagged commit.
8. Python tests, `tessctl doctor`, `tessctl verify`, create-tess tests, GUI
   tests, package manifests, tracked-path scrub, and vault-registry scrub pass.

The release workflow publishes only after those gates. It does not download an
unchecked secret-scanner binary and it does not publish npm packages.

Tag pushes are deliberately inert. Production is an explicit `Release`
workflow dispatch from protected `main` with the already-created `vX.Y.Z` tag
as input. The workflow checks out trusted release control from main and the tag
into a separate candidate directory. Trusted control validates candidate
identity and contents with read-only permissions; a separate downstream job is
the only job granted `contents: write`, and that job runs no candidate code.

`publish-npm.yml` is a separate manual, post-release action. It checks out the
same `vX.Y.Z` tag, repeats source/signature/version/workflow gates, requires the
successful GitHub Release and secret-scan checks for that exact commit, tests
and packs all package surfaces, and only then requests npm's Trusted Publishing
OIDC credential. It uses the same trusted-control/candidate split and disables
npm lifecycle scripts for publication. Independent `create-tess-v*` tags are
no longer a publication authority.

## Protected environment configuration

The repository owner must configure a GitHub environment named `release` with:

- environment secret `TESS_SIGNING_PUBKEY`: the armored **public** release key;
- environment variable `TESS_RELEASE_SIGNER_FINGERPRINT`: its exact 40- or
  64-character uppercase primary fingerprint.

Set the environment's deployment branch policy to **selected branches and
tags: protected `main` only**. Do not allow every branch or release tags to
deploy to this environment. That external policy ensures a workflow definition
from an untrusted branch or tag cannot receive release configuration, even if
repository code is maliciously changed.

Also add a repository ruleset for `v*` tags that forbids tag updates and
deletions. Preflight records the exact annotated-tag object and the downstream
publication job checks it again, while the external immutability rule closes
the remaining check-to-publication race.

The environment must not contain private key material. The preflight imports
the public key into an isolated temporary GPG home, rejects secret-key records,
requires exactly one primary public key, and checks the `VALIDSIG` primary
fingerprint. Neither the candidate repository nor `.tess/tess.lock` can supply
or override the release signer allowlist. The lock fingerprint belongs to the
runtime update trust path; it is not release authorization.

Configuring this environment is a key-custody operation. The workflow does not
generate a key, register a verifier, create a verdict, or bootstrap trust on
the owner's behalf.

## Credential-free rehearsal

Pull requests that change release-bearing paths and manual `Release` workflow
runs with a blank `release_tag` use the `rehearse` job. It has read-only
repository permissions, no `release` environment, no release secrets, no
publishing step, and runs npm packing with scripts disabled.

Locally, the same non-publishing checks are:

```sh
python scripts/release_preflight.py metadata --advisory
python scripts/release_preflight.py workflows
python scripts/release_preflight.py packs
python -m pytest tests/test_release_preflight.py
```

`metadata --advisory` always reports readiness honestly but returns success for
rehearsal. An actual tag run omits `--advisory`, so the same mismatch blocks the
release.

## Current release-preparation debt

At the time this contract was added, the root metadata package reports
`0.1.0`, while create-tess and the trusted framework lock report `0.1.1`.
This branch deliberately does not reconcile them. A separately reviewed
release-preparation change must choose the intended release version and align
all public release fields before any production tag can pass.

## Owner checklist before enabling the workflow

1. Review and merge release hardening through the normal security process.
2. Configure the protected `release` environment values and protected-main-only
   deployment policy above.
3. Make `CI / secret scan (gitleaks)` a required successful check for `main`.
4. Reconcile the public release version fields in a separate reviewed change.
5. Confirm a manual credential-free rehearsal is green.
6. Only then create the owner-signed annotated tag on the exact current main
   commit.
7. From the workflow's protected `main` ref, manually run `Release` with the
   full `vX.Y.Z` tag and wait for both preflight and GitHub Release jobs.
8. After the signed GitHub Release succeeds, manually run `Publish create-tess
   to npm` from protected `main` with the same `X.Y.Z` value if npm publication
   is intended.

Tagging, signing, and npm publication remain explicit owner operations.
