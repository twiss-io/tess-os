# Data-leak safety: the overlay/dogfood model

> **What this page is for:** running a real Tess OS instance with real
> operator/client/business data, without that data ending up committed (and
> potentially pushed to a public repo) by an ordinary `git add -A`.

## The model: framework + private overlay

A live Tess OS instance is two things layered on top of each other:

1. **The framework** — everything `tessctl` renders, merges, and updates:
   `agents/`, `conductor/`, `.claude/agents|commands|hooks|skills`,
   `CLAUDE.md`, `prompts/`, `AGENTS.md`, `core/contracts|policy`,
   `clients/_template/`. These paths are **overwritten on update**
   (`tessctl update` / `tessctl restore`) — see `tess.manifest.json`'s
   `owned_globs`. Cyra proved this directly: a real operator secret hand-
   planted at `agents/<name>.md` (a framework-owned path) gets silently
   clobbered by the next upstream file at that exact path.
2. **The private overlay** — everything that is *your* data, never
   framework content: `clients/*/**` (real client folders), `kb/**`
   (internal + client knowledge base), `operator/**` (your identity and
   context), `.env`/`.env.*`, `*.local.md` (the append-first customization
   shadow layer), and vault material (`.claude/vault/**`, `**/*.age`).
   `tess.manifest.json`'s `never_touch` list is the authoritative registry
   of these paths — `tessctl` itself refuses to write to any of them
   (`check_manifest_write_gate` / `guarded_write`).

**The hard rule:** private data lives ONLY in the overlay directories above.
Never place private data in a framework-owned directory — it will not
survive the next update, and (worse) it will look "safe" right up until it
silently vanishes or gets overwritten.

## Two boundaries, not one

Before this hardening, only ONE side of this model was actually enforced:

| Boundary | Control | Status |
|---|---|---|
| **Write** — can `tessctl` write to a private path? | `check_manifest_write_gate` / `guarded_write` (`.tess/bin/tessctl`) | Enforced. Allowlist-based; hard guards (`.git`, vault, `*.local.md`) can't be overridden even by a poisoned manifest. |
| **Commit** — can `git commit` capture a private path? | `.gitignore` | **Was NOT reconciled with the write-gate.** `operator/*.md`, `operator/profile.json`, `*.local.md`, and `kb/wiki/log.md` were NOT gitignored — a plain `git add -A` would stage them. |

A security review found this divergence directly: the write-gate is solid,
but nothing stopped an operator's own `git add -A && git commit` from
capturing exactly the paths the write-gate refuses to touch. This page and
the two new controls below close that gap.

## Control 1 — reconciled `.gitignore`

