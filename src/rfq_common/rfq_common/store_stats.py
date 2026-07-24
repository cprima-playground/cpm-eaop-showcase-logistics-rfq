"""Minimal in-memory-store metadata -- quantifies memory pressure without a
new dependency. `approx_bytes` is each item's serialized JSON size summed,
not a true object-graph memory measurement (Python object overhead, shared
references, etc. aren't counted) -- an honest proxy correlated with actual
footprint, not a precise one. Good enough to answer "is this store growing
in a way worth noticing," not a profiler replacement."""

from __future__ import annotations

from pydantic import BaseModel


def collection_stats(items: list[BaseModel]) -> dict:
    return {
        "count": len(items),
        "approx_bytes": sum(len(item.model_dump_json().encode("utf-8")) for item in items),
    }


def combine_stats(*stats: dict) -> dict:
    """Merge multiple collections' stats (e.g. TMS's routes + availability,
    or masterdata's 9 domains) into one summary."""
    return {
        "count": sum(s["count"] for s in stats),
        "approx_bytes": sum(s["approx_bytes"] for s in stats),
    }
