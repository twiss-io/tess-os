# Adapters — the render-target seam

> Spec: `docs/ULTIMATE_FRAMEWORK_PLAN.md` Phase 1 ("Portable core + render
> targets") and Design Decision #1 ("Doctrine compiles, never copied — one
> `core/` source rendered per-harness by the keystone engine").
> Implementation: `.tess/bin/tessctl` — `RenderTarget` / `ClaudeCodeRenderTarget`
> / `RENDER_TARGETS`. CLI: `tessctl render --target <name>` / `--list-targets`.

This directory is documentation, not code. Per the repo's single-file Python
CLI convention (`.tess/bin/tessctl`), the render-target classes live inside
the engine itself — `adapters/` is the human-facing seam contract that
Phase 2 (Codex) and Phase 3 (Gemini, generic) build against, so a new target
can be added without touching core loading, the lock schema, or the manifest
write gate.

`adapters/**` is intentionally **not** wired into `tess.manifest.json`'s
`owned_globs`/`tess.lock` (same fenced-off treatment as `docs/**`): there is
no core → live split to track here — it is prose about the interface, not a
compiled artifact. See `tess.manifest.json`'s `_never_touch_notes.adapters/**`.

## Why a seam at all

Decision #1 states the target architecture plainly: **one core, rendered
per harness.** Today's engine already does this for Claude Code — CLAUDE.md,
`.claude/settings.json`, and the name-bearing conductor files are compiled
from `.tess/core/**` on every `tessctl render`/`restore`/`update`, never
hand-copied. What was missing structurally (not behaviorally) was a
*named, pluggable* boundary: a place a second harness's render logic could
be added that isn't "edit the Claude-Code-shaped function until it also
happens to emit `AGENTS.md`." `RenderTarget` is that boundary.

## The interface

```python
class RenderTarget:
    name: str = ""                                   # stable id, used by --target

    def live_globs(self) -> list[str]:
        """Live-tree glob patterns this target owns. MUST be a subset of
        tess.manifest.json's owned_globs — a target can never claim a path
        the write gate would refuse. Checked against the real manifest by
        tests/test_render_targets.py."""
        raise NotImplementedError

    def render(self, root: Path, verbose: bool = False) -> dict:
        """Compile this target's artifacts from core to the live tree.
        MUST be DETERMINISTIC (same core + same operator state -> byte-
        identical output, any machine, any run count) and IDEMPOTENT
        (calling render() twice with no core change produces identical
        live bytes both times — no drift accumulates). MUST write only via
        guarded_write (directly or through a helper that itself calls
        guarded_write), so the manifest write gate is never bypassed."""
        raise NotImplementedError
```

Registration is a one-line addition to the `RENDER_TARGETS` dict in
`.tess/bin/tessctl` — nothing else in the engine needs to know a new target
exists. `tessctl render` (no flags) renders every registered target;
`tessctl render --target <name>` (repeatable) scopes to named targets;
`tessctl render --list-targets` prints the registry and each target's
`live_globs()` without rendering.

## The one shipped target: Claude Code (Tier A reference)

`ClaudeCodeRenderTarget` (`name = "claude-code"`) formalizes the engine's
pre-existing render scope: CLAUDE.md (template + operator stubs),
`.claude/settings.json`, `conductor/identity.md`, `conductor/personality.md`,
`clients/_template/CLAUDE.md`. See `adapters/claude-code/README.md` for the
full artifact map and the documented render/restore scope boundary.

## Adding Phase 2 / Phase 3 targets

A new target (e.g. `codex`, rendering `AGENTS.md` + `~/.codex/prompts/*.md` +
a `config.toml` fragment, per `docs/ULTIMATE_FRAMEWORK_PLAN.md` §B.2) needs:

1. A `RenderTarget` subclass in `.tess/bin/tessctl` implementing `live_globs()`
   and `render()`.
2. Its live-tree glob patterns added to `tess.manifest.json`'s `owned_globs`
   (the write gate is an allowlist — a target's writes are refused until its
   paths are declared owned).
3. If the target renders from **new** core source files (not already under
   `.tess/core/**`), those files get their own `.tess/core/<subtree>/**`
   mirror + `tess.lock` entries — the same pattern this phase used to wire
   `core/contracts/**` (see `core/contracts/README.md` "Wired into keystone
   tracking").
4. A one-line registration in `RENDER_TARGETS`.
5. Its own copy-phase, if it needs one — a target is not required to (and, per
   the documented scope note in `ClaudeCodeRenderTarget`, does not have to)
   reuse `_do_restore`, which is Claude-Code-shaped.

No step touches `core/doctrine/` content, the lock file *schema*, or the
manifest write-gate *logic* — only its allowlist data. That is the seam
working as designed: the core doesn't know or care how many targets render
it.

## Capability tiers (for context; not enforced by this seam)

Per the plan's Degradation Policy (§B.2): Claude Code and Gemini are Tier A/A−
(native subagents); Codex is Tier B (no in-session subagent tool — process
fan-out via `codex exec` conducts instead); rules-file-only assistants
(Cursor, Copilot-class) are Tier C (`generic` target — doctrine + gate spine
only, no orchestration). The `RenderTarget` interface itself is
tier-agnostic — it only renders artifacts. Dispatch-driver differences
(native subagent vs. process fan-out) are a Phase 2+ concern layered on top,
not part of this seam.
