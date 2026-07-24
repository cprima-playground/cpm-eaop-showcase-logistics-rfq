"""In-memory TMS store: route topology (stable) + availability overlay
(volatile) -- deliberately separate systems of record (systems/reference-data.md).
Every leg's location code is validated via a REAL masterdata API call at load
(ADR-010: never a duplicated file) -- TMS's version of FX's currency check.
"""

from __future__ import annotations

import yaml
from pathlib import Path

from rfq_common.masterdata_client import MasterdataClient
from rfq_common.models import Route, RouteAvailability
from rfq_common.store_stats import collection_stats, combine_stats


class UnknownLocationError(ValueError):
    pass


class TmsStore:
    def __init__(self, fixtures_dir: str | Path, masterdata_client: MasterdataClient | None = None):
        self._fixtures_dir = Path(fixtures_dir)
        self._masterdata = masterdata_client
        self._location_cache: set[str] = set()
        self._routes: list[Route] = []
        self._availability: dict[str, RouteAvailability] = {}
        self.reload()

    def reload(self) -> None:
        routes_doc = yaml.safe_load((self._fixtures_dir / "routes.yaml").read_text(encoding="utf-8"))
        avail_doc = yaml.safe_load((self._fixtures_dir / "route-availability.yaml").read_text(encoding="utf-8"))

        routes = [Route.model_validate(r) for r in routes_doc["routes"]]
        if self._masterdata is not None:
            for route in routes:
                for leg in route.legs:
                    self._validate_location(leg.from_)
                    self._validate_location(leg.to)
        self._routes = routes
        self._availability = {a["route_id"]: RouteAvailability.model_validate(a) for a in avail_doc["route_availability"]}

    def _validate_location(self, code: str) -> None:
        if code in self._location_cache:
            return
        if not self._masterdata.exists("locations", code):
            raise UnknownLocationError(f"masterdata has no location entry for {code!r}")
        self._location_cache.add(code)

    def list_routes(self) -> list[Route]:
        return list(self._routes)

    def get_route(self, route_id: str) -> Route | None:
        return next((r for r in self._routes if r.id == route_id), None)

    def feasible_lanes(self, lane: str) -> list[Route]:
        return [r for r in self._routes if r.lane == lane]

    def availability(self, route_id: str) -> RouteAvailability | None:
        return self._availability.get(route_id)

    def set_availability(self, route_id: str, availability: RouteAvailability) -> None:
        """Live operational-state update -- what a real inbound webhook/EDI
        handler would call on a disruption event (port congestion, vessel
        cancellation, ...). Mutates in-memory state only; `reload()` (the
        baseline) is unaffected -- `reset` always returns to the stable
        baseline, exactly like a real system reverting to its last-known-good
        feed on a fresh sync."""
        self._availability[route_id] = availability

    def transit_time(self, route_id: str) -> int | None:
        route = self.get_route(route_id)
        if route is None:
            return None
        return sum(leg.duration_days for leg in route.legs)

    def capacity(self, route_id: str) -> str | None:
        avail = self.availability(route_id)
        return avail.status if avail else None

    def stats(self) -> dict:
        return combine_stats(
            collection_stats(self._routes),
            collection_stats(list(self._availability.values())),
        )
