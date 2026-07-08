# Ship-Gate Quickstart

Tess OS's flagship control is a **cryptographically-signed, fail-closed
ship-gate**: `tessctl gate` refuses to let a `prod_touching` / `client_facing`
/ `externally_visible` change ship without a COMMITTED, schema-valid,
`disposition: APPROVE` verdict, signed by a real, registered verifier's GPG
key, that covers the exact content being pushed. Full mechanism and trust
model: `README.md`'s "`tessctl gate` — the enforcement spine" section and
`conductor/verdict-signing.md`.

Out of the box, the gate ships **inert on purpose** —
`core/policy/policy.yaml`'s `verifier_keys: {}` is deliberately empty (see
that file's own header) so no throwaway "Reid" identity is ever fabricated as
a stand-in for a real trust anchor. That honesty has a cost: a fresh adopter
had no mechanical path from "I want a real verifier" to a registered signing
key short of hand-running `gpg --full-gen-key`, `gpg --export`, and editing
**two** copies of `policy.yaml` (the live one and the `.tess/core` pristine
mirror) without tripping `tessctl doctor`/`verify`/`lock --check`.

This walkthrough turns the gate on, end to end, in one sitting:
`tessctl init` → `tessctl verdict keygen` → add a real rule → install the git
hooks → cover the framework's own pre-existing doctrine surface (the
"bootstrap warning" below) → watch an uncovered prod change get **BLOCKED**
→ write and sign a covering verdict → watch the same change get **CLEARED**.

Every command below is runnable verbatim, in order, from the root of a
Tess OS project (a fresh `git clone` of this framework, or a project
scaffolded from it). It uses a **local scratch bare remote** so you can see
BLOCKED → CLEARED safely, without touching your project's real `origin` — if
you already have `tessctl gate install-hooks` installed against your real
remote, the exact same hook fires on a normal `git push`; nothing about the
mechanism changes.

