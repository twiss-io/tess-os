#!/usr/bin/env bash
# verify_release_tag.sh <tag> — pass only if <tag> is an annotated tag whose
# signature verifies AND was made by the pinned Tess OS release key.
#
# The public key comes from the committed .tess/keys/twiss-release-key.asc,
# imported into a throwaway GNUPGHOME, so no other key on the runner can
# satisfy the check. A valid signature from any other key is refused.
# PINNED_FPR must equal tess.lock framework.trusted_key_fingerprint
# (tests/test_v021_release_pipeline.py checks this).
#
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

PINNED_FPR="EBEABC618C11B6A7340A7D1601DD637667B8CC89"
TAG="${1:?usage: verify_release_tag.sh <tag>}"
KEY_FILE="${RELEASE_KEY_FILE:-.tess/keys/twiss-release-key.asc}"

if [ "$(git cat-file -t "refs/tags/${TAG}" 2>/dev/null || echo missing)" != "tag" ]; then
  echo "::error::${TAG} is not an annotated tag (git tag -s ${TAG})."
  exit 1
fi
if [ ! -f "$KEY_FILE" ]; then
  echo "::error::release public key not found at ${KEY_FILE}."
  exit 1
fi

GNUPGHOME="$(mktemp -d)"
export GNUPGHOME
trap 'rm -rf "$GNUPGHOME"' EXIT
gpg --batch --quiet --import "$KEY_FILE" 2>/dev/null

status="$(git verify-tag --raw "$TAG" 2>&1 >/dev/null || true)"
# [GNUPG:] VALIDSIG <signing-key-fpr> ... <primary-key-fpr>
signer="$(printf '%s\n' "$status" | awk '$1=="[GNUPG:]" && $2=="VALIDSIG" {print $NF; exit}')"
if [ -z "$signer" ]; then
  echo "::error::${TAG} has no valid signature from the release key."
  printf '%s\n' "$status" | grep '^\[GNUPG:\]' | cut -d' ' -f1-3 || true
  exit 1
fi
if [ "$signer" != "$PINNED_FPR" ]; then
  echo "::error::${TAG} is signed by ${signer}, not the pinned release key ${PINNED_FPR}."
  exit 1
fi
echo "OK: ${TAG} is signed by the pinned release key ${PINNED_FPR}."
