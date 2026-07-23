# Corporate FX API — interface contract

`TARGET` — no OpenAPI is committed in cpm-eaop today; this is the first. Documented
as a contract, not implemented. The spike mocks it (`spikes/repricing/mock-fx/`).

## Mock vs live — mock (deterministic), seeded from a real source

**The showcase mocks FX.** A live rate would break reproducibility (the FX-flip must
fire on cue; `../../RUNNING.md` requires frozen rates). Same rule as the geography:
**seed the fixtures from a real historical CNY/EUR** (e.g. ECB reference rates) for
credible numbers, then **freeze + serve deterministically** (`../../fixtures/fx/`).

The internal FX service abstracts the provider, so a **live mode** (real provider:
ECB · exchangerate.host · a corporate feed) is swappable behind the *same contract*.
Live mode is for realism only — the **scripted scenarios always run on the frozen
snapshot**. `effectiveAt` + a pinned `NOW` yield a fixed `fx_age_seconds`.

## Why a direct API, not MCP

FX is a **plain HTTP dependency**, deliberately not behind MCP: deterministic,
narrow, centrally managed, trivial to mock. Only the internal FX service is called;
it fronts the external rate provider. (MCP is reserved for agent access to internal
systems of record — see `interfaces/mcp/tools.yaml`.)

```text
Commercial Normalization Agent ──HTTP──► Corporate FX API ──► external provider
```

## Operation

```http
GET /exchange-rates/{base}/{quote}?effectiveAt={iso8601}
```

Example: `GET /exchange-rates/CNY/EUR?effectiveAt=2026-07-24T08:00:00Z`

### Response (the fields the policy + normalization depend on)

```json
{
  "pair": "CNY/EUR",
  "rate": 0.1194,
  "rate_type": "corporate",
  "source": "corporate-fx-service",
  "observed_at": "2026-07-24T08:00:00Z",
  "valid_until": "2026-07-24T16:00:00Z",
  "rate_ref": "FX-20260724-CNY-EUR"
}
```

`observed_at` drives `context.fx_age_seconds` (data-provenance: freshness ≤ 900s →
else **deny**, policies D1/D2). `rate_ref` is the auditable snapshot id carried on
`route-cost.normalize`.

## Domain-action binding

The operation maps to domain action `fx-rate.read` on resource
`ExchangeRate::"CNY-EUR"`. The authorization decision (D1) gates the read on
freshness; the API itself is unauthenticated-to-the-agent only after the PDP allows.

<!-- When the OpenAPI is authored, add x-domain-action / x-resource-type / x-authz-context
     extensions so the API, MCP, agent, and Cedar artifacts share one action vocabulary. -->
