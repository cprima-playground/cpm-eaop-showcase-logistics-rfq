"""In-memory TMS store: a reusable directed edge pool (stable topology) +
named commercial routes referencing ordered edges + an availability
overlay (volatile) -- three deliberately separate concerns
(systems/reference-data.md). Every edge's location code is validated via a
REAL masterdata API call at load (ADR-010: never a duplicated file) --
TMS's version of FX's currency check.

Route validation is fail-closed at load time: a discontinuous route, a
route that doesn't reach its lane's endpoints, an unknown edge reference,
or a duplicate id anywhere in the pool all raise immediately rather than
silently loading bad topology.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from rfq_common.masterdata_client import MasterdataClient
from rfq_common.models import Route, RouteAvailability, RouteEdge
from rfq_common.store_stats import collection_stats, combine_stats


class UnknownLocationError(ValueError):
    pass


class InvalidTopologyError(ValueError):
    """A route or the edge pool itself fails structural validation --
    unknown edge reference, discontinuous sequence, repeated location,
    lane-endpoint mismatch, duplicate id, or a malformed compatibility
    fixture. Fail closed: bad topology must never load silently."""
    pass


def parse_lane_id(lane_id: str) -> tuple[str, str]:
    """Every lane id today is a clean LOCODE-LOCODE pair -- derived, not
    loaded from a separate Lane file (that convention breaking is the real
    signal to introduce one, not something to guess past)."""
    parts = lane_id.split("-")
    if len(parts) != 2:
        raise InvalidTopologyError(
            f"lane id {lane_id!r} isn't a clean LOCODE-LOCODE pair -- introduce a real Lane record instead of guessing"
        )
    return parts[0], parts[1]


def location_serves_endpoint(location_id: str, lane_endpoint_id: str, compatibility: dict[str, list[str]]) -> bool:
    """Exact-id equality by default; a location also serves an endpoint if
    explicitly declared compatible (e.g. CNPVG airport serving the CNSHA
    seaport-named lane) -- never inferred from a leg's transport mode."""
    return location_id == lane_endpoint_id or location_id in compatibility.get(lane_endpoint_id, [])


