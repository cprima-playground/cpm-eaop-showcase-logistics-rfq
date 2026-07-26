"""Coastline-aware A* between two lon/lat points, per tmp/geo.md #2.

Grid resolution adapts to the edge's bounding-box span (target_cells per
axis) so a short strait crossing gets a fine grid and a long ocean crossing
gets a coarse one, without a fixed global raster. Antimeridian-spanning
edges are computed in a longitude-shifted (unwrapped) frame so the bbox and
grid stay contiguous; results are wrapped back to [-180, 180] on return.

The raw grid path zigzags along cell edges (see geo.md #5's smoothing step)
-- line-of-sight simplification removes that stepped look by pulling the
path straight wherever a direct chord stays off land, then a final
land-intersection check guards against the simplification cutting a corner.
"""

from __future__ import annotations

import heapq
import logging
import math
from itertools import pairwise

import numpy as np
from pyproj import Geod

from . import landmask

_GEOD = Geod(ellps="WGS84")

log = logging.getLogger(__name__)

TARGET_CELLS = 160  # grid cells along the longer bbox axis, at the UNPADDED span
MIN_RES_DEG = 0.02
MAX_RES_DEG = 1.0
MAX_CELLS_PER_AXIS = 400  # resolution is coarsened (not the search retried) past this
BBOX_PAD_FRACTION = 0.15
MIN_PAD_DEG = 2.0


def _wrap(lon: float) -> float:
    return ((lon + 180.0) % 360.0) - 180.0


def _haversine(p1, p2) -> float:
    lon1, lat1 = p1
    lon2, lat2 = p2
    r1, r2, dlat, dlon = map(math.radians, (lat1, lat2, lat2 - lat1, lon2 - lon1))
    a = math.sin(dlat / 2) ** 2 + math.cos(r1) * math.cos(r2) * math.sin(dlon / 2) ** 2
    return 2 * 6371000.0 * math.asin(math.sqrt(a))


def _shift_for_antimeridian(lon1: float, lon2: float) -> tuple[float, float]:
    if abs(lon1 - lon2) > 180:
        if lon1 < 0:
            lon1 += 360
        else:
            lon2 += 360
    return lon1, lon2


def _build_grid(lon_min, lon_max, lat_min, lat_max, base_res: float):
    """Grid at base_res (fixed per edge -- see ocean_path), coarsened only if
    the padded extent would otherwise blow past MAX_CELLS_PER_AXIS. Keeping
    resolution independent of padding matters: a narrow strait's resolution
    must not degrade just because a *later* retry widened the search box.
    """
    nx = max(2, round((lon_max - lon_min) / base_res) + 1)
    ny = max(2, round((lat_max - lat_min) / base_res) + 1)
    res = base_res
    if max(nx, ny) > MAX_CELLS_PER_AXIS:
        res = base_res * (max(nx, ny) / MAX_CELLS_PER_AXIS)
        nx = max(2, round((lon_max - lon_min) / res) + 1)
        ny = max(2, round((lat_max - lat_min) / res) + 1)
    lons = lon_min + np.arange(nx) * res
    lats = lat_min + np.arange(ny) * res
    lon_grid, lat_grid = np.meshgrid(lons, lats)  # shape (ny, nx)
    blocked = landmask.is_blocked(lon_grid, lat_grid)
    log.debug(
        "grid %dx%d res=%.4f° (~%.0fkm) blocked_frac=%.3f bbox=[%.2f,%.2f]x[%.2f,%.2f]",
        nx,
        ny,
        res,
        res * 111,
        blocked.mean(),
        lon_min,
        lon_max,
        lat_min,
        lat_max,
    )
    return lons, lats, res, blocked


