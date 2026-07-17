# Layer A — Bypass Corpus Scorecard

Generated: 2026-07-17T09:45:32.863463+00:00

**12/12 attacks BLOCKED** (0 slipped through). Every attack ran the real `.tess/bin/tessctl` engine, real `git`, real `gpg`, against a fixture policy forked verbatim from this repo's own shipped `core/policy/policy.yaml`.

| ID | Attack | Result | Mechanism |
|---|---|---|---|
| A1 | --no-verify local hook bypass | BLOCKED | local pre-push hook bypassed via --no-verify (push rc=0, local_bypass_succeeded=True); CI-equivalent `tessctl gate ci` over the same base..head range BLOCKED it independently — ['COVERING_APPROVAL_MISSING: no covering APPROVE verdict found', 'COVERING_APPROVAL_MISSING: no covering APPROVE verdict found', 'COVERING_APPROVAL_MISSING: no covering APPROVE verdict found'] |
| A2 | hard-floor path + valid signed APPROVE verdict | BLOCKED | hard-floor 'credentials' rule matched config.env; a fully valid, correctly-signed Quinn APPROVE verdict was NOT sufficient — blocked=True, hard_floor_code_present=True (['HARD_FLOOR_UNSATISFIED: a required hard-floor sign-off is not valid']). With a real, cryptographically SIGNED schema-v2 signoff-only attestation (from a registered fixture-only policy.signoff_keys identity) bound to the exact payload, the SAME change clears (blocked=False) — proving this is a real escape valve (authenticated human sign-off), not the hard floor being permanently unusable. |
| A3 | policy-tamper in the same push (self-gating rule deleted) | BLOCKED | policy.yaml edited to DELETE its own self-gating rule ('tess-os-security-tier-doctrine', which covers core/policy/** — MEDIUM-1) AND the prod-src rule, in the SAME commit as an unreviewed src/prod/app.py change. `_gate_load_policy` reads policy.yaml straight off the checked-out working tree (no base-ref pin, no diff-against-previous-policy check) — result: BLOCKED (['COVERING_APPROVAL_MISSING: no covering APPROVE verdict found', 'COVERING_APPROVAL_MISSING: no covering APPROVE verdict found']) |
| A4 | unsigned verdict | BLOCKED | unsigned APPROVE verdict, otherwise perfect (right glob/hashes/verifier) — ['VERDICT_SIGNATURE_INVALID: a covering verdict signature is invalid'] |
| A5 | wrong-key / mismatched-identity signature | BLOCKED | verdict claims verifier=Quinn but is signed with Reid's key — ['VERDICT_SIGNATURE_INVALID: a covering verdict signature is invalid'] |
| A6 | tampered-after-signing verdict | BLOCKED | verdict content edited after signing (signed_content_sha256 stale) — ['VERDICT_SIGNATURE_INVALID: a covering verdict signature is invalid'] |
| A7 | pre-planted / uncommitted verdict | BLOCKED | a fully valid signed verdict sits UNCOMMITTED in the working tree (git status: '?? verdicts/') at check time — covering-verdict discovery reads the git TREE at the pushed head, not the on-disk working tree (HIGH-1(c)) — ['COVERING_APPROVAL_MISSING: no covering APPROVE verdict found'] |
| A8 | .github/workflows neutering in the same push | BLOCKED | .github/workflows/tess-gate.yml body replaced with a no-op in the same commit as the unreviewed src/prod change; .github/workflows/** is itself covered by tess-os-security-tier-doctrine (MEDIUM-1) — BLOCKED (['COVERING_APPROVAL_MISSING: no covering APPROVE verdict found', 'COVERING_APPROVAL_MISSING: no covering APPROVE verdict found']). NOTE: this only proves the CONTENT check blocks the commit from clearing `tessctl gate ci` run independently; it does not (cannot, from inside this arena) prove a real GitHub branch-protection required-check would refuse to go green if the neutered workflow is what actually executes in CI — that half of defense-in-depth is a GitHub-admin-side control (required status checks + CODEOWNERS on .github/workflows/**), disclosed as a boundary, not tested here. |
| A9 | stale artifact_hashes replay | BLOCKED | verdict's artifact_hashes records v2's blob sha (01d7864ea22f524ba5967b2465248b9b156686ef); the pushed head's actual content is v3 (different blob) — ['VERDICT_CONTENT_STALE: a covering verdict is not bound to current content'] |
| A10 | shape attacks — master-key glob, empty verifier_keys, expired key | BLOCKED | master_key_glob: BLOCKED — should be rejected at schema/lint time (HIGH-1(b), 'is_overbroad_glob') before it ever reaches covering-verdict discovery \| empty_verifier_keys: BLOCKED — a real signature with nowhere to be checked against must fail-closed, not fail-open \| expired_key: BLOCKED — the key's short (seconds=6) Expire-Date has genuinely elapsed by verification time (waited past the key's own recorded expiration epoch, not a fixed sleep); `_gate_verify_verdict_signature` inspects gpg's own EXPKEYSIG/REVKEYSIG status classification (`_gpg_signing_key_validity_reason`), checked at verification time, not signing time. Empirically: the gate BLOCKED it — an expired verifier key's signature is rejected fail-closed even though the crypto math and exact fingerprint both check out. |
| A11 | same-push engine tamper (honesty-capstone-audit-2026-07-08 §3-c) | BLOCKED | `.tess/bin/tessctl`'s `_gate_run_ship_check` edited to unconditionally return not-blocked, in the SAME commit as an unreviewed src/prod/app.py change. Naive execution (the pushed tree's OWN engine — exactly what the v2/unpatched CI workflow ran): NOT BLOCKED — slips past naively ({'phase': 'ci', 'blocked': False, 'reasons': [], 'changed_paths_count': 2, 'authoritative': False, 'diagnostic_only': True}). The REAL, committed .github/workflows/tess-gate.yml's own trusted-engine steps (v3 — extracts and runs the engine as it existed at the push's BASE ref, never the pushed tree's copy): BLOCKED ( external admission)   changed paths: 2     - ADMISSION_EVENT_SOURCE_REQUIRED: an authoritative admission event source is required     - COVERING_APPROVAL_MISSING: no covering APPROVE verdict found     - COVERING_APPROVAL_MISSING: no covering APPROVE verdict found   refusing (fail-closed) — see README.md 'tessctl gate', conductor/verification-routing.md, docs/ULTIMATE_FRAMEWORK_PLAN.md Decision #6) |
| A12 | hard-floor sign-off forgery (honesty-capstone-audit-2026-07-08 §3-d) | BLOCKED | credentials hard floor matched config.env. Forged, otherwise fully revision-bound v2 sign-off: blocked=True, hard_floor_code_present=True (['HARD_FLOOR_UNSATISFIED: a required hard-floor sign-off is not valid', 'COVERING_APPROVAL_MISSING: no covering APPROVE verdict found']). With the SAME sign-off cryptographically signed by a REAL, registered operator key in the fixture-only policy.signoff_keys and committed as the exact single-parent signoff-only child: blocked=False ([]) — proving the mechanism is a real, satisfiable escape valve once AUTHENTICATED, not a hard floor that is either permanently broken or permanently unusable. |

## Full mechanism detail

### A1 — --no-verify local hook bypass

Push an unreviewed prod-src change with --no-verify, then check whether the CI gate independently catches it.

**Result:** BLOCKED

**Mechanism:** local pre-push hook bypassed via --no-verify (push rc=0, local_bypass_succeeded=True); CI-equivalent `tessctl gate ci` over the same base..head range BLOCKED it independently — ['COVERING_APPROVAL_MISSING: no covering APPROVE verdict found', 'COVERING_APPROVAL_MISSING: no covering APPROVE verdict found', 'COVERING_APPROVAL_MISSING: no covering APPROVE verdict found']

### A2 — hard-floor path + valid signed APPROVE verdict

A .env credential change gets a syntactically-valid, correctly-signed APPROVE verdict from an allowed verifier — the hard floor must still block on verdict alone.

**Result:** BLOCKED

**Mechanism:** hard-floor 'credentials' rule matched config.env; a fully valid, correctly-signed Quinn APPROVE verdict was NOT sufficient — blocked=True, hard_floor_code_present=True (['HARD_FLOOR_UNSATISFIED: a required hard-floor sign-off is not valid']). With a real, cryptographically SIGNED schema-v2 signoff-only attestation (from a registered fixture-only policy.signoff_keys identity) bound to the exact payload, the SAME change clears (blocked=False) — proving this is a real escape valve (authenticated human sign-off), not the hard floor being permanently unusable.

### A3 — policy-tamper in the same push (self-gating rule deleted)

Delete policy.yaml's own self-gating rule (protecting core/policy/**) AND ship an unreviewed prod-src change, both in one commit.

**Result:** BLOCKED

**Mechanism:** policy.yaml edited to DELETE its own self-gating rule ('tess-os-security-tier-doctrine', which covers core/policy/** — MEDIUM-1) AND the prod-src rule, in the SAME commit as an unreviewed src/prod/app.py change. `_gate_load_policy` reads policy.yaml straight off the checked-out working tree (no base-ref pin, no diff-against-previous-policy check) — result: BLOCKED (['COVERING_APPROVAL_MISSING: no covering APPROVE verdict found', 'COVERING_APPROVAL_MISSING: no covering APPROVE verdict found'])

### A4 — unsigned verdict

A hand-authored, schema-valid APPROVE verdict with correct glob/artifact_hashes/verifier but no signature block.

**Result:** BLOCKED

**Mechanism:** unsigned APPROVE verdict, otherwise perfect (right glob/hashes/verifier) — ['VERDICT_SIGNATURE_INVALID: a covering verdict signature is invalid']

### A5 — wrong-key / mismatched-identity signature

A verdict claims verifier: Quinn but is signed with Reid's real, registered key.

**Result:** BLOCKED

**Mechanism:** verdict claims verifier=Quinn but is signed with Reid's key — ['VERDICT_SIGNATURE_INVALID: a covering verdict signature is invalid']

### A6 — tampered-after-signing verdict

A validly-signed verdict is edited (summary_line changed) after signing, without re-signing.

**Result:** BLOCKED

**Mechanism:** verdict content edited after signing (signed_content_sha256 stale) — ['VERDICT_SIGNATURE_INVALID: a covering verdict signature is invalid']

### A7 — pre-planted / uncommitted verdict

A perfectly valid, signed verdict is planted in the working tree but never committed.

**Result:** BLOCKED

**Mechanism:** a fully valid signed verdict sits UNCOMMITTED in the working tree (git status: '?? verdicts/') at check time — covering-verdict discovery reads the git TREE at the pushed head, not the on-disk working tree (HIGH-1(c)) — ['COVERING_APPROVAL_MISSING: no covering APPROVE verdict found']

### A8 — .github/workflows neutering in the same push

Replace the gate's own CI workflow body with a no-op, keeping the same job name, in the same commit as the payload.

**Result:** BLOCKED

**Mechanism:** .github/workflows/tess-gate.yml body replaced with a no-op in the same commit as the unreviewed src/prod change; .github/workflows/** is itself covered by tess-os-security-tier-doctrine (MEDIUM-1) — BLOCKED (['COVERING_APPROVAL_MISSING: no covering APPROVE verdict found', 'COVERING_APPROVAL_MISSING: no covering APPROVE verdict found']). NOTE: this only proves the CONTENT check blocks the commit from clearing `tessctl gate ci` run independently; it does not (cannot, from inside this arena) prove a real GitHub branch-protection required-check would refuse to go green if the neutered workflow is what actually executes in CI — that half of defense-in-depth is a GitHub-admin-side control (required status checks + CODEOWNERS on .github/workflows/**), disclosed as a boundary, not tested here.

### A9 — stale artifact_hashes replay

A validly-signed verdict approves v2 of a file; v3 ships in the same range, reusing the old (stale) verdict.

**Result:** BLOCKED

**Mechanism:** verdict's artifact_hashes records v2's blob sha (01d7864ea22f524ba5967b2465248b9b156686ef); the pushed head's actual content is v3 (different blob) — ['VERDICT_CONTENT_STALE: a covering verdict is not bound to current content']

### A10 — shape attacks — master-key glob, empty verifier_keys, expired key

Three related fail-closed-by-shape checks: an over-broad covers_paths glob, a registry with no key for the claimed verifier, and a key that is already expired.

**Result:** BLOCKED

**Mechanism:** master_key_glob: BLOCKED — should be rejected at schema/lint time (HIGH-1(b), 'is_overbroad_glob') before it ever reaches covering-verdict discovery | empty_verifier_keys: BLOCKED — a real signature with nowhere to be checked against must fail-closed, not fail-open | expired_key: BLOCKED — the key's short (seconds=6) Expire-Date has genuinely elapsed by verification time (waited past the key's own recorded expiration epoch, not a fixed sleep); `_gate_verify_verdict_signature` inspects gpg's own EXPKEYSIG/REVKEYSIG status classification (`_gpg_signing_key_validity_reason`), checked at verification time, not signing time. Empirically: the gate BLOCKED it — an expired verifier key's signature is rejected fail-closed even though the crypto math and exact fingerprint both check out.

### A11 — same-push engine tamper (honesty-capstone-audit-2026-07-08 §3-c)

Edit the gate engine's own decision logic (_gate_run_ship_check) to self-attest 'not blocked', in the same push as an unreviewed payload — does the REAL CI workflow's trusted-engine defense still catch it?

**Result:** BLOCKED

**Mechanism:** `.tess/bin/tessctl`'s `_gate_run_ship_check` edited to unconditionally return not-blocked, in the SAME commit as an unreviewed src/prod/app.py change. Naive execution (the pushed tree's OWN engine — exactly what the v2/unpatched CI workflow ran): NOT BLOCKED — slips past naively ({'phase': 'ci', 'blocked': False, 'reasons': [], 'changed_paths_count': 2, 'authoritative': False, 'diagnostic_only': True}). The REAL, committed .github/workflows/tess-gate.yml's own trusted-engine steps (v3 — extracts and runs the engine as it existed at the push's BASE ref, never the pushed tree's copy): BLOCKED ( external admission)
  changed paths: 2
    - ADMISSION_EVENT_SOURCE_REQUIRED: an authoritative admission event source is required
    - COVERING_APPROVAL_MISSING: no covering APPROVE verdict found
    - COVERING_APPROVAL_MISSING: no covering APPROVE verdict found
  refusing (fail-closed) — see README.md 'tessctl gate', conductor/verification-routing.md, docs/ULTIMATE_FRAMEWORK_PLAN.md Decision #6)

### A12 — hard-floor sign-off forgery (honesty-capstone-audit-2026-07-08 §3-d)

A forged, otherwise fully revision-bound v2 sign-off (forgeable by any agent able to write a file) must NOT clear a hard floor; the same sign-off, cryptographically signed by a registered operator key, must.

**Result:** BLOCKED

**Mechanism:** credentials hard floor matched config.env. Forged, otherwise fully revision-bound v2 sign-off: blocked=True, hard_floor_code_present=True (['HARD_FLOOR_UNSATISFIED: a required hard-floor sign-off is not valid', 'COVERING_APPROVAL_MISSING: no covering APPROVE verdict found']). With the SAME sign-off cryptographically signed by a REAL, registered operator key in the fixture-only policy.signoff_keys and committed as the exact single-parent signoff-only child: blocked=False ([]) — proving the mechanism is a real, satisfiable escape valve once AUTHENTICATED, not a hard floor that is either permanently broken or permanently unusable.
