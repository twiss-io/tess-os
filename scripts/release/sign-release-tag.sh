#!/usr/bin/env bash
# sign-release-tag.sh: create a Tess OS release tag carrying BOTH release signatures.
#
# This is the one human step in a Tess OS release. The tag it creates is the only
# thing the release/npm workflows accept. One run makes:
#   1. an SSH signature (Twiss SSH release key, namespace "tess-release") over the
#      release manifest "tess-release-manifest/1\ntag T\nobject C\ntree R\n",
#      embedded in the tag message, so machines WITHOUT gpg can verify updates
#      with the built-in `ssh-keygen -Y verify`;
#   2. the OpenPGP signature on the annotated tag itself (Twiss Release Signing
#      Key), exactly as before; it also covers the embedded SSH signature.
# Both passphrases are stored in the login Keychain with an EMPTY trusted-app
# list, so a run shows TWO macOS prompts (SSH first, then gpg). Click "Allow",
# NOT "Always Allow". "Always Allow" would let any local process read the
# passphrase silently again.
#
# Usage:
#   scripts/release/sign-release-tag.sh [--repo DIR] [--no-keychain] [--ssh-key FILE] TAG [COMMIT]
#     --repo DIR      git repo to tag (default: current directory)
#     --no-keychain   skip the Keychain; ssh-keygen and gpg ask for each
#                     passphrase themselves (fallback if prompts are unavailable)
#     --ssh-key FILE  SSH release private key, kept OUTSIDE this repo (default:
#                     $TESS_RELEASE_SSH_KEY; one of the two is required)
#     TAG             e.g. v1.0.0 or create-tess-v1.0.0
#     COMMIT          commit to tag (default: HEAD)
# After it succeeds, push the tag yourself: git push origin TAG
#
# Security (review 2026-09-29, H4): while the release key is unlocked, nothing
# from the repo being tagged may run. git is invoked with no global/system config,
# hooks off, fsmonitor off and a fixed gpg program; the tag object is built and
# signed here (gpg + `git mktag` + `git update-ref`) instead of `git tag -s`; gpg,
# gpg-connect-agent, ssh-keygen and security are called by absolute path from
# fixed install locations; the gpg passphrase cache is wiped right after signing.
#
# Contains no secrets. Passphrases live only in the Keychain items below.
set -euo pipefail

KEY_FPR="EBEABC618C11B6A7340A7D1601DD637667B8CC89"   # Twiss Release Signing Key (OpenPGP)
KC_SERVICE="Twiss Release Signing Key passphrase"
KC_ACCOUNT="twiss-release-key"
SSH_FPR="SHA256:2G0Xp5X+54NdmGbIOBhWicNlhU/Law9WpWisuAitBoI"   # Twiss Release Signing Key (SSH)
KC_SSH_SERVICE="Twiss Release SSH Signing Key passphrase"
KC_SSH_ACCOUNT="twiss-release-ssh-key"
SSH_NS="tess-release"
SSH_MARKER="Tess-Release-SSH-Signature: tess-release-manifest/1"

die() { echo "sign-release-tag: $*" >&2; exit 1; }
realpath_of() { /usr/bin/python3 -c 'import os,sys;print(os.path.realpath(sys.argv[1]))' "$1"; }

# --- trusted tools -----------------------------------------------------------
SSH_KEYGEN=/usr/bin/ssh-keygen
SECURITY=/usr/bin/security
GPG=""; GPGCA=""
for d in /opt/homebrew/bin /usr/local/bin /usr/local/MacGPG2/bin; do
  if [[ -x "$d/gpg" && -x "$d/gpg-connect-agent" ]]; then GPG="$d/gpg"; GPGCA="$d/gpg-connect-agent"; break; fi
done
[[ -n "$GPG" ]] || die "gpg not found in /opt/homebrew/bin, /usr/local/bin or /usr/local/MacGPG2/bin"
for b in "$GPG" "$GPGCA" "$SSH_KEYGEN" "$SECURITY"; do
  real=$(realpath_of "$b")
  perm=$(/usr/bin/stat -f '%Lp' "$real")
  (( (8#$perm & 8#022) == 0 )) || die "$real is group/world-writable; refusing to use it"
done

repo="."; use_keychain=1
# Maintainer tool shipped in tess-os (never in the create-tess template). The key
# never lives in a repo: name it with --ssh-key or TESS_RELEASE_SSH_KEY.
ssh_key="${TESS_RELEASE_SSH_KEY:-}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) repo="${2:?--repo needs a directory}"; shift 2 ;;
    --no-keychain) use_keychain=0; shift ;;
    --ssh-key) ssh_key="${2:?--ssh-key needs a file}"; shift 2 ;;
    -h|--help) sed -n '2,34p' "$0"; exit 0 ;;
    -*) die "unknown option: $1" ;;
    *) break ;;
  esac
