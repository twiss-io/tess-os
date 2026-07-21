### The Ship-Gate

A push touching a path matched by a `require_verdict` rule in `core/policy/policy.yaml` is blocked at pre-push/CI without a signed APPROVE verdict from an allowed verifier ([conductor/verification-routing.md](conductor/verification-routing.md)). The four hard-floor categories above are never satisfiable by a verdict alone — they additionally require a human sign-off artifact at `.tess/gate/signoffs/<id>.signoff.json`.

**You cannot clear your own work.** Do not author, edit, or sign verdict files; do not touch `core/policy/`, `.github/workflows/tess-gate.yml`, `.tess/keys/verifiers/**`, or `.tess/gate/signoffs/` — the gate treats any of that as tamper and fails closed. Finish the change, state what needs review, and stop. Check status any time with `tessctl gate pre-push` or `tessctl doctor`.
