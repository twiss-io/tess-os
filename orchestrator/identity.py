"""Local approval identity: signing/verification primitives for the
DEFAULT `ApprovalGate` adapter (`adapters/local_identity.py`).

## The problem this exists to fix

Today, `spec_engine.approval.record_approval()` accepts `approved_by` as a
bare, caller-supplied string. ANY code path in the process can call
`record_approval(plan, approved_by="Xavier", approved=True)` and get back
a structurally-valid `Approval` that claims to be Xavier's decision — with
zero verification that a caller is who they say they are. That module is
correct that it never should decide whether a plan is good; the gap is
that nothing upstream of it ever authenticates the identity flowing into
`approved_by` either.

## What this module provides instead

A **local, non-forgeable approval identity**: a random 256-bit key,
generated once per OS account, stored at `~/.tess-os/approval-identity/
<username>.key` with file permissions restricted to that account
(`chmod 600` — enforced, not just requested; see `_enforce_key_permissions`).
`adapters/local_identity.py`'s `LocalIdentityApprovalGate` uses this key to
HMAC-sign every field of an `Approval` record (`approval_id`, `plan_id`,
`approved`, `approved_by`, `approved_at`, plus a fresh nonce) at the moment
a human confirms a decision. `approved_by` itself is derived from the OS
account (`getpass.getuser()`) — never accepted as a parameter a caller
could override — and the signature makes every field of the resulting
record tamper-evident: change any one of them after the fact and
`verify_signature()` fails.

This is deliberately NOT the same system as `.tess/bin/tessctl verdict`'s
GPG verifier-key registry (`core/policy/policy.yaml`'s `verifier_keys`).
That is the ship-gate's cryptographic identity system for signing mission
verdicts; this is a separate, unrelated, product-layer mechanism for
authenticating who approved a spec before code is generated from it. Do
not conflate the two, and do not point this module at `core/policy/**` or
`.tess/**` — it owns its own key material entirely outside the repo, under
the OS account's home directory.

## Honest limitation — read before treating this as production-grade

This proves "the process producing this signature had read access to this
OS account's local approval-identity key file, and something confirmed
the decision through this gate's own interactive/injected confirmation
step." It does **not**:

- prove which human was physically at the keyboard (any process running
  as that OS account can sign);
- survive a compromised OS account (whoever controls the account controls
  the key, same trust model as an SSH key or `~/.aws/credentials`);
- scale to multiple distinct human approvers sharing one OS account/CI
  runner (there is exactly one identity per OS account here, on purpose —
  a v1 scoping choice, not an oversight); or
- replace a real IdP (SSO/OAuth, WebAuthn, a verified Telegram user id
  bound to a bot's own auth, etc.) for a genuinely multi-user production
  deployment.

This is flagged as an open design question for Xavier in the PR body: a
production-grade adapter (Telegram, web, CLI-with-real-auth) implementing
`ApprovalGate` is the natural next step, and needs a per-human identity
mechanism, not a per-OS-account one.
"""

from __future__ import annotations

import getpass
import hashlib
import hmac
import json
import os
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Union

PathLike = Union[str, Path]

KEY_BYTES = 32
AUTH_MECHANISM = "local-hmac-sha256-v1"


def default_identity_dir() -> Path:
    """`~/.tess-os/approval-identity` — resolved LAZILY (at call time),
    never cached as a module-level constant. `Path.home()` reads `$HOME`
    (or the platform equivalent); a module-level constant would freeze
    that value at first import, which is both wrong in principle (this
    process's home directory shouldn't be pinned before anyone asked for
    it) and untestable (a test that monkeypatches `$HOME` after
    `orchestrator` has already been imported once elsewhere in the same
    test session would silently have no effect on an already-evaluated
    constant)."""
    return Path.home() / ".tess-os" / "approval-identity"


class IdentityError(ValueError):
    """Fail loud on any malformed identity/signing state — never silently
    treat a corrupt or over-permissive key as usable."""


