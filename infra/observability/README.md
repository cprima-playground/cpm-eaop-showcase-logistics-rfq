# infra/observability

Local OTel Collector + Tempo + Prometheus + Grafana stack (M5.9). Joins
the app stack's `rfq-showcase` Docker network natively — every showcase
service exports real traces/metrics here via OTLP, no manual
`docker network connect` step (see `docker-compose.yml`'s own header
comment for the network-join details).

## Running

Bring-up order matters only for the network join (this project's own
`networks:` block declares `rfq-showcase` as `external: true`, so it must
already exist):

```
# 1. support stack first -- creates the rfq-showcase network
docker compose -f infra/compose.support.yaml up -d

# 2. observability stack -- can come up before or after showcase
docker compose -f infra/observability/docker-compose.yml up -d

# 3. showcase stack -- the actual app services
docker compose -f infra/compose.support.yaml -f infra/compose.showcase.yaml --profile full up -d --build
```

Each project is independently disposable (`docker compose -f
infra/observability/docker-compose.yml down`) — no coupling to app
service lifecycle. Telemetry itself is not persisted across `down` (no
named volumes) — this is a local dev observability stack, not a
retention system.

## UIs

| | URL | Notes |
|---|---|---|
| Grafana | http://localhost:3000 | Anonymous Admin (local dev only — see `docker-compose.yml`'s own warning) |
| Prometheus | http://localhost:9090 | Direct query/debugging |
| Tempo | http://localhost:3200 | Direct API debugging; normally queried via Grafana or `mission-control-api`'s `/api/v1/traces` |

## Verifying the pipeline is actually flowing

1. `docker network inspect rfq-showcase` — confirm `tempo`,
   `otel-collector`, `prometheus`, `grafana` are attached alongside the
   app containers.
2. Generate real traffic — log into ops-dashboard and hit `/map`
   (exercises masterdata/tms/rate/geo-api calls), or run any real-stack
   integration test (e.g. `src/tms-mcp/tests/test_capacity_checkpoint.py`).
3. Grafana's provisioned `otel-stack-health` dashboard — the "Recent
   traces (Tempo)" panel should show spans from multiple `service.name`
   values, not just one manually-injected test span.
4. Prometheus — query `up{job="otel-collector"}` (collector self-health)
   and a real app-emitted metric (e.g. an `http_server_*` name from
   FastAPI/httpx auto-instrumentation) to confirm application metrics,
   not just the collector's own self-monitoring, are flowing.
5. `mission-control-api`'s `GET /api/v1/traces` (`src/mission-control-api/
   mission_control_api/traces.py`) returns `cedar.authorize` spans from
   this live traffic.

## Failure semantics

Observability is never a synchronous dependency of business execution
(`src/rfq_common/rfq_common/observability.py`'s own header states this
as a hard rule). Stopping `otel-collector` mid-session must not affect
any app service's ability to keep serving real traffic — telemetry is
dropped/buffered per the OTel SDK's own policy, nothing more.
