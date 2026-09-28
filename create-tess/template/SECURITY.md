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

### Release signatures (how `tessctl update` trusts a release)

Every release tag carries two independent signatures, and both keys are pinned
in the install:

- **OpenPGP.** The annotated tag is signed with the Twiss Release Signing Key
  (`.tess/keys/twiss-release-key.asc`, fingerprint pinned in `.tess/tess.lock`
  `framework.trusted_key_fingerprint`). This is unchanged from earlier releases.
- **SSH.** The tag message also carries an OpenSSH signature (namespace
  `tess-release`) by the Twiss SSH release key
  (`.tess/keys/twiss-release-allowed-signers`, SHA256 fingerprint pinned in
  `framework.trusted_ssh_key_fingerprint`). It signs the manifest
  `tess-release-manifest/1`, `tag <name>`, `object <commit>`, `tree <tree>`.
  The verifier rebuilds that manifest from the fetched git objects, so the
  signature is bound to the exact tag name and the exact commit that
  `tessctl update` and `self-update` check out. It cannot be replayed onto
  another commit, a renamed tag or a same-named branch. It needs only
  `ssh-keygen -Y verify`, which ships with macOS, most Linux distributions
  and Windows 10+, so installs without gpg can still verify updates.

When gpg is installed, the OpenPGP signature must verify; when the SSH key is
also pinned and `ssh-keygen` is present, the SSH signature must verify too.
Without gpg, the SSH signature alone decides. A missing, malformed or
wrong-key signature fails closed before any file is written. The ship gate
applies the same rule to `.tess/release-proof.json`, reading both pins and
both public keys from the base commit, never from the candidate. Write access
to the repository is not enough to forge a release: both private keys stay
offline on the maintainer's machine, each behind a passphrase that is released
only after an interactive approval.

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
