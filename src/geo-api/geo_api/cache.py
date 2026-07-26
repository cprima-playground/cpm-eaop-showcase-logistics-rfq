"""geo_api.cache -- SQLite-backed leg-geometry cache (D1/D8/D9/D10). Keyed
on (from_locode, to_locode, mode, routing_version), not route id -- a
port-pair/mode routing result is reusable across every route sharing that
edge, but only while the inputs that produced it (routing algorithm, graph
config, resolved coordinates) haven't changed.

Deployment invariant (D13, restated in geo-api/README.md): geometry
computation is deterministic, so cache state is never authoritative -- it's
purely an optimization. The single-flight lock below is PROCESS-LOCAL ONLY:
multiple replicas may each compute the same cache miss concurrently.
Correctness survives via SQLite's INSERT ... ON CONFLICT DO NOTHING
(idempotent write, the same row either way); cross-replica deduplication is
a latency optimization this cache does not attempt."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Callable

DEFAULT_DB_PATH = Path("/data/cache/geo-api-cache.sqlite3")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS leg_geometry (
    from_locode TEXT NOT NULL,
    to_locode TEXT NOT NULL,
    mode TEXT NOT NULL,
    routing_version TEXT NOT NULL,
    from_lat REAL NOT NULL,
    from_lon REAL NOT NULL,
    to_lat REAL NOT NULL,
    to_lon REAL NOT NULL,
    geometry_json TEXT NOT NULL,
    distance_km REAL NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (from_locode, to_locode, mode, routing_version)
);
"""

# Float round-trip tolerance (repeated JSON/SQLite storage), not a
# real-world distance margin -- D9's mismatch check must not false-positive
# on the same coordinate resolved twice.
_COORD_EPSILON = 1e-6


class LegGeometryCache:
    """One instance per process. Every operation opens and closes its own
    sqlite3 connection (never a shared long-lived connection across threads
    -- D10) and owns its own per-key single-flight locks."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH, *, clock: Callable[[], float] = time.time):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock
        self._master_lock = threading.Lock()
        self._key_locks: dict[tuple, threading.Lock] = {}
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_schema(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(_SCHEMA)
            conn.commit()
        finally:
            conn.close()

    def _key_lock(self, key: tuple) -> threading.Lock:
        with self._master_lock:
            lock = self._key_locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._key_locks[key] = lock
            return lock

    def _read(self, key: tuple) -> sqlite3.Row | None:
        from_locode, to_locode, mode, routing_version = key
        conn = self._connect()
        try:
            conn.row_factory = sqlite3.Row
            return conn.execute(
                "SELECT * FROM leg_geometry WHERE from_locode=? AND to_locode=? AND mode=? AND routing_version=?",
                (from_locode, to_locode, mode, routing_version),
            ).fetchone()
        finally:
            conn.close()

    def _write(self, key: tuple, *, from_coord: tuple[float, float], to_coord: tuple[float, float], result: dict) -> None:
        from_locode, to_locode, mode, routing_version = key
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO leg_geometry
                    (from_locode, to_locode, mode, routing_version,
                     from_lat, from_lon, to_lat, to_lon, geometry_json, distance_km, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (from_locode, to_locode, mode, routing_version) DO NOTHING
                """,
                (
                    from_locode, to_locode, mode, routing_version,
                    from_coord[1], from_coord[0], to_coord[1], to_coord[0],
                    json.dumps(result["geometry"]), result["distance_km"], self._clock(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_or_compute(
        self, *, from_locode: str, to_locode: str, mode: str, routing_version: str,
        from_coord: tuple[float, float], to_coord: tuple[float, float],
        compute: Callable[[], dict],
    ) -> dict:
        """from_coord/to_coord are (lon, lat), freshly resolved by the
        CALLER for THIS request (D9) -- this cache never resolves locodes
        itself and never caches a coordinate across requests. A cache row
        whose stored coordinates no longer match is treated as a miss and
        recomputed, not silently served -- guards against mock-masterdata
        coordinate drift between the cache write and a later read."""
        key = (from_locode, to_locode, mode, routing_version)

        row = self._read(key)
        if row is not None and _coords_match(row, from_coord, to_coord):
            return _row_to_result(row)

        with self._key_lock(key):
            # Re-check under the per-key lock: a concurrent caller for the
            # SAME key, in THIS process, may already have computed and
            # written it while this one was waiting (D10 -- real
            # single-flight, process-local only, see module docstring).
            row = self._read(key)
            if row is not None and _coords_match(row, from_coord, to_coord):
                return _row_to_result(row)

            result = compute()
            self._write(key, from_coord=from_coord, to_coord=to_coord, result=result)

            # Re-read after write rather than returning `result` directly:
            # a DIFFERENT process/replica (outside this single-flight
            # domain, D13) may have won the INSERT race. The persisted row
            # is the canonical value regardless of who computed it --
            # geometry computation is deterministic, so this is never a
            # correctness concern, only which caller's compute() was wasted.
            row = self._read(key)
            return _row_to_result(row)


def _coords_match(row: sqlite3.Row, from_coord: tuple[float, float], to_coord: tuple[float, float]) -> bool:
    return (
        abs(row["from_lon"] - from_coord[0]) < _COORD_EPSILON
        and abs(row["from_lat"] - from_coord[1]) < _COORD_EPSILON
        and abs(row["to_lon"] - to_coord[0]) < _COORD_EPSILON
        and abs(row["to_lat"] - to_coord[1]) < _COORD_EPSILON
    )


def _row_to_result(row: sqlite3.Row) -> dict:
    return {"geometry": json.loads(row["geometry_json"]), "distance_km": row["distance_km"]}