@dataclass(frozen=True)
class LocalIdentity:
    """A resolved local approval identity. Deliberately carries no key
    material — only `key_path` (so callers can re-read fresh bytes when
    they actually need to sign/verify) and `fingerprint` (a public,
    non-secret `sha256(key)[:16]` hex digest safe to log, embed in an
    Approval's notes, or print to a terminal)."""

    username: str
    key_path: Path
    fingerprint: str


def _safe_username(username: str) -> str:
    # getpass.getuser() is OS-provided, but never trust any string as a raw
    # filesystem path component unexamined.
    cleaned = "".join(c for c in username if c.isalnum() or c in "._-")
    return cleaned or "unknown"


def _enforce_key_permissions(key_path: Path) -> None:
    """Fail loud if the key file is group/world-accessible — a key an
    attacker with local (non-owner) access could read is not proof of
    anything, so refuse to treat it as a non-forgeable identity."""
    mode = stat.S_IMODE(os.stat(key_path).st_mode)
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise IdentityError(
            f"approval identity key {key_path} is group/world-accessible "
            f"(mode {oct(mode)}) — refusing to use it as a non-forgeable "
            f"identity. Fix with: chmod 600 {key_path}"
        )


def _create_key(key_path: Path) -> None:
    key_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = secrets.token_bytes(KEY_BYTES)
    # Write, THEN restrict permissions — restricting after write (not
    # before) means there is never a window where a caller could beat us
    # to an fopen() on an already-existing-but-still-open-permissions file;
    # os.open with O_EXCL further ensures we never overwrite a key another
    # process just created concurrently (races to os.chmod harmlessly).
    fd = os.open(str(key_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, key)
    finally:
        os.close(fd)


def load_or_create_local_identity(identity_dir: Optional[PathLike] = None) -> LocalIdentity:
    """Resolve (creating on first use) THIS OS account's local approval
    identity. `username` is read from the OS via `getpass.getuser()` —
    never accepted as a parameter here, so a caller cannot ask this
    function to mint or resolve an identity for someone else."""
    resolved_dir = Path(identity_dir) if identity_dir is not None else default_identity_dir()
    username = getpass.getuser()
    key_path = resolved_dir / f"{_safe_username(username)}.key"
    if not key_path.exists():
        _create_key(key_path)
    key = read_current_key(key_path)
    fingerprint = hashlib.sha256(key).hexdigest()[:16]
    return LocalIdentity(username=username, key_path=key_path, fingerprint=fingerprint)


def read_current_key(key_path: Path) -> bytes:
    """Read the key fresh from disk every time (never cached on a
    long-lived object attribute) and re-validate its permissions on every
    read — catches a key that was rotated, deleted, or had its
    permissions loosened between signing and verifying."""
    if not key_path.is_file():
        raise IdentityError(f"approval identity key not found at {key_path}")
    _enforce_key_permissions(key_path)
    key = key_path.read_bytes()
    if len(key) != KEY_BYTES:
        raise IdentityError(f"approval identity key at {key_path} is corrupt (wrong length)")
    return key


def canonical_payload(
    *, approval_id: str, plan_id: str, approved: bool, approved_by: str, approved_at: str, nonce: str
) -> Dict[str, Any]:
    """The exact, complete field set that gets signed — binds the
    signature to EVERY identity-relevant field of the Approval record, so
    tampering with any one of them after signing is detectable by
    `verify_signature()`."""
    return {
        "approval_id": approval_id,
        "plan_id": plan_id,
        "approved": approved,
        "approved_by": approved_by,
        "approved_at": approved_at,
        "nonce": nonce,
    }


def sign_payload(key: bytes, payload: Dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(key, canonical, hashlib.sha256).hexdigest()


def verify_signature(key: bytes, payload: Dict[str, Any], signature: str) -> bool:
    """Constant-time comparison (`hmac.compare_digest`) — never a plain
    `==` on secret-derived material, to avoid a timing side-channel."""
    expected = sign_payload(key, payload)
    return hmac.compare_digest(expected, signature)


__all__ = [
    "AUTH_MECHANISM",
    "default_identity_dir",
    "KEY_BYTES",
    "IdentityError",
    "LocalIdentity",
    "load_or_create_local_identity",
    "read_current_key",
    "canonical_payload",
    "sign_payload",
    "verify_signature",
]
