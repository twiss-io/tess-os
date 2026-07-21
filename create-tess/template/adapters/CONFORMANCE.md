# Adapter conformance

Tess OS is provider-neutral in its governance model, not automatically
provider-complete. Every platform is described by a versioned local manifest
and a support level. A manifest records evidence and limits; it never grants
permissions or changes the gate.

## Levels

| Level | Meaning | Public claim allowed |
|---|---|---|
| C0 | No adapter or driver exists. | Not supported. |
| C1 | A bounded, read-only research worker may return cited material. | Research-worker preview only. |
| C2 | Instructions or local artifacts can support a human/manual gate; an unproven local driver may exist. | Manual-gated compatibility preview. |
| C3 | A managed/reference adapter has documented lifecycle evidence beyond C2. | Managed-adapter preview, never protected delivery. |
| C4 | Certified protected workflow. | Only after independent conformance evidence and external admission controls. |

`adapter-manifest.v1` deliberately accepts **C0–C3 only**. A self-authored
JSON file cannot assert C4. C4 requires independent evidence of capability
mapping, artifact provenance, denied actions, version-drift handling,
isolation, and required external enforcement. It also depends on the
production prerequisites in [Support and status](../docs/STATUS.md).

The distinction between C2 and C3 is evidence, not whether a local driver is
present. Codex can expose a local process-driver at C2 while its lifecycle and
native-parity evidence remain incomplete. C3 is the managed/reference-preview
bar; neither level is protected delivery.

## Manifest contract

The advisory schema is
[`contracts/adapter-manifest.schema.json`](contracts/adapter-manifest.schema.json).
Records live in [`manifests/`](manifests/):

- Claude Code — C3 managed-adapter preview
- Codex — C2 manual-gated compatibility preview
- Generic AGENTS.md host — C2 manual-gated compatibility preview
- Perplexity — C0, no adapter or driver

The schema is intentionally outside `core/contracts/`, is not accepted by
`tessctl validate`, and is never a gate, policy, signing, key, verifier, or
approval input. It is validated by a dependency-free offline test harness;
the harness performs no provider calls and writes no repository state. It
checks schema shape plus repository-local evidence-pointer containment and
existence; it does not certify a provider's live behavior.

## Local advisory check

From a source checkout, run:

```sh
python3 -m tools.validate_adapter_manifests --root . --json
```

The result is stable JSON with `"advisory": true`, `"valid"`, and a sorted
`"findings"` list. Exit `0` means the local advisory records are structurally
consistent; exit `1` means they are not. The checker accepts exactly the four
canonical manifests, rejects duplicate JSON keys, symlink/non-regular inputs
and evidence, and compares the fixed claims to literal registry keys parsed
from `.tess/bin/tessctl` with Python AST—without importing or executing that
source.

It is strictly read-only and offline: no provider calls, credentials,
subprocesses, writes, mutation flag, runtime integration, policy decision, or
gate integration exists. A passing result is neither an approval nor C4
certification. It proves literal-declaration parity and reports detected direct
reflective access; it does not prove arbitrary runtime data flow or semantic
behavior.

## Promotion rule

Promotion changes documentation and evidence first; it does not change a
trust boundary by itself. A C4 proposal must be a separate protected change
with independent evidence and the external, human-owned trust-root decision.
Until then, platform labels remain exact descriptions of the artifact surface
that is actually present.
