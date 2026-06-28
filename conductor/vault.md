# Vault — Ref-Only Doctrine

**Primary control for secret safety in the Tess OS vault subsystem.**

---

## The Rule

Conductors emit `vault://` references. They NEVER emit raw secret values.

```
CORRECT:   vault://github/token
INCORRECT: ghp_ABCdef...XYZ (the actual token)
```

A `vault://` reference is a safe, opaque pointer. The raw value never enters
a subagent prompt, dispatch transcript, or log. This is the primary wall
against credential leakage — not the dispatch scan hook (which is backstop only).

---

## How Agents Resolve a Ref

An agent that needs a secret uses `tessctl vault exec`:

```bash
tessctl vault exec --ref github/token -- gh pr create ...
tessctl vault exec --ref anthropic/api_key --as ANTHROPIC_API_KEY -- python3 run.py
```

The value is decrypted JIT, injected into the child environment only, and is
never captured by tessctl's stdout or stderr. The agent process exits; the
value is gone from memory.

---

## Dispatch Brief Pattern

When dispatching an agent that needs a credential, the brief must name
the ref, not the value:

```
# CORRECT dispatch brief excerpt
CREDENTIAL: vault://github/token  (resolve via: tessctl vault exec --ref github/token -- <cmd>)

# INCORRECT — never do this
CREDENTIAL: ghp_ABCdef123...
```

If a raw value appears in a dispatch prompt, the `vault-dispatch-scan.py`
hook (`.claude/hooks/`) will block the dispatch and tell Claude why. Work
around: restructure the prompt to use a `vault://` ref instead.

---

## Vault Command Reference

| Command | Purpose |
|---|---|
| `tessctl vault init` | Initialise vault (generate identity, create blob) |
| `tessctl vault set <ref>` | Store a secret (stdin or TTY prompt — never argv) |
| `tessctl vault get <ref>` | Display masked value (add `--reveal` for raw, pipe only) |
| `tessctl vault list` | List all refs (no values shown) |
| `tessctl vault exec --ref <ref> -- <cmd>` | Inject secret into child env JIT |
| `tessctl vault rotate <ref>` | Re-encrypt under a new value |
| `tessctl vault rm <ref>` | Delete a ref from the vault |
| `tessctl vault doctor` | Audit vault health (perms, gitignore, hooks) |

---

## Why Refs, Not Values

The vault is encrypted at rest (`vault.age` — age X25519, 0600). The identity
key never appears in logs, snapshots, or dispatches. But encryption at rest
only protects against disk reads — it does not help if a plaintext value is
pasted into an agent's context window.

The ref-only doctrine is the behavioural complement to the cryptographic layer.
Together they ensure the value is decrypted in exactly one place (the child
process env) and at exactly one time (execution, not dispatch).

---

## What the Dispatch Scan Hook Does (and Does Not Do)

`vault-dispatch-scan.py` is wired as a `PreToolUse` hook on `Task|Agent` tools.
It scans dispatch prompts for secret-shaped patterns (GitHub tokens, Stripe keys,
age private keys, AWS access keys, PEM blocks, generic high-entropy assignments).

- Exit 2 = blocked. Claude is told why and how to fix.
- Exit 0 = allowed. The hook is fail-open by design.

The hook is **defense-in-depth** — a backstop for accidents. It cannot catch
every encoding or obfuscation. The real wall is this doctrine: emit refs, not values.

---

## Vault Architecture

See `tessctl` source (`.tess/bin/tessctl`, `VAULT SUBSYSTEM` section starting
around line 4592) for the full implementation: crypto backend detection,
identity custody (env → keychain → file), blob I/O, hard-guard tier.

The vault registry catalog (no values, safe to commit) is at:
`.claude/vault/vault.registry.json`
