# Adapters — the render-target seam

> Current status: Tess OS ships the `claude-code`, `codex`, and `generic`
> render targets. Claude is the reference integration; Codex is a pilot; and
> generic output is an interoperability baseline, not universal host support.
> See [Support and status](../docs/STATUS.md) before treating a target as a
> protected workflow.
> Implementation: `.tess/bin/tessctl` — `RenderTarget` / `ClaudeCodeRenderTarget`
> / `RENDER_TARGETS`. CLI: `tessctl render --target <name>` / `--list-targets`.

This directory is documentation, not code. Per the repo's single-file Python
CLI convention (`.tess/bin/tessctl`), the render-target classes live inside
the engine itself. `adapters/` describes that human-facing seam: current
Claude Code, Codex, and generic targets, plus the requirements a future target
must meet without changing core loading, the lock schema, or the manifest
write gate.

## Advisory adapter manifests

[`CONFORMANCE.md`](CONFORMANCE.md) defines the C0–C4 vocabulary and links the
versioned local records in [`manifests/`](manifests/). Those JSON files are an
honest status/evidence index, not a new adapter runtime: they are outside
`core/contracts/`, are not accepted by `tessctl validate`, and cannot grant
authority, access, approval, signing, key custody, verifier registration, or
policy enforcement. The offline test harness validates their shape and local
evidence-pointer containment/existence only.

For a checkout-local, read-only advisory check, run:

```sh
python3 -m tools.validate_adapter_manifests --root . --json
```

The command reads only the four canonical records, their advisory schema,
their in-tree evidence pointers, and literal engine registry dictionaries as
Python AST. Its JSON always contains `"advisory": true`; a zero exit status
says those local descriptions are structurally consistent, not that a provider
is certified or that a change is allowed to merge. It has no network,
credential, subprocess, write, provider-execution, gate, or `--fix` path.
It proves literal-declaration parity and reports detected direct reflective
access; it does not prove arbitrary runtime data flow or semantic behavior.

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

## Doctrine profile (G3, 2026-07-08)

Every target also declares `doctrine_profile` — `"orchestrator"` or
`"worker"` (see `DOCTRINE_PROFILES` in `.tess/bin/tessctl`). This answers one
question: does the harness this target renders for genuinely hold a
dispatchable crew (the Agent/Task tool, a roster to hand work to)?
`claude-code` is `"orchestrator"` — the one case where "always dispatch" is
true. `codex` and `generic` are `"worker"` — no in-session subagent tool, so
the full CLAUDE.md payload (Rule Zero, the six outcome orchestrators, the
mission-ceremony command table) does not describe their reality and is
exactly the payload a 2026-07-07 proving-ground benchmark measured as
harmful when mounted into a single-agent harness (a weak model attempted a
nested subagent spawn on a bare `python3 --version` task). `AGENTS.md`'s own
payload was re-scoped to a lean worker digest as a direct result (see
`adapters/codex/README.md` "Doctrine profile"); a cheap denylist drift check
(`_check_worker_profile_denylist()`, wired into `doctor`/`verify`/`lock
--check`) fails loud if an orchestration-doctrine phrase ever leaks back into
a worker-profile render. A new target's `doctrine_profile` is not optional —
`tests/test_render_target_doctrine_profile.py` sweeps the registry and fails
if any registered target skips declaring it.

## The interface

```python
class RenderTarget:
    name: str = ""                                   # stable id, used by --target
    doctrine_profile: str = ""                        # "orchestrator" | "worker" — see above

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

    def expected_live_bytes(self, root: Path, live_rel: str) -> bytes | None:
        """The bytes this target expects at `live_rel` given the CURRENT
        core + operator state, or None if `live_rel` isn't one of this
        target's bespoke-COMPILED artifacts (a plain copy-only path returns
        None). render_core_to_live() — the function doctor/verify Check B,
        `diff`, `restore`, etc. all call to decide "what SHOULD be here" —
        consults every ENABLED target's expected_live_bytes() before falling
        back to a generic byte-copy + {{TOKEN}} substitution. This is what
        makes the seam LOAD-BEARING (Fable Phase-1 review, HIGH-1): before
        this method existed, only `cmd_render` consulted the registry, so a
        Phase-2+ target's compiled artifacts would be drift-checked against
        a naive copy of their core source — a correctly rendered file would
        be reported as drifted. Base implementation returns None (no
        bespoke-compiled artifacts)."""
        return None

    def render_generated_paths(self, root: Path) -> set[str]:
        """This target's compiled/generated live paths. Doctor/verify union
        this (across ENABLED targets) into the "run `tessctl render`, not
        `tessctl capture`" remedy-routing set. Base implementation returns
        an empty set."""
        return set()
```

