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
2. Set up a fresh local clone with the [local development quickstart](docs/LOCAL_DEV_QUICKSTART.md).
   It documents the supported Python baseline, the one-time mutating
   initialization step, and why Node commands stay scoped to `create-tess`.
3. Make the change. Keep files within the project's quality gates: no file > 300
   lines where avoidable, no function > 50 lines, no swallowed errors.
4. Keep all gates green (below). Add or adjust tests for any behavior change.
5. Open a PR. Describe what changed and why; note any doctrine or NOTICE updates.

## Accountability

This applies identically to **human contributors and to any agent operating in
this repo** (Claude Code, Codex, or otherwise — see [AGENTS.md](AGENTS.md)).
Tess OS is a governance framework; it has no standing to help anyone else run
an accountable engineering process if it doesn't run one itself.

- **Every tracked piece of work gets a GitHub issue.** If it's worth doing,
  it's worth an issue — that's what makes the tracker a reliable signal of
  what's actually outstanding.
- **Every PR that resolves an issue MUST reference it with `Closes #N`**
  (or `Fixes #N` / `Resolves #N`) in the PR description. Do not rely on
  someone remembering to close it by hand afterward — link it so merging the
  PR closes it automatically.
- **CI must be green and an independent review must approve before merge.**
  This is existing practice restated explicitly: nothing here merges red, and
  nothing merges without a reviewer other than the author signing off.
- **Direct commits to `main` are not permitted** — see "Workflow" above; PRs
  are the only path in. If a repo admin ever has to bypass this in a genuine
  production emergency, open a retroactive PR/issue immediately afterward so
  the change still has a linked, reviewable audit trail rather than a silent
  gap in history.

### Agents operating this repo

Agents follow the identical loop, with no shortcuts for being automated:
issue → PR referencing it with `Closes #N` → CI green → independent review →
merge. An agent never self-provisions verifier keys or signs its own
approval, and never pushes directly to `main` — see the Ship-Gate section of
[AGENTS.md](AGENTS.md) for the mechanism that enforces the review-gate half
of this for policy-tagged paths.

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