```bash
set -euo pipefail

# 1. Bootstrap the live tree from committed core (idempotent — safe to
#    re-run any time). `tessctl init` scaffolds operator/ stubs, restores
#    every framework-owned file from .tess/core, and renders CLAUDE.md.
./tessctl init
./tessctl doctor

# 2. Generate Reid's verifier key and register it — the turnkey step this
#    quickstart exists to prove. Generates a fresh, sign-only, local GPG
#    identity; exports the PUBLIC half to .tess/keys/verifiers/reid.asc;
#    registers {fingerprint, public_key_file} in BOTH core/policy/policy.yaml
#    and .tess/core/policy/policy.yaml; re-pins that one lock entry.
#    The PRIVATE key never leaves your local GPG keyring — tessctl never
#    stores or transmits it (same posture as the release-signing key).
./tessctl verdict keygen --verifier Reid
./tessctl doctor
./tessctl verify
./tessctl lock --check

# 3. Add a real require_verdict rule. core/policy/policy.yaml ships one
#    worked EXAMPLE rule (a glob no real tree matches, "__REPLACE_ME__/..."
#    — see that file's own header) so `tessctl doctor` shows the shape of a
#    real rule without silently gating anything. Replace it with your
#    project's actual path — here, src/prod/**, requiring Reid's sign-off.
#    This uses an anchor-based, COMMENT-PRESERVING text patch (the same
#    principle `verdict keygen` itself uses on policy.verifier_keys), so
#    policy.yaml's extensive header documentation survives — a plain YAML
#    load+dump round-trip would silently drop every comment in the file.
python3 - <<'PY'
import pathlib

anchor = "    - id: example-prod-service-placeholder\n"
new_rule = (
    "    - id: my-prod-rule\n"
    "      description: >-\n"
    "        Require a signed covering verdict before shipping changes under\n"
    "        src/prod/**.\n"
    "      globs:\n"
    "        - \"src/prod/**\"\n"
    "      classification: [prod_touching]\n"
    "      require_verdict: true\n"
    "      allowed_verifiers: [Reid]\n\n"
)
for path in ("core/policy/policy.yaml", ".tess/core/policy/policy.yaml"):
    p = pathlib.Path(path)
    text = p.read_text()
    if anchor not in text:
        raise SystemExit(f"{path}: anchor line not found — is this the shipped default policy.yaml?")
    p.write_text(text.replace(anchor, new_rule + anchor, 1))
PY
# Re-pin ONLY the one core file this step touched (`tessctl lock --regen`'s
# new --only flag — never re-baselines any OTHER file's drift/tamper as a
# side effect, unlike the unscoped --regen).
./tessctl lock --regen --only .tess/core/policy/policy.yaml --yes
./tessctl doctor

# 4. Install the git hooks + CI workflow so the gate actually fires on a
#    real `git commit`/`git push` (idempotent; splices above any pre-existing
#    hook, same coexistence pattern as `tessctl vault init`).
./tessctl gate install-hooks
git add -A
git commit -q -m "tessctl init + Reid's verifier key + a real prod rule + gate hooks"

# 5. BOOTSTRAP WARNING for a fresh adopter (conductor/verdict-signing.md's
#    own documented gotcha): core/policy/policy.yaml ships ONE rule that is
#    genuinely live in THIS repo already —
#    `tess-os-security-tier-doctrine`, protecting the doctrine/schema/
#    policy/key-registry/workflow files this framework ships from minute
#    one. Those files already exist in your very first commit, so your
#    very FIRST push needs its own covering verdict too — not a bug, the
#    gate protecting its own bootstrap surface. Write and sign ONE verdict
#    covering exactly the files that currently exist under that rule.
python3 - <<'PY'
import subprocess, pathlib, yaml

paths = [
    "conductor/guardrails.md",
    "conductor/verification-routing.md",
    "conductor/channel-guardrails.md",
    "conductor/dispatch-brief.md",
    "core/contracts/brief.schema.json",
    "core/contracts/verdict.schema.json",
    "core/contracts/policy.schema.json",
    "core/policy/policy.yaml",
    ".tess/keys/verifiers/reid.asc",
    ".github/workflows/tess-gate.yml",
]
artifact_hashes = {}
for path in paths:
    if not pathlib.Path(path).exists():
        continue
    r = subprocess.run(["git", "hash-object", path], capture_output=True, text=True, check=True)
    artifact_hashes[path] = r.stdout.strip()

verdict = {
    "verifier": "Reid",
    "output_domain": "Code diff / PR",
    "primary_artifacts_read": list(artifact_hashes),
    "findings": [],
    "severity_counts": {"critical": 0, "high": 0, "medium": 0, "low": 0},
    "summary_line": "Reviewed. Found 0 CRITICAL, 0 HIGH, 0 MEDIUM, 0 LOW. Top priority: none.",
    "disposition": "APPROVE",
    "covers_paths": list(artifact_hashes),
    "artifact_hashes": artifact_hashes,
}
p = pathlib.Path("missions/m1/verdicts/bootstrap-doctrine.verdict.md")
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(
    "---\n" + yaml.safe_dump(verdict) + "---\n\n"
    "# Bootstrap verdict\n\nCovers the framework's own pre-existing "
    "tier:security doctrine surface (already gated from minute one) so the "
    "very first push is not blocked by files this repo ships out of the box.\n"
)
PY
FINGERPRINT="$(python3 -c "import yaml; print(yaml.safe_load(open('core/policy/policy.yaml'))['policy']['verifier_keys']['Reid']['fingerprint'])")"
./tessctl verdict sign missions/m1/verdicts/bootstrap-doctrine.verdict.md --verifier Reid --key-id "$FINGERPRINT"
git add -A
git commit -q -m "bootstrap: cover pre-existing doctrine surface with a signed Reid verdict"

# 6. NOW the baseline push succeeds — a scratch LOCAL bare remote, so this
#    is safe to try without touching your project's real origin.
rm -rf /tmp/gate-quickstart-remote.git
git init --bare -q /tmp/gate-quickstart-remote.git
git remote remove origin 2>/dev/null || true
git remote add origin /tmp/gate-quickstart-remote.git
git push -u origin HEAD:main

# 7. Ship a NEW prod change under the rule from step 3, with NO covering
#    verdict yet — this WILL be rejected. That is the gate working as
#    designed, not a bug.
mkdir -p src/prod
echo "print('hello prod')" > src/prod/app.py
git add -A
git commit -q -m "add a prod handler"

if git push origin HEAD:main; then
  echo "UNEXPECTED: push should have been BLOCKED — see the gate's own output above." >&2
  exit 1
fi
echo ">>> As expected: BLOCKED — no covering APPROVE verdict for src/prod/app.py yet."

# 8. Write a verdict covering exactly this content, sign it with Reid's
#    key, then push again — CLEARED.
BLOB="$(git hash-object src/prod/app.py)"
mkdir -p missions/m1/verdicts
cat > missions/m1/verdicts/prod-src.verdict.md <<VERDICT
---
verifier: Reid
output_domain: Code diff / PR
primary_artifacts_read:
  - src/prod/app.py
findings: []
severity_counts: {critical: 0, high: 0, medium: 0, low: 0}
summary_line: "Reviewed. Found 0 CRITICAL, 0 HIGH, 0 MEDIUM, 0 LOW. Top priority: none."
disposition: APPROVE
covers_paths:
  - src/prod/**
artifact_hashes:
  src/prod/app.py: $BLOB
---

# Verdict body

Reviewed src/prod/app.py end to end; no issues found.
VERDICT

./tessctl verdict sign missions/m1/verdicts/prod-src.verdict.md --verifier Reid --key-id "$FINGERPRINT"
./tessctl verdict verify missions/m1/verdicts/prod-src.verdict.md

git add -A
git commit -q -m "add signed covering verdict for src/prod/app.py"

git push origin HEAD:main
echo ">>> CLEARED — the signed, covering verdict satisfied the gate."
```