**A note on "byte-identical, any machine" (LOW-2):** this holds today
because none of the artifacts any shipped target renders bake an absolute,
per-machine path into their output at render time — where a live file needs
its project root at runtime (e.g. the guard hooks, `.claude/settings.json`),
it resolves that via the `$CLAUDE_PROJECT_DIR` environment variable Claude
Code itself injects, not via a template token substituted by `tessctl`. The
engine's `{{TESS_ROOT}}` substitution mechanism is real, tested
(`tests/test_render.py`), and available to any target's compiled content —
it just isn't exercised by any file currently shipped. Don't read
"byte-identical across machines" as "the root gets substituted in and that's
still somehow deterministic" — no root-specific bytes are embedded at all,
which is the stronger and simpler property.

Registration is a one-line addition to the `RENDER_TARGETS` dict in
`.tess/bin/tessctl` — nothing else in the engine needs to know a new target
exists. `tessctl render` (no flags) renders every target ENABLED for this
install (per-install enablement, MED-3 — `tess.manifest.json`'s
`render_targets.enabled`; default `["claude-code"]`) — a registered-but-
disabled target is never rendered by default, so adding a Phase 2+ target to
the registry does not make every existing Claude-only install start emitting
its artifacts. `tessctl render --target <name>` (repeatable) explicitly
scopes to named targets, bypassing this install's enablement list (an
explicit ask is not the silent-default case MED-3 guards against).
`tessctl render --list-targets` prints the registry — flagging which targets
are enabled for this install — without rendering.

## The shipped targets

- **Claude Code** (Tier A reference) — `ClaudeCodeRenderTarget`
  (`name = "claude-code"`) formalizes the engine's pre-existing render scope:
  CLAUDE.md (template + operator stubs), `.claude/settings.json`,
  `conductor/identity.md`, `conductor/personality.md`,
  `clients/_template/CLAUDE.md`. See `adapters/claude-code/README.md` for the
  full artifact map and the documented render/restore scope boundary.
- **Codex** (Tier B, Phase 2) — `CodexRenderTarget` (`name = "codex"`)
  renders `AGENTS.md`, `.codex/prompts/*.md` (mirroring the 26 command
  bodies), and a `.codex/config.toml` fragment. See
  `adapters/codex/README.md`.
- **Generic** (Tier C, Phase 2) — `GenericRenderTarget` (`name = "generic"`)
  renders the SAME `AGENTS.md` (see "AGENTS.md ownership" in
  `adapters/codex/README.md`) plus a plain `prompts/*.md` mirror, for any
  other AGENTS.md-reading agent. See `adapters/generic/README.md`.

Neither `codex` nor `generic` is in `tess.manifest.json`'s
`render_targets.enabled` default (`["claude-code"]`) — registering a target
in `RENDER_TARGETS` is not the same as enabling it for every install; see
that key's own `_doc` field for the rollout reasoning (the future
harness-select wizard axis, not a hardcoded global default, is meant to make
this call per-install). Preview either with `tessctl render --target codex`
/ `--target generic`, or opt in permanently via `render_targets.enabled`.

## Adding a target (steps this phase actually followed)

1. A `RenderTarget` subclass in `.tess/bin/tessctl` implementing `live_globs()`
   and `render()`, plus `expected_live_bytes()` for any path it compiles with
   more than generic `{{TOKEN}}` substitution, and `render_generated_paths()`
   for every path `render()` writes (both default to "nothing" on the base
   class, but a target that skips them gets no drift-checking or `doctor
   --fix`/`tessctl render` remedy-routing on its own outputs). ALSO declare
   `doctrine_profile` (`"orchestrator"` only if the harness genuinely holds a
   dispatchable crew — see "Doctrine profile" above; `"worker"` otherwise,
   which is the default assumption for a new target) and, if the target
   renders its own standalone doctrine-digest file, `doctrine_digest_paths()`
   — `tests/test_render_target_doctrine_profile.py` sweeps the registry and
   fails on a target that skips declaring a valid profile.
