# tools/geo — route geometry generation + viewer

Generates per-mode GeoJSON geometry for `systems/tms/fixtures/routes.yaml`
(air/sea/rail/road all render differently — straight lines through the ocean
are wrong) and a small Leaflet viewer to eyeball the result. Not a service —
a one-off generation tool, run whenever `routes.yaml` or `maritime_graph.yaml`
change, that writes into `systems/tms/fixtures/route-geometry/`.

## Run it

```sh
uv run --project tools/geo python -m tools.geo.route_geometry                    # all 17 routes
uv run --project tools/geo python -m tools.geo.route_geometry --route-id SHA-HAM-MUC
uv run --project tools/geo python -m tools.geo.route_geometry -v                 # log per-edge routing decisions

uv run --project tools/geo python -m tools.geo.viewer                            # http://127.0.0.1:8000
```

## Input data

| File | Shape | Used for |
| --- | --- | --- |
| `systems/tms/fixtures/routes.yaml` | `routes: [{id, lane, contracted?, legs: [{from, to, mode, duration_days}]}]` | drives generation: one output file per route, one `Feature` per leg |
| `systems/masterdata/fixtures/locations.jsonl` | one JSON object per line: `{locode, name, type, country, timezone, lat, lon}` | resolves every leg's `from`/`to` locode to a real coordinate; **never altered** by this tool |
| `tools/geo/maritime_graph.yaml` | `nodes: {NODE_ID: {name, lat, lon}}`, `edges: [[a, b]]` or `[{edge: [a, b], kind: canal\|segment}]` | the maritime waypoint graph — topology (which chokepoints a sea leg passes through) and per-edge geometry strategy |
| `tools/geo/keepout_zones.yaml` | `zones: [{name, circle: {lat, lon, radius_km}}]` or `[{name, polygon: [[lon, lat], ...]}]` | manual no-go zones merged into the router's blocked mask (piracy risk, uncharted shoal, anything Natural Earth's land layer doesn't capture) — sea legs only, see note below |
| `data/vendor/naturalearth/10m-physical/ne_10m_land/*.shp` | Natural Earth 1:10m land polygon shapefile | ground-truth "is this point/segment actually on land" check (`landmask.is_land`) |
| `data/vendor/naturalearth/50m-physical/ne_50m_land/*.shp` | Natural Earth 1:50m land polygon shapefile (pre-simplified by NE) | the buffered "blocked" mask the router avoids — buffering the 10m layer directly was tried and was minutes-slow |
| `data/vendor/naturalearth/10m-cultural/{ne_10m_ports,ne_10m_airports}/*.shp` | Natural Earth port/airport point shapefiles | downloaded, currently **unused** by the pipeline (no port/airport matching implemented yet) |

`mode` in `routes.yaml` legs is one of `ocean`, `air`, `rail`, `road`.
`kind` in `maritime_graph.yaml` edges defaults to `ocean` if omitted.

## Output data

One `systems/tms/fixtures/route-geometry/<route_id>.geojson` file per route,
a GeoJSON `FeatureCollection`:

```jsonc
{
  "type": "FeatureCollection",
  "bbox": [minLon, minLat, maxLon, maxLat],   // west > east signals an antimeridian-wrapping box
  "metadata": {
    "route_id": "SHA-HAM-MUC",
    "lane": "CNSHA-DEMUC",
    "contracted": true,
    "total_distance_km": 21358.4,             // sum of every leg's routed-polyline length
    "total_duration_days": 29,                // sum of routes.yaml's leg duration_days
    "leg_count": 2
  },
  "features": [
    {
      "type": "Feature",
      "bbox": [minLon, minLat, maxLon, maxLat],   // this leg only
      "properties": {
        "route_id": "SHA-HAM-MUC",
        "leg_index": 0,
        "from": "CNSHA", "to": "DEHAM", "mode": "ocean",
        "duration_days": 27,
        "distance_km": 20746.2,               // along the actual routed polyline, not the endpoint chord
        "waypoints": [
          {"id": "CNSHA", "name": "Shanghai", "lon": 121.47, "lat": 31.23,
           "source": "masterdata", "ref": "locations.jsonl:CNSHA"},
          {"id": "SOUTH_CHINA_SEA_MID", "name": "South China Sea, mid-crossing",
           "lon": 113.0, "lat": 12.0,
           "source": "naturalearth", "ref": "data/vendor/naturalearth/10m-physical/ne_10m_land"}
          // ... every named node the leg's Dijkstra path passed through, in order
        ]
      },
      "geometry": {"type": "LineString", "coordinates": [[lon, lat], ...]}
      // "type": "MultiLineString" with coordinates: [[[lon,lat],...], [[lon,lat],...]]
      // instead, for the 2 transpacific legs that cross the antimeridian
    }
  ]
}
```

