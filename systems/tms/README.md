# TMS (built)

**Owns:** RouteTopology · FeasibleLane · TransitTime · Capacity. **Interface:**
REST, APIKEY — `src/mock-tms/` (MCP `tms-mcp` still `TARGET`, Phase 3).

Route topology + operational availability, two systems of record (stable vs
volatile). Locations referenced via **masterdata**, never embedded (ADR-010) —
`fixtures/locations.yaml` was removed here; masterdata is the sole owner.

- `fixtures/routes.yaml` — topology (13 routes, ~24 legs, 4 lanes: the
  China->Germany corridor plus Transpacific, Middle-East/Suez, Intra-Europe)
- `fixtures/route-availability.yaml` — the volatile overlay (the repricing trigger)
- Service: `../../src/mock-tms/README.md` — `uv run mock-tms serve`
