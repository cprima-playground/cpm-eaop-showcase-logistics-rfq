"""Live locode -> coordinate resolution via mock-masterdata (D9, ADR-010) --
geo-api never reads systems/masterdata/fixtures/locations.jsonl directly."""

from __future__ import annotations

from rfq_common.masterdata_client import MasterdataClient

from .log import get_logger

log = get_logger(__name__)


class LocodeNotFoundError(KeyError):
    pass


def resolve_locode(
    client: MasterdataClient, locode: str, request_cache: dict[str, tuple[float, float]],
) -> tuple[float, float]:
    """(lon, lat) for `locode`. `request_cache` is a REQUEST-SCOPED lookup
    cache the caller must create fresh per request (D9's Step 5 correction)
    -- it exists only to avoid re-resolving the same locode twice within one
    leg lookup (e.g. an ocean leg's endpoint also appearing as a dijkstra
    path node), never to persist a resolution across requests. A long-lived
    process-level locode cache would silently defeat D9's staleness check,
    which deliberately depends on a fresh mock-masterdata lookup every time."""
    if locode in request_cache:
        log.trace("resolve_locode: %s (request-scoped cache hit)", locode)
        return request_cache[locode]
    log.trace("resolve_locode: %s (fetching from mock-masterdata)", locode)
    try:
        row = client.get("locations", locode)
    except Exception:
        log.error("resolve_locode: %s: mock-masterdata call failed", locode, exc_info=True)
        raise
    if row is None:
        log.warning("resolve_locode: %s: no masterdata location found", locode)
        raise LocodeNotFoundError(f"no masterdata location for locode {locode!r}")
    coord = (row["lon"], row["lat"])
    request_cache[locode] = coord
    return coord