One `Feature` per `routes.yaml` leg, in the same order. `waypoints` is only
populated with named graph nodes for `mode: ocean` legs beyond their two
endpoints — `air`/`rail`/`road` legs get just their `from`/`to` as waypoints,
both `source: masterdata`. A waypoint's `source` is `masterdata` (a real
port, `ref` points into `locations.jsonl`) or `naturalearth` (a hand-plotted
chokepoint/buoy, verified against the vendored coastline, `ref` points at
the shapefile it was checked against).

## How each mode is resolved

- **air**: `pyproj.Geod.npts` — a true WGS84 geodesic, densified by distance.
- **rail/road**: unchanged straight 2-point line (out of scope — short inland
  hops, no coastline to avoid).
- **sea**: the interesting part, three layers:
  1. `maritime_graph.yaml` hand-curates the **topology** — which chokepoints
     a lane passes through (Malacca, Suez, Gibraltar, Cape of Good Hope,
     the Danish straits, ...) — and Dijkstra picks the shortest chokepoint
     sequence between a leg's two ports.
  2. Each hop's **geometry** between two chokepoints is one of:
     - `ocean` (default): `ocean_astar.py` — try a direct geodesic first: if
       it doesn't come within Natural Earth's land + clearance buffer, use it.
       Otherwise fall back to a coastline-aware grid A*, then simplify the
       raw grid path with line-of-sight shortcutting so it doesn't zigzag.
     - `canal`: a trusted straight hop, no coastline check at all — for a
       real artificial cut (Suez) or a river mouth (Hamburg/Antwerp/
       Rotterdam's port coordinate sits inland; the coastline dataset can't
       represent either, so there's nothing to check against).
     - `segment`: also a trusted straight hop, but for a long *open-water*
       corridor (Mediterranean transit, Indian Ocean crossing) that's
       hand-plotted with real clearance from land, rather than left to A* —
       A* alone was found hugging/grazing real coastline on long crossings
       even when every sampled point technically tested clear.
  3. `split_antimeridian` breaks anything crossing ±180° into a
     `MultiLineString` (only the transpacific legs hit this).

## Why the graph has so many hand-placed waypoints

Every chokepoint/buoy node in `maritime_graph.yaml` exists because a shorter
version of the graph produced a real bug, in order of discovery:

1. A single geodesic hop between two water points can cut straight across a
   continent (a geodesic bulges toward the pole between similar-latitude
   points) — e.g. Cape of Good Hope → Hamburg direct, or Malacca → Suez
   direct through India/Iran. Fixed by resolving each edge against the
   coastline instead of trusting a raw chord.
2. A real strait narrower than roughly 2x the clearance buffer (~9km) can
   get fully closed by that buffer — Bab-el-Mandeb (~30km) needed splitting
   into two nodes so no single A* run has to cross the pinch.
3. A port's own coordinate can be inland on a river (Hamburg/Antwerp/
   Rotterdam) — invisible to any coastline dataset the same way an
   artificial canal is. Each gets a `kind: canal` connector to its real
   sea mouth.
4. Reaching the Baltic means threading Denmark's islands — no single hop's
   grid resolution can resolve that maze. Chained short waypoints along the
   real deep-draft lane (Skagerrak → Kattegat → Great Belt — not Öresund,
   shallower; not the Kiel Canal, too small for ocean freight) fixed it.
5. A*/direct-chord logic is indifferent between clearing an island by 1km or
   100km, so long open-water crossings visually hugged the coast (Sri Lanka,
   Spain, Crete, Vietnam) even without technically crossing land. Fixed by
   hand-plotting those corridors as `kind: segment` instead.
6. Two different `routes.yaml` entries sharing the same two port endpoints
   (`CNSHA`→`DEHAM`) always resolve to the *same* shortest path — Dijkstra
   doesn't know one of them is supposed to be the Cape-of-Good-Hope
   escalation. Fixed by giving the escalation route an explicit intermediate
   waypoint (`CNSHA`→`ZADUR`→`DEHAM`), same pattern `MEA-CAPE` already used.
7. A keepout zone sized to cover an entire gulf can pinch a real, narrow
   shipping corridor shut with no detour A* can find — a 150km-radius piracy
   zone in the Gulf of Aden broke `HORMUZ`→`BAB_EL_MANDEB` entirely; 60km
   left room to route around it. Radii should stay well under the corridor
   they sit in, not just "generously large."

## Not done yet

`keepout_zones.yaml` only ever feeds `ocean_astar.py`'s blocked mask — it has
no effect on `air` legs, which are still an unconstrained `pyproj.Geod.npts`
geodesic with zero obstacle-avoidance. A NOTAM-style no-fly zone would need
its own check wired into `geodesic_segment`/the air branch of
`build_leg_coords`, not just another `keepout_zones.yaml` entry.
