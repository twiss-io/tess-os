# browser-use evaluation — status, boundary, and deferred decision

> Repository snapshot: `main` at
> `1d6fc4475be55e404afbdad14fa00aee30cf6bd1` (reviewed 2026-07-15).
> This is an evaluation record, not an enablement guide or an authorization to
> use browser automation.

## Decision status

**Recommendation: DEFER retain/remove.** `browser-use` already has a package
declaration, lockfile resolution, and core-managed skill in this repository,
but the current Tess engine, test suite, and CI do not directly invoke it.
Xavier should first decide whether Tess OS has a supported browser-automation
use case and name an accountable owner. Until then, do not add a use case,
enable a new execution path, or treat its presence as approval to use it.

If no supported use case and owner are identified, a separate removal proposal
would be better supported than retaining an unexercised default dependency. If
one is identified, a separate proposal should define the permitted target,
account/data boundary, local-versus-cloud browser mode, and operational
controls before any implementation decision.

This recommendation does **not** decide retention or removal, alter the
signed review gate, or authorize any browser, network, account, credential,
profile, cookie, cloud, or tunnel operation.

## Confirmed repository facts

| Area | Evidence | What it establishes |
|---|---|---|
| Package declaration | [`pyproject.toml`](../pyproject.toml) declares `browser-use>=0.12.6`. | The package is a project dependency. |
| Resolved version | [`uv.lock`](../uv.lock) resolves `browser-use` to `0.13.1` from PyPI. Its package entry lists 35 direct dependencies, including browser/CDP, HTTP, telemetry, cloud/LLM-provider, and file/document libraries. | The locked package's direct dependency set. |
| Python metadata | [`pyproject.toml`](../pyproject.toml) declares `requires-python = ">=3.9"`; the lock header declares `>=3.13`. The [PyPI metadata for locked version 0.13.1](https://pypi.org/pypi/browser-use/0.13.1/json) declares `>=3.11,<4.0`. | The repository's project, lock, and locked-package Python constraints are not aligned. |
| Managed skill | [`.tess/tess.lock`](../.tess/tess.lock) maps the core `browser-use` skill to [`.claude/skills/browser-use/SKILL.md`](../.claude/skills/browser-use/SKILL.md), tier `normal`; the skill declares `Bash(browser-use:*)`. | The repository ships a documented optional skill with a Bash-scoped tool declaration. |
| Direct use | A source audit found no Tess engine or test import/subprocess invocation of `browser_use` / `browser-use`. The CI workflow installs [`requirements-dev.txt`](../requirements-dev.txt), which does not list the package; the remaining runtime-adjacent references are the package declaration, managed-skill inventory, and a non-executing restore-path example in [`.tess/bin/tessctl`](../.tess/bin/tessctl). | No direct invocation was found in the reviewed engine/test paths, and current CI does not install the package through its declared test requirements. |

The local skill documents browser launch/navigation, page interaction, file
upload, JavaScript evaluation, cookie read/export/import, existing Chrome
profiles with saved logins, cloud-browser connection/API-key login, persistent
cloud profiles, profile synchronization, and tunnels. Those are documented
capabilities, not evidence that Tess OS invokes or approves them.

The upstream project publishes the library under the [MIT
License](https://raw.githubusercontent.com/browser-use/browser-use/main/LICENSE).
That statement concerns the upstream project; it is not a license assessment
of every transitive dependency in the lockfile.

## Assessment (inferences, not current behavior claims)

The 35 listed direct dependencies and the unaligned Python constraints make
the package a meaningful supply-chain and packaging-review surface, despite the
absence of a verified current engine call site. This document does not diagnose
or change the compatibility issue; it records it for the retain/remove
decision. The existing CI's treatment of that package is out of scope for this
documentation-only change.

## Current control boundary

The `tessctl run` Claude dispatch driver's default allowlist contains `Read`,
`Write`, `Edit`, `Grep`, and `Glob`, and deliberately omits `Bash`; the source
and its regression tests document that default in
[`.tess/bin/tessctl`](../.tess/bin/tessctl) and
[`tests/test_run.py`](../tests/test_run.py). This is a useful
least-privilege default for those workers.

It is **not** a browser-use-specific or absolute execution denial. The driver
also accepts an explicit `allowed_tools` override, including a Bash-containing
allowlist. Therefore, use outside the default has to be an explicit
task/harness decision under operator policy; no technical check documented
here blocks every possible browser execution.

In particular, a manifest entry or managed skill authorizes **neither**
browser use **nor** external, account, profile, cookie, credential, cloud, or
tunnel access. This record creates no new permission, exception, sign-off, or
trust anchor, and it does not relax Tess OS's signed fail-closed review gate.

## Privacy and security surface to assess before a future proposal

The following are upstream-documented capabilities and data paths, not claims
about current Tess OS behavior:

- Browser Use's [remote-browser documentation](https://docs.browser-use.com/open-source/customize/browser/remote)
  describes Cloud and third-party CDP connections, API keys, cloud profiles,
  proxy credentials, authentication handling, and global proxies.
- Its [telemetry documentation](https://docs.browser-use.com/open-source/development/monitoring/telemetry)
  says telemetry may include task instructions, visited URLs, action traces,
  errors, and final results; it documents `ANONYMIZED_TELEMETRY=false` as the
  opt-out setting.

Accordingly, a future supported-use-case proposal should explicitly assess the
target's authorization, account ownership, data classification, credential
handling, profile/cookie access, whether telemetry is permitted, and whether
local or remote/cloud execution is allowed. It should not assume that the
default worker-tool boundary supplies those controls after an explicit
override.

## Scope and non-decisions

This evaluation does not add, remove, install, resolve, or execute
`browser-use`. It does not modify a dependency declaration or lockfile; it
does not change a skill, runtime, test, policy, workflow, verifier key,
verdict, sign-off, or trust state. It also makes no claim that browser
automation improves a model or that its use is currently required by Tess OS.

The next decision belongs to Xavier: identify a supported use case and owner,
or explicitly choose removal. Either path requires a separately reviewed
proposal; this document deliberately leaves both choices open.