done
tag="${1:-}"; commit="${2:-HEAD}"
[[ -n "$tag" ]] || die "missing TAG (see --help)"
[[ -n "$ssh_key" ]] || die "no SSH release key: pass --ssh-key FILE or set TESS_RELEASE_SSH_KEY"
[[ "$tag" =~ ^(create-tess-)?v[0-9]+\.[0-9]+\.[0-9]+([-.][0-9A-Za-z.]+)?$ ]] \
  || die "tag '$tag' does not look like vX.Y.Z or create-tess-vX.Y.Z"
repo=$(cd "$repo" && pwd -P) || die "cannot open repo $repo"
for b in "$GPG" "$GPGCA"; do
  case "$(realpath_of "$b")" in "$repo"/*) die "$b resolves inside the repo being tagged; refusing" ;; esac
done

# Hardened git: command-line -c beats the repo's own config; hooks and fsmonitor off.
sgit() {
  env -u GIT_DIR -u GIT_WORK_TREE -u GIT_CONFIG_PARAMETERS -u GIT_CONFIG_COUNT \
      GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 \
    git -c core.hooksPath=/dev/null -c core.fsmonitor=false -c gpg.format=openpgp \
        -c gpg.program="$GPG" -c gpg.ssh.program="$SSH_KEYGEN" -C "$repo" "$@"
}

sgit rev-parse --verify --quiet "refs/tags/$tag" >/dev/null && die "tag $tag already exists"
target=$(sgit rev-parse --verify "$commit^{commit}") || die "cannot resolve $commit"
tree=$(sgit rev-parse --verify "$target^{tree}") || die "cannot resolve the tree of $target"

# The SSH key must be the pinned one (public half read from FILE.pub, checked
# before any passphrase is requested).
[[ -f "$ssh_key" && -f "$ssh_key.pub" ]] || die "SSH release key not found at $ssh_key (+ .pub)"
ssh_fp=$("$SSH_KEYGEN" -lf "$ssh_key.pub" | awk '{print $2}')
[[ "$ssh_fp" == "$SSH_FPR" ]] || die "SSH key $ssh_key is $ssh_fp, not the pinned $SSH_FPR"

# Keygrip of the OpenPGP signing (primary) key, used to wipe the agent cache.
keygrip=$("$GPG" --batch --with-colons --with-keygrip --list-secret-keys "$KEY_FPR" \
  | awk -F: '/^sec/{s=1;next} s&&/^grp/{print $10; exit}')
[[ -n "$keygrip" ]] || die "release key $KEY_FPR is not in this keyring"

work=$(mktemp -d); chmod 700 "$work"
forget() { "$GPGCA" "clear_passphrase --mode=normal $keygrip" /bye >/dev/null 2>&1 || true; }
cleanup() { forget; rm -rf "$work"; }
trap cleanup EXIT

# --- 1. SSH signature over the release manifest ------------------------------
manifest="$work/manifest"
printf 'tess-release-manifest/1\ntag %s\nobject %s\ntree %s\n' "$tag" "$target" "$tree" > "$manifest"
if [[ $use_keychain -eq 1 ]]; then
  echo "macOS will ask to let 'security' read \"$KC_SSH_SERVICE\". Click Allow (NOT Always Allow)." >&2
  # ssh-keygen gets the passphrase from this askpass helper, which reads it from
  # the Keychain and writes it straight into ssh-keygen's pipe. The helper
  # file holds no secret; the passphrase is never in argv, env or on disk.
  cat > "$work/askpass" <<ASKPASS
#!/bin/sh
exec $SECURITY find-generic-password -s "$KC_SSH_SERVICE" -a "$KC_SSH_ACCOUNT" -w
ASKPASS
  chmod 700 "$work/askpass"
  env -u SSH_AUTH_SOCK SSH_ASKPASS="$work/askpass" SSH_ASKPASS_REQUIRE=force DISPLAY="${DISPLAY:-:0}" \
    "$SSH_KEYGEN" -q -Y sign -f "$ssh_key" -n "$SSH_NS" "$manifest" </dev/null \
    || die "SSH signing failed (Keychain read refused, or wrong passphrase; rerun with --no-keychain to type it)"
else
  env -u SSH_AUTH_SOCK "$SSH_KEYGEN" -q -Y sign -f "$ssh_key" -n "$SSH_NS" "$manifest" \
    || die "SSH signing failed"
fi
[[ -s "$manifest.sig" ]] || die "ssh-keygen produced no signature"

msg="$work/message"
{ printf 'Release %s\n\n%s\n' "$tag" "$SSH_MARKER"; sed 's/^/    /' "$manifest.sig"; } > "$msg"

# --- 2. OpenPGP-signed annotated tag, built here (no `git tag -s`) -----------
tagger="${TESS_RELEASE_TAGGER:-Twiss Release Signing Key <legal@twiss.io>}"
body="$work/tagbody"
{ printf 'object %s\ntype commit\ntag %s\ntagger %s %s %s\n\n' \
    "$target" "$tag" "$tagger" "$(date +%s)" "$(date +%z)"
  cat "$msg"; } > "$body"
if [[ $use_keychain -eq 1 ]]; then
  echo "macOS will ask to let 'security' read \"$KC_SERVICE\". Click Allow (NOT Always Allow)." >&2
  pp=$("$SECURITY" find-generic-password -s "$KC_SERVICE" -a "$KC_ACCOUNT" -w) \
    || die "Keychain read refused or failed (rerun with --no-keychain to type the passphrase)"
  printf '%s' "$pp" | "$GPG" --batch --yes --quiet --pinentry-mode loopback --passphrase-fd 0 \
    --local-user "$KEY_FPR!" --armor --detach-sign --output "$work/tag.asc" "$body" \
    || { unset pp; forget; die "passphrase from Keychain did not unlock the release key"; }
  unset pp
else
  GPG_TTY=$(tty) || true; export GPG_TTY
  "$GPG" --local-user "$KEY_FPR!" --armor --detach-sign --output "$work/tag.asc" "$body" \
    || { forget; die "OpenPGP signing failed"; }
fi
forget   # wipe the cached passphrase now, before any further git command runs
cat "$body" "$work/tag.asc" > "$work/tagobj"
obj=$(sgit mktag < "$work/tagobj") || die "git mktag rejected the tag object"
sgit update-ref "refs/tags/$tag" "$obj" "" || die "could not create refs/tags/$tag"

# --- 3. Verify both signatures on the tag as created; delete it on any miss --
fail() { sgit update-ref -d "refs/tags/$tag" >/dev/null 2>&1 || true; die "$* ; tag deleted"; }
vout=$(sgit verify-tag --raw "$tag" 2>&1 || true)
[[ "$vout" == *"VALIDSIG $KEY_FPR "* ]] || fail "OpenPGP signature on $tag did not verify as $KEY_FPR"

sgit cat-file tag "refs/tags/$tag" > "$work/tag"
[[ "$(awk 'NR==1{print $2}' "$work/tag")" == "$target" ]] || fail "tag does not name $target"
awk -v m="$SSH_MARKER" '
  /^-----BEGIN PGP SIGNATURE-----$/ {exit}
  $0==m {f=1; next}
  f && /^    / {print substr($0,5); next}
  f {exit}' "$work/tag" > "$work/embedded.sig"
printf 'twiss-release namespaces="%s" %s\n' "$SSH_NS" "$(awk '{print $1" "$2}' "$ssh_key.pub")" > "$work/allowed"
sout=$("$SSH_KEYGEN" -Y verify -f "$work/allowed" -I twiss-release -n "$SSH_NS" \
  -s "$work/embedded.sig" < "$manifest" 2>&1) || fail "SSH signature on $tag did not verify: $sout"
[[ "$sout" == *"$SSH_FPR"* ]] || fail "SSH signature on $tag is not by $SSH_FPR"

# Warn if someone clicked "Always Allow" (a Keychain ACL regained a trusted app).
if [[ $use_keychain -eq 1 ]]; then
  acl=$("$SECURITY" dump-keychain -a 2>/dev/null || true)
  for svc in "$KC_SERVICE" "$KC_SSH_SERVICE"; do
    n=$(awk -v s="\"svce\"<blob>=\"$svc\"" '
        index($0,s){f=1} f&&/^keychain:/{exit} f&&/authorizations.*decrypt/{d=1}
        f&&d&&/applications/{if (match($0,/\(([0-9]+)\)/)) print substr($0,RSTART+1,RLENGTH-2); else print 0; exit}' <<<"$acl" || true)
    if [[ "${n:-0}" != "0" ]]; then
      echo "WARNING: the Keychain item \"$svc\" now trusts $n app(s); passphrase is readable silently." >&2
      echo "         Fix: Keychain Access > \"$svc\" > Access Control > remove all apps." >&2
    fi
  done
fi

echo "Signed $tag -> $target with $KEY_FPR (OpenPGP) and $SSH_FPR (SSH). Push it: git -C $repo push origin $tag"
