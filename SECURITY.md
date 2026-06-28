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

Tess OS is a **doctrine + roster + config scaffold plus an upgrade engine** for
Claude Code. It is not a hosted service; it runs on your machine with the
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

- **Guard hooks and guardrails.** Ways the dispatch / anti-fabrication / channel
  guards, or the clarification hard floor (credentials, money movement,
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
