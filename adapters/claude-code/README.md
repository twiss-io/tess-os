# Claude Code render target — reference integration

> **C3 — Managed-adapter preview.** This is Tess OS's reference render target
> and driver. It remains uncertified for protected delivery until the external
> trust-root and required GitHub-check prerequisites are complete. See
> [Support and status](../../docs/STATUS.md).

Implementation: `ClaudeCodeRenderTarget` in `.tess/bin/tessctl`
(`name = "claude-code"`, registered in `RENDER_TARGETS`).

## What it renders

`ClaudeCodeRenderTarget.render()` calls the engine's existing `_do_render()`
compile step. It is the **templated subset** of the Claude Code surface —
files that require token substitution and/or operator-profile assembly, not
plain copies:

| Live path | Compiled from |
|---|---|
| `CLAUDE.md` | `.tess/core/templates/CLAUDE.md.tpl` + the 5 `claude-md/*.md` fragments + `operator/*` stubs (`inject:`-gated) + `CLAUDE.md.local.md` shadow |
| `.claude/settings.json` | `.tess/core/settings-core.json`, passed through the render pipeline's `{{TOKEN}}` substitution (LOW-2: the shipped `settings-core.json` uses `$CLAUDE_PROJECT_DIR`, resolved by Claude Code at runtime, not `{{TESS_ROOT}}` — no core file ships that token today; see `adapters/README.md`'s note on why output is byte-identical across machines) |
| `conductor/identity.md` | `.tess/core/conductor/identity.md` with name tokens resolved |
| `conductor/personality.md` | `.tess/core/conductor/personality.md` + the active persona fragment (`.tess/core/personas/<pathway>.md`) |
| `clients/_template/CLAUDE.md` | `.tess/core/templates/client/_template/CLAUDE.md` with `{{ASSISTANT_NAME}}` resolved |

`ClaudeCodeRenderTarget.expected_live_bytes()` implements the interface's
drift-checking hook (HIGH-1) for the two entries above that need a bespoke
compile function (`render_claude_md()` / `render_settings_json()`) rather
than generic token substitution — the exact two special cases
`render_core_to_live()` used to hardcode inline before this fix.
`render_generated_paths()` returns all 5 rows in this table (this target has
no copy-only path of its own — see the scope-boundary note below), so
doctor/verify correctly route drift on any of them to `tessctl render`, not
`tessctl capture`.

## What it does NOT render (by documented, deliberate scope)

The copy-only portion of the Claude Code surface — `.claude/agents/**`,
`.claude/commands/**`, `.claude/hooks/**`, `.claude/skills/**`, `agents/**`,
non-templated `conductor/**` files, `core/contracts/**` — is a pure
`.tess/core/<path>` → `<live_path>` byte copy (with `{{TESS_ROOT}}`
substitution where applicable) driven by the pre-existing, target-agnostic
`tessctl restore` (`_do_restore`, iterating every `core-managed` entry in
`tess.lock`). That loop predates the render-target abstraction and is not
target-scoped today — there is only one target, so nothing is lost — but it
means this target's `render()` does not duplicate it.

**Why this split, not a merge:** `restore` (full idempotent sync of every
lock-tracked file) and `render` (the templated-compile subset) are two
verbs the existing test suite already depends on staying distinct and
correctly ordered — `cmd_update`'s "Step 7" runs the per-file resolution
*then* `_do_render`, and `tests/test_render_ordering_guard.py` +
`tests/test_tracked_render_e2e.py` exist specifically to catch a
render-before-core-advance regression. Folding `_do_restore`'s copy-phase
into `ClaudeCodeRenderTarget.render()` would have been a rearchitecture of
that ordering guarantee for no Phase 1 benefit (there is exactly one target
to disambiguate against). This is a documented interpretive choice — flagged
for Fable review — not an oversight.

## Determinism and idempotency

Both properties the interface requires (see `adapters/README.md`) hold
today because `_do_render` is a pure function of `.tess/core/**` bytes +
`operator/*` state: same core, same operator profile → same output, on
every call, on every machine. `tests/test_render_targets.py` asserts this
directly (two independent synthetic projects with identical core content
render byte-identical output; two consecutive calls on one project produce
identical bytes on both calls).

## Doctrine profile (G3, 2026-07-08)

`ClaudeCodeRenderTarget.doctrine_profile == "orchestrator"` — the one case
where the full CLAUDE.md payload (Rule Zero, the six outcome orchestrators,
the mission-ceremony command table) is true of the harness reading it:
Claude Code as Tess genuinely holds the Agent/Task tool. This profile is
UNCHANGED by G3 — the re-scope applied only to `codex`/`generic`'s AGENTS.md
(see `adapters/codex/README.md` "Doctrine profile"). Its own defense is
operational (routing, parallelism, verification discipline, audit trail),
not a claim that the doctrine makes output smarter — the 2026-07-07
proving-ground benchmark could not test a conductor loop and makes no claim
either way for this profile.

## Adding a Phase 2/3 target

See `adapters/README.md` "Adding Phase 2 / Phase 3 targets" for the general
steps. The Codex target is a sibling of `ClaudeCodeRenderTarget`, not a
subclass. Its durable Codex surfaces are `AGENTS.md` and trusted-project
`.codex/config.toml`; it also retains legacy/deprecated `.codex/prompts/*.md`
mirrors that Codex does not discover from the repository. Its process driver
uses `codex exec` separately from rendering.
