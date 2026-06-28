#!/usr/bin/env bash
# Verify No Secrets Hook — Stop
# Checks staged git files for accidentally committed secrets.
# Runs when Claude finishes a turn — catches secrets before they're committed.
#
# Based on Claude Code Mastery Guides V1-V5 by TheDecipherist

# Only run if we're in a git repo
if ! git rev-parse --is-inside-work-tree &>/dev/null 2>&1; then
    exit 0
fi

# Check if there are staged files
STAGED=$(git diff --cached --name-only 2>/dev/null)
if [ -z "$STAGED" ]; then
    exit 0
fi

VIOLATIONS=""

# Check for sensitive files being staged (match basename only — anchored)
SENSITIVE_BASENAMES=".env .env.local .env.production .env.staging secrets.json credentials.json service-account.json .npmrc"
for pattern in $SENSITIVE_BASENAMES; do
    while IFS= read -r file; do
        basename=$(basename "$file")
        if [ "$basename" = "$pattern" ]; then
            VIOLATIONS="${VIOLATIONS}\n  - SENSITIVE FILE STAGED: $file"
        fi
    done <<< "$STAGED"
done

# Check for private key files (anchored to basename)
while IFS= read -r file; do
    basename=$(basename "$file")
    case "$basename" in
        id_rsa|id_ed25519|id_ecdsa|id_dsa|*.pem|*.key)
            VIOLATIONS="${VIOLATIONS}\n  - PRIVATE KEY FILE STAGED: $file"
            ;;
    esac
done <<< "$STAGED"

# Check staged file contents for common secret patterns
while IFS= read -r file; do
    if [ -f "$file" ]; then
        # Generic API key / secret / password / token patterns
        if grep -qEi '(api[_-]?key|secret[_-]?key|password|token)\s*[:=]\s*["\x27][A-Za-z0-9+/=_-]{16,}' "$file" 2>/dev/null; then
            VIOLATIONS="${VIOLATIONS}\n  - POSSIBLE SECRET in $file"
        fi
        # AWS access keys
        if grep -qE 'AKIA[0-9A-Z]{16}' "$file" 2>/dev/null; then
            VIOLATIONS="${VIOLATIONS}\n  - AWS ACCESS KEY in $file"
        fi
        # GitHub tokens (ghp_, gho_, ghs_, ghr_, github_pat_)
        if grep -qE '(ghp_[A-Za-z0-9]{36,}|gho_[A-Za-z0-9]{36,}|ghs_[A-Za-z0-9]{36,}|ghr_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})' "$file" 2>/dev/null; then
            VIOLATIONS="${VIOLATIONS}\n  - GITHUB TOKEN in $file"
        fi
        # Slack tokens
        if grep -qE '(xoxb-|xoxp-|xoxo-|xoxa-)[0-9A-Za-z-]{20,}' "$file" 2>/dev/null; then
            VIOLATIONS="${VIOLATIONS}\n  - SLACK TOKEN in $file"
        fi
        # Stripe keys
        if grep -qE '(sk_live_|pk_live_|rk_live_)[A-Za-z0-9]{20,}' "$file" 2>/dev/null; then
            VIOLATIONS="${VIOLATIONS}\n  - STRIPE KEY in $file"
        fi
        # PEM-format private keys
        if grep -qE '-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----' "$file" 2>/dev/null; then
            VIOLATIONS="${VIOLATIONS}\n  - PEM PRIVATE KEY in $file"
        fi
    fi
done <<< "$STAGED"

if [ -n "$VIOLATIONS" ]; then
    echo -e "⚠️  POTENTIAL SECRETS DETECTED:${VIOLATIONS}" >&2
    echo "" >&2
    echo "Review staged files before committing." >&2
    # Exit 2 = block and inform Claude
    exit 2
fi

exit 0
