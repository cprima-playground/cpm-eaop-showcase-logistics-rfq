"""Generate per-mode route geometry from systems/tms/fixtures/routes.yaml.

Implements tmp/geo.md:
  - air:  WGS84 geodesic interpolation (pyproj.Geod.npts)
  - sea:  hand-authored maritime waypoint graph (tools/geo/maritime_graph.yaml)
          for topology + Dijkstra shortest path; each hop's actual geometry is
          resolved by ocean_astar.py against the Natural Earth coastline
          (`kind: canal` edges, i.e. Suez, are a trusted direct hop instead --
          a raw geodesic chord can cut across land between two water points)
  - rail/road/other: unchanged straight 2-point line
  - antimeridian-crossing legs are split into GeoJSON MultiLineString

Origin/destination coordinates are always taken verbatim from
systems/masterdata/fixtures/locations.jsonl and never altered.

Usage (run as a module from the repo root -- needs the sibling ocean_astar/
landmask imports, and tools/geo/pyproject.toml's env for the deps):
  uv run --project tools/geo python -m tools.geo.route_geometry
  uv run --project tools/geo python -m tools.geo.route_geometry --route-id SHA-HAM-MUC
"""

from __future__ import annotations

import argparse
import heapq
import json
import logging
from itertools import pairwise
from pathlib import Path

import yaml
from pyproj import Geod

from . import ocean_astar

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOCATIONS = REPO_ROOT / "systems/masterdata/fixtures/locations.jsonl"
DEFAULT_ROUTES = REPO_ROOT / "systems/tms/fixtures/routes.yaml"
DEFAULT_EDGES = REPO_ROOT / "systems/tms/fixtures/edges.yaml"
DEFAULT_GRAPH = Path(__file__).resolve().parent / "maritime_graph.yaml"
DEFAULT_OUT_DIR = REPO_ROOT / "systems/tms/fixtures/route-geometry"

GEOD = Geod(ellps="WGS84")

MIN_POINTS = 20
MAX_POINTS = 100
KM_PER_POINT = 300  # denser interpolation for longer legs, capped at MAX_POINTS


def load_locations(path: Path) -> dict[str, dict]:
    locations = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        locations[rec["locode"]] = {
            "coord": (rec["lon"], rec["lat"]),  # GeoJSON lon,lat order
            "name": rec["name"],
        }
    return locations


