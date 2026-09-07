"""geo-api's routing core, migrated from tools/geo/route_geometry.py (M10 --
precompute-and-commit retired, this is now called live per request instead
of once per CLI run). Implements tmp/geo.md:
  - air:  WGS84 geodesic interpolation (pyproj.Geod.npts)
  - ocean: hand-authored maritime waypoint graph (maritime_graph.yaml) for
    topology + Dijkstra shortest path; each hop's actual geometry is
    resolved by ocean_astar.py against the Natural Earth coastline
    (`kind: canal` edges, i.e. Suez, are a trusted direct hop instead -- a
    raw geodesic chord can cut across land between two water points)
  - rail/road/other: unchanged straight 2-point line
  - antimeridian-crossing legs are split into a GeoJSON MultiLineString

Origin/destination coordinates are whatever the caller resolved live from
mock-masterdata (D9) -- this module never reads a fixture file itself."""

from __future__ import annotations

import hashlib
import heapq
from itertools import pairwise
from pathlib import Path

import yaml
from pyproj import Geod

from . import ocean_astar
from .log import get_logger

log = get_logger(__name__)

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_GRAPH_PATH = PACKAGE_DIR / "maritime_graph.yaml"
DEFAULT_KEEPOUT_PATH = PACKAGE_DIR / "keepout_zones.yaml"

GEOD = Geod(ellps="WGS84")

MIN_POINTS = 20
MAX_POINTS = 100
KM_PER_POINT = 300  # denser interpolation for longer legs, capped at MAX_POINTS

# D8: bumped BY HAND only when the routing ALGORITHM itself changes (A*
# strategy, clearance buffer, chokepoint-splitting logic) -- config-file
# content changes (maritime_graph.yaml / keepout_zones.yaml) are already
# captured by routing_version()'s hash below, no bump needed for those.
ROUTING_ALGORITHM_VERSION = "1"


class GraphLookupError(KeyError):
    """start/end isn't a node in the loaded maritime graph -- distinct from
    a plain KeyError so api routes can translate it into a 422, not a 500."""


class NoMaritimePathError(ValueError):
    """start/end are both graph nodes, but no path connects them."""


def routing_version(graph_path: Path = DEFAULT_GRAPH_PATH, keepout_path: Path = DEFAULT_KEEPOUT_PATH) -> str:
    """D8 -- the exact cache-validity fingerprint:
    sha256(maritime_graph.yaml bytes + keepout_zones.yaml bytes) + ':' +
    ROUTING_ALGORITHM_VERSION. Any change to either config file, or a
    hand-bumped ROUTING_ALGORITHM_VERSION, produces a new value; a cache row
    keyed to an old value simply stops being looked up -- no migration."""
    digest = hashlib.sha256()
    digest.update(graph_path.read_bytes())
    digest.update(keepout_path.read_bytes())
    return f"{digest.hexdigest()}:{ROUTING_ALGORITHM_VERSION}"


class MaritimeGraph:
    """Loaded once at startup (D2), immutable for the process lifetime --
    nodes/adjacency/edge_kind never change after load_graph() returns."""

    def __init__(
        self,
        nodes: dict[str, tuple[float, float]],
        adjacency: dict[str, list[tuple[str, float]]],
        edge_kind: dict[frozenset, str],
    ):
        self.nodes = nodes
        self.adjacency = adjacency
        self.edge_kind = edge_kind


