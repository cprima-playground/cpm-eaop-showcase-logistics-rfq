# Rate Service (mock)

**Owns:** ContractRate · CarrierSpotRate · LaneSurcharge. **Interface:** `rate-mcp` (TARGET).

Put here: interface contract, fixtures (carrier rates in local currencies — CNY for
route-a, EUR for route-b — plus surcharges), and the mock spec. See
`../systems-of-record.yaml` and `../../interfaces/mcp/tools.yaml`.

- `contract.yaml` — get_contract_rate · get_carrier_rate · get_lane_surcharges
- `fixtures/` — route-a 42000 CNY, route-b 5650 EUR, lane surcharges
- `mock-spec.md`
