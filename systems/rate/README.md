# Rate Service (built)

**Owns:** ContractRate · CarrierSpotRate · LaneSurcharge. **Interface:** REST,
APIKEY — `src/mock-rate/` (MCP `rate-mcp` still `TARGET`, Phase 3).

Carrier identity (`carrier_id`) and currency are referenced via **masterdata**,
never embedded (ADR-010) — first system to exercise the Party domain, including
correctly rejecting a customer id used as a carrier.

- `fixtures/rates.yaml` — 8 carrier rates (cross-currency: CNY contracted lane, EUR alternatives)
- `cost-model.md` — the correlated, seeded derivation of these rates
- Service: `../../src/mock-rate/README.md` — `uv run mock-rate serve`
