"""Land polygon lookup backed by Natural Earth's land layers.

Vendored at data/vendor/naturalearth/{10m,50m}-physical/ (see
data/vendor/naturalearth/README.md for provenance). Loaded once and reused
by ocean_astar.py for grid rasterization and for post-hoc segment validation.

Two variants are exposed:
  - raw land (is_land / segment_crosses_land): the 10m layer, ground truth
    for "did this actually cross land." Used for the final safety-net check.
  - blocked (is_blocked / segment_crosses_blocked): the 50m layer -- already
    simplified by Natural Earth itself, so buffering it by CLEARANCE_DEG is
    cheap -- plus keepout_zones.yaml circles. This is what the router
    actually avoids, so a path doesn't skim a coastline or an island by a
    few hundred meters just because that's marginally shorter.

    Buffering the 10m layer directly was tried and rejected: tens of
    thousands of vertices made it minutes-slow. CLEARANCE_DEG is also kept
    modest (not the wide margin first tried) -- wide enough to matter in
    open water, narrow enough not to close a real strait under ~2x its
    width (Bab-el-Mandeb is ~30km).

Curated graph nodes (register_clear_zone) are punched back out of the
blocked mask even where they land inside CLEARANCE_DEG of the coastline --
e.g. Suez's Gulf-of-Suez mouth is a natural funnel narrower than the
buffer margin, but it's hand-vetted open water, not a coastline to keep
clear of. A canal edge already skips buffering entirely (it's a direct
trusted hop); a clear zone grants that same trust to the grid-routed
*approach* into a node, rather than to the node's own edge.
"""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path

import numpy as np
import shapefile
import yaml
from shapely import vectorized
from shapely.geometry import LineString, MultiLineString, Point, Polygon, shape
from shapely.ops import unary_union

REPO_ROOT = Path(__file__).resolve().parents[2]
LAND_SHP = (
    REPO_ROOT / "data/vendor/naturalearth/10m-physical/ne_10m_land/ne_10m_land.shp"
)
COARSE_LAND_SHP = (
    REPO_ROOT / "data/vendor/naturalearth/50m-physical/ne_50m_land/ne_50m_land.shp"
)
KEEPOUT_YAML = Path(__file__).resolve().parent / "keepout_zones.yaml"

CLEARANCE_DEG = 0.08  # ~9km at the equator -- clears open-water coast-hugging
# without closing straits much narrower than ~20km
KM_PER_DEG = 111.0  # rough, fine for a circular exclusion radius

CLEAR_ZONE_RADIUS_KM = 25  # generous vs. the ~9km buffer margin being punched out

_land_geom = None
_coarse_land_geom = None
_land_geom_buffered = None
_keepout_geom = None
_blocked_geom = None
_clear_zone_points: list[tuple[float, float]] = []


def _load_shapefile(path: Path):
    sf = shapefile.Reader(str(path))
    return unary_union([shape(s.__geo_interface__) for s in sf.shapes()])


def land_geometry():
    """Unioned Natural Earth 10m land MultiPolygon (WGS84 lon/lat), cached."""
    global _land_geom
    if _land_geom is None:
        _land_geom = _load_shapefile(LAND_SHP)
    return _land_geom


def coarse_land_geometry():
    """Natural Earth's 50m land layer -- editorially simplified by NE, so
    buffering it is fast (unlike buffering the 10m layer directly)."""
    global _coarse_land_geom
    if _coarse_land_geom is None:
        _coarse_land_geom = _load_shapefile(COARSE_LAND_SHP)
    return _coarse_land_geom


def land_geometry_buffered():
    global _land_geom_buffered
    if _land_geom_buffered is None:
        _land_geom_buffered = coarse_land_geometry().buffer(CLEARANCE_DEG)
    return _land_geom_buffered


def _zone_geometry(zone: dict):
    if "circle" in zone:
        c = zone["circle"]
        return Point(c["lon"], c["lat"]).buffer(c["radius_km"] / KM_PER_DEG)
    if "polygon" in zone:
        return Polygon(zone["polygon"])
    raise ValueError(
        f"keepout zone {zone.get('name')!r} has neither 'circle' nor 'polygon'"
    )


def keepout_geometry():
    """Manually declared no-go zones from keepout_zones.yaml, unioned --
    each either a circle (quick) or a polygon (matches how real IMO/UKMTO
    High Risk Area advisories are actually published, as coordinate lists).

    Policy exclusions, not physical land -- merged only into the blocked
    mask the router avoids, never into the raw land truth used for
    pass/fail validation.
    """
    global _keepout_geom
    if _keepout_geom is None:
        zones = (
            yaml.safe_load(KEEPOUT_YAML.read_text(encoding="utf-8")).get("zones") or []
        )
        geoms = [_zone_geometry(z) for z in zones]
        _keepout_geom = unary_union(geoms) if geoms else None
    return _keepout_geom


