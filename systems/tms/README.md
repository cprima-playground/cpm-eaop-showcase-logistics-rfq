# TMS (mock)

**Owns:** RouteTopology · FeasibleLane · TransitTime · Capacity. **Interface:** `tms-mcp` (TARGET).

Put here: interface contract, fixtures (feasible lanes + transit + capacity for
`RFQ-1001`, incl. the capacity-rejection state for scenario 02), and the mock spec.
See `../systems-of-record.yaml` and `../../interfaces/mcp/tools.yaml`.

- `contract.yaml` — get_feasible_lanes · get_lane_transit_time · check_lane_capacity · get_route_restrictions
- `fixtures/` — route-a / route-b topology, transit, capacity (available | unavailable)
- `mock-spec.md`
