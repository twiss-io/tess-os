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
7. The existing upstream `secret scan (gitleaks)` job is proven through the
   Actions API chain: exact active workflow file and workflow ID, latest run ID
   and attempt, `push` event, protected-main branch, exact head SHA, exact job,
   successful conclusion, check-suite identity, and GitHub Actions App ID.
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

`publish-npm.yml` is a separate manual, post-release action. Its first job tests
the candidate with read-only permissions and no OIDC authority. A second job
freshly checks out the exact tag, repeats source/signature/version gates, runs
no package lifecycle scripts, and uploads only the validated `create-tess`
tarball plus a SHA-256/source/tag evidence envelope. The final protected job has
no checkout, no candidate test or build command, and no tar extraction. It
downloads the exact artifact by immutable artifact ID, validates the artifact
service digest and tarball SHA-256, rechecks the live annotated-tag object, and
publishes that exact tarball with `--ignore-scripts --provenance`. Only this
minimal final job receives `id-token: write`. Independent `create-tess-v*` tags
are not publication authority.

## Protected environment configuration

The repository owner must configure a GitHub environment named `release` with:

- environment secret `TESS_SIGNING_PUBKEY`: the armored **public** release key;
- environment variable `TESS_RELEASE_SIGNER_FINGERPRINT`: its exact 40- or
  64-character uppercase primary fingerprint.

Set the environment's deployment branch policy to **selected branches and
tags**, add exactly the protected `main` branch, and add no tag pattern. Do not
use the broader "all protected branches" option. Deselect **Allow
administrators to bypass configured protection rules**. These settings are
external enforcement: a workflow definition from another branch or tag cannot
obtain the release environment or its npm OIDC identity, and an administrator
cannot force a bypass through the Actions approval UI.

Also add an active repository tag ruleset targeting `refs/tags/v*` that forbids
updates and deletions with no bypass actors. Do not enable "restrict creations"
unless a separately reviewed custodial creation path exists: the signed-tag
gate, not a broad ruleset bypass, authorizes release identity. Preflight records
the exact annotated-tag object and both GitHub Release and npm publication check
it immediately before their write, while the external immutability rule closes
the remaining check-to-publication race.

The environment is the only release-signer allowlist. Do not duplicate
`TESS_SIGNING_PUBKEY` or `TESS_RELEASE_SIGNER_FINGERPRINT` as repository or
organization values, and never accept candidate or lockfile values as release
authorization. The environment must not contain private key material. Preflight imports
the public key into an isolated temporary GPG home, rejects secret-key records,
requires exactly one primary public key, and checks the `VALIDSIG` primary
fingerprint. Neither the candidate repository nor `.tess/tess.lock` can supply
or override the release signer allowlist. The lock fingerprint belongs to the
runtime update trust path; it is not release authorization.

Configuring this environment is a key-custody operation. The workflow does not
generate a key, register a verifier, create a verdict, or bootstrap trust on
the owner's behalf.

## Exact npm Trusted Publisher configuration

In the npm settings for the existing `create-tess` package, configure one
GitHub Actions Trusted Publisher with these case-sensitive values:

| npm field | Exact value |
|---|---|
| Organization or user | `twiss-io` |
| Repository | `tess-os` |
| Workflow filename | `publish-npm.yml` |
| Environment name | `release` |
| Allowed actions | `npm publish` only |

Do not enable `npm stage publish`. The workflow requires GitHub-hosted runners,
Node 24, npm 11.5.1 or newer, and job-level `id-token: write` only on
`publish_oidc`. npm validates the workflow filename rather than a full path, so
the configured value must be exactly `publish-npm.yml`, including the suffix.
See npm's canonical [Trusted Publishers documentation](https://docs.npmjs.com/trusted-publishers/)
for the provider form and current runtime floor.

Before enabling production publication, revoke every legacy npm automation or
granular write token for this package and remove `NPM_TOKEN` and
`NODE_AUTH_TOKEN` from repository, organization, and environment secrets. The
workflow validator rejects either token binding. Keep no fallback write token:
if OIDC is unavailable or misbound, publication must stop.

The pinned artifact actions are official `actions/upload-artifact` v4.6.2 and
`actions/download-artifact` v4.3.0 commits. CI downloads Gitleaks 8.30.1 to a
temporary file and verifies the official linux-x64 SHA-256 before extraction;
it never streams an unchecked download into `tar`.

GitHub documents the protected-branch policy and the separate switch for
disabling administrator bypass under [Deployments and environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments).

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
3. Disable administrator bypass on `release` and activate the immutable `v*`
   tag ruleset described above.
4. Configure the exact npm Trusted Publisher binding above, revoke legacy npm
   write tokens, and confirm no npm token secret remains.
5. Make `CI / secret scan (gitleaks)` a required successful check for `main`.
6. Reconcile the public release version fields in a separate reviewed change.
7. Confirm a manual credential-free rehearsal is green.
8. Only then create the owner-signed annotated tag on the exact current main
   commit.
9. From the workflow's protected `main` ref, manually run `Release` with the
   full `vX.Y.Z` tag and wait for both preflight and GitHub Release jobs.
10. After the signed GitHub Release succeeds, manually run `Publish create-tess
   to npm` from protected `main` with the same `X.Y.Z` value if npm publication
   is intended.

Tagging, signing, and npm publication remain explicit owner operations.
