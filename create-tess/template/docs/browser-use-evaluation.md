# Browser automation integration decision

> Decision recorded 2026-07-23. This is a boundary record, not an enablement
> guide or authorization for browser automation.

## Decision

Tess OS does not ship a browser-automation package, binary, managed skill, or
default execution path. The previously bundled browser-use integration was
retired because the engine, test suite, and CI had no direct call site for it,
while its dependency graph exceeded Tess OS's supported Python 3.9 baseline.

This preserves a small, model-agnostic core: agents can be governed regardless
of whether a particular browser tool is installed. It is not a statement about
model capability or a ban on operators selecting an external integration.

## External integrations

An operator may evaluate a browser automation tool outside Tess OS when a
specific use case needs it. That tool is not installed, verified, advertised
as available, or activated by Tess OS. Its installation, credentials, browser
profiles, account access, cookies, telemetry, network targets, and cloud use
remain outside the shipped runtime and require an explicit, separately
reviewed integration decision.

The default `tessctl run` worker-tool allowlist excludes `Bash`; an explicit
worker configuration can change that allowlist. Neither fact grants browser,
network, account, credential, profile, cookie, cloud, or tunnel access.

## Verification requirements for a future integration

Any proposal to add a browser capability must identify its accountable owner,
permitted targets, authorization model, data classification, credential and
profile handling, telemetry policy, and local-versus-remote execution model.
It must also prove both directions: the intended path works and the
unauthorized path is denied. It must not alter Tess OS's signed, fail-closed
review gate or create a verifier key, verdict, or sign-off artifact merely to
make a change pass.

## Scope

This decision removes an unexercised default dependency and its bundled skill.
It does not install or execute an alternative browser tool, change policy,
workflows, verifier keys, verdicts, sign-offs, releases, or trust state.
