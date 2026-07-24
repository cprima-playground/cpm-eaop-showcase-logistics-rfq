# mock-fx — the Corporate FX Service, actually running

First Phase 2 system (build-plan.md). Built on `rfq_common`; realizes
`interfaces/api/fx-api.md` / `fx.openapi.yaml`. Deterministic, seeded from real
historical CNY/EUR snapshots (`fixtures/fx/*.json`) — not a live provider (see
"Mock vs live" in `fx-api.md`). No SSO, no MCP: **APIKEY only**
(`systems/mock-architecture.md`).

## Run it

```sh
uv run mock-fx serve --port 8001    # Swagger UI at http://localhost:8001/docs
uv run mock-fx get-rate CNY EUR                              # CLI, no HTTP
uv run mock-fx get-rate CNY EUR --effective-at 2026-07-23T12:00:00Z
uv run mock-fx reset                                          # reload fixtures
uv run pytest -v                                              # 21 tests
```

```sh
curl -H "X-API-Key: dev-fx-key" http://localhost:8001/exchange-rates/CNY/EUR
```

`FX_API_KEY` env overrides the dev default; `FX_FIXTURES_DIR` overrides the
fixtures location (defaults to `../../fixtures/fx/`).

## What's here

| File | Role |
| --- | --- |
| `store.py` | in-memory FX store; point-in-time lookup by `effectiveAt` |
| `auth.py` | APIKEY dependency — authenticates the caller→backend hop (not Cedar authz) |
| `api.py` | `GET /exchange-rates/{base}/{quote}`, `POST /admin/reset`, on `rfq_common.create_app` |
| `cli.py` | `reset` / `get-rate` / `serve`, on `rfq_common.create_cli` |

Free from `rfq_common.app.create_app`: `/healthz`, `/_theme.css`, Swagger UI at
`/docs`, ReDoc at `/redoc`, raw OpenAPI at `/openapi.json`, the `SHOWCASE` banner
header.

## Result

Verified live (not just tested): `uv run mock-fx serve` + `curl` proved `/healthz`,
`/docs` (200, real Swagger UI), 401 without an API key, and the correct rate
(`0.1194`, ref `FX-20260724-CNY-EUR`) with one. 21/21 tests green.

## Phase 2 exit criterion (for this system)

> serves REST + Typer CLI; loads its fixtures; `reset` restores baseline. **Met.**