## What just happened

- **Step 1** proved the framework's own integrity guarantee: a freshly
  restored/rendered live tree matches `.tess/core` byte for byte — `doctor:
  OK` before anything else happens.
- **Step 2** is the point of this document: `tessctl verdict keygen` did, in
  one command, everything `conductor/verdict-signing.md`'s "Onboarding a
  verifier" section documents by hand — generate, export, register, re-pin —
  and left `doctor`/`verify`/`lock --check` clean immediately afterward.
- **Step 3** turned ONE glob (`src/prod/**`) from `example-prod-service-
  placeholder`'s inert placeholder into a real, live `require_verdict` rule,
  without losing a single line of `policy.yaml`'s own documentation.
- **Step 5** is the honest, easy-to-miss part: `tess-os-security-tier-
  doctrine` is not a placeholder — it already protects real files this repo
  ships from minute one, so those need their own covering verdict before
  ANY push clears, independent of whatever new rule you just added. See
  `conductor/verdict-signing.md`'s "Bootstrap warning for a fresh adopter."
- **Step 7** proved the gate is load-bearing: an otherwise-unremarkable
  one-line file, under a path the new rule protects, with **zero** covering
  verdict, is rejected at `git push` — not a lint warning, a hard reject.
- **Step 8** proved the gate is satisfiable, not a permanent wall: the exact
  same change, with a genuine, signed, content-bound `APPROVE` verdict from
  an allowed verifier, clears immediately.

## Troubleshooting

- **`tessctl verdict keygen` refuses with "refusing to clobber existing
  ... key material"** — a public key file or policy registration for this
  verifier already exists. This is deliberate (idempotent, no silent
  overwrite). Pass `--force` to generate a NEW keypair and REPLACE both (a
  manual key rotation, automated).
- **`gpg` not found on PATH** — install GnuPG (`brew install gnupg` /
  `apt-get install gnupg`) and retry; `keygen` checks for it before doing
  anything else.
- **`git push` blocked even after signing** — run `tessctl verdict verify
  <file>` on the verdict directly; it uses the exact same check `tessctl
  gate` does and prints WHY (wrong key, tampered content, unregistered
  verifier, wrong `--verifier` at sign time, etc.).
- **A repo-admin step this quickstart does NOT do**: making the CI check a
  **required status check** in branch protection (job name `tessctl gate
  ci`), and the recommended CODEOWNERS/ruleset belt-and-suspenders over
  `.github/workflows/**` / `core/policy/**` / `.tess/keys/verifiers/**`. See
  `conductor/verdict-signing.md`'s "CI auto-enforce" section.
- **`git push --no-verify` bypasses the local hook** — expected; `tessctl
  gate ci` (wired into `.github/workflows/tess-gate.yml` by `install-hooks`)
  is the harness-independent backstop for exactly that reason.

## Next steps

- Repeat step 2 for every real verifier your project needs
  (`--verifier Quinn`, `--verifier Cyra`, ...) — see
  `core/contracts/policy.schema.json`'s `verifier`/`allowed_verifiers` enum
  for the six named verifiers.
- Replace the illustrative `src/prod/**` rule with your project's actual
  production/client-facing/external-visible surfaces — `policy.yaml`'s
  header documents the four classification categories
  (`prod_touching`/`client_facing`/`externally_visible`/
  `irreversible_decision`) and the separate, never-verdict-satisfiable
  `hard_floor_rules` (credentials, money movement, destructive prod data,
  client-external claims — `guardrails.md` Rule 18).
- Configure branch protection so `tessctl gate ci` is actually a required
  check, not just advisory CI (see Troubleshooting above).
