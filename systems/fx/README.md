# Corporate FX Service (mock)

**Owns:** ExchangeRate. **Interface:** `fx-api` / REST (TARGET) — a direct HTTP
dependency, deliberately NOT MCP (deterministic, narrow, centrally managed, easy to
mock). See `../../interfaces/api/fx-api.md`.

Put here: the interface contract (already sketched in `interfaces/api/fx-api.md`),
fixtures (a "today" and a "yesterday" CNY/EUR snapshot to drive the FX-flip), and the
mock spec.

- `fixtures/` — `CNY-EUR-today.json`, `CNY-EUR-yesterday.json` (also under `../../fixtures/fx/`)
- `mock-spec.md` — `GET /exchange-rates/{base}/{quote}?effectiveAt=...`; returns rate · observed_at · valid_until · rate_ref
