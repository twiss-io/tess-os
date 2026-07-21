<!--
Thanks for contributing to Tess OS!
By opening this PR you agree your contribution is licensed under Apache-2.0
(inbound = outbound). See CONTRIBUTING.md and CLA.md.
-->

## What this changes

A clear description of the change and the motivation behind it.

Fixes # (issue), if applicable.

## Type of change

- [ ] Bug fix
- [ ] New feature / enhancement
- [ ] Doctrine / agent / command change (`conductor/`, `agents/`)
- [ ] Engine change (`tessctl`)
- [ ] Docs only
- [ ] Other (describe)

## Checklist

- [ ] I branched off `main` (no direct commits to `main`).
- [ ] **No secrets or client data** in the diff (no tokens, keys, `.env`,
      `*.age`, client records).
- [ ] **No AGPL-licensed (or otherwise Apache-incompatible) code or text** added
      to this Apache-2.0 repo.
- [ ] I updated [NOTICE](../NOTICE) if I added or changed a dependency.
- [ ] I added/adjusted tests for any behavior change.
- [ ] Quality gates pass locally (see below).
- [ ] If I changed a framework-owned, lock-tracked file, I re-pinned the merge
      base (`./tessctl lock --regen --yes`) and `doctor` / `verify` are green.
- [ ] My contribution is offered under **Apache-2.0** (inbound = outbound).

## Gates run locally

```bash
python -m pytest
cd create-tess && npm test && cd ..
./tessctl doctor && ./tessctl verify
npm pack --dry-run
```

Paste the relevant results, or confirm all green.

## Anything reviewers should know

Doctrine notes, follow-ups, screenshots, or open questions.
