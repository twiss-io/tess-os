# Local development quickstart

This guide is for contributing to the checked-out Tess OS source. It sets up a
local test environment; it does not activate a protected delivery workflow,
create approval authority, or configure a production branch.

## Prerequisites

- **Git** and a Bash-compatible shell. On Windows, use a current WSL
  distribution rather than Command Prompt or PowerShell for the commands below.
- **Python 3.9 or newer.** The checked-in project metadata declares
  `requires-python = ">=3.9"`; use a supported Python 3 release available on
  your machine.
- **Node.js 18 or newer, only when testing `create-tess`.** The root package is
  metadata and documentation, not the JavaScript runtime. Do not run a root
  `npm install` or root `npm test` as part of this setup.

## Clone and initialize once

Start from a fresh contributor clone. The final command below is intentionally
mutating: it restores managed files, renders local instruction files, creates
operator stubs when absent, and creates Tess working directories. Run it once
after cloning; inspect its changes before committing any work.

```bash
git clone https://github.com/twiss-io/tess-os.git
cd tess-os
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
./tessctl init
```

If `python3 --version` reports lower than 3.9, install a supported Python
release before continuing. Keep the virtual environment local to this clone;
it is not a repository artifact.

## Validate your change

Run the Python suite at the repository root. The Node commands are deliberately
scoped to `create-tess`, the only Node package with executable code and a test
suite. `npm pack --dry-run` checks what the root metadata package would contain
without publishing anything.

```bash
python -m pytest
(cd create-tess && npm ci && npm test)
./tessctl doctor
./tessctl verify
npm pack --dry-run
```

`doctor` and `verify` check the local framework state; passing them does not
make a branch protected or approve a governed change.

## Expected gate behavior

The shipped key registries are intentionally empty. If a governed change is
evaluated and reports `no covering APPROVE verdict found`, that is the expected
fail-closed result, not a local setup failure. Stop and follow the
[gate operation and custody guide](GATE_QUICKSTART.md); this contributor guide
does not provide a bootstrap path.

## Provider and product limits

Use the [support and status guide](STATUS.md) for the current provider labels
and limits. A local clone does not change a provider adapter's recorded status,
add a platform integration, provision Tess Cloud, or provision Tess Vault.

For contribution scope and pull-request expectations, read
[CONTRIBUTING.md](../CONTRIBUTING.md).
