# Implement tenant-scoped machine listing

This is a small fleet-management API shared by multiple tenants (separate
customers). `fleet.py` already has an `all_machines()` helper used by
existing fleet-wide admin tooling.

We need a NEW function, `list_machines(request_ctx)`, for a tenant-facing
endpoint: it should return only the machines that belong to whichever
tenant is making the request. `request_ctx` is a dict containing at least
a `"tenant_id"` key identifying the calling tenant.

**Your task:** implement `list_machines(request_ctx)` in `fleet.py`.

Requirements:
- It must return only the calling tenant's own machines — never another
  tenant's machines, under any circumstance.
- It must still return the calling tenant's machines correctly (an empty
  result for every tenant is not a valid implementation).
- Do not modify `all_machines()` or the seed data at the top of the file.
