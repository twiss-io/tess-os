# Contributing to Tess OS

Thanks for your interest in Tess OS. This repository is the **Apache-2.0**
distribution of the framework, the roster, the upgrade engine (`tessctl`), the
embedded vault, and the `create-tess` wizard.

By participating you agree to our [Code of Conduct](CODE_OF_CONDUCT.md).

## Ground rules

- **License of contributions.** Unless you state otherwise, contributions you
  submit are licensed under **Apache-2.0** (inbound = outbound; see LICENSE §5).
  **No CLA is required for Tess OS.** A CLA *does* apply to the future AGPL
  standalone vault in its own repo — see [CLA.md](CLA.md) for why and when.
- **No AGPL code here.** A future *standalone* vault product is planned under a
  different license (AGPL-3.0 + CLA) in a **separate** repository. Do not
  introduce AGPL-licensed (or otherwise Apache-incompatible) code or text into
  this repo.
- **Respect the marks.** "Tess", "Twiss", "Tess OS", and "Twiss Vault" are
  trademarks; the Apache-2.0 license does not license them. Don't introduce
  rebrands of, or claims of official status for, third-party forks. See
  [TRADEMARK.md](TRADEMARK.md).
- **Never commit a secret.** No tokens, keys, credentials, `.env` files, vault
  blobs (`*.age`), or client data. The git pre-commit/pre-push guards and CI
  secret-scan gates will reject them — but the first line of defense is you.
- **Third-party attribution.** If you add or change a dependency, update the
  [NOTICE](NOTICE) file accurately (name, license, and whether it is a runtime
  dependency or prior-art studied for concepts only).

## Workflow

1. Branch off `main` (never commit directly to `main`).
2. Make the change. Keep files within the project's quality gates: no file > 300
   lines where avoidable, no function > 50 lines, no swallowed errors.
3. Keep all gates green (below). Add or adjust tests for any behavior change.
4. Open a PR. Describe what changed and why; note any doctrine or NOTICE updates.

## Quality gates (must pass before a PR is mergeable)

Run these locally before pushing:

```bash
# 1. Python engine + vault + render + merge + hook-coexistence suite
python -m pytest

# 2. The create-tess wizard suite
cd create-tess && npm test && cd ..

# 3. Engine integrity + parse
python -c "import ast; ast.parse(open('.tess/bin/tessctl').read())"
./tessctl doctor
./tessctl verify

# 4. Nothing secret/bloated ships to npm
npm pack --dry-run
```

CI additionally runs a full-history secret scan (gitleaks), a tracked-path scrub
(no vault/secret paths), and a vault-registry integrity check on tagged releases.
The release itself is gated on a **signed annotated tag** verified against a
provisioned signer key.

## Engine notes

- `.tess/bin/tessctl` is a single self-contained Python 3 file (stdlib + PyYAML;
  the vault adds `pyrage`). It must `ast.parse` cleanly and keep `doctor`/`verify`
  green.
- Doctrine changes belong in `conductor/`; agent specs in `agents/` (with the
  pristine merge base mirrored under `.tess/core/`).

## Reporting security issues

Do not open a public issue for a vulnerability. Report it privately so a fix can
ship before disclosure — see [SECURITY.md](SECURITY.md) for how.
