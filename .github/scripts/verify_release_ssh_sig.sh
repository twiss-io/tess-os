#!/usr/bin/env bash
# verify_release_ssh_sig.sh <tag> — pass only if <tag> is an annotated tag whose
# message carries the SSH release signature (namespace "tess-release") made by
# the PINNED Twiss SSH release key over the manifest of THIS tag and commit:
#
#   tess-release-manifest/1\ntag <tag>\nobject <commit>\ntree <tree>\n
#
# This is the signature gpg-less installs rely on (`ssh-keygen -Y verify`), so
# a release that lacks it, or carries one over another commit/tag, must not
# ship. The public key comes from the committed
# .tess/keys/twiss-release-allowed-signers (exactly one entry); its SHA256
# fingerprint must equal PINNED_SSH_FPR, which must equal tess.lock
# framework.trusted_ssh_key_fingerprint (tests/test_v1_ssh_release_sig.py).
#
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

PINNED_SSH_FPR="SHA256:2G0Xp5X+54NdmGbIOBhWicNlhU/Law9WpWisuAitBoI"
TAG="${1:?usage: verify_release_ssh_sig.sh <tag>}"
SIGNERS_FILE="${RELEASE_SSH_SIGNERS_FILE:-.tess/keys/twiss-release-allowed-signers}"
MARKER="Tess-Release-SSH-Signature: tess-release-manifest/1"

if [ "$(git cat-file -t "refs/tags/${TAG}" 2>/dev/null || echo missing)" != "tag" ]; then
  echo "::error::${TAG} is not an annotated tag."
  exit 1
fi
if [ ! -f "$SIGNERS_FILE" ] || [ -L "$SIGNERS_FILE" ]; then
  echo "::error::SSH release allowed_signers not found at ${SIGNERS_FILE}."
  exit 1
fi

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
git cat-file tag "refs/tags/${TAG}" > "$work/tag"

# Canonical tag header order: object, type, tag, tagger.
object="$(awk 'NR==1 && $1=="object" {print $2}' "$work/tag")"
otype="$(awk 'NR==2 && $1=="type" {print $2}' "$work/tag")"
name="$(awk 'NR==3 && $1=="tag" {print $2}' "$work/tag")"
if [ "$otype" != "commit" ] || [ -z "$object" ] || [ "$name" != "$TAG" ]; then
  echo "::error::${TAG}: tag object is not a tag named ${TAG} pointing at a commit."
  exit 1
fi
tree="$(git rev-parse --verify "${object}^{tree}")"
printf 'tess-release-manifest/1\ntag %s\nobject %s\ntree %s\n' "$TAG" "$object" "$tree" > "$work/manifest"

# The signature block: the 4-space-indented lines after the ONE marker line,
# inside the message (before any OpenPGP signature).
awk '/^-----BEGIN PGP SIGNATURE-----$/ {exit} {print}' "$work/tag" > "$work/payload"
if [ "$(grep -c 'Tess-Release-SSH-Signature' "$work/payload" || true)" != "1" ] \
   || [ "$(grep -cx "$MARKER" "$work/payload" || true)" != "1" ]; then
  echo "::error::${TAG} carries no (or more than one) SSH release signature. Sign with scripts/release/sign-release-tag.sh (tess-os maintainer tool; see conductor/release-process.md step 8)."
  exit 1
fi
awk -v m="$MARKER" '$0==m {f=1; next} f && /^    / {print substr($0,5); next} f {exit}' \
  "$work/payload" > "$work/sig"

# Exactly one allowed_signers entry, the twiss-release ed25519 key; verify
# against a normalized copy so no option in the file can widen trust.
entries="$(grep -vE '^[[:space:]]*(#|$)' "$SIGNERS_FILE")"
if [ "$(printf '%s\n' "$entries" | wc -l | tr -d ' ')" != "1" ]; then
  echo "::error::${SIGNERS_FILE} must hold exactly one entry."
  exit 1
fi
read -r principal opts ktype kb64 _rest <<<"$entries"
if [ "$principal" != "twiss-release" ] || [ "$opts" != 'namespaces="tess-release"' ] \
   || [ "$ktype" != "ssh-ed25519" ]; then
  echo "::error::${SIGNERS_FILE} entry is not the twiss-release ssh-ed25519 key."
  exit 1
fi
printf '%s %s\n' "$ktype" "$kb64" > "$work/key.pub"
fpr="$(ssh-keygen -lf "$work/key.pub" | awk '{print $2}')"
if [ "$fpr" != "$PINNED_SSH_FPR" ]; then
  echo "::error::${SIGNERS_FILE} holds ${fpr}, not the pinned SSH release key ${PINNED_SSH_FPR}."
  exit 1
fi
printf 'twiss-release namespaces="tess-release" %s %s\n' "$ktype" "$kb64" > "$work/allowed"

if ! out="$(ssh-keygen -Y verify -f "$work/allowed" -I twiss-release -n tess-release \
      -s "$work/sig" < "$work/manifest" 2>&1)"; then
  echo "::error::${TAG} SSH release signature does not verify for ${object}: ${out}"
  exit 1
fi
case "$out" in
  *"$PINNED_SSH_FPR"*) ;;
  *) echo "::error::${TAG} SSH release signature is not by ${PINNED_SSH_FPR}."; exit 1 ;;
esac
echo "OK: ${TAG} (${object}) carries an SSH release signature by the pinned key ${PINNED_SSH_FPR}."
