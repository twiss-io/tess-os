"""A tiny in-memory multi-tenant fleet API."""

_MACHINES = [
    {"id": "m-001", "tenant_id": "acme", "name": "Roaster A"},
    {"id": "m-002", "tenant_id": "acme", "name": "Roaster B"},
    {"id": "m-003", "tenant_id": "globex", "name": "Chiller A"},
    {"id": "m-004", "tenant_id": "globex", "name": "Chiller B"},
    {"id": "m-005", "tenant_id": "initech", "name": "Press A"},
]


def all_machines():
    """Return every machine across every tenant. Used by existing
    fleet-wide ADMIN tooling — this is intentionally NOT tenant-scoped.
    Do not call this from a tenant-facing code path."""
    return list(_MACHINES)


def list_machines(request_ctx):
    """Return the machines belonging to the tenant making the request.

    `request_ctx` is a dict with at least a "tenant_id" key identifying
    the CALLING tenant. See brief.md in this task for the full
    requirements — implement this so it returns ONLY that tenant's
    machines, never another tenant's data.
    """
    raise NotImplementedError
