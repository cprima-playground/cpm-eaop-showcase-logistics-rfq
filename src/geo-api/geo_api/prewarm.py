"""Startup cache warm-up for ocean legs (M10 follow-up). Found live: a cold
`geo-api-cache` volume made every browser's FIRST /map view of any ocean leg
502 -- ops-dashboard's GeoClient gives up after 60s, but a cold-cache
coastline A* pass genuinely takes minutes-class (README's own words),
confirmed live at 96.5s for CNSHA->DEHAM alone. Warming the demo's known
ocean legs here, before uvicorn.run() starts serving, means the first real
request always hits a warm cache instead of racing that client timeout.

Reads systems/tms/fixtures/routes.yaml directly rather than going through
mock-tms live (unlike masterdata.py's locode resolution, which is required
by D9/ADR-010 to always be live) -- this is a best-effort startup
optimization, not a correctness dependency (D13: cache state is never
authoritative), so a stale/missing/malformed fixture only means a slower
first request, never a wrong one."""

from __future__ import annotations

import concurrent.futures
import re
import time
from pathlib import Path
from typing import Callable

import yaml

from . import routing
from .masterdata import resolve_locode

_OCEAN_EDGE_ID_RE = re.compile(r"^OCEAN-([A-Z0-9]{5})-([A-Z0-9]{5})$")


def ocean_leg_pairs(routes_fixture_path: Path) -> list[tuple[str, str]]:
    """Unique (from_locode, to_locode) pairs for every OCEAN-* edge_id
    referenced anywhere in the routes fixture."""
    if not routes_fixture_path.exists():
        return []
    with routes_fixture_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    pairs: set[tuple[str, str]] = set()
    for route in data.get("routes", []) or []:
        for edge in route.get("edges", []) or []:
            match = _OCEAN_EDGE_ID_RE.match(edge.get("edge_id", ""))
            if match:
                pairs.add((match.group(1), match.group(2)))
    return sorted(pairs)


def warm_ocean_cache(
    *, cache, graph, routing_version: str, masterdata_client,
    routes_fixture_path: Path, max_workers: int = 1,
    log: Callable[[str], None] = lambda msg: print(msg, flush=True),
) -> None:
    pairs = ocean_leg_pairs(routes_fixture_path)
    if not pairs:
        log("prewarm: no ocean legs found in routes fixture, skipping")
        return

    log(f"prewarm: warming {len(pairs)} ocean leg(s) -- cold ones take tens of seconds to minutes each")
    t0 = time.time()

    def _warm_one(pair: tuple[str, str]) -> None:
        from_locode, to_locode = pair
        try:
            from_coord = resolve_locode(masterdata_client, from_locode, {})
            to_coord = resolve_locode(masterdata_client, to_locode, {})
        except Exception as exc:
            log(f"prewarm: skipping {from_locode}->{to_locode}: locode resolution failed: {exc}")
            return

        def _compute() -> dict:
            return routing.compute_leg_geometry(
                mode="ocean", from_locode=from_locode, to_locode=to_locode,
                from_coord=from_coord, to_coord=to_coord, graph=graph,
            )

        t1 = time.time()
        try:
            cache.get_or_compute(
                from_locode=from_locode, to_locode=to_locode, mode="ocean",
                routing_version=routing_version, from_coord=from_coord, to_coord=to_coord,
                compute=_compute,
            )
            log(f"prewarm: {from_locode}->{to_locode} ready in {time.time() - t1:.1f}s")
        except Exception as exc:
            log(f"prewarm: {from_locode}->{to_locode} failed after {time.time() - t1:.1f}s: {exc}")

    # max_workers=1 (sequential) is NOT a tuning choice -- found live:
    # max_workers=6 crashed the process with "free(): corrupted unsorted
    # chunks", a native heap-corruption abort, reproducibly, within the
    # first ~90s of prewarming. That's GEOS/shapely's C extension being
    # called concurrently from multiple threads inside
    # routing.compute_leg_geometry() (coastline A* + shapely ops), and it
    # is NOT thread-safe here. This is a PRE-EXISTING bug this prewarm code
    # only surfaced, not one it introduced: GET /v1/legs/geometry's handler
    # is a plain `def`, which FastAPI already dispatches to its own
    # threadpool for every request -- two real concurrent ocean-leg browser
    # requests hitting a cold cache today would hit the same corruption.
    # Raising max_workers back up is unsafe until that's fixed upstream
    # (e.g. a process-wide lock around compute_leg_geometry, or confirming
    # GEOS's thread-local context handling covers this call path).
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        list(pool.map(_warm_one, pairs))

    log(f"prewarm: done in {time.time() - t0:.1f}s")
