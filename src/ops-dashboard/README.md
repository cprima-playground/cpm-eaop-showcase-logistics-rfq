# ops-dashboard — read-only ops view, first frontend + first human SSO in RfQ

De-risks QMS (build-plan.md): proves Jinja2/HTMX/Tailwind (ADR-006) + Keycloak
human SSO (identity/claims-contract.md) in isolation, with **zero write
actions and zero domain state machine** — QMS's approval UI builds on this
proven shell instead of inventing frontend+SSO plumbing under
approval-workflow pressure too.

Reads TMS (routes/availability), Rate (carrier rates), FX (currency-pair
lookup), and Masterdata (all 9 reference domains) live over their real REST
APIs — the first thing in RfQ to fan out to more than two peer systems
(`TmsClient`/`RateClient`/`FxClient` in `clients.py`, same shape as
`rfq_common.masterdata_client.MasterdataClient`, which is reused directly for
the masterdata browser).

## Views

| Path | Shows |
| --- | --- |
| `/` | Route list + availability KPI strip |
| `/routes/{id}` | Route detail, legs, its carrier rate |
| `/fx?base=&quote=` | FX rate lookup + a 30-day rate chart (Chart.js) with a ±2.0% threshold band |
| `/masterdata` | The 9 reference domains |
| `/masterdata/{domain}` | All rows in one domain (parties/locations/currencies/…) |
| `/map` | World map (Leaflet + vendored Natural Earth basemap), straight-line per route |
| `/status` | Two-check health page per backend (`/healthz` + a real authenticated call) |

## Run it

```sh
# infra/vault + infra/keycloak must be up (docker compose up -d + terraform apply
# in infra/keycloak/terraform), masterdata/tms/rate/fx must be running
uv run ops-dashboard serve --port 8006
uv run pytest -v                          # 35 tests
```

Via the local Caddy edge (`infra/keycloak`'s redirect URIs cover both) — this
is the real path; requires HTTPS + hosts-file entries, see `infra/caddy/README.md`:

```sh
cd ../../infra/caddy && docker compose up -d --build
OPS_DASHBOARD_PUBLIC_URL=https://ops-dashboard.rfq-showcase.localhost uv run ops-dashboard serve
# open https://ops-dashboard.rfq-showcase.localhost
```

Login as `alice` / `rfq-dev-user` (has `ops-viewer` — sees the dashboard) or
`bob` / `rfq-dev-user` (logged in, no role — 403).

## What it proves

- Human SSO end-to-end: PKCE login (`sso.py`, adapted from cpm-eaop's
  `controlpanel/sso.py`) → `rfq_common.verify.fetch_jwks`/`verify_with_jwks`
  (signature/issuer/audience) → `rfq_common.identity.resolve_principal()` —
  the first real (partial) implementation of `identity/claims-contract.md`.
- RP-initiated logout: `/logout` ends both our session AND Keycloak's own SSO
  session (`id_token_hint`) — without this, `/logout` looked like it worked
  but the next `/login` silently re-authenticated as the same user (see
  `KNOWN-ISSUES.md` #8, fixed).
- Role-gated views: `ops-viewer` role required, 403 without it, redirect to
  `/login` if anonymous.
- Theming (`/_theme.css`, ADR-007), environment banner, correlation-id
  header/footer, cross-system deep-link (route → its rate), API docs link.
- Route map (`/map`): Leaflet (CDN) + a vendored Natural Earth 110m countries
  basemap (`static/vendor/natural-earth/`, public domain, no external tile
  server) — straight lines only, since `RouteLeg` carries no polyline/waypoint
  data, just endpoint locodes (looked up via masterdata for lat/lon).
  Longitude is unwrapped across the antimeridian so a Transpacific route
  draws the short way, not through Europe/Africa (`KNOWN-ISSUES.md` F12).
- FX chart (`/fx`): a real 30-day series (28 generated + the 2 real anchor
  points), Chart.js via CDN (the first chart in the repo) — the last point is
  the project's documented breakout (2.7% move vs. the 2.0% D4 threshold),
  visually distinct from the generated "normal" band.

**Perf note** (`KNOWN-ISSUES.md` F11): every client defaults to `127.0.0.1`,
not `localhost` — on this dev machine, connecting via `localhost` costs ~2s
per connection (IPv6 happy-eyeballs fallback), and `/map` makes ~20
sequential backend calls; that compounded to a real ~49s page load before
the fix, caught via a HAR capture from an actual browser session.

## Not built here (explicitly out of scope)

Any write action, audit/history trail, task inbox — those are QMS/Workflow
concepts tied to actual state changes, which this dashboard has none of.

## Result

35/35 tests green: 32 offline (stub `TmsClient`/`RateClient`/`FxClient`/
`MasterdataClient`, principal injected directly to test view/role-gate logic
without a real login) + 3 that genuinely hit the live Keycloak realm (ROPC
grant for `alice`/`bob`, real token verify + `resolve_principal`, real
403 for the role-less user). All 7 views also verified live through a real
browser-equivalent flow (login → dashboard → map → FX chart → masterdata
browser → status → logout → re-login) — the map correctly shows all 16
routes including the geographic-diversity lanes (Transpacific, Middle-East/
Suez, Intra-Europe, Transatlantic), each drawn with real masterdata-sourced
coordinates; the FX chart shows a real 30-day series ending in the
documented 2.7% breakout.
