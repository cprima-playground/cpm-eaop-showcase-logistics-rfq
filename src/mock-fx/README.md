# mock-fx — the Corporate FX Service, actually running

First Phase 2 system (build-plan.md). Built on `rfq_common`; the live
`/openapi.json` it serves (FastAPI-generated from real routes, `mock_fx/api.py`)
IS the interface contract — no separate hand-authored spec file.
**Live by default**: on boot
and every `reset`, fetches the ECB's real public daily reference-rate history
(`ecb_client.py`, `eurofxref-hist-90d.xml`) for USD/GBP/JPY/CNY vs EUR — the
baseline carries **no breakout by design**; a breakout is a scenario-pack
concept, never baked into default state. Opt-out via `FX_LIVE_ANCHOR=0`. Three
fallback tiers if the live feed can't be reached: (1) live fetch, (2) a
manually-downloaded copy of the same feed (`FX_ECB_HIST_FILE` — open
`eurofxref-hist-90d.xml` in a browser, Ctrl+S, point the env var at the saved
file), (3) committed fixture snapshots (`fixtures/fx/*.json`) plus a
**generated** 28-day run-up (`generator.py`, seeded via `rfq_common.clock` —
never committed as fixture files). Not a live *trading* provider — no SSO,
no MCP: **APIKEY only** (`systems/mock-architecture.md`).

**Depends on the masterdata source being up** (ADR-010): every currency in every
FX fixture is validated against masterdata's real API at load time (fail closed
if masterdata is unreachable or a currency is unknown) — `uv run mock-masterdata
serve --port 8003` first, in `../mock-masterdata/`.

## Run it

```sh
# masterdata must be running first (see above)
uv run mock-fx serve --port 8001    # Swagger UI at http://localhost:8001/swagger
uv run mock-fx get-rate CNY EUR                              # CLI, no HTTP
uv run mock-fx get-rate CNY EUR --effective-at 2026-07-23T12:00:00Z
uv run mock-fx convert 42000 CNY EUR                          # -> 5451.22 EUR (live) / varies offline
uv run mock-fx reset                                          # re-fetch ECB (or reload fixtures, offline)
uv run pytest -v                                              # 59 tests
```

The CLI (`FxStore` constructed directly) and the test suite always run with
`live_anchor=False` — hermetic, no network, fixture-anchored. Only the running
service (`serve`, via `api.build_app()`) defaults to live.

The API key comes from **`FX_API_KEY`** if set, else **Vault** (ADR-009) — there is
no hardcoded default (`KNOWN-ISSUES.md` #1, fixed). Get the seeded value and use it:

```sh
# in infra/vault/: docker compose up -d && uv run seed.py   (once)
KEY=$(curl -s -H "X-Vault-Token: rfq-dev-root" \
  http://localhost:8200/v1/secret/data/rfq/fx-api-key | python -c \
  "import sys,json; print(json.load(sys.stdin)['data']['data']['value'])")
curl -H "X-API-Key: $KEY" http://localhost:8001/exchange-rates          # all 4 pairs, latest
curl -H "X-API-Key: $KEY" http://localhost:8001/exchange-rates/CNY/EUR
curl -H "X-API-Key: $KEY" "http://localhost:8001/convert?amount=42000&from_currency=CNY&to_currency=EUR"
```

`FX_FIXTURES_DIR` overrides the fixtures location (defaults to `../../fixtures/fx/`).
`MASTERDATA_URL` overrides where FX reaches masterdata (defaults to `:8003`).
`FX_LIVE_ANCHOR=0` disables the live ECB fetch (opt-out, on by default in the
running service). `FX_ECB_HIST_FILE` points at a manually-downloaded copy of
`eurofxref-hist-90d.xml` — the offline-demo fallback if live fetch fails.

## What's here

| File | Role |
| --- | --- |
| `store.py` | in-memory FX store; point-in-time lookup; validates every currency via a **real masterdata API call** at load (ADR-010 — never a duplicated file); three-tier reload (live ECB / cache file / fixtures+generator) |
| `ecb_client.py` | fetches + parses the ECB's public `eurofxref-hist-90d.xml` (no API key); `EcbUnavailableError` on any network/parse failure — callers fall back to the next tier |
| `generator.py` | fixture-tier-only: deterministic 28-day history (`generate_history`, seeded via `rfq_common.clock`) + a standalone cumulative-step-breakout capability (`generate_staircase`, unit-tested, not yet wired to a scenario pack — blocked on the not-yet-built scenario runner, `KNOWN-ISSUES.md`) |
| `convert.py` | currency-conversion rounding — the caveat: **JPY has `minor_unit=0`** (a whole-yen amount, not yen-cents); hardcoding 2 decimals would silently corrupt it |
| `auth.py` | APIKEY dependency — authenticates the caller→backend hop (not Cedar authz) |
| `api.py` | `GET /exchange-rates` (latest per pair), `GET /exchange-rates/{base}/{quote}`, `GET /exchange-rates/{base}/{quote}/history?days=`, `GET /convert`, `POST /admin/reset` (also the live-anchor refresh trigger — re-fetches ECB every call, not just at boot), on `rfq_common.create_app` |
| `cli.py` | `reset` / `get-rate` / `convert` / `serve`, on `rfq_common.create_cli` |

Free from `rfq_common.app.create_app`: `/healthz`, `/_theme.css`, Swagger UI at
`/swagger`, ReDoc at `/redoc`, raw OpenAPI at `/openapi.json`, the `SHOWCASE` banner
header.

`/convert` returns a **locale-neutral decimal string** (e.g. `"5451.22"`) — i18n/l10n
display formatting (thousands separators, `,` vs `.`) is a frontend concern
(Phase 5), deliberately not done here.

## Result

Verified live (not just tested): `uv run mock-fx serve` + `curl` proved `/healthz`,
`/swagger` (200, real Swagger UI), 401 without an API key, and `/convert` for
CNY/EUR both directions, offline (fixture-anchored). 59/59 tests green,
including 3 that genuinely hit a live masterdata service (not a stub) and prove
fail-closed behavior when it's unreachable or a currency is unknown; generator
tests (same seed → byte-identical history, every generated point stays within
the 2.0% D4 band, `generate_staircase` proves a cumulative breakout the naive
yesterday-vs-today check alone would miss); and `ecb_client`/live-anchor tests
(feed parsing, 3-tier fallback, graceful degrade to fixtures on total ECB
unavailability).

## Phase 2 exit criterion (for this system)

> serves REST + Typer CLI; loads its fixtures; `reset` restores baseline. **Met**
> — and now also consumes the masterdata source via its API, per ADR-010.
