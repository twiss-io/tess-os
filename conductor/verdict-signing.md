# Verdict Signing — Phase 2b (Gate Spine Hardening)

> Closes the Fable Phase-2 adversarial-review residual: "verdict + sign-off
> files are committer-authored with NO signing — a weak/malicious agent
> could hand-write a fake `disposition: APPROVE` verdict to clear its own
> gate." Stacked on Phase 2 (`docs/ULTIMATE_FRAMEWORK_PLAN.md` Design
> Decisions #2/#6 — see `README.md`'s `tessctl gate` section and
> `core/contracts/README.md`).

---

## What changed

Before Phase 2b, a covering verdict meant: *a schema-valid, COMMITTED file
carries `disposition: APPROVE`, a `covers_paths` glob matching the changed
path, a `verifier` name in the matched rule's `allowed_verifiers`, and an
`artifact_hashes` entry matching the path's current git blob SHA.* Every one
of those fields was a plain, unauthenticated string or value a committer who
controls their own branch could hand-author — including the `verifier` name
itself. `README.md`'s own "Trust boundary" disclosure said this plainly:
*"a committer who controls their own branch can hand-author any verdict
content, including a false `verifier` name."*

After Phase 2b, a covering verdict means: **the right verifier
cryptographically signed off on this exact reviewed change.** Concretely, a
verdict must ALSO carry a `signature` block
(`core/contracts/verdict.schema.json` `$defs.VerdictSignature`) that:

1. Is a detached GPG signature over the verdict's **canonical content**
   (`tessctl`'s `verdict_canonical_bytes()` — the instance minus the
   `signature` key itself, serialized as compact, key-sorted JSON so the
   canonical form is a pure function of the data, independent of whether
   the verdict is authored as JSON, YAML, or markdown front-matter).
2. Verifies against the **registered public key** for the verdict's claimed
   `verifier`, in `core/policy/policy.yaml`'s `policy.verifier_keys` map
   (the ALLOWED-KEY SET).
3. Was made by a key whose fingerprint **exactly matches** the registered
   fingerprint (C3 — no short-ID or proximity matching, same discipline
   `framework.trusted_key_fingerprint` already applies to release-tag
   pinning).
4. Has a `signed_content_sha256` that still matches the verdict's CURRENT
   canonical content (tamper detection — checked before the more expensive
   GPG call).

`tessctl gate`'s covering-verdict check now requires this SIGNATURE check
in addition to (not instead of) the Phase 2 checks: glob match,
`allowed_verifiers` membership, and content-hash freshness. Signing ties to
`allowed_verifiers` — a valid signature from a REAL, registered verifier who
is simply not permitted for the matched rule still does not clear it (see
the "wrong-verifier" test cases below). Together: **a covering verdict now
means the right verifier, cryptographically authenticated, signed off on
the exact content being shipped — not just that a file exists claiming so.**

An unsigned verdict, a malformed signature block, a signature from an
unregistered verifier, a signature made by the wrong key, or a verdict
edited after signing (tamper) are all treated identically to "no covering
verdict at all" — **fail-closed**, the same posture `covers_paths` and
`artifact_hashes` already established.

---

## Why this reuses the keystone signing primitives, not a new scheme

`tessctl` already ships a signed-update trust bootstrap for framework
upgrades (`release-process.md`): a GPG-signed annotated git tag, verified
via `git verify-tag --raw` inside an **isolated GNUPGHOME** seeded with
exactly the pinned key, checked against `framework.trusted_key_fingerprint`
in `tess.lock` with exact (not prefix) fingerprint equality.

Verdict signing reuses the SAME primitives:

- The same `_parse_gpg_fingerprint()` parser (machine-readable `VALIDSIG`
  and human-readable `using ... key` fallback).
