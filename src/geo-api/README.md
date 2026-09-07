# geo-api

M10's on-the-fly route-geometry compute service. Replaces `tools/geo`'s
precompute-and-commit batch CLI (which wrote committed `*.geojson` files
into `systems/tms/fixtures/route-geometry/` and went stale the moment a
route changed): a route's curved geometry is now computed live, the first
time it's asked for, and cached.

## Capability vs. binding

`geo-api` exists to serve one capability today, `route.geometry.compute`,
bound to a specific workload/protocol/deployment:

```
route.geometry.compute  ->  workload.geo-api  ->  REST GET /v1/legs/geometry
   (capability)               (workload)              (protocol binding)
```

**The capability name is stable; the workload/protocol/deployment are
bindings that can change without renaming the capability.** A future
re-platforming (e.g. a managed cloud geospatial service, a different
protocol, a different deployment topology) changes the right side of that
arrow, not the left. Future endpoints on this service (`GET /v1/ports/
nearest`, `GET /v1/keepout-zones`) are expected to follow the same
`/v1/<resource>/<sub-resource-or-action>` naming convention as
`/v1/legs/geometry` — new endpoints slot into the same shape without
renegotiating naming each time.

## Auth

OIDC AuthN via the same Keycloak-introspection path every other workload
in this repo uses (`rfq_common.mcp_auth`) — **no Cedar authorization
decision**. Every authenticated caller gets the same access; this is
stated narrowly as *this service's endpoints need authentication, not a
business authorization decision*, not a blanket claim that no endpoint
added here will ever need one. Mechanically enforced: no source file under
`geo_api/` may reference the real authorization-decision surface
(`tests/test_no_authorization_decisions.py`, same pattern as
mission-control-api's own guard).

`GET /healthz`, `GET /descriptor`, and `GET /v1/provenance` are
unauthenticated, matching every other service's `/healthz`/`/descriptor`
posture — none of the three expose anything sensitive.

## Caching

Cache key: `(from_locode, to_locode, mode, routing_version)` — a
port-pair/mode routing result is reusable across every route that shares
that edge, but only while the inputs that produced it haven't changed.

- **`routing_version`** is `sha256(maritime_graph.yaml bytes +
  keepout_zones.yaml bytes) + ":" + ROUTING_ALGORITHM_VERSION`
  (`geo_api/routing.py`). Any config-file change is picked up
  automatically via the hash; `ROUTING_ALGORITHM_VERSION` is bumped by
  hand only when the *algorithm itself* changes (A* strategy, clearance
  buffer, chokepoint-splitting logic). `GET /v1/provenance` reports the
  combined value plus its components broken out for readability.
- **Resolved coordinates are stored and re-validated on every read**
  (`geo_api/cache.py`): locodes resolve live from `mock-masterdata` on
  every request (never a long-lived process cache — see "locode
  resolution" below), and a cache row whose stored coordinates no longer
  match a fresh resolution is treated as a miss and recomputed, not
  silently served.
- **Cache-fill single-flight is process-local only.** Two concurrent
  requests for the same uncached key, within one process, compute exactly
  once (`geo_api/cache.py`'s per-key lock). Multiple replicas may each
  compute the same cache miss concurrently — this cache does not attempt
  cross-replica deduplication.
- **Deployment invariant: cache state is never authoritative.** Geometry
  computation is deterministic — the same `(from, to, mode,
  routing_version, resolved coordinates)` always produces the same
  result. Cache state is purely a latency optimization. Replicas may run
  independent caches without affecting correctness (SQLite `INSERT ...
  ON CONFLICT DO NOTHING` makes the write idempotent even when two
  replicas race). This is what lets local Compose stay simple (one named
  volume, one replica) while a future horizontally-scaled deployment can
  choose per-instance caches, a shared cache, or a cache service later,
  without changing the API contract or the correctness model.

## Locode resolution

Coordinates are resolved live from `mock-masterdata`'s real
`GET /locations/{locode}` (ADR-010) — this service never reads
`systems/masterdata/fixtures/locations.jsonl` directly. Resolution uses a
**request-scoped** lookup cache only (a plain `dict` built fresh per
request, in `geo_api/api.py`'s route handler) — never a long-lived
process cache. A persistent locode cache would silently defeat the
cache-row staleness check above, which deliberately depends on a fresh
`mock-masterdata` resolution every time.

## Routing

Migrated from `tools/geo/route_geometry.py` (`geo_api/routing.py`),
`tools/geo/landmask.py`, `tools/geo/ocean_astar.py` (unchanged, now
`geo_api/landmask.py` / `geo_api/ocean_astar.py`):

- **air**: WGS84 geodesic interpolation (`pyproj.Geod.npts`).
- **ocean**: Dijkstra over a hand-authored chokepoint graph
  (`geo_api/maritime_graph.yaml`), each hop resolved by a coastline-aware
  A* against vendored Natural Earth land layers (`data/vendor/
  naturalearth`), except `kind: canal` edges (Suez), which are a trusted
  direct hop.
- **rail/road/other**: unchanged straight 2-point line.
- Antimeridian-crossing legs are split into a GeoJSON `MultiLineString`.

Land-mask + `register_clear_zone()` warm-up happens **eagerly at
startup** (`geo_api/cli.py`, before `uvicorn.run()`), not lazily on the
first request — `landmask.register_clear_zone()` has a hard load-order
rule (must run for every graph node before the first `blocked_geometry()`
call) that a server handling concurrent requests must not rely on lazy
first-call ordering to satisfy. `GET /v1/legs/geometry`'s handler stays a
plain `def`, not `async def` — the A* call is CPU-bound and would block
the event loop otherwise; FastAPI dispatches sync handlers to its
threadpool automatically.

## Endpoints

| Endpoint | Auth | What it does |
|---|---|---|
| `GET /v1/legs/geometry?from=<locode>&to=<locode>&mode=<air\|ocean\|rail\|road>` | bearer token | Computes (or serves cached) curved geometry + distance for one leg |
| `GET /v1/provenance` | none | `routing_version` + its components + a Natural Earth data label |
| `GET /descriptor` | none | `kind="platform"`, `skills=["route.geometry.compute"]` |
| `GET /healthz` | none | Liveness |

## Data packaging

`data/vendor/naturalearth` (~7.8 MB) is **baked into this service's
Docker image** (`Dockerfile`'s `COPY`), not bind-mounted — immutable
routing inputs (shapefiles, `maritime_graph.yaml`, `keepout_zones.yaml`)
are versioned with the code that consumes them and belong in the workload
artifact, not a separately-managed mutable volume. This posture holds
regardless of deployment environment; no environment-specific exception
is anticipated for this dataset.

## Running

Part of `infra/compose.showcase.yaml`'s `platform` (or `full`) profile:

```
docker compose -f infra/compose.support.yaml -f infra/compose.showcase.yaml --profile platform up -d --build
```

Reachable at `https://geo.eaop-logistics.localhost` once Caddy picks up the
vhost (`infra/compose/Caddyfile`). Port `8400` — a new port tier
(mocks `800x` / MCP `810x` / agents `820x` / control-plane `830x` /
**platform `840x`**) for real, always-on, non-business, non-agent,
non-MCP services.

`geo-api` joins Mission Control's `ObservedServiceRegistry` like every
other descriptor-bearing service (`interfaces/platform/services.yaml` —
the registry's third roster-derivation source, alongside
`agents/catalog.yaml` and `interfaces/mcp/tools.yaml`).

## Tests

```
uv run pytest tests/
```

No test here requires Docker or a live Keycloak/mock-masterdata to pass
(same discipline as mission-control-api). Deliberately deterministic, not
timing-based — a cache hit is proven by a call-count spy showing the
wrapped compute function was NOT invoked again, never by wall-clock
comparison. Real coastline A* (slow, minutes-class on a cold land-mask
cache) is never exercised by the automated suite — that's a live/manual
smoke test against a running stack (e.g. `CNSHA` -> `DEHAM`, ocean;
confirmed manually during M10 to return ~20,600 km, matching real-world
Shanghai-Hamburg-via-Suez shipping distance).

## Known gap

`tools/geo/viewer/` (a small stdlib-only Leaflet debug page for
inspecting precomputed geometry) was retired along with the rest of
`tools/geo` and was **not** rebuilt against this service's live API in
this pass — an acknowledged, deliberate scope cut, not a silent drop.
