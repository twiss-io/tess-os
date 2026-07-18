"""Load and validate a routing table: the configurable list of internal
entry points (command + orchestrator + outcome type + signal vocabulary)
the router selects among.

A routing table is the ONE deployment-specific input this whole package
takes. `routing_table.example.yaml` (this repo's own 26 commands + 6
outcome orchestrators — see conductor/commands.md and
conductor/outcome-orchestrators/README.md) is a reference instance, not a
hardcoded default: any tess-os deployment can ship its own table with a
completely different command/orchestrator set and every module in this
package keeps working unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterator, List, Union

import yaml

from .types import IntentRouterError, Route

PathLike = Union[str, Path]


class RoutingTableError(IntentRouterError):
    pass


class RoutingTable(object):
    """An immutable, id-deduplicated collection of `Route`s."""

    def __init__(self, routes: List[Route]):
        if not routes:
            raise RoutingTableError("a routing table must contain at least one route")
        by_id: Dict[str, Route] = {}
        for r in routes:
            if r.id in by_id:
                raise RoutingTableError(f"duplicate route id: {r.id!r}")
            by_id[r.id] = r
        self.routes: List[Route] = list(routes)
        self._by_id: Dict[str, Route] = by_id

    def get(self, route_id: str) -> Route:
        try:
            return self._by_id[route_id]
        except KeyError:
            raise RoutingTableError(f"no such route id: {route_id!r}") from None

    def __contains__(self, route_id: str) -> bool:
        return route_id in self._by_id

    def __len__(self) -> int:
        return len(self.routes)

    def __iter__(self) -> Iterator[Route]:
        return iter(self.routes)

    @classmethod
    def from_list(cls, raw_routes: List[Dict[str, Any]]) -> "RoutingTable":
        routes: List[Route] = []
        for i, raw in enumerate(raw_routes):
            if not isinstance(raw, dict):
                raise RoutingTableError(f"routes[{i}] must be a mapping, got {type(raw).__name__}")
            missing = [f for f in ("id", "entry_command", "outcome_type") if f not in raw]
            if missing:
                raise RoutingTableError(f"routes[{i}] missing required field(s): {missing}")
            routes.append(
                Route(
                    id=raw["id"],
                    entry_command=raw["entry_command"],
                    outcome_type=raw["outcome_type"],
                    description=raw.get("description", ""),
                    orchestrator=raw.get("orchestrator"),
                    default_guilds=list(raw.get("default_guilds", []) or []),
                    keywords=list(raw.get("keywords", []) or []),
                    examples=list(raw.get("examples", []) or []),
                )
            )
        return cls(routes)

    @classmethod
    def load(cls, path: PathLike) -> "RoutingTable":
        """Load a routing table from a YAML file shaped `{routes: [...]}`.
        Fails loud on a missing file, malformed YAML, or missing required
        fields — never silently falls back to an empty or partial table."""
        p = Path(path)
        if not p.is_file():
            raise RoutingTableError(f"routing table not found: {p}")
        with p.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict) or "routes" not in data:
            raise RoutingTableError(f"{p}: expected a top-level 'routes' key holding a list")
        raw_routes = data["routes"]
        if not isinstance(raw_routes, list):
            raise RoutingTableError(f"{p}: 'routes' must be a list")
        return cls.from_list(raw_routes)