def load_routes(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["routes"]


def load_edges(path: Path) -> dict[str, dict]:
    return {e["id"]: e for e in yaml.safe_load(path.read_text(encoding="utf-8"))["edges"]}


def to_legacy_route_shape(route: dict, edges_by_id: dict[str, dict]) -> dict:
    """routes.yaml now stores `lane_id`/`roles`/edge references (real graph
    groundwork -- see systems/tms/fixtures/edges.yaml). This generator's own
    internal leg/route dict shape and GeoJSON OUTPUT property names
    (`from`/`to`/`duration_days`/`lane`/`contracted`) are a separate,
    already-documented stable schema (tools/geo/README.md) -- not worth
    churning just because the input fixture's shape changed. Resolve here,
    once, so every function below stays exactly as it was."""
    return {
        "id": route["id"],
        "lane": route["lane_id"],
        "contracted": "contracted" in route.get("roles", []),
        "legs": [
            {
                "from": edges_by_id[ref["edge_id"]]["origin_id"],
                "to": edges_by_id[ref["edge_id"]]["destination_id"],
                "mode": edges_by_id[ref["edge_id"]]["mode"],
                "duration_days": ref["indicative_duration_days"],
            }
            for ref in route["edges"]
        ],
    }


def load_graph(path: Path, locations: dict[str, dict]):
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    nodes = {
        node_id: (attrs["lon"], attrs["lat"]) for node_id, attrs in raw["nodes"].items()
    }
    # every node is either a masterdata port (identifiable by its locode) or a
    # hand-plotted chokepoint/buoy, chosen and verified against the vendored
    # Natural Earth coastline -- both count as an "external reference" a map
    # viewer's waypoint metadata can cite.
    node_meta: dict[str, dict] = {}
    for node_id, attrs in raw["nodes"].items():
        if node_id in locations:
            node_meta[node_id] = {
                "name": locations[node_id]["name"],
                "source": "masterdata",
                "ref": f"locations.jsonl:{node_id}",
            }
        else:
            node_meta[node_id] = {
                "name": attrs["name"],
                "source": "naturalearth",
                "ref": "data/vendor/naturalearth/10m-physical/ne_10m_land",
            }
    for locode, loc in locations.items():
        if locode in nodes and nodes[locode] != loc["coord"]:
            raise ValueError(
                f"maritime_graph.yaml node {locode} {nodes[locode]} disagrees with "
                f"locations.jsonl {loc['coord']}"
            )
    # every hand-placed node (chokepoint or port) is trusted open water --
    # exempt it from ocean_astar's coastline clearance buffer so a real but
    # narrow approach (e.g. Suez's Gulf-of-Suez mouth) isn't closed by it.
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
    return nodes, adjacency, edge_kind, node_meta


def dijkstra(adjacency, nodes, start: str, end: str) -> list[str]:
    if start not in adjacency or end not in adjacency:
        raise KeyError(f"maritime graph has no node for {start!r} or {end!r}")
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
        for neighbor, weight in adjacency[node]:
            nd = d + weight
            if nd < dist.get(neighbor, float("inf")):
                dist[neighbor] = nd
                prev[neighbor] = node
                heapq.heappush(queue, (nd, neighbor))
    if end not in dist:
        raise ValueError(f"no maritime path from {start} to {end}")
    path = [end]
    while path[-1] != start:
        path.append(prev[path[-1]])
    path.reverse()
    return path


def geodesic_segment(
    p1: tuple[float, float], p2: tuple[float, float]
) -> list[tuple[float, float]]:
    """Densified geodesic points from p1 to p2, endpoints included."""
    lon1, lat1 = p1
    lon2, lat2 = p2
    distance_m = GEOD.inv(lon1, lat1, lon2, lat2)[2]
    npts = int(
        min(MAX_POINTS, max(MIN_POINTS, round(distance_m / 1000 / KM_PER_POINT)))
    )
    if distance_m == 0:
        return [p1]
    intermediate = GEOD.npts(lon1, lat1, lon2, lat2, npts)
    return [p1, *intermediate, p2]


def location_waypoint(locode: str, locations: dict) -> dict:
    lon, lat = locations[locode]["coord"]
    return {
        "id": locode,
        "name": locations[locode]["name"],
        "lon": lon,
        "lat": lat,
        "source": "masterdata",
        "ref": f"locations.jsonl:{locode}",
    }


def graph_waypoint(node_id: str, graph_nodes, node_meta) -> dict:
    lon, lat = graph_nodes[node_id]
    meta = node_meta[node_id]
    return {
        "id": node_id,
        "name": meta["name"],
        "lon": lon,
        "lat": lat,
        "source": meta["source"],
        "ref": meta["ref"],
    }


def build_leg_coords(
    leg: dict, locations, graph_nodes, graph_adjacency, graph_edge_kind, node_meta
) -> tuple[list[tuple[float, float]], list[dict]]:
    origin = locations[leg["from"]]["coord"]
    dest = locations[leg["to"]]["coord"]

    if leg["mode"] == "air":
        return geodesic_segment(origin, dest), [
            location_waypoint(leg["from"], locations),
            location_waypoint(leg["to"], locations),
        ]

    if leg["mode"] == "ocean":
        path = dijkstra(graph_adjacency, graph_nodes, leg["from"], leg["to"])
        coords: list[tuple[float, float]] = []
        for a, b in pairwise(path):
            kind = graph_edge_kind[frozenset((a, b))]
            if kind in ("canal", "segment"):
                segment = geodesic_segment(graph_nodes[a], graph_nodes[b])
            else:
                segment = ocean_astar.ocean_path(graph_nodes[a], graph_nodes[b])
            coords.extend(
                segment if not coords else segment[1:]
            )  # drop duplicate join point
        waypoints = [graph_waypoint(n, graph_nodes, node_meta) for n in path]
        return coords, waypoints

    # rail / road / other: unchanged straight line, per geo.md scope (air + sea only)
    return [origin, dest], [
        location_waypoint(leg["from"], locations),
        location_waypoint(leg["to"], locations),
    ]


def split_antimeridian(
    coords: list[tuple[float, float]],
) -> list[list[tuple[float, float]]]:
    """Split a coordinate list into segments wherever it crosses longitude ±180."""
    segments: list[list[tuple[float, float]]] = [[coords[0]]]
    for (lon1, lat1), (lon2, lat2) in pairwise(coords):
        if abs(lon2 - lon1) > 180:
            # crossing the antimeridian: interpolate the crossing latitude in
            # unwrapped longitude space, then split into two segments.
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


def bbox_of_geometry(geometry: dict) -> list[float]:
    """[minLon, minLat, maxLon, maxLat], or an antimeridian-wrapping box
    (minLon > maxLon, per GeoJSON's own convention) for a MultiLineString.

    Assumes at most one antimeridian crossing per leg -- true for every route
    in this fixture set (only the transpacific legs cross it, exactly once).
    """
    if geometry["type"] == "LineString":
        lons = [c[0] for c in geometry["coordinates"]]
        lats = [c[1] for c in geometry["coordinates"]]
        return [min(lons), min(lats), max(lons), max(lats)]

    segments = geometry["coordinates"]
    all_lats = [c[1] for seg in segments for c in seg]
    # first segment runs from its westmost reach up to +180; last segment
    # runs from -180 up to its eastmost reach -- the box's west/east
    # boundaries are those far ends, not the +-180 crossing point itself.
    west = min(c[0] for c in segments[0])
    east = max(c[0] for c in segments[-1])
    return [west, min(all_lats), east, max(all_lats)]


def merge_bbox(boxes: list[list[float]]) -> list[float]:
    """Combine feature bboxes, correctly even when one leg's bbox wraps the
    antimeridian (west > east) and another's doesn't. Each box's longitude
    coverage is treated as an eastward arc of `span` degrees starting at its
    west edge (span = (east - west) mod 360, which works for both wrapping
    and non-wrapping boxes given GeoJSON's own convention). Arcs are placed
    on a shared unwrapped number line anchored at the first box, and the
    union's start/end is normalized back to [-180, 180] -- if that union
    itself crosses +180, the result naturally comes out as a wrapping box.
    """
    if len(boxes) == 1:
        return boxes[0]
    anchor = boxes[0][0] % 360
    starts_ends = []
    for b in boxes:
        span = (b[2] - b[0]) % 360
        start = b[0] % 360
        while start < anchor - 180:
            start += 360
        while start > anchor + 180:
            start -= 360
        starts_ends.append((start, start + span))
    start = min(s for s, _ in starts_ends)
    end = min(max(e for _, e in starts_ends), start + 360)

    def normalize(x):
        x %= 360
        return x - 360 if x > 180 else x

    return [
        normalize(start),
        min(b[1] for b in boxes),
        normalize(end),
        max(b[3] for b in boxes),
    ]


def build_route_feature_collection(
    route: dict, locations, graph_nodes, graph_adjacency, graph_edge_kind, node_meta
) -> dict:
    features = []
    total_distance_km = 0.0
    for i, leg in enumerate(route["legs"]):
        coords, waypoints = build_leg_coords(
            leg, locations, graph_nodes, graph_adjacency, graph_edge_kind, node_meta
        )
        geometry = leg_to_geometry(coords)
        distance_km = round(leg_distance_km(coords), 1)
        total_distance_km += distance_km
        features.append(
            {
                "type": "Feature",
                "bbox": bbox_of_geometry(geometry),
                "properties": {
                    "route_id": route["id"],
                    "leg_index": i,
                    "from": leg["from"],
                    "to": leg["to"],
                    "mode": leg["mode"],
                    "duration_days": leg["duration_days"],
                    "distance_km": distance_km,
                    "waypoints": waypoints,
                },
                "geometry": geometry,
            }
        )
    return {
        "type": "FeatureCollection",
        "bbox": merge_bbox([f["bbox"] for f in features]),
        "metadata": {
            "route_id": route["id"],
            "lane": route["lane"],
            "contracted": route.get("contracted", False),
            "total_distance_km": round(total_distance_km, 1),
            "total_duration_days": sum(leg["duration_days"] for leg in route["legs"]),
            "leg_count": len(features),
        },
        "features": features,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--locations", type=Path, default=DEFAULT_LOCATIONS)
    parser.add_argument("--routes", type=Path, default=DEFAULT_ROUTES)
    parser.add_argument("--edges", type=Path, default=DEFAULT_EDGES)
    parser.add_argument("--graph", type=Path, default=DEFAULT_GRAPH)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument(
        "--route-id", action="append", help="restrict to these route ids (repeatable)"
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="log per-edge routing decisions (direct vs A*, grid size/resolution, pad retries) to stderr",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(name)s: %(message)s",
    )

    locations = load_locations(args.locations)
    edges_by_id = load_edges(args.edges)
    routes = [to_legacy_route_shape(r, edges_by_id) for r in load_routes(args.routes)]
    graph_nodes, graph_adjacency, graph_edge_kind, node_meta = load_graph(
        args.graph, locations
    )

    if args.route_id:
        wanted = set(args.route_id)
        routes = [r for r in routes if r["id"] in wanted]
        missing = wanted - {r["id"] for r in routes}
        if missing:
            raise SystemExit(f"unknown route id(s): {sorted(missing)}")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for route in routes:
        fc = build_route_feature_collection(
            route, locations, graph_nodes, graph_adjacency, graph_edge_kind, node_meta
        )
        out_path = args.out_dir / f"{route['id']}.geojson"
        out_path.write_text(json.dumps(fc, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {out_path.relative_to(REPO_ROOT)} ({len(fc['features'])} legs)")


if __name__ == "__main__":
    main()
