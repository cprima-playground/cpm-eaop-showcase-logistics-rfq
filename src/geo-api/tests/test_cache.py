"""Deterministic cache tests (D1/D8/D9/D10) -- no timing-based assertions
("second call measurably faster" was explicitly rejected during planning
review as flaky-under-CI). Every test uses a call-count spy instead: a
cache hit is proven by the wrapped compute function NOT being invoked
again, not by wall-clock comparison."""

from __future__ import annotations

import threading
import time

from geo_api.cache import LegGeometryCache

FROM_COORD = (121.5, 31.2)  # CNSHA-ish, lon/lat
TO_COORD = (9.9, 53.5)  # DEHAM-ish, lon/lat

FAKE_RESULT = {"geometry": {"type": "LineString", "coordinates": [[121.5, 31.2], [9.9, 53.5]]}, "distance_km": 12345.6}


def _spy(result=None):
    calls = {"count": 0}

    def compute():
        calls["count"] += 1
        return result or FAKE_RESULT

    return compute, calls


def test_first_call_is_a_miss_second_call_is_a_hit(tmp_path):
    cache = LegGeometryCache(tmp_path / "cache.sqlite3")
    compute, calls = _spy()

    r1 = cache.get_or_compute(
        from_locode="CNSHA", to_locode="DEHAM", mode="ocean", routing_version="v1",
        from_coord=FROM_COORD, to_coord=TO_COORD, compute=compute,
    )
    r2 = cache.get_or_compute(
        from_locode="CNSHA", to_locode="DEHAM", mode="ocean", routing_version="v1",
        from_coord=FROM_COORD, to_coord=TO_COORD, compute=compute,
    )

    assert calls["count"] == 1  # compute() ran exactly once
    assert r1 == r2 == FAKE_RESULT


def test_a_new_routing_version_is_a_fresh_miss_not_a_stale_hit(tmp_path):
    """D8: changing the routing_version (maritime_graph.yaml/keepout_zones.yaml
    content, or a hand-bumped ROUTING_ALGORITHM_VERSION) must never silently
    reuse a cache row computed under the OLD algorithm/config."""
    cache = LegGeometryCache(tmp_path / "cache.sqlite3")
    compute, calls = _spy()

    cache.get_or_compute(
        from_locode="CNSHA", to_locode="DEHAM", mode="ocean", routing_version="v1",
        from_coord=FROM_COORD, to_coord=TO_COORD, compute=compute,
    )
    cache.get_or_compute(
        from_locode="CNSHA", to_locode="DEHAM", mode="ocean", routing_version="v2",
        from_coord=FROM_COORD, to_coord=TO_COORD, compute=compute,
    )

    assert calls["count"] == 2  # a different routing_version is a different cache row


def test_a_resolved_coordinate_mismatch_is_treated_as_a_miss(tmp_path):
    """D9: a cache row whose stored coordinates no longer match a fresh
    live resolution is recomputed, not silently served -- guards against
    mock-masterdata coordinate drift between the write and a later read."""
    cache = LegGeometryCache(tmp_path / "cache.sqlite3")
    compute, calls = _spy()

    cache.get_or_compute(
        from_locode="CNSHA", to_locode="DEHAM", mode="ocean", routing_version="v1",
        from_coord=FROM_COORD, to_coord=TO_COORD, compute=compute,
    )
    drifted_from_coord = (FROM_COORD[0] + 1.0, FROM_COORD[1])
    cache.get_or_compute(
        from_locode="CNSHA", to_locode="DEHAM", mode="ocean", routing_version="v1",
        from_coord=drifted_from_coord, to_coord=TO_COORD, compute=compute,
    )

    assert calls["count"] == 2  # coordinate drift forced a recompute


def test_only_one_row_is_ever_stored_for_the_same_key(tmp_path):
    db_path = tmp_path / "cache.sqlite3"
    cache = LegGeometryCache(db_path)
    compute, _ = _spy()

    for _ in range(3):
        cache.get_or_compute(
            from_locode="CNSHA", to_locode="DEHAM", mode="ocean", routing_version="v1",
            from_coord=FROM_COORD, to_coord=TO_COORD, compute=compute,
        )

    import sqlite3
    conn = sqlite3.connect(db_path)
    try:
        (count,) = conn.execute("SELECT COUNT(*) FROM leg_geometry").fetchone()
    finally:
        conn.close()
    assert count == 1


def test_concurrent_requests_for_the_same_uncached_key_compute_exactly_once(tmp_path):
    """D10: per-key single-flight, process-local. Every caller waiting on
    the same key must observe the SAME persisted result, and the wrapped
    compute() must never run more than once for it."""
    cache = LegGeometryCache(tmp_path / "cache.sqlite3")
    calls = {"count": 0}
    lock = threading.Lock()

    def compute():
        with lock:
            calls["count"] += 1
        time.sleep(0.05)  # widen the race window so concurrent callers actually overlap
        return FAKE_RESULT

    results: list[dict] = []
    results_lock = threading.Lock()

    def worker():
        r = cache.get_or_compute(
            from_locode="CNSHA", to_locode="DEHAM", mode="ocean", routing_version="v1",
            from_coord=FROM_COORD, to_coord=TO_COORD, compute=compute,
        )
        with results_lock:
            results.append(r)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert calls["count"] == 1
    assert len(results) == 8
    assert all(r == FAKE_RESULT for r in results)


def test_different_keys_never_block_each_other(tmp_path):
    cache = LegGeometryCache(tmp_path / "cache.sqlite3")
    compute_a, calls_a = _spy({"geometry": {"type": "LineString", "coordinates": []}, "distance_km": 1.0})
    compute_b, calls_b = _spy({"geometry": {"type": "LineString", "coordinates": []}, "distance_km": 2.0})

    ra = cache.get_or_compute(
        from_locode="CNSHA", to_locode="DEHAM", mode="ocean", routing_version="v1",
        from_coord=FROM_COORD, to_coord=TO_COORD, compute=compute_a,
    )
    rb = cache.get_or_compute(
        from_locode="USLAX", to_locode="NLRTM", mode="ocean", routing_version="v1",
        from_coord=FROM_COORD, to_coord=TO_COORD, compute=compute_b,
    )

    assert calls_a["count"] == 1
    assert calls_b["count"] == 1
    assert ra["distance_km"] == 1.0
    assert rb["distance_km"] == 2.0
