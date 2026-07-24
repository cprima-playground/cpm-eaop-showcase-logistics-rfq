# mock-tms — route topology + operational availability, actually running

Second bulk Phase-2 system (mechanical, same pattern as `mock-fx`). Built on
`rfq_common`. Two systems of record, deliberately separate
(`systems/reference-data.md`): **topology** (`routes.yaml`, stable) and
**availability** (`route-availability.yaml`, volatile — the trigger for the
repricing subprocess). No SSO, no frontend — APIKEY only.

**Depends on masterdata being up** (ADR-010): every leg's location code is
validated via masterdata's real `/locations/{code}` API at load — fail closed.

## Run it

```sh
# masterdata must be running first
uv run mock-tms serve --port 8004        # Swagger UI at http://localhost:8004/docs
uv run mock-tms routes                    # CLI, no HTTP
uv run mock-tms feasible-lanes CNSHA-DEMUC
uv run mock-tms reset
uv run mock-tms set-availability SHA-HAM-MUC unavailable --reason "port congestion"
uv run pytest -v                          # 33 tests
```

```sh
curl -H "X-API-Key: $KEY" http://localhost:8004/routes/SHA-HAM-MUC/transit-time
curl -H "X-API-Key: $KEY" "http://localhost:8004/feasible-lanes?lane=CNSHA-DEMUC"
curl -X PATCH -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"status":"unavailable","reason":"port congestion"}' \
  http://localhost:8004/routes/SHA-HAM-MUC/availability
```

`TMS_API_KEY` env or Vault (ADR-009); `TMS_FIXTURES_DIR` overrides the fixtures
location (defaults to `../../systems/tms/fixtures/`).

## Routes

| Route | REST | Note |
| --- | --- | --- |
| List routes | `GET /routes` | topology |
| One route | `GET /routes/{id}` | with legs |
| Availability | `GET /routes/{id}/availability` | volatile overlay |
| Transit time | `GET /routes/{id}/transit-time` | sum of leg durations |
| Capacity | `GET /routes/{id}/capacity` | from availability |
| Feasible lanes | `GET /feasible-lanes?lane=...` | routes sharing a lane |
| Set availability | `PATCH /routes/{id}/availability` | live operational-state update |
| Reset | `POST /admin/reset` | restores baseline, discards any PATCH |

### Realism note — why `PATCH`, not an `apply-scenario` endpoint

`RouteAvailability` is a real entity TMS holds, so it gets standard REST:
**`PATCH /routes/{route_id}/availability`**. This is not a demo-only convenience —
it stands in for what a real inbound webhook/EDI handler would call when a
disruption event arrives from a visibility platform (project44/FourKites-style)
or a port community system. The *mechanism* (push → mutate live entity) is
realistic; only *who calls it* differs (a demo/scenario script vs. a real
external system). "Applying a scenario pack" is therefore **client-side
composition** — a script issues one `PATCH` per override in the pack — TMS
itself never needs a "scenario" concept. `POST /admin/reset` always restores
the stable baseline from `route-availability.yaml`, discarding any PATCH.

## A real data nuance found while testing

`routes.yaml`'s curated `lane_alternatives` comment lists only **6** routes for
lane `CNSHA-DEMUC` — but **7** routes actually carry that `lane` field (it
excludes the Baltic/Gdansk gateway, `SHA-GDN-MUC`). `feasible_lanes()` groups by
the raw field (mechanical, complete, 7) — the curated list is a narrower,
business-prioritized subset this store doesn't currently expose separately.
Not a bug; documented in `tests/test_store.py`.

## Result

33/33 tests green, including 3 that genuinely hit a live masterdata service
(not a stub) — real load, real rejection of an unknown location, real
fail-closed behavior when masterdata is unreachable.

## Operational note (credential rotation)

Re-seeding Vault rotates a credential's value; an **already-running** consumer
process caches its key at startup and won't pick up the new value until
restarted. Hit this for real while building this system — not a code bug, a
real operational behavior worth knowing (see `KNOWN-ISSUES.md`).
