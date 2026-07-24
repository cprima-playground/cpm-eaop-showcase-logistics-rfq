# mock-fx — the Corporate FX Service, actually running

First Phase 2 system (build-plan.md). Built on `rfq_common`; realizes
`interfaces/api/fx-api.md` / `fx.openapi.yaml`. Deterministic, seeded from real
historical CNY/EUR snapshots (`fixtures/fx/*.json`) — not a live provider (see
"Mock vs live" in `fx-api.md`). No SSO, no MCP: **APIKEY only**
(`systems/mock-architecture.md`).

**Depends on the masterdata source being up** (ADR-010): every currency in every
FX fixture is validated against masterdata's real API at load time (fail closed
if masterdata is unreachable or a currency is unknown) — `uv run mock-masterdata
serve --port 8003` first, in `../mock-masterdata/`.

## Run it

```sh
# masterdata must be running first (see above)
uv run mock-fx serve --port 8001    # Swagger UI at http://localhost:8001/docs
uv run mock-fx get-rate CNY EUR                              # CLI, no HTTP
uv run mock-fx get-rate CNY EUR --effective-at 2026-07-23T12:00:00Z
uv run mock-fx convert 42000 CNY EUR                          # -> 5014.80 EUR
uv run mock-fx reset                                          # reload fixtures
uv run pytest -v                                              # 37 tests
```

The API key comes from **`FX_API_KEY`** if set, else **Vault** (ADR-009) — there is
no hardcoded default (`KNOWN-ISSUES.md` #1, fixed). Get the seeded value and use it:

```sh
# in infra/vault/: docker compose up -d && uv run seed.py   (once)
KEY=$(curl -s -H "X-Vault-Token: rfq-dev-root" \
  http://localhost:8200/v1/secret/data/rfq/fx-api-key | python -c \
  "import sys,json; print(json.load(sys.stdin)['data']['data']['value'])")
curl -H "X-API-Key: $KEY" http://localhost:8001/exchange-rates/CNY/EUR
curl -H "X-API-Key: $KEY" "http://localhost:8001/convert?amount=42000&from_currency=CNY&to_currency=EUR"
```

`FX_FIXTURES_DIR` overrides the fixtures location (defaults to `../../fixtures/fx/`).
`MASTERDATA_URL` overrides where FX reaches masterdata (defaults to `:8003`).

## What's here

| File | Role |
| --- | --- |
| `store.py` | in-memory FX store; point-in-time lookup; validates every currency via a **real masterdata API call** at load (ADR-010 — never a duplicated file) |
| `convert.py` | currency-conversion rounding — the caveat: **JPY has `minor_unit=0`** (a whole-yen amount, not yen-cents); hardcoding 2 decimals would silently corrupt it |
| `auth.py` | APIKEY dependency — authenticates the caller→backend hop (not Cedar authz) |
| `api.py` | `GET /exchange-rates/{base}/{quote}`, **`GET /convert`**, `POST /admin/reset`, on `rfq_common.create_app` |
| `cli.py` | `reset` / `get-rate` / `convert` / `serve`, on `rfq_common.create_cli` |

Free from `rfq_common.app.create_app`: `/healthz`, `/_theme.css`, Swagger UI at
`/docs`, ReDoc at `/redoc`, raw OpenAPI at `/openapi.json`, the `SHOWCASE` banner
header.

`/convert` returns a **locale-neutral decimal string** (e.g. `"5014.80"`) — i18n/l10n
display formatting (thousands separators, `,` vs `.`) is a frontend concern
(Phase 5), deliberately not done here.

## Result

Verified live (not just tested): `uv run mock-fx serve` + `curl` proved `/healthz`,
`/docs` (200, real Swagger UI), 401 without an API key, the correct rate
(`0.1194`, ref `FX-20260724-CNY-EUR`), and `/convert` (42000 CNY → 5014.80 EUR,
matching the documented golden fixture, both directions). 37/37 tests green,
including 3 that genuinely hit a live masterdata service (not a stub) and prove
fail-closed behavior when it's unreachable or a currency is unknown.

## Phase 2 exit criterion (for this system)

> serves REST + Typer CLI; loads its fixtures; `reset` restores baseline. **Met**
> — and now also consumes the masterdata source via its API, per ADR-010.
