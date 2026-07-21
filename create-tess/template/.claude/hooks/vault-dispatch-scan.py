#!/usr/bin/env python3
"""
vault-dispatch-scan.py — PreToolUse hook on ^(Task|Agent)$

Scans the dispatch prompt for secret-shaped values before the prompt reaches
a subagent's context. Defense-in-depth backstop (Cyra MUST-FIX c / §3.1).

IMPORTANT — HONEST ORDERING:
The REAL wall is the ref-only doctrine: conductors emit vault:// references,
never raw values. This hook is the backstop for accidents, not the primary
control. It cannot catch every secret (encoding, context, side-channels) and
MUST NOT be marketed as "blocks secrets."

Exit code 2 = block and tell Claude why.
Exit code 0 = allow (including on errors — fail-open per design; the wall is
doctrine, not this hook).

Patterns matched:
  - PEM private keys
  - GitHub tokens (ghp_/gho_/ghs_/ghr_/github_pat_)
  - Stripe live keys (sk_live_/pk_live_)
  - Slack tokens (xox[bpoa]-)
  - AWS access keys (AKIA...)
  - age private keys (AGE-SECRET-KEY-...)
  - Generic high-entropy tokens >=20 chars assigned to key/secret/token/password fields

This hook fires on EVERY Task|Agent dispatch, including inside subagents.
The dispatch-lock suppression in dispatch-guard.sh does NOT apply here — this
guard runs always (Cyra d: redactor must not inherit dispatch-lock suppression).

Design: conductor/vault.md (ref-only doctrine); tessctl VAULT SUBSYSTEM §3.1, §3.4, §6 Layer 3
"""

import json
import re
import sys

# Secret-shaped patterns (same set as VAULT_SECRET_PATTERNS in tessctl)
_PATTERNS = [
    (re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
     "PEM private key"),
    (re.compile(r"ghp_[A-Za-z0-9]{36,}"),
     "GitHub personal access token (ghp_)"),
    (re.compile(r"gho_[A-Za-z0-9]{36,}"),
     "GitHub OAuth token (gho_)"),
    (re.compile(r"ghs_[A-Za-z0-9]{36,}"),
     "GitHub server-to-server token (ghs_)"),
    (re.compile(r"ghr_[A-Za-z0-9]{36,}"),
     "GitHub refresh token (ghr_)"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{22,}"),
     "GitHub fine-grained PAT (github_pat_)"),
    (re.compile(r"sk_live_[A-Za-z0-9]{20,}"),
     "Stripe live secret key (sk_live_)"),
    (re.compile(r"pk_live_[A-Za-z0-9]{20,}"),
     "Stripe live publishable key (pk_live_)"),
    (re.compile(r"xox[bpoa]-[0-9A-Za-z-]{20,}"),
     "Slack token (xox[bpoa]-)"),
    (re.compile(r"AKIA[0-9A-Z]{16}"),
     "AWS access key (AKIA...)"),
    (re.compile(r"AGE-SECRET-KEY-[A-Z0-9]{50,}"),
     "age private identity key (AGE-SECRET-KEY-)"),
    # Generic: assignment of high-entropy value to a secret-named field
    (re.compile(r'(?:api[_-]?key|secret|password|token)\s*[=:]\s*["\']?[A-Za-z0-9+/=_\-\.]{20,}',
                re.IGNORECASE),
     "generic secret assignment (key/secret/token/password = <value>)"),
]


def _scan_text(text: str) -> list[str]:
    """Return list of human-readable match descriptions found in text."""
    hits = []
    seen_descs: set[str] = set()
    for pattern, desc in _PATTERNS:
        if desc in seen_descs:
            continue
        if pattern.search(text):
            hits.append(desc)
            seen_descs.add(desc)
    return hits


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        # Malformed input — fail open (do not block dispatch)
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    if tool_name not in ("Task", "Agent"):
        sys.exit(0)

    # Extract the dispatch prompt
    tool_input = data.get("tool_input", {})
    prompt = ""
    if isinstance(tool_input, dict):
        # Agent tool: prompt field
        prompt = tool_input.get("prompt", "") or ""
        # Task tool: description field
        if not prompt:
            prompt = tool_input.get("description", "") or ""
        # Fallback: stringify the whole input
        if not prompt:
            prompt = json.dumps(tool_input)

    if not prompt:
        sys.exit(0)

    hits = _scan_text(prompt)
    if not hits:
        sys.exit(0)

    # Block and report (exit 2 = block + inform Claude)
    hit_list = "\n".join(f"  - {h}" for h in hits)
    message = (
        f"VAULT DISPATCH SCAN — BLOCKED: secret-shaped value(s) detected in "
        f"the {tool_name} dispatch prompt:\n{hit_list}\n\n"
        f"The conductor MUST emit vault:// references (e.g. vault://github/token), "
        f"never raw secret values. The agent resolves the ref via:\n"
        f"  tessctl vault exec --ref github/token -- <command>\n\n"
        f"This scan is defense-in-depth — the real control is the ref-only doctrine "
        f"(conductor/vault.md).\n"
        f"Do NOT work around this hook by encoding or splitting values — "
        f"restructure the dispatch to use vault:// refs instead."
    )
    print(json.dumps({"decision": "block", "reason": message}))
    sys.exit(2)


if __name__ == "__main__":
    main()
