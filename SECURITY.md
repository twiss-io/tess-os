# Security Policy

Thank you for helping keep Tess OS and its users safe. This document explains how
to report a vulnerability responsibly and what to expect in return.

## Report privately — do not open a public issue

**Please do not report security vulnerabilities through public GitHub issues,
pull requests, or discussions.** A public report tips off attackers before a fix
is available.

Instead, report privately through one of:

- **GitHub Security Advisories (preferred)** — use the repository's
  **Security → Report a vulnerability** ("Privately report a vulnerability")
  flow, which opens a private advisory thread with the maintainers.
- **Email** — **legal@twiss.io**, if you are unable to use GitHub Security
  Advisories.

If you wish to encrypt your report, request a key in your first (low-detail)
message and we will share one.

## What to include

A good report helps us reproduce and triage quickly:

- The component affected (e.g. `tessctl` engine, the **vault** subsystem, a guard
  hook, the `create-tess` wizard, a guardrail/doctrine gate).
- The version / commit you tested against.
- Steps to reproduce, a proof-of-concept, or the conditions required.
- The impact you believe it has (what an attacker could read, write, or bypass).
- Any suggested remediation, if you have one.

## Our commitment

- We will **acknowledge** your report within a few business days.
- We will work with you to **confirm** the issue and determine its severity.
- We will keep you **informed** of remediation progress.
- We will **credit** you when the fix is published, unless you prefer to remain
  anonymous.
- We ask that you give us a **reasonable opportunity to fix** the issue before
  any public disclosure (coordinated disclosure).

## Trust model

**The release-signing key is the single root of trust, and signing a release tag
is the single human step.** Everything before a release is automated: CI, the
automated verifier verdicts, and merges to `main`. Nothing reaches users unless it
comes from a tag signed by that key.

| | |
|---|---|
| Key | Twiss Release Signing Key, fingerprint `EBEA BC61 8C11 B6A7 340A  7D16 01DD 6376 67B8 CC89` |
| Public key | [`.tess/keys/twiss-release-key.asc`](.tess/keys/twiss-release-key.asc) |
| Custody | The private key is passphrase-protected. The passphrase is stored in the maintainer's OS keychain with no pre-authorised applications, so every use needs the maintainer to approve an OS prompt on the signing machine. gpg-agent forgets it after at most 60 seconds idle (300 seconds absolute). |
| Human step | The maintainer signs the release tag (`git tag -s`) and approves the prompt. No other step needs a person. |

### What the signature gates

| Channel | Check | Runs on |
|---|---|---|
| GitHub Release (`v*` tags) | `release.yml` Gate 1: the tag must be annotated and pass `git verify-tag` against the `TESS_SIGNING_PUBKEY` secret. | GitHub Actions |
| npm `create-tess` (`create-tess-v*` tags) | `publish-npm.yml` Gate 0: annotated tag, `VALIDSIG` from the pinned fingerprint above. The job runs in the `npm-publish` environment, which only admits `create-tess-v*` tags, and npm Trusted Publishing is bound to that environment. | GitHub Actions |
| `tessctl update` / `self-update` | The tag is verified in an isolated GNUPGHOME seeded only with the pinned `framework.trusted_key_fingerprint` before any file is extracted. If no fingerprint is pinned, the update refuses unless the operator passes `--trust-on-first-use`, which records the first signer seen. New installs ship with the fingerprint pinned. | The user's machine |

Repository rulesets back this up. `v*` and `create-tess-v*` tags cannot be moved
or deleted by anyone, including admins. Only repository admins can create them.
Branches named `v<digit>…` or `create-tess-v…` cannot be created, so a branch can
never shadow a release tag.

### Verifier signatures are automated attestations

The registered verifier key (Cyra, `F9321F92…76E8`) belongs to an automated
reviewer. By design it has no passphrase and is used by the review automation
without a human in the loop. A valid Cyra verdict attests **"the automated
review of this exact content passed"**. It does **not** mean a human approved the
change. Earlier Reid verifier keys are retired, and no Reid key is registered in
`policy.yaml`'s `verifier_keys`.

### No required human PR review, by design

The `main` ruleset requires the status checks (including the App-bound
`tessctl gate ci`), strict up-to-date branches and no bypass actors. It requires
**0 approving reviews**, deliberately. Review is automated. The human control sits
at release, not at merge.

### What an attacker with repository write access can and cannot do

