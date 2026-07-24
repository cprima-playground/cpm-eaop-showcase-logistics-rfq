# mock-rate — carrier rates per route, actually running

Third bulk Phase-2 system (mechanical, same pattern as `mock-fx`/`mock-tms`).
Built on `rfq_common`. No SSO, no frontend — APIKEY only.

**Depends on masterdata being up** (ADR-010): every rate's `carrier_id` is
validated as a real masterdata Party **with `kind=carrier`** (not just any
Party — a customer id used as a carrier is correctly rejected), and every
`currency` is validated against masterdata's Currency list. Both via real API
calls, fail closed. First system to exercise the **Party** domain (FX/TMS only
ever touched Currency/Location).

## Run it

```sh
# masterdata must be running first
uv run mock-rate serve --port 8005       # Swagger UI at http://localhost:8005/docs
uv run mock-rate rates                    # CLI, no HTTP
uv run mock-rate get-rate SHA-HAM-MUC
uv run mock-rate reset
uv run pytest -v                          # 24 tests
```

```sh
curl -H "X-API-Key: $KEY" http://localhost:8005/rates/SHA-HAM-MUC
curl -H "X-API-Key: $KEY" http://localhost:8005/rates/SHA-HAM-MUC/surcharges
```

`RATE_API_KEY` env or Vault (ADR-009); `RATE_FIXTURES_DIR` overrides the
fixtures location (defaults to `../../systems/rate/fixtures/`).

## Routes

| Route | REST |
| --- | --- |
| List rates | `GET /rates` |
| One rate | `GET /rates/{route_id}` |
| Surcharges | `GET /rates/{route_id}/surcharges` |
| Reset | `POST /admin/reset` |

## Result

25/25 tests green, including 3 that genuinely hit a live masterdata service —
real load, real rejection of an unknown carrier, real fail-closed behavior when
masterdata is unreachable. Verified live end-to-end (`SHA-HAM-MUC` → COSCO,
42000 CNY).