def _nearest_navigable(
    blocked: np.ndarray,
    lons: np.ndarray,
    lats: np.ndarray,
    i: int,
    j: int,
    target: tuple[float, float],
) -> tuple[int, int]:
    """Nearest cell to (i, j) that is both unblocked AND has a blocked-clear
    straight connector to `target` (the real endpoint coordinate).

    The A* path's first/last point gets forcibly replaced by the exact
    target coordinate -- an unchecked connector from whatever cell this
    returns. Checking only "is this cell itself unblocked" (the original
    version of this function) let that connector cross real coastline: at
    coarse resolution the nearest unblocked cell can be tens of km from the
    target, easily on the wrong side of a harbor approach or headland.

    Uses the same `blocked` test as grid navigability (not raw land) so a
    curated node's clear-zone exemption applies to its own approach too --
    e.g. Suez's Gulf-of-Suez funnel is real narrow water, correctly lenient
    here. This is only safe because every node whose *own coordinate* is
    genuinely on land (river/harbor ports like Hamburg, New York, Shanghai)
    is reached via a `kind: canal` bypass instead, never through here.
    """
    ny, nx = blocked.shape
    i = min(max(i, 0), ny - 1)
    j = min(max(j, 0), nx - 1)

    # A connector is meant to be a short local hop, not a long-haul leg -- a
    # capped ring radius means a genuinely walled-off case fails fast into
    # the outer pad-multiplier retry instead of exhausting the whole
    # (possibly huge) grid at ever-growing cost.
    max_ring = min(max(nx, ny), 60)

    def connector_safe(ii, jj):
        candidate = (lons[jj], lats[ii])
        return not landmask.line_crosses_blocked(_geodesic_points(candidate, target))

    for r in range(max_ring):
        for di in range(-r, r + 1):
            for dj in range(-r, r + 1):
                if r > 0 and abs(di) != r and abs(dj) != r:
                    continue  # only the ring at exactly radius r
                ii, jj = i + di, j + dj
                if (
                    0 <= ii < ny
                    and 0 <= jj < nx
                    and not blocked[ii, jj]
                    and connector_safe(ii, jj)
                ):
                    return ii, jj
    raise RuntimeError(
        "no navigable grid cell with a land-clear connector found within "
        f"{max_ring} cells -- retry with wider padding or finer resolution"
    )


_NEIGHBORS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def _astar_grid(blocked: np.ndarray, lons, lats, start, goal) -> list[tuple[int, int]]:
    ny, nx = blocked.shape

    def cell_point(i, j):
        return (lons[j], lats[i])

    def h(node):
        return _haversine(cell_point(*node), cell_point(*goal))

    open_heap = [(h(start), 0.0, start)]
    came_from = {}
    g_score = {start: 0.0}
    visited = set()

    while open_heap:
        _, g, node = heapq.heappop(open_heap)
        if node in visited:
            continue
        visited.add(node)
        if node == goal:
            break
        i, j = node
        for di, dj in _NEIGHBORS:
            ii, jj = i + di, j + dj
            if not (0 <= ii < ny and 0 <= jj < nx) or blocked[ii, jj]:
                continue
            neighbor = (ii, jj)
            step = _haversine(cell_point(i, j), cell_point(ii, jj))
            ng = g + step
            if ng < g_score.get(neighbor, float("inf")):
                g_score[neighbor] = ng
                came_from[neighbor] = node
                heapq.heappush(open_heap, (ng + h(neighbor), ng, neighbor))

    if goal not in came_from and goal != start:
        raise RuntimeError("no navigable grid path found between endpoints")

    path = [goal]
    while path[-1] != start:
        path.append(came_from[path[-1]])
    path.reverse()
    return path


MIN_POINTS = 20
MAX_POINTS = 100
KM_PER_POINT = 300
GEODESIC_STEP_KM = 100  # chord fidelity to the true WGS84 geodesic curve, not a
# land-crossing sampling gap -- crossing itself is now checked exactly
# (line-vs-polygon intersection, see landmask.line_crosses_*), so this only
# needs to be fine enough that consecutive straight chords don't bulge away
# from the geodesic path they approximate


def _geodesic_points(
    p1: tuple[float, float], p2: tuple[float, float]
) -> list[tuple[float, float]]:
    """Points along the true WGS84 geodesic from p1 to p2, not a straight
    lon/lat (rhumb-line) interpolation -- the two diverge enough over long
    distances/high latitudes to change whether a chord clears a coastline.
    """
    distance_m = _haversine(p1, p2)
    npts = min(300, max(0, round(distance_m / 1000 / GEODESIC_STEP_KM) - 1))
    if npts <= 0:
        return [p1, p2]
    intermediate = _GEOD.npts(p1[0], p1[1], p2[0], p2[1], npts)
    return [p1, *intermediate, p2]


