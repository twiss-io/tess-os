"""connectors — the external-service seam (Tess OS Connectors v1).

This package is documentation + advisory validation tooling for the
`connectors/registry/**` manifests, mirroring `adapters/**`'s split: the
manifests themselves are plain JSON data, never imported at runtime by
`spec_engine` (see `spec_engine.connector_resolver`, which reads them as
raw JSON independently — zero cross-component import edge, same
discipline every other top-level tess-os component applies to itself).

See `connectors/README.md` and `docs/design/connectors-architecture.md`
for the full architecture.
"""

__all__: list = []