Every `never_touch` path that represents genuine **private data** (as
opposed to "tessctl must not manage this, but it's fine to be a normal
tracked repo file" — see below) is now gitignored:

- `operator/**` (four static doc-template stubs re-included by name — see
  `.gitignore`'s own comment block for exactly which, and why
  `operator/profile.json` deliberately gets **no** re-include: it is the one
  file `create-tess`'s onboarding wizard unconditionally overwrites with
  real identity)
- `*.local.md`, `**/*.local.md`
- `kb/**` (the previous `!kb/wiki/index.md` / `!kb/wiki/log.md` overrides
  are removed — `log.md` is exactly the file a live instance appends real
  mission/client entries to)
- `clients/*/**` (`clients/_template/**` stays committable)
- `.env`, `.env.*`, vault material
- `missions/**`, `UPGRADE-NOTES.md`, `.mcp.json`

**Not everything in `never_touch` is private data.** `docs/**`,
`adapters/**`, `starter/**`, `README.md`, `main.py`, `pyproject.toml`,
`uv.lock`, and a handful of other entries are in `never_touch` because
`tessctl` is structurally out of scope to manage them — they are ordinary,
public, tracked framework/repo content. Gitignoring them would be wrong (and
was tried during development of this hardening: it produced ~155 false
"violations" against this repo's own history — files like every doc under
`docs/` and `adapters/` — which would make a commit gate permanently block
ordinary framework development).

Verify any path with:

```bash
git check-ignore --no-index -v <path>
```

`--no-index` matters: it evaluates the gitignore *rule* independent of
whether a path happens to already be tracked. A handful of files (this
repo's own generic `operator/profile.json`, `kb/wiki/log.md` /
`kb/wiki/index.md`) remain tracked in *this* repo's history as the shipped,
harmless, generic default — via git's ordinary "already-tracked files
survive a new ignore rule" behavior, not a `!` override. A **freshly
scaffolded instance** starts from an empty `git init`, so this same
`.gitignore` (copied verbatim by `create-tess`) protects it from the start:
the real identity `writeProfile()` writes, or the real mission entries you
append to `kb/wiki/log.md` over months of use, are never picked up by
`git add -A` in the first place.

## Control 2 — the publish-clean gate (commit-side, symmetric to the write-gate)

```bash
tessctl doctor --publish-clean              # staged changes only (the pre-commit hook body)
tessctl doctor --publish-clean --publish-clean-all   # full git-tracked-set audit
```

FAILS if a path about to be committed matches the curated private-data set:
operator identity, `kb/**`, `clients/**`, `.env*`, `*.local.md`, vault
material, `missions/**`. This is deliberately a **curated subset** of
`never_touch`, not the whole list — see Control 1's explanation of why the
full list is the wrong tool for a commit gate. `owned_globs` still wins
(e.g. `clients/_template/**`), and a small allowlist covers the same static
doc-template stubs `.gitignore` re-includes.

`--publish-clean` (default) checks **staged** changes
(`git diff --cached --diff-filter=ACMR`) — this is what the pre-commit hook
actually needs: block a commit that *introduces or modifies* a private path,
without re-flagging a pre-existing grandfathered tracked file on every
future unrelated commit forever. `--publish-clean-all` checks the full
`git ls-files` index for a manual repo-hygiene audit — it does report
grandfathered files; that's diagnostic, not the gate's default behavior.

Installed as a git pre-commit hook by the existing hook mechanism:

```bash
tessctl gate install-hooks
```

This single command now installs **four** independent hook layers (each its
own marker, each spliced above whatever was already there, so none of them
silently neuters another): the contract gate guard (`tess-gate-guard`), the
new publish-clean guard (`tess-publish-guard`), the vault secret-pattern
guard (`tess-vault-guard`, installed separately by `tessctl vault init`),
and the new local gitleaks guard (`tess-gitleaks-guard`, below).

## Control 3 — local gitleaks pre-push (secrets only — read this carefully)

`gitleaks` was already run in CI (`.github/workflows/ci.yml`'s
`secret-scan` job, full history, every push/PR). `tessctl gate
install-hooks` now ALSO installs a local pre-push hook that runs `gitleaks`
against just the commits being pushed, for a faster local feedback loop.

**This control is secrets-only.** It looks for API keys, tokens, and
credential-shaped strings. It does **not** know that `operator/profile.json`
holds your real name, or that `kb/wiki/log.md` holds a real client's
business details — that is Control 2's job, not this one. Do not treat a
clean gitleaks run as "nothing private was committed."

If `gitleaks` is not installed locally, the hook prints a warning and lets
the push through — CI's `secret-scan` job is the enforced backstop
regardless of what's on a given contributor's machine.

## What this does *not* do

- It does not scan file **content** for PII (names, emails, phone numbers) —
  only **paths**. A real name typed into a framework-owned file that isn't
  in the private-data set (e.g. hand-edited into `README.md`) is not caught
  by either gate. Keep private data in the overlay directories; don't rely
  on a content scanner that doesn't exist.
- It does not rewrite git history. If a private path was already committed
  and pushed before this hardening, `git rm --cached <path>` stops *further*
  leakage; removing it from history (and rotating any real secret involved)
  is a separate, deliberate operation — see `SECURITY.md`.
- It does not replace human judgment about what belongs in the overlay vs.
  the framework. The manifest's `never_touch` list and this page's curated
  subset are a floor, not a substitute for reading `tess.manifest.json`
  before deciding where a new kind of data should live.

## Keep the overlay local-only or on a private remote

None of the above matters if the *remote* the overlay's git history pushes
to is public. If you are dogfooding a live instance with real data, either:

- keep the instance's `.git` local-only (no remote at all), or
- push to a **private** repository you control.

`twiss-io/tess-os` (this repo) is the public framework distribution. It is
never the right remote for a live, data-bearing instance.