class TmsStore:
    def __init__(self, fixtures_dir: str | Path, masterdata_client: MasterdataClient | None = None):
        self._fixtures_dir = Path(fixtures_dir)
        self._masterdata = masterdata_client
        self._location_cache: set[str] = set()
        self._routes: list[Route] = []
        self._availability: dict[str, RouteAvailability] = {}
        self._edges: dict[str, RouteEdge] = {}
        self._lane_endpoint_compatibility: dict[str, list[str]] = {}
        self._edges_by_origin: dict[str, tuple[RouteEdge, ...]] = {}
        self._edges_by_destination: dict[str, tuple[RouteEdge, ...]] = {}
        self.reload()

    def reload(self) -> None:
        edges_doc = yaml.safe_load((self._fixtures_dir / "edges.yaml").read_text(encoding="utf-8"))
        compat_doc = yaml.safe_load(
            (self._fixtures_dir / "lane-endpoint-compatibility.yaml").read_text(encoding="utf-8")
        )
        routes_doc = yaml.safe_load((self._fixtures_dir / "routes.yaml").read_text(encoding="utf-8"))
        avail_doc = yaml.safe_load((self._fixtures_dir / "route-availability.yaml").read_text(encoding="utf-8"))

        compatibility = compat_doc.get("lane_endpoint_compatibility", {}) or {}
        if self._masterdata is not None:
            self._validate_compatibility_fixture(compatibility)

        edges = [RouteEdge.model_validate(e) for e in edges_doc["edges"]]
        if self._masterdata is not None:
            for edge in edges:
                self._validate_location(edge.origin_id)
                self._validate_location(edge.destination_id)
        self._validate_edge_pool(edges)
        edges_by_id = {e.id: e for e in edges}

        routes = [Route.model_validate(r) for r in routes_doc["routes"]]
        self._validate_routes(routes, edges_by_id, compatibility)

        self._edges = edges_by_id
        self._lane_endpoint_compatibility = compatibility
        self._edges_by_origin = self._index_by(edges, key=lambda e: e.origin_id)
        self._edges_by_destination = self._index_by(edges, key=lambda e: e.destination_id)
        self._routes = routes
        self._availability = {
            a["route_id"]: RouteAvailability.model_validate(a) for a in avail_doc["route_availability"]
        }

    @staticmethod
    def _index_by(edges: list[RouteEdge], *, key) -> dict[str, tuple[RouteEdge, ...]]:
        index: dict[str, list[RouteEdge]] = {}
        for edge in sorted(edges, key=lambda e: e.id):
            index.setdefault(key(edge), []).append(edge)
        return {k: tuple(v) for k, v in index.items()}

    def _validate_location(self, code: str) -> None:
        if code in self._location_cache:
            return
        if not self._masterdata.exists("locations", code):
            raise UnknownLocationError(f"masterdata has no location entry for {code!r}")
        self._location_cache.add(code)

    def _validate_compatibility_fixture(self, compatibility: dict[str, list[str]]) -> None:
        for lane_endpoint_id, compatible_ids in compatibility.items():
            self._validate_location(lane_endpoint_id)
            if len(compatible_ids) != len(set(compatible_ids)):
                raise InvalidTopologyError(
                    f"lane-endpoint-compatibility.yaml: duplicate compatible id for {lane_endpoint_id!r}"
                )
            for compatible_id in compatible_ids:
                if compatible_id == lane_endpoint_id:
                    raise InvalidTopologyError(
                        f"lane-endpoint-compatibility.yaml: {lane_endpoint_id!r} redundantly maps to itself"
                    )
                self._validate_location(compatible_id)

    @staticmethod
    def _validate_edge_pool(edges: list[RouteEdge]) -> None:
        seen_ids: set[str] = set()
        seen_triples: set[tuple[str, str, str]] = set()
        for edge in edges:
            if edge.id in seen_ids:
                raise InvalidTopologyError(f"duplicate edge id {edge.id!r}")
            seen_ids.add(edge.id)

            if edge.origin_id == edge.destination_id:
                raise InvalidTopologyError(f"edge {edge.id!r} has identical origin/destination {edge.origin_id!r}")

            expected_id = f"{edge.mode.upper()}-{edge.origin_id}-{edge.destination_id}"
            if edge.id != expected_id:
                raise InvalidTopologyError(
                    f"edge id {edge.id!r} doesn't match its own fields (expected {expected_id!r} or a "
                    f"qualifier-suffixed variant of it)"
                )

            triple = (edge.origin_id, edge.destination_id, edge.mode)
            if triple in seen_triples:
                raise InvalidTopologyError(f"duplicate edge topology {triple!r} (edge {edge.id!r})")
            seen_triples.add(triple)

    @staticmethod
    def _validate_routes(
        routes: list[Route], edges_by_id: dict[str, RouteEdge], compatibility: dict[str, list[str]]
    ) -> None:
        seen_route_ids: set[str] = set()
        for route in routes:
            if route.id in seen_route_ids:
                raise InvalidTopologyError(f"duplicate route id {route.id!r}")
            seen_route_ids.add(route.id)

            if not route.edges:
                raise InvalidTopologyError(f"route {route.id!r} has no edges")

            resolved: list[RouteEdge] = []
            for ref in route.edges:
                edge = edges_by_id.get(ref.edge_id)
                if edge is None:
                    raise InvalidTopologyError(f"route {route.id!r} references unknown edge {ref.edge_id!r}")
                resolved.append(edge)

            for prev_edge, next_edge in zip(resolved, resolved[1:]):
                if prev_edge.destination_id != next_edge.origin_id:
                    raise InvalidTopologyError(
                        f"route {route.id!r} is discontinuous: {prev_edge.id!r} ends at "
                        f"{prev_edge.destination_id!r} but {next_edge.id!r} starts at {next_edge.origin_id!r}"
                    )

            # Full node sequence (origin, then every edge's destination in
            # order) -- a simple path must never revisit a node.
            node_sequence = [resolved[0].origin_id] + [e.destination_id for e in resolved]
            if len(node_sequence) != len(set(node_sequence)):
                raise InvalidTopologyError(
                    f"route {route.id!r} repeats a location in {node_sequence!r} -- "
                    f"named commercial routes must be simple paths"
                )

            lane_origin, lane_destination = parse_lane_id(route.lane_id)
            if not location_serves_endpoint(resolved[0].origin_id, lane_origin, compatibility):
                raise InvalidTopologyError(
                    f"route {route.id!r} starts at {resolved[0].origin_id!r}, not compatible with lane "
                    f"{route.lane_id!r}'s origin {lane_origin!r}"
                )
            if not location_serves_endpoint(resolved[-1].destination_id, lane_destination, compatibility):
                raise InvalidTopologyError(
                    f"route {route.id!r} ends at {resolved[-1].destination_id!r}, not compatible with lane "
                    f"{route.lane_id!r}'s destination {lane_destination!r}"
                )

    def list_edges(self) -> tuple[RouteEdge, ...]:
        return tuple(sorted(self._edges.values(), key=lambda e: e.id))

    def outgoing_edges(self, location_id: str) -> tuple[RouteEdge, ...]:
        return self._edges_by_origin.get(location_id, ())

    def incoming_edges(self, location_id: str) -> tuple[RouteEdge, ...]:
        return self._edges_by_destination.get(location_id, ())

    def resolve_legs(self, route: Route) -> list[dict]:
        """The one, deterministic way a route's edges become a resolved
        leg view: a direct id lookup against the pool, never a graph
        search. Denormalized dict shape for the API layer's `legs`
        response (item 8 of the plan) -- kept here so store and API agree
        on exactly what "resolved" means."""
        legs = []
        for ref in route.edges:
            edge = self._edges[ref.edge_id]
            legs.append({
                "origin_id": edge.origin_id,
                "destination_id": edge.destination_id,
                "mode": edge.mode,
                "indicative_duration_days": ref.indicative_duration_days,
            })
        return legs

    def list_routes(self) -> list[Route]:
        return list(self._routes)

    def get_route(self, route_id: str) -> Route | None:
        return next((r for r in self._routes if r.id == route_id), None)

    def feasible_lanes(self, lane_id: str) -> list[Route]:
        return [r for r in self._routes if r.lane_id == lane_id]

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
        return sum(ref.indicative_duration_days for ref in route.edges)

    def capacity(self, route_id: str) -> str | None:
        avail = self.availability(route_id)
        return avail.status if avail else None

    def stats(self) -> dict:
        return combine_stats(
            collection_stats(self._routes),
            collection_stats(list(self._availability.values())),
        )