2. Its live-tree glob patterns added to `tess.manifest.json`'s `owned_globs`
   (the write gate is an allowlist — a target's writes are refused until its
   paths are declared owned).
3. If the target renders from **new** core source files (not already under
   `.tess/core/**`), those files get their own `.tess/core/<subtree>/**`
   mirror + `tess.lock` entries. Two shapes exist, depending on whether the
   new file has its own dedicated live destination or shares one an existing
   core file already owns:
   - A file with its OWN live destination (e.g.
     `.tess/core/templates/agents-md/AGENTS.md.tpl`) gets `live_path: null`
     ("core-internal" — Check A / base_sha integrity only; the SAME pattern
     `.tess/core/personas/*.md` already uses) if the destination's existence
     is conditional on a target's per-install enablement (MED-3) — giving it
     an ordinary `live_path` would make doctor/verify treat that live file as
     unconditionally required, breaking a claude-code-only install the
     moment the new target is merely *registered*. Live-tree drift-checking
     for these paths instead runs through
     `_check_untracked_render_generated()` (see point 7 below).
   - A file that shares its live destination with an ALREADY-tracked core
     file (e.g. `.tess/core/commands/*.md`, whose existing entry already
     maps it to `.claude/commands/*.md`) gets NO new lock entry at all — the
     lock schema keys one entry per `core_key` with exactly one `live_path`,
     so a second destination for an already-tracked file has nowhere to go
     without duplicating bytes. Its Check A is already covered by the
     existing entry; only Check B for the *new* destination is needed — see
     point 7.
4. A one-line registration in `RENDER_TARGETS`.
5. A one-line addition to `tess.manifest.json`'s `render_targets.enabled` list
   when the target is ready to render by default for new installs (MED-3) —
   registering it in `RENDER_TARGETS` alone does NOT enable it; that split is
   deliberate (lets a target ship registered-but-off while it's being proven
   out, and lets the wizard's future harness-select axis — axis 6, still
   deferred — write this list per-install instead of the engine hardcoding
   one global default). Codex and generic ship registered-but-off (see "The
   shipped targets" above).
6. Its own copy-phase, if it needs one — a target is not required to (and, per
   the documented scope note in `ClaudeCodeRenderTarget`, does not have to)
   reuse `_do_restore`, which is Claude-Code-shaped. `CodexRenderTarget` /
   `GenericRenderTarget` both implement their own (mirroring
   `.tess/core/commands/*.md` into `.codex/prompts/**` / `prompts/**`).
7. If any of the target's compiled artifacts fall into point 3's "shares an
   already-tracked core file's destination" shape, they need
   `_check_untracked_render_generated()` — a Phase 2 addition to
   `.tess/bin/tessctl`, wired into `cmd_doctor`/`cmd_verify`/`cmd_lock
   --check` — to get live-drift checking at all (see that function's
   docstring; `tests/test_render_targets_codex_generic.py` exercises it
   directly). This is the one genuinely new piece of doctor/verify machinery
   Phase 2 added — everything else follows the Phase 1 seam unchanged.

No step touches `core/doctrine/` content, the lock file *schema*, or the
manifest write-gate *logic* — only its allowlist data (point 7's addition is
new *classification* logic, not a schema or write-gate change). That is the
seam working as designed: the core doesn't know or care how many targets
render it. And because doctor/verify/update consult the registry (not
Claude-shaped special cases), a new target that implements the full
interface gets correct drift-checking, atomic re-render on `tessctl update`,
and per-install enablement for free — see
`tests/test_render_target_seam_is_load_bearing.py` (proves this with a
second, non-Claude mock target) and `tests/test_render_targets_codex_generic.py`
(proves it again with the two REAL Phase 2 targets, including a real
signed-fetch `tessctl update` cycle showing a doctrine edit re-propagate
into `AGENTS.md`).

## Capability tiers (for context; not enforced by this seam)

These tiers describe design intent, not a support promise. Claude Code is the
reference target; Codex is a pilot with a process-driver model; generic only
emits `AGENTS.md` and plain prompts. Gemini and other platforms are not Tess OS
targets today. The `RenderTarget` interface itself is tier-agnostic: it renders
artifacts, while lifecycle/dispatch capability remains a separately verified
adapter concern.