def _line_of_sight_simplify(
    points: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    if len(points) <= 2:
        return points
    result = [points[0]]
    i = 0
    n = len(points)
    while i < n - 1:
        j = n - 1
        while j > i + 1 and landmask.line_crosses_blocked(
            _geodesic_points(points[i], points[j])
        ):
            j -= 1
        result.append(points[j])
        i = j
    return result


def _direct_unobstructed(p1: tuple[float, float], p2: tuple[float, float]):
    """A geodesic chord if it never comes within the land clearance margin --
    the "unobstructed shortest path" case. A* only kicks in when this is
    blocked, so open water never gets bent into a grid-shaped detour.
    """
    distance_m = _haversine(p1, p2)
    geodesic = _geodesic_points(p1, p2)
    if landmask.line_crosses_blocked(geodesic):
        return None
    npts = min(MAX_POINTS, max(MIN_POINTS, round(distance_m / 1000 / KM_PER_POINT)))
    if npts <= len(geodesic):
        return geodesic
    return [p1, *_GEOD.npts(p1[0], p1[1], p2[0], p2[1], npts - 2), p2]


# A route that must round a coastal promontory (e.g. Gibraltar -> Hamburg
# has to clear Portugal's Atlantic coast first) needs a bbox wider than the
# two endpoints' own span. Retry with escalating padding rather than
# guessing one padding fraction that would either waste grid resolution on
# the common case or still be too tight for the worst case.
PAD_MULTIPLIERS = (1, 2, 4, 8, 16)


def ocean_path(
    p1: tuple[float, float], p2: tuple[float, float]
) -> list[tuple[float, float]]:
    """Land-avoiding path from p1 to p2, both (lon, lat), endpoints preserved exactly."""
    lon1, lat1 = p1
    lon2, lat2 = p2
    shifted_lon1, shifted_lon2 = _shift_for_antimeridian(lon1, lon2)
    log.debug("edge %s -> %s (distance=%.0fkm)", p1, p2, _haversine(p1, p2) / 1000)

    direct = _direct_unobstructed((shifted_lon1, lat1), (shifted_lon2, lat2))
    if direct is not None:
        log.debug("  direct unobstructed chord, %d pts, skipping A*", len(direct))
        wrapped = [(_wrap(lon), lat) for lon, lat in direct]
        wrapped[0], wrapped[-1] = p1, p2
        return wrapped

    base_lon_min, base_lon_max = sorted((shifted_lon1, shifted_lon2))
    base_lat_min, base_lat_max = sorted((lat1, lat2))
    base_res = min(
        MAX_RES_DEG,
        max(
            MIN_RES_DEG,
            max(base_lon_max - base_lon_min, base_lat_max - base_lat_min)
            / TARGET_CELLS,
        ),
    )
    log.debug(
        "  direct chord blocked, falling back to grid A* (base_res=%.4f°)", base_res
    )

    last_error = None
    for multiplier in PAD_MULTIPLIERS:
        pad_lon = (
            max(MIN_PAD_DEG, (base_lon_max - base_lon_min) * BBOX_PAD_FRACTION)
            * multiplier
        )
        pad_lat = (
            max(MIN_PAD_DEG, (base_lat_max - base_lat_min) * BBOX_PAD_FRACTION)
            * multiplier
        )
        lon_min, lon_max = base_lon_min - pad_lon, base_lon_max + pad_lon
        lat_min = max(-89.0, base_lat_min - pad_lat)
        lat_max = min(89.0, base_lat_max + pad_lat)

        log.debug("  attempt pad=%dx", multiplier)
        lons, lats, res, blocked = _build_grid(
            lon_min, lon_max, lat_min, lat_max, base_res
        )

        try:
            start = _nearest_navigable(
                blocked,
                lons,
                lats,
                round((lat1 - lat_min) / res),
                round((shifted_lon1 - lon_min) / res),
                (shifted_lon1, lat1),
            )
            goal = _nearest_navigable(
                blocked,
                lons,
                lats,
                round((lat2 - lat_min) / res),
                round((shifted_lon2 - lon_min) / res),
                (shifted_lon2, lat2),
            )
            cell_path = _astar_grid(blocked, lons, lats, start, goal)
        except RuntimeError as exc:
            log.debug("  attempt pad=%dx failed: %s", multiplier, exc)
            last_error = exc
            continue

        log.debug(
            "  attempt pad=%dx succeeded, raw path %d cells", multiplier, len(cell_path)
        )
        shifted_points = [(lons[j], lats[i]) for i, j in cell_path]
        shifted_points[0] = (shifted_lon1, lat1)
        shifted_points[-1] = (shifted_lon2, lat2)

        simplified = _line_of_sight_simplify(shifted_points)
        log.debug("  line-of-sight simplified to %d pts", len(simplified))

        # safety net: LOS simplification chords are still validated; if a
        # chord somehow clips land, fall back to the raw (already-valid)
        # grid path.
        for a, b in pairwise(simplified):
            if landmask.line_crosses_land(_geodesic_points(a, b)):
                log.debug(
                    "  LOS simplification clipped land, falling back to raw grid path"
                )
                simplified = shifted_points
                break

        wrapped = [(_wrap(lon), lat) for lon, lat in simplified]
        wrapped[0] = p1  # _wrap()'s float modulo drifts even in-range values
        wrapped[-1] = p2
        return wrapped

    raise RuntimeError(
        f"no navigable path from {p1} to {p2} even at {PAD_MULTIPLIERS[-1]}x padding"
    ) from last_error