**Can:** open and merge pull requests to `main` that pass the required checks,
including changes to workflows. Push ordinary branches. If they also control the
review automation, produce valid Cyra verdicts. In other words, `main` can contain
unreviewed-by-a-human code. That is why `main` is not a release.

**Cannot:**
- Create, move or delete a `v*` / `create-tess-v*` tag. Creation is admin-only, and nobody can update or delete these tags.
- Publish `create-tess` to npm. That needs a job in the `npm-publish` environment, which only runs on `create-tess-v*` tags.
- Get a tag accepted by `tessctl update` on a machine that pins the release fingerprint without the release key and the maintainer's approval.

**Limits, stated plainly:**
- The build automation's GitHub credentials have **admin** rights. Someone holding those credentials can create release tags and edit workflows, so the CI gates are not the last line against them. For `tessctl update` with a pinned fingerprint, the check on the user's machine still holds, because no repository change can forge the release signature.
- GitHub Release pages and uploaded assets are not signed artifacts; the signed tag is. Verify with `git verify-tag <tag>` against the key above.
- An unpinned `tessctl` install refuses to update; with `--trust-on-first-use` it trusts the first signer it sees. Keep `framework.trusted_key_fingerprint` pinned to the fingerprint above.
- If the release key or the maintainer's machine is compromised, this model is compromised. Report suspected misuse privately (see above).
- **Multi-push policy reduction on `main` (A14, the #181 lineage) is out of scope.** Someone with write access can weaken `policy.yaml` in one merge and use the weaker policy in a later one; the gate only stops a relaxation from applying to the push that introduces it. This is accepted: `main` protections are best-effort, `main` is not a release, and users are protected by the signed release tag and the pinned key when they install or update. Reports of this pattern alone are not treated as vulnerabilities; a way to get unsigned code accepted by `tessctl update` with a pinned fingerprint is.

## Scope and threat model

Tess OS is a local governance framework with a doctrine/roster scaffold,
upgrade engine, and coding-agent render targets. Claude Code is the reference
integration; Codex is a pilot and generic output is an interoperability
baseline. It is not a hosted service; it runs on your machine with the
credentials and access **you** grant it. Keep this in mind when assessing impact.

We are especially interested in reports concerning:

- **The vault (`tessctl vault`).** The vault is a **local-first, encrypted-at-rest
  secret store plus a commit/push backstop — a risk reducer, not a guarantee.**
  Its threat model is documented in `conductor/vault.md`. Reports that strengthen
  it are welcome, including:
  - Ways encrypted material (`*.age`, identities, recipients) could be exposed,
    written outside the intended paths, or logged in plaintext.
  - Ways the pre-commit / pre-push guards could be **bypassed** so a secret or
    vault blob reaches a remote, or ways they silently neuter an adopter's own
    pre-existing hooks.
  - Ways a secret reference (`vault://…`) could leak its value into argv, logs,
    environment dumps, or error output.

  Out of scope for the vault, by design: it cannot protect against a compromised
  local machine, a malicious operator, an attacker who already has your age
  identity, or secrets you grant to processes Tess OS legitimately injects them
  into. The vault is **defense-in-depth**, not a vault appliance.

- **The upgrade engine (`tessctl`).** Path-escape / write-outside-root in the
  manifest write gate, merge-base (`tess.lock`) integrity bypass, security-tier
  quarantine bypass, or a doctor/verify gate that can be fooled into reporting
  clean on tampered core.

- **Guard hooks and guardrails.** Ways the dispatch guard, the client-isolation
  guardrails, or the clarification hard floor (credentials, money movement,
  destructive production operations, external factual claims), could be bypassed.

- **Secret / client-data leakage.** Anything that causes the repository, an
  instance, or the npm package to ship a real secret or client data — this repo
  is designed to contain **zero** of either.

### Generally not in scope

- Vulnerabilities in third-party dependencies you install yourself (report those
  upstream — see `NOTICE`), unless Tess OS uses them in an unsafe way.
- Issues that require a pre-compromised host, physical access, or an actively
  malicious operator.
- Social-engineering of the operator, and prompt-injection that merely *asks* the
  agent to do something the operator could already authorize — though we **do**
  want to hear about prompt-injection that defeats a guardrail or hard floor.

## A note on doing your testing safely

Please only test against your **own** instance and your **own** credentials. Do
not attempt to access data or systems that are not yours.

---

_This policy may be updated over time. It is provided for clarity and is not legal
advice._
