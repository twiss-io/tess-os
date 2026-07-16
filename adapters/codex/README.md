# Codex render target — pilot

> **C2 — Manual-gated compatibility.** Tess OS has a registered Codex render
> target and a local `codex exec` driver, but the driver has not been
> live-tested against native event samples. This is not native-parity or
> protected-delivery certification. See
> [Support and status](../../docs/STATUS.md).

Implementation: `CodexRenderTarget` and `CodexExecDriver` in
`.tess/bin/tessctl` (`codex` in `RENDER_TARGETS` and `RUN_DRIVERS`).

## Evidence-backed surface

| Surface | Current behavior |
|---|---|
| `AGENTS.md` | Durable repository guidance rendered by `render_agents_md()`. The generic target renders the same bytes. |
| `.codex/config.toml` | Project settings rendered from `.tess/core/templates/agents-md/codex-config.toml.tpl`. Codex considers project configuration only for a project the operator has marked trusted. |
| `codex exec` driver | `tessctl run --driver codex` invokes a local `codex exec --experimental-json` process and can pass an output schema. The event parser remains provisional until live samples are tested. |
| `.codex/prompts/*.md` | Legacy/deprecated compatibility mirrors of `.tess/core/commands/*.md`. Tess OS still renders and drift-checks them, but Codex does not discover them from the repository. |

The target's `expected_live_bytes()` and `render_generated_paths()` methods
keep all generated files deterministic and drift-checked. That implementation
fact does not turn every generated file into a Codex-native surface.

## Durable Codex surfaces today

- **`AGENTS.md`** is the repository-scoped location for durable instructions,
  commands to run, verification expectations, and project conventions.
- **`.codex/config.toml`** is the repository-scoped configuration fragment.
  It is considered only for a trusted project, and its `approval_policy` and
  `sandbox_mode` values do not grant review authority or branch protection.
- **`codex exec`** is the actual process boundary used by the Tess OS driver.
  It fails clearly if the `codex` binary is absent. A clean process exit is
  currently treated conservatively because native event samples have not yet
  been added to the conformance evidence.
- **Codex skills**, where available, are the preferred reusable-workflow
  surface. This adapter does not currently render or install Codex skills.

## Legacy custom-prompt artifacts

Codex custom prompts are deprecated. Their loader is home-only and reads
Markdown files placed directly at the top level of `$CODEX_HOME/prompts`
(normally `~/.codex/prompts`). It does not discover this project's
`.codex/prompts` directory.

Therefore:

- `.codex/prompts/*.md` is a legacy artifact-preservation surface, not native
  prompt integration;
- Tess OS does not write outside the project to install personal prompts;
- a directory symlink into a nested home subdirectory is not a working
  top-level prompt installation and is not recommended; and
- new durable behavior belongs in `AGENTS.md`, trusted-project
  `.codex/config.toml`, or a Codex skill where the workflow fits.

See OpenAI's
[Custom prompts](https://learn.chatgpt.com/docs/custom-prompts) documentation
for the deprecated personal-prompt boundary. No prompt-installation recipe is
provided here because the Tess OS adapter does not own a user's home directory.

## AGENTS.md ownership

`render_agents_md(root)` takes no harness argument. `CodexRenderTarget` and
`GenericRenderTarget` intentionally produce byte-identical `AGENTS.md` output,
so enabling both does not create an ordering conflict. Their companion
artifacts differ: Codex renders trusted-project configuration and legacy
prompt mirrors, while generic renders plain `prompts/*.md` files.

## Enabling this target

Codex is registered but not enabled by default. Inspect the registry and render
a one-time preview with:

```bash
./tessctl render --list-targets
./tessctl render --target codex
./tessctl doctor
./tessctl verify
```

That command produces the durable `AGENTS.md` and `.codex/config.toml` files
plus the legacy prompt mirrors described above. It does not permanently enable
the target.

There is no `enable-target` CLI command in this build. To opt in for future
unscoped `tessctl render` and update cycles, add `"codex"` to the existing
`tess.manifest.json` list without removing another target unless that is your
explicit intent:

```json
"render_targets": {
  "enabled": ["claude-code", "codex"]
}
```

Then run:

```bash
./tessctl render
./tessctl doctor
./tessctl verify
```

These commands render files and check local integrity. They do not create a
verifier, approval, required Git check, or protected workflow.

## Determinism and doctrine profile

The target is deterministic and idempotent: its artifacts are functions of
`.tess/core/**` plus operator state, with no machine-specific absolute path
embedded. Tests cover byte-identical independent renders, repeat renders, and
drift detection.

`CodexRenderTarget.doctrine_profile == "worker"`. The rendered `AGENTS.md`
stays deliberately lean and does not claim Claude Code-style in-session
subagent dispatch. Process fan-out, when used, happens through the separately
bounded `codex exec` driver rather than a native Tess OS subagent API.