- The same isolated-GNUPGHOME-per-check pattern (`_gpg_verify_detached_signature`
  mirrors `_verify_tag_secure`'s structure), so a verdict-signature check
  never pollutes or depends on the ambient/system GPG keyring.
- The same exact-40-hex-fingerprint discipline (`_FULL_FP_RE`), no
  short-ID/proximity matching, applied to `policy.verifier_keys[verifier].fingerprint`
  exactly like `framework.trusted_key_fingerprint`.
- The same "public key bundled in the repo" convention
  `.tess/keys/twiss-release-key.asc` already established — extended
  per-verifier at `.tess/keys/verifiers/<name>.asc`.

**One deliberate difference:** release-tag verification requires the
operator to `gpg --import key.asc` into their OWN ambient keyring first — a
genuine bootstrapping requirement, since a fresh clone must not yet trust
anything in the repo it just cloned. Verdict-signature verification instead
imports the registered verifier's public key **straight from the repo's own
`.tess/keys/verifiers/<name>.asc` file** into a fresh, isolated GNUPGHOME
per check — no ambient keyring dependency, so CI needs no manual import
step. This is safe specifically because, by the time a verdict is being
checked, the gate already trusts the checked-out tree enough to read
`core/policy/policy.yaml` — and `.tess/keys/verifiers/**` is itself gated as
`prod_touching` under this repo's own `tess-os-security-tier-doctrine`
policy rule, so tampering with the key registry requires its own covering
Reid/Cyra verdict (closing the "who guards the key registry" loop).

---

## Key management

### Where keys live

| What | Where |
|---|---|
| A verifier's PUBLIC key (bundled, committed) | `.tess/keys/verifiers/<name-lowercase>.asc` |
| The ALLOWED-KEY SET (fingerprint + path registration) | `core/policy/policy.yaml`'s `policy.verifier_keys.<Name>` |
| A verifier's PRIVATE key | The verifier's own custody ONLY — never committed, same posture `release-process.md` already documents for the release signing key |

### Onboarding a verifier

**Turnkey path (recommended — `tessctl verdict keygen`, added to close the
"cannot turn the gate on without manual GPG surgery" adoption gap; full
walkthrough: `docs/GATE_QUICKSTART.md`):**

```bash
tessctl verdict keygen --verifier Reid
```

Does steps 1–3 below in one command: generates a fresh, sign-only, local
GPG identity for the named verifier; exports the PUBLIC half to
`.tess/keys/verifiers/<name>.asc`; registers `{fingerprint,
public_key_file}` under `policy.verifier_keys.<Name>` in BOTH
`core/policy/policy.yaml` and the `.tess/core/policy/policy.yaml` pristine
mirror (a comment-preserving text patch — `policy.yaml`'s own extensive
header documentation is never lost); re-pins the one `tess.lock` entry this
touches (scoped — never blesses any OTHER core file's drift/tamper as a side
effect, unlike an unscoped `tessctl lock --regen`). Idempotent: refuses to
clobber an existing key/registration for that verifier without `--force`
(which generates a NEW keypair and REPLACES both — a manual key rotation,
automated). tessctl never stores or transmits the resulting PRIVATE
key — it lives solely in the local GPG keyring (ambient, or `--gnupg-home`),
exactly as if the verifier had run `gpg --full-gen-key` themselves. Step 4
below still applies regardless of which path generated the key.

**Manual path (an already-existing keypair, or full control over key
parameters):**

1. The verifier generates their own GPG keypair (private key never leaves
   their custody).
2. Export the public half and commit it:
   `gpg --export --armor <fingerprint> > .tess/keys/verifiers/<name>.asc`
3. Register it in `core/policy/policy.yaml`:
   ```yaml
   verifier_keys:
     Reid:
       fingerprint: "<the exact 40-hex fingerprint>"
       public_key_file: .tess/keys/verifiers/reid.asc
   ```

**Either path, then:**

4. That change to `core/policy/policy.yaml` is itself `prod_touching`
   (`tess-os-security-tier-doctrine`) and needs its own covering, signed
   Reid/Cyra verdict before it ships — the key registry cannot bootstrap
   itself around the gate it participates in.
5. The verifier signs their own verdicts going forward:
   `tessctl verdict sign <file> --verifier <Name> --key-id <fingerprint>`

### `tessctl verdict sign` / `tessctl verdict verify`

```bash
# Sign a verdict's canonical content with your own GPG key.
tessctl verdict sign missions/m1/verdicts/prod-src.verdict.md \
  --verifier Reid --key-id <your-fingerprint>

# Independently check a verdict's signature (without running the full gate).
tessctl verdict verify missions/m1/verdicts/prod-src.verdict.md
```

`sign` writes a `signature` block back into the file, preserving its
original format (`.json` / `.yaml` / `.md` front-matter). `--verifier`, if
given, must match the file's own `verifier:` field — a Reid-keyed signer
cannot casually sign a verdict claiming to be a different verifier (a
fail-fast sanity check for the SIGNER; the real security boundary is at
VERIFY time, where the signing key's fingerprint must match the CLAIMED
verifier's registered key).

### Currently registered (this repo)

`core/policy/policy.yaml` ships `verifier_keys: {}` — **deliberately
empty**, not an oversight. See that file's own comment block: until Reid's
and Cyra's real signing keys are generated and registered, this repo's own
`tess-os-security-tier-doctrine` rule (which already names them as
`allowed_verifiers`) is unsatisfiable by ANY verdict — fail-closed, not a
silent bypass, and a disclosed, deferred maintainer follow-up (this PR
builds and tests the mechanism; it does not fabricate a throwaway "Reid"
identity that could be mistaken for a real trust anchor).

---

## Trust model — honest disclosure

**What this closes:** hand-authoring a verdict file with a fabricated
`disposition: APPROVE` and a plausible-looking `verifier` name no longer
clears the gate. The `verifier` field is now a claim that must be backed by
a cryptographic signature from that verifier's registered key — an
unsigned, hand-faked, wrong-key, or tampered verdict is rejected,
fail-closed, before it ever reaches the `allowed_verifiers` or
`artifact_hashes` checks.

**What remains the boundary — key custody, not the mechanism:** whoever
holds a verifier's PRIVATE key can sign as that verifier. This is the same
boundary every signature scheme has (including this repo's own release-tag
signing). If a verifier's private key is compromised or shared, their
signature no longer means what it claims to. `tessctl` never generates,
stores, or has access to a verifier's private key — it is entirely the
verifier's own custody responsibility, exactly like the release signing key
(`release-process.md`: "must stay on the maintainer's machine only").

**What this does NOT do:** it does not prove a specific HUMAN (as opposed
to whichever process holds the key) reviewed the content, and it does not
prevent a verifier from signing off on a review they did not actually
perform carefully — it proves the signature is genuinely theirs, not that
their review was rigorous. Combined with HIGH-1's diff-binding
(`artifact_hashes`), it does prove: the exact content being shipped is what
a specific, key-holding identity cryptographically attested to, not a
different or later-edited version.

**Git hooks remain locally bypassable** (`git push --no-verify`) — this was
already true and unaffected by signing; `tessctl gate ci` (see below) is
the harness-independent backstop for exactly that reason.

---

## CI auto-enforce

`.github/workflows/tess-gate.yml` (installed/upgraded by
`tessctl gate install-hooks`) now triggers on `push` (to protected
branches) and `pull_request`, in addition to `workflow_dispatch` (kept for
ad hoc/manual re-checks of an arbitrary ref range). Before Phase 2b, this
workflow shipped `workflow_dispatch`-only — advisory, never run unless
someone remembered to trigger it by hand. Now the ship-gate runs
automatically on every push/PR and BLOCKS the check on a fail-closed
result.

### Making it actually block a merge — branch protection

A CI check that runs automatically is still only **advisory** until it is
configured as a **required status check** — GitHub does not block a merge
on a failing check unless branch protection says so. To make the ship-gate
load-bearing:

1. Repo Settings → Branches → Branch protection rules → (rule for the
   protected branch, e.g. `main`).
2. Enable "Require status checks to pass before merging."
3. Add the required check by its **job name**: `tessctl gate ci` (the
   `jobs.ship-gate.name` field in `tess-gate.yml` — NOT the workflow's
   top-level `name: Tess OS ship-gate`, which is only a grouping label in
   the GitHub UI).
4. Optionally enable "Require branches to be up to date before merging" so
   the check runs against the actual merge result, not a stale base.

This step is **not automated by this change** — it is a repo-admin action
(branch protection settings), out of scope for a code PR to perform
unilaterally, and is called out here so it is not silently skipped.

### Defense-in-depth — gating the gate's own workflow file

A required check enforced **only** by its job name (`tessctl gate ci`, per
step 3 above) has a well-known hole: GitHub verifies that a check with that
*name* passed, not that the workflow file which produced it still does what
it claims to. A PR could keep the required check name intact while
neutering its step — e.g. replacing the `tessctl gate ci` run in
`.github/workflows/tess-gate.yml` with `exit 0` — **in the same PR**, and
branch protection would see a green "tessctl gate ci" and allow the merge.
This is the universal GitHub self-gating trap: a required check can never
fully protect its own definition through the required-check mechanism
alone.

MEDIUM-1 (Fable Phase-2b follow-up review) closes the mechanical half of
this: `.github/workflows/**` is now itself a glob under
`tess-os-security-tier-doctrine` in `core/policy/policy.yaml`, so any change
to `tess-gate.yml` (or any other workflow file) is `prod_touching` and needs
its own covering, signed Reid/Cyra verdict before `tessctl gate` will clear
it — the same content-level control that already protects
`conductor/guardrails.md`, `core/policy/**`, and `.tess/keys/verifiers/**`.

That control is still a **content** check run by `tessctl gate` itself —
which is exactly the workflow whose integrity is in question. As
**belt-and-suspenders**, add an independent, GitHub-native control that does
not depend on the gate at all:

1. **CODEOWNERS.** Add an entry to `.github/CODEOWNERS` (create the file if
   it does not exist) requiring a specific reviewer/team on any change under
   the gate's own surface:
   ```
   /.github/workflows/  @<maintainer-or-security-team>
   /core/policy/         @<maintainer-or-security-team>
   /.tess/keys/verifiers/ @<maintainer-or-security-team>
   ```
2. **Branch protection ruleset.** In the same branch protection rule from
   the previous section, enable "Require review from Code Owners" so the
   CODEOWNERS entry above is actually enforced, not just documentary.
3. Optionally, use a repo **ruleset** (Settings → Rules → Rulesets) with a
   "Restrict file paths" / required-reviewers condition scoped to
   `.github/workflows/**` for organizations on a plan that supports path-
   scoped rulesets, as an additional layer beyond CODEOWNERS.

This is a **repo-admin action**, like branch protection itself — not
automated by this change, and called out here so it is not silently
skipped. Two independent controls (a signed content verdict AND a
GitHub-native required-reviewer gate) mean an attacker must defeat both to
silently neuter the gate's own CI entrypoint, not just one.

### Bootstrap warning for a fresh adopter

If a project's `core/policy/policy.yaml` rules already have real
(non-placeholder) globs but no covering, validly-signed APPROVE verdict yet
exists for the paths they match, the FIRST push/PR touching those paths
**will be blocked** — this is the gate working as designed (fail-closed),
not a bug. `tess-gate.yml`'s own header comment documents the grace-period
option (temporarily drop the `push`/`pull_request` triggers, keep
`workflow_dispatch`, until at least one real, signed covering verdict
exists per rule).

---

## Deferred / out of scope for this change

- **Real Reid/Cyra signing keys for this repo.** Disclosed above — a
  maintainer private-key-custody decision, not fabricated here.
- **Branch protection configuration.** A repo-admin action; documented
  above, not performed by this PR.
- **Key rotation / revocation.** No revocation mechanism exists yet (mirrors
  the release-key trust model, which also has none — see
  `release-process.md`). A compromised verifier key today requires manually
  editing `core/policy/policy.yaml` to remove/replace the entry (itself
  gated as `prod_touching`).
- **Signature expiry.** `signature.signed_at` is documentary only; this
  scheme has no notion of an expiring signature.

---

## See also

- `README.md` — `tessctl gate` section (updated trust-boundary disclosure)
  and CHANGELOG.md.
- `core/contracts/README.md` — contract schema table (verdict.schema.json /
  policy.schema.json rows).
- `release-process.md` — the release-signing trust model this reuses.
- `core/policy/policy.yaml` — the actual `verifier_keys` registration point
  for this repo.
- `.tess/keys/verifiers/README.md` — what goes in that directory and what
  never does.
