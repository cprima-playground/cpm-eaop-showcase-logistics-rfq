# Data provenance — repricing subprocess

The runbook discipline (cpm-eaop `docs/policies/domain-to-cedar-runbook.md`, step 10):
a correct schema is not enough if the runtime cannot reliably supply the fact. For
**every policy-relevant fact**, name its source, retrieval path, freshness, and
failure behavior. Default failure behavior is **deny** (fail closed).

| Authorization fact | Source | Retrieval path | Freshness | Failure behavior |
| --- | --- | --- | --- | --- |
| `exchange_rate` / `fx_rate_ref` | FX service (Treasury) | FX REST API | ≤ 15 min (freshness window) | deny — never normalize on a stale rate |
| `fx_age_seconds` | derived from `observed_at` | computed at entity build | authoritative | deny if unknown |
| `margin_pct_x10` | CPQ (pricing terms + floor) | commercial MCP | synchronous | deny |
| `margin_floor` | CPQ | commercial MCP, cached | 1 hour | deny |
| `carrier_rate` (amount+currency) | Rate management | rate MCP | synchronous | deny |
| `capacity_status` | TMS | tms MCP | 5 min | deny |
| `contracted_lane` | CRM / contract mgmt | crm MCP | authoritative | deny |
| `quote.prior_version_fx` | CPQ (previous quote) | commercial MCP | authoritative | deny |
| `principal.active` | IdP claim → resolved principal | token | per-request | deny |
| `quote_value_eur_cents` | derived (normalized cost × price) | computed | authoritative | deny |
| `quote.status` (human decision) | CPQ / CRM | commercial MCP | authoritative | deny — resume only on a real status change |
| `cost_variance_pct_x10` | derived vs baseline lane cost | computed | authoritative | deny |
| `transit_variance_days` | derived vs baseline transit | TMS-sourced | 5 min | deny |

## Freshness is a policy input, not a nicety

The FX freshness window is enforced twice, on purpose:
- **Process** (`process.md`): refuse to normalize on a stale snapshot; fetch a new one.
- **Policy** (`authorization/policies.cedar` D1/D2): `fx-rate.read` / `route-cost.normalize`
  are permitted only when `context.fx_age_seconds` is within the window. Obligation
  `oblig-fx-freshness` (`authorization/obligations.yaml`) carries the limit for the PEP.

A stale FX fact therefore yields a **deny**, not a silently wrong price.
