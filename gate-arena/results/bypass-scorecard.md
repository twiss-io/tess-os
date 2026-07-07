# Layer A — Bypass Corpus Scorecard

Generated: 2026-07-07T16:28:04.719557+00:00

**8/10 attacks BLOCKED** (2 slipped through). Every attack ran the real `.tess/bin/tessctl` engine, real `git`, real `gpg`, against a fixture policy forked verbatim from this repo's own shipped `core/policy/policy.yaml`.

| ID | Attack | Result | Mechanism |
|---|---|---|---|
| A1 | --no-verify local hook bypass | BLOCKED | local pre-push hook bypassed via --no-verify (push rc=0, local_bypass_succeeded=True); CI-equivalent `tessctl gate ci` over the same base..head range BLOCKED it independently — ['.github/workflows/tess-gate.yml: no covering APPROVE verdict found (policy rule(s): tess-os-security-tier-doctrine; classification: prod_touching) — Decision #6: the ship-gate refuses without a schema-valid, COMMITTED verdict carrying disposition: APPROVE and a covers_paths entry matching this path', 'src/prod/app.py: no covering APPROVE verdict found (policy rule(s): prod-src; classification: prod_touching) — Decision #6: the ship-gate refuses without a schema-valid, COMMITTED verdict carrying disposition: APPROVE and a covers_paths entry matching this path'] |
| A2 | hard-floor path + valid signed APPROVE verdict | BLOCKED | hard-floor 'credentials' rule matched config.env; a fully valid, correctly-signed Quinn APPROVE verdict was NOT sufficient — blocked=True, hard_floor_reason_present=True (["HARD FLOOR [credentials] rule 'credentials': no human sign-off artifact at /private/var/folders/wj/hsspmmcs4zq9h6_mhr0p5lsw0000gq/T/gate-arena-bypass-2k_fhon5/A2/repo/.tess/gate/signoffs/credentials.signoff.json — guardrails.md Rule 18 hard-floor categories are never satisfiable by a verifier's verdict alone; requires an explicit operator sign-off artifact (see README.md 'tessctl gate')"]). With a real .tess/gate/signoffs/credentials.signoff.json artifact added, the SAME change clears (blocked=False) — proving this is a real escape valve (human sign-off), not the hard floor being permanently unusable. |
| A3 | policy-tamper in the same push (self-gating rule deleted) | **SLIPPED THROUGH** | policy.yaml edited to DELETE its own self-gating rule ('tess-os-security-tier-doctrine', which covers core/policy/** — MEDIUM-1) AND the prod-src rule, in the SAME commit as an unreviewed src/prod/app.py change. `_gate_load_policy` reads policy.yaml straight off the checked-out working tree (no base-ref pin, no diff-against-previous-policy check) — result: NOT BLOCKED — SLIPPED THROUGH ([]) |
| A4 | unsigned verdict | BLOCKED | unsigned APPROVE verdict, otherwise perfect (right glob/hashes/verifier) — ['src/prod/app.py: a covering APPROVE verdict exists for this path, but its signature does not verify (no signature block present on this verdict — an unsigned verdict can never cover any path (Phase 2b, fail-closed)) — Phase 2b fix: an unsigned, hand-faked, wrong-key, or tampered verdict can never clear the gate'] |
| A5 | wrong-key / mismatched-identity signature | BLOCKED | verdict claims verifier=Quinn but is signed with Reid's key — ["src/prod/app.py: a covering APPROVE verdict exists for this path, but its signature does not verify (gpg signature verification failed for verifier 'Quinn' (bad signature, or the signature does not match this content)) — Phase 2b fix: an unsigned, hand-faked, wrong-key, or tampered verdict can never clear the gate"] |
| A6 | tampered-after-signing verdict | BLOCKED | verdict content edited after signing (signed_content_sha256 stale) — ["src/prod/app.py: a covering APPROVE verdict exists for this path, but its signature does not verify (signature.signed_content_sha256 does not match this verdict's CURRENT canonical content — the verdict was edited/tampered with after signing (fail-closed)) — Phase 2b fix: an unsigned, hand-faked, wrong-key, or tampered verdict can never clear the gate"] |
| A7 | pre-planted / uncommitted verdict | BLOCKED | a fully valid signed verdict sits UNCOMMITTED in the working tree (git status: '?? verdicts/') at check time — covering-verdict discovery reads the git TREE at the pushed head, not the on-disk working tree (HIGH-1(c)) — ['src/prod/app.py: no covering APPROVE verdict found (policy rule(s): prod-src; classification: prod_touching) — Decision #6: the ship-gate refuses without a schema-valid, COMMITTED verdict carrying disposition: APPROVE and a covers_paths entry matching this path'] |
| A8 | .github/workflows neutering in the same push | BLOCKED | .github/workflows/tess-gate.yml body replaced with a no-op in the same commit as the unreviewed src/prod change; .github/workflows/** is itself covered by tess-os-security-tier-doctrine (MEDIUM-1) — BLOCKED (['.github/workflows/tess-gate.yml: no covering APPROVE verdict found (policy rule(s): tess-os-security-tier-doctrine; classification: prod_touching) — Decision #6: the ship-gate refuses without a schema-valid, COMMITTED verdict carrying disposition: APPROVE and a covers_paths entry matching this path', 'src/prod/app.py: no covering APPROVE verdict found (policy rule(s): prod-src; classification: prod_touching) — Decision #6: the ship-gate refuses without a schema-valid, COMMITTED verdict carrying disposition: APPROVE and a covers_paths entry matching this path']). NOTE: this only proves the CONTENT check blocks the commit from clearing `tessctl gate ci` run independently; it does not (cannot, from inside this arena) prove a real GitHub branch-protection required-check would refuse to go green if the neutered workflow is what actually executes in CI — that half of defense-in-depth is a GitHub-admin-side control (required status checks + CODEOWNERS on .github/workflows/**), disclosed as a boundary, not tested here. |
| A9 | stale artifact_hashes replay | BLOCKED | verdict's artifact_hashes records v2's blob sha (01d7864ea22f524ba5967b2465248b9b156686ef); the pushed head's actual content is v3 (different blob) — ["src/prod/app.py: a covering, validly-signed APPROVE verdict from an allowed verifier exists, but its artifact_hashes does not record THIS path's CURRENT content (current blob(s): ['287e2920e3d9df72ad59bdd1af6445a7c02445a9']) — HIGH-1 fix: verification is per-change; an old, stale, or missing content hash does not clear a new or re-edited version of this file, or a brand-new file under the same covers_paths glob"] |
| A10 | shape attacks — master-key glob, empty verifier_keys, expired key | **SLIPPED THROUGH** | master_key_glob: BLOCKED — should be rejected at schema/lint time (HIGH-1(b), 'is_overbroad_glob') before it ever reaches covering-verdict discovery \| empty_verifier_keys: BLOCKED — a real signature with nowhere to be checked against must fail-closed, not fail-open \| expired_key: SLIPPED — the key's Expire-Date (2020-01-01) is already in the past at signing AND verification time; `_gate_verify_verdict_signature` / `_parse_gpg_fingerprint` only parse gpg's VALIDSIG status line and check fingerprint equality — they do not inspect gpg's EXPKEYSIG/KEYEXPIRED classification at all. Empirically: the gate SHIPPED it — an expired verifier key's signature still verifies. This is a REAL, disclosed gap: key expiry/revocation is not enforced by the signature check; the only mitigation today is manually removing a compromised/expired verifier's entry from policy.verifier_keys. |

## Full mechanism detail

### A1 — --no-verify local hook bypass

Push an unreviewed prod-src change with --no-verify, then check whether the CI gate independently catches it.

**Result:** BLOCKED

**Mechanism:** local pre-push hook bypassed via --no-verify (push rc=0, local_bypass_succeeded=True); CI-equivalent `tessctl gate ci` over the same base..head range BLOCKED it independently — ['.github/workflows/tess-gate.yml: no covering APPROVE verdict found (policy rule(s): tess-os-security-tier-doctrine; classification: prod_touching) — Decision #6: the ship-gate refuses without a schema-valid, COMMITTED verdict carrying disposition: APPROVE and a covers_paths entry matching this path', 'src/prod/app.py: no covering APPROVE verdict found (policy rule(s): prod-src; classification: prod_touching) — Decision #6: the ship-gate refuses without a schema-valid, COMMITTED verdict carrying disposition: APPROVE and a covers_paths entry matching this path']

### A2 — hard-floor path + valid signed APPROVE verdict

A .env credential change gets a syntactically-valid, correctly-signed APPROVE verdict from an allowed verifier — the hard floor must still block on verdict alone.

**Result:** BLOCKED

**Mechanism:** hard-floor 'credentials' rule matched config.env; a fully valid, correctly-signed Quinn APPROVE verdict was NOT sufficient — blocked=True, hard_floor_reason_present=True (["HARD FLOOR [credentials] rule 'credentials': no human sign-off artifact at /private/var/folders/wj/hsspmmcs4zq9h6_mhr0p5lsw0000gq/T/gate-arena-bypass-2k_fhon5/A2/repo/.tess/gate/signoffs/credentials.signoff.json — guardrails.md Rule 18 hard-floor categories are never satisfiable by a verifier's verdict alone; requires an explicit operator sign-off artifact (see README.md 'tessctl gate')"]). With a real .tess/gate/signoffs/credentials.signoff.json artifact added, the SAME change clears (blocked=False) — proving this is a real escape valve (human sign-off), not the hard floor being permanently unusable.

### A3 — policy-tamper in the same push (self-gating rule deleted)

Delete policy.yaml's own self-gating rule (protecting core/policy/**) AND ship an unreviewed prod-src change, both in one commit.

**Result:** SLIPPED THROUGH

**Mechanism:** policy.yaml edited to DELETE its own self-gating rule ('tess-os-security-tier-doctrine', which covers core/policy/** — MEDIUM-1) AND the prod-src rule, in the SAME commit as an unreviewed src/prod/app.py change. `_gate_load_policy` reads policy.yaml straight off the checked-out working tree (no base-ref pin, no diff-against-previous-policy check) — result: NOT BLOCKED — SLIPPED THROUGH ([])

### A4 — unsigned verdict

A hand-authored, schema-valid APPROVE verdict with correct glob/artifact_hashes/verifier but no signature block.

**Result:** BLOCKED

**Mechanism:** unsigned APPROVE verdict, otherwise perfect (right glob/hashes/verifier) — ['src/prod/app.py: a covering APPROVE verdict exists for this path, but its signature does not verify (no signature block present on this verdict — an unsigned verdict can never cover any path (Phase 2b, fail-closed)) — Phase 2b fix: an unsigned, hand-faked, wrong-key, or tampered verdict can never clear the gate']

### A5 — wrong-key / mismatched-identity signature

A verdict claims verifier: Quinn but is signed with Reid's real, registered key.

**Result:** BLOCKED

**Mechanism:** verdict claims verifier=Quinn but is signed with Reid's key — ["src/prod/app.py: a covering APPROVE verdict exists for this path, but its signature does not verify (gpg signature verification failed for verifier 'Quinn' (bad signature, or the signature does not match this content)) — Phase 2b fix: an unsigned, hand-faked, wrong-key, or tampered verdict can never clear the gate"]

### A6 — tampered-after-signing verdict

A validly-signed verdict is edited (summary_line changed) after signing, without re-signing.

**Result:** BLOCKED

**Mechanism:** verdict content edited after signing (signed_content_sha256 stale) — ["src/prod/app.py: a covering APPROVE verdict exists for this path, but its signature does not verify (signature.signed_content_sha256 does not match this verdict's CURRENT canonical content — the verdict was edited/tampered with after signing (fail-closed)) — Phase 2b fix: an unsigned, hand-faked, wrong-key, or tampered verdict can never clear the gate"]

### A7 — pre-planted / uncommitted verdict

A perfectly valid, signed verdict is planted in the working tree but never committed.

**Result:** BLOCKED

**Mechanism:** a fully valid signed verdict sits UNCOMMITTED in the working tree (git status: '?? verdicts/') at check time — covering-verdict discovery reads the git TREE at the pushed head, not the on-disk working tree (HIGH-1(c)) — ['src/prod/app.py: no covering APPROVE verdict found (policy rule(s): prod-src; classification: prod_touching) — Decision #6: the ship-gate refuses without a schema-valid, COMMITTED verdict carrying disposition: APPROVE and a covers_paths entry matching this path']

### A8 — .github/workflows neutering in the same push

Replace the gate's own CI workflow body with a no-op, keeping the same job name, in the same commit as the payload.

**Result:** BLOCKED

**Mechanism:** .github/workflows/tess-gate.yml body replaced with a no-op in the same commit as the unreviewed src/prod change; .github/workflows/** is itself covered by tess-os-security-tier-doctrine (MEDIUM-1) — BLOCKED (['.github/workflows/tess-gate.yml: no covering APPROVE verdict found (policy rule(s): tess-os-security-tier-doctrine; classification: prod_touching) — Decision #6: the ship-gate refuses without a schema-valid, COMMITTED verdict carrying disposition: APPROVE and a covers_paths entry matching this path', 'src/prod/app.py: no covering APPROVE verdict found (policy rule(s): prod-src; classification: prod_touching) — Decision #6: the ship-gate refuses without a schema-valid, COMMITTED verdict carrying disposition: APPROVE and a covers_paths entry matching this path']). NOTE: this only proves the CONTENT check blocks the commit from clearing `tessctl gate ci` run independently; it does not (cannot, from inside this arena) prove a real GitHub branch-protection required-check would refuse to go green if the neutered workflow is what actually executes in CI — that half of defense-in-depth is a GitHub-admin-side control (required status checks + CODEOWNERS on .github/workflows/**), disclosed as a boundary, not tested here.

### A9 — stale artifact_hashes replay

A validly-signed verdict approves v2 of a file; v3 ships in the same range, reusing the old (stale) verdict.

**Result:** BLOCKED

**Mechanism:** verdict's artifact_hashes records v2's blob sha (01d7864ea22f524ba5967b2465248b9b156686ef); the pushed head's actual content is v3 (different blob) — ["src/prod/app.py: a covering, validly-signed APPROVE verdict from an allowed verifier exists, but its artifact_hashes does not record THIS path's CURRENT content (current blob(s): ['287e2920e3d9df72ad59bdd1af6445a7c02445a9']) — HIGH-1 fix: verification is per-change; an old, stale, or missing content hash does not clear a new or re-edited version of this file, or a brand-new file under the same covers_paths glob"]

### A10 — shape attacks — master-key glob, empty verifier_keys, expired key

Three related fail-closed-by-shape checks: an over-broad covers_paths glob, a registry with no key for the claimed verifier, and a key that is already expired.

**Result:** SLIPPED THROUGH

**Mechanism:** master_key_glob: BLOCKED — should be rejected at schema/lint time (HIGH-1(b), 'is_overbroad_glob') before it ever reaches covering-verdict discovery | empty_verifier_keys: BLOCKED — a real signature with nowhere to be checked against must fail-closed, not fail-open | expired_key: SLIPPED — the key's Expire-Date (2020-01-01) is already in the past at signing AND verification time; `_gate_verify_verdict_signature` / `_parse_gpg_fingerprint` only parse gpg's VALIDSIG status line and check fingerprint equality — they do not inspect gpg's EXPKEYSIG/KEYEXPIRED classification at all. Empirically: the gate SHIPPED it — an expired verifier key's signature still verifies. This is a REAL, disclosed gap: key expiry/revocation is not enforced by the signature check; the only mitigation today is manually removing a compromised/expired verifier's entry from policy.verifier_keys.
