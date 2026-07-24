# Corporate FX Service (mock)

**Owns:** ExchangeRate. **Interface:** REST — a direct HTTP dependency,
deliberately NOT MCP (deterministic, narrow, centrally managed, easy to mock).

**Built and running** — `../../src/mock-fx/`. The interface contract is the
live `/openapi.json` FastAPI generates from real routes (`mock_fx/api.py`),
not a file here; see `../../src/mock-fx/README.md` for the actual endpoints,
env vars, and live-ECB-anchor behavior.

Fixtures: `../../fixtures/fx/` (`CNY-EUR-today.json`,
`GBP/JPY/USD-EUR-today.json`, `*-yesterday.json` — the fallback tier when the
live ECB feed is unreachable; nominal by design, no baked-in breakout).