def load_graph(path: Path = DEFAULT_GRAPH_PATH) -> MaritimeGraph:
    """D2: also calls ocean_astar.landmask.register_clear_zone() for every
    node here, before any blocked_geometry()/A* call -- landmask's own
    hard load-order rule, satisfied by construction (this is the only
    place a MaritimeGraph is ever built)."""
    log.info("loading maritime graph from %s", path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    nodes = {node_id: (attrs["lon"], attrs["lat"]) for node_id, attrs in raw["nodes"].items()}
    for lon, lat in nodes.values():
        ocean_astar.landmask.register_clear_zone(lon, lat)
    adjacency: dict[str, list[tuple[str, float]]] = {n: [] for n in nodes}
    edge_kind: dict[frozenset, str] = {}
    for entry in raw["edges"]:
        if isinstance(entry, dict):
            a, b = entry["edge"]
            kind = entry.get("kind", "ocean")
        else:
            a, b = entry
            kind = "ocean"
        _, _, distance_m = GEOD.inv(nodes[a][0], nodes[a][1], nodes[b][0], nodes[b][1])
        adjacency[a].append((b, distance_m))
        adjacency[b].append((a, distance_m))
        edge_kind[frozenset((a, b))] = kind
    log.info("maritime graph loaded: %d nodes, %d edges", len(nodes), len(edge_kind))
    return MaritimeGraph(nodes, adjacency, edge_kind)


def dijkstra(graph: MaritimeGraph, start: str, end: str) -> list[str]:
    if start not in graph.adjacency or end not in graph.adjacency:
        log.error("dijkstra: no graph node for %r or %r", start, end)
        raise GraphLookupError(f"maritime graph has no node for {start!r} or {end!r}")
    dist = {start: 0.0}
    prev: dict[str, str] = {}
    queue = [(0.0, start)]
    visited = set()
    while queue:
        d, node = heapq.heappop(queue)
        if node in visited:
            continue
        visited.add(node)
        if node == end:
            break
        for neighbor, weight in graph.adjacency[node]:
            nd = d + weight
            if nd < dist.get(neighbor, float("inf")):
                dist[neighbor] = nd
                prev[neighbor] = node
                heapq.heappush(queue, (nd, neighbor))
    if end not in dist:
        log.error("dijkstra: no maritime path from %s to %s (%d nodes visited)", start, end, len(visited))
        raise NoMaritimePathError(f"no maritime path from {start} to {end}")
    path = [end]
    while path[-1] != start:
        path.append(prev[path[-1]])
    path.reverse()
    log.trace("dijkstra: %s -> %s via %s", start, end, path)
    return path


def geodesic_segment(p1: tuple[float, float], p2: tuple[float, float]) -> list[tuple[float, float]]:
    """Densified geodesic points from p1 to p2, endpoints included."""
    lon1, lat1 = p1
    lon2, lat2 = p2
    distance_m = GEOD.inv(lon1, lat1, lon2, lat2)[2]
    if distance_m == 0:
        return [p1]
    npts = int(min(MAX_POINTS, max(MIN_POINTS, round(distance_m / 1000 / KM_PER_POINT))))
    intermediate = GEOD.npts(lon1, lat1, lon2, lat2, npts)
    return [p1, *intermediate, p2]


def build_leg_coords(
    *,
    mode: str,
    from_locode: str,
    to_locode: str,
    from_coord: tuple[float, float],
    to_coord: tuple[float, float],
    graph: MaritimeGraph | None,
) -> list[tuple[float, float]]:
    if mode == "air":
        return geodesic_segment(from_coord, to_coord)

    if mode == "ocean":
        if graph is None:
            log.error("build_leg_coords: mode=ocean called with graph=None (%s -> %s)", from_locode, to_locode)
            raise RuntimeError("ocean routing requires a loaded MaritimeGraph")
        log.info("build_leg_coords: ocean leg %s -> %s", from_locode, to_locode)
        path = dijkstra(graph, from_locode, to_locode)
        coords: list[tuple[float, float]] = []
        for a, b in pairwise(path):
            kind = graph.edge_kind[frozenset((a, b))]
            if kind in ("canal", "segment"):
                log.trace("build_leg_coords: %s -> %s is a trusted %s hop", a, b, kind)
                segment = geodesic_segment(graph.nodes[a], graph.nodes[b])
            else:
                segment = ocean_astar.ocean_path(graph.nodes[a], graph.nodes[b])
            coords.extend(segment if not coords else segment[1:])  # drop duplicate join point
        log.info("build_leg_coords: ocean leg %s -> %s done, %d pts total", from_locode, to_locode, len(coords))
        return coords

    # rail / road / other: unchanged straight line, per geo.md scope (air + sea only)
    return [from_coord, to_coord]


def split_antimeridian(coords: list[tuple[float, float]]) -> list[list[tuple[float, float]]]:
    """Split a coordinate list into segments wherever it crosses longitude +-180."""
    segments: list[list[tuple[float, float]]] = [[coords[0]]]
    for (lon1, lat1), (lon2, lat2) in pairwise(coords):
        if abs(lon2 - lon1) > 180:
            if lon1 < 0:
                lon1_unwrapped, lon2_unwrapped, sign = lon1 + 360, lon2, 180.0
            else:
                lon1_unwrapped, lon2_unwrapped, sign = lon1, lon2 + 360, 180.0
            span = lon2_unwrapped - lon1_unwrapped
            t = (sign - lon1_unwrapped) / span if span else 0.5
            cross_lat = lat1 + t * (lat2 - lat1)
            cross_lon = 180.0 if lon1 > 0 else -180.0
            segments[-1].append((cross_lon, cross_lat))
            segments.append([(-cross_lon, cross_lat)])
        segments[-1].append((lon2, lat2))
    return segments


def leg_to_geometry(coords: list[tuple[float, float]]) -> dict:
    segments = split_antimeridian(coords)
    if len(segments) == 1:
        return {"type": "LineString", "coordinates": [list(c) for c in segments[0]]}
    return {
        "type": "MultiLineString",
        "coordinates": [[list(c) for c in seg] for seg in segments],
    }


def leg_distance_km(coords: list[tuple[float, float]]) -> float:
    """Length along the actual (curved/routed) polyline, not the endpoint chord."""
    if len(coords) < 2:
        return 0.0
    lons, lats = zip(*coords)
    return GEOD.line_length(lons, lats) / 1000


def compute_leg_geometry(
    *,
    mode: str,
    from_locode: str,
    to_locode: str,
    from_coord: tuple[float, float],
    to_coord: tuple[float, float],
    graph: MaritimeGraph | None,
) -> dict:
    """The single entry point cache.py's single-flight fill wraps (D10) --
    every uncached (from, to, mode, routing_version) lookup calls this
    exactly once. Returns {"geometry": <GeoJSON geometry>, "distance_km": float}."""
    log.info("compute_leg_geometry: %s -> %s mode=%s: starting", from_locode, to_locode, mode)
    try:
        coords = build_leg_coords(
            mode=mode, from_locode=from_locode, to_locode=to_locode,
            from_coord=from_coord, to_coord=to_coord, graph=graph,
        )
    except Exception:
        log.error("compute_leg_geometry: %s -> %s mode=%s: failed", from_locode, to_locode, mode, exc_info=True)
        raise
    result = {
        "geometry": leg_to_geometry(coords),
        "distance_km": round(leg_distance_km(coords), 1),
    }
    log.info(
        "compute_leg_geometry: %s -> %s mode=%s: done, distance_km=%.1f",
        from_locode, to_locode, mode, result["distance_km"],
    )
    return result
