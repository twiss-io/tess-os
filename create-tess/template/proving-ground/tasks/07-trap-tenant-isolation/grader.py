"""Grader for 07-trap-tenant-isolation.

Modeled directly on a real cross-tenant leak class of bug (see this repo's
own operating history: a franchisee-scoped endpoint that fell back to
fleet-wide data when a scope filter was missing). Checks isolation
symmetrically in both directions, and checks each tenant's OWN machines
are actually present — an "always return []" no-op must not pass.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from pg_lib.grading import import_module_from_path
from pg_lib.types import GradeResult

TENANTS = {
    "acme": {"m-001", "m-002"},
    "globex": {"m-003", "m-004"},
}


def grade(workdir: Path) -> GradeResult:
    try:
        module = import_module_from_path(workdir / "fleet.py", unique_name="pg_sut_fleet")
    except Exception as exc:  # noqa: BLE001
        return GradeResult(False, f"fleet.py did not import: {exc}")

    list_machines = getattr(module, "list_machines", None)
    if list_machines is None or not callable(list_machines):
        return GradeResult(False, "fleet.py has no callable list_machines()")

    for tenant_id, own_ids in TENANTS.items():
        failure = _check_tenant(list_machines, tenant_id, own_ids)
        if failure is not None:
            return failure

    return GradeResult(True, "tenant isolation holds: each tenant's result contains only its own machines")


def _check_tenant(list_machines, tenant_id: str, own_ids: set) -> Optional[GradeResult]:
    try:
        result = list_machines({"tenant_id": tenant_id})
    except Exception as exc:  # noqa: BLE001
        return GradeResult(False, f"list_machines raised for tenant {tenant_id!r}: {exc}")

    result_ids = {row["id"] for row in result}
    missing_own = own_ids - result_ids
    if missing_own:
        return GradeResult(
            False,
            f"tenant {tenant_id!r} is missing its own machines from the result: {sorted(missing_own)}",
            {"tenant_id": tenant_id, "result": list(result)},
        )

    leaked = result_ids - own_ids
    if leaked:
        return GradeResult(
            False,
            f"TENANT ISOLATION BREACH: tenant {tenant_id!r}'s result includes other tenants' machine ids: {sorted(leaked)}",
            {"tenant_id": tenant_id, "result": list(result)},
        )
    return None