def register_clear_zone(lon: float, lat: float) -> None:
    """Mark (lon, lat) as hand-vetted open water, exempt from the buffer
    margin. Call before the first blocked_geometry()/is_blocked() use --
    the result is cached and won't pick up later registrations.
    """
    if _blocked_geom is not None:
        raise RuntimeError(
            "blocked_geometry() already cached -- register clear zones first"
        )
    _clear_zone_points.append((lon, lat))


def clear_zone_geometry():
    if not _clear_zone_points:
        return None
    radius_deg = CLEAR_ZONE_RADIUS_KM / KM_PER_DEG
    return unary_union(
        [Point(lon, lat).buffer(radius_deg) for lon, lat in _clear_zone_points]
    )


def blocked_geometry():
    global _blocked_geom
    if _blocked_geom is None:
        geoms = [land_geometry_buffered()]
        keepout = keepout_geometry()
        if keepout is not None:
            geoms.append(keepout)
        blocked = unary_union(geoms)
        clear = clear_zone_geometry()
        if clear is not None:
            blocked = blocked.difference(clear)
        _blocked_geom = blocked
    return _blocked_geom


def _test(geom, lons, lats) -> np.ndarray:
    lons = np.asarray(lons, dtype=float)
    wrapped = ((lons + 180.0) % 360.0) - 180.0
    return vectorized.contains(geom, wrapped, lats)


def is_land(lons, lats) -> np.ndarray:
    """Vectorized land test. lons/lats are same-shape arrays, any dimension.

    lons may be outside [-180, 180] (e.g. antimeridian-shifted, unwrapped
    longitudes used by ocean_astar) -- wrapped to standard range internally.
    """
    return _test(land_geometry(), lons, lats)


def is_blocked(lons, lats) -> np.ndarray:
    return _test(blocked_geometry(), lons, lats)


def _wrap_point(lon: float, lat: float) -> tuple[float, float]:
    return (((lon + 180.0) % 360.0) - 180.0, lat)


def _line_test(geom, points: list[tuple[float, float]]) -> bool:
    """Exact intersection test of a polyline against geom -- no sampling gap
    can miss a landmass narrower than a sample spacing, unlike testing
    discrete interpolated points along the chord.

    Points may be in an antimeridian-shifted (unwrapped, possibly outside
    [-180, 180]) frame -- each is wrapped independently, and the line is
    split wherever consecutive points jump by more than 180 degrees so the
    wrap doesn't draw a spurious line across the whole map.
    """
    wrapped = [_wrap_point(*p) for p in points]
    parts: list[list[tuple[float, float]]] = [[wrapped[0]]]
    for (lon1, lat1), (lon2, lat2) in pairwise(wrapped):
        if abs(lon2 - lon1) > 180:
            if lon1 < 0:
                unwrapped1, unwrapped2, cross_lon = lon1 + 360, lon2, -180.0
            else:
                unwrapped1, unwrapped2, cross_lon = lon1, lon2 + 360, 180.0
            span = unwrapped2 - unwrapped1
            t = (180.0 - unwrapped1) / span if span else 0.5
            cross_lat = lat1 + t * (lat2 - lat1)
            parts[-1].append((cross_lon, cross_lat))
            parts.append([(-cross_lon, cross_lat)])
        parts[-1].append((lon2, lat2))
    lines = [LineString(part) for part in parts if len(part) >= 2]
    if not lines:
        return bool(geom.intersects(Point(wrapped[0])))
    return bool(geom.intersects(MultiLineString(lines) if len(lines) > 1 else lines[0]))


def line_crosses_land(points: list[tuple[float, float]]) -> bool:
    """True if the polyline through `points` touches land anywhere along its
    straight lon/lat segments (not just at the sampled/interpolated points)."""
    return _line_test(land_geometry(), points)


def line_crosses_blocked(points: list[tuple[float, float]]) -> bool:
    return _line_test(blocked_geometry(), points)


def segment_crosses_land(p1: tuple[float, float], p2: tuple[float, float]) -> bool:
    """True if the straight lon/lat chord between p1 and p2 touches land anywhere."""
    return line_crosses_land([p1, p2])


def segment_crosses_blocked(p1: tuple[float, float], p2: tuple[float, float]) -> bool:
    return line_crosses_blocked([p1, p2])
