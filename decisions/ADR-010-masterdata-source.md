# ADR-010 — Masterdata source

**Status:** accepted.
**Context:** the current data model is thin — `Quote`/`RFQ` have no customer
reference at all, `RouteOption.carrier_rate_currency` is a bare string, carrier
names are free text in fixtures. Below Silverston "Party pattern" level. Fixing
this raised a real question: should a shared, transparently-used **masterdata
source** exist, to stop every system from drifting its own copy of reference facts?

## The apparent conflict with ADR-002 — and why there isn't one

ADR-002 says: **no single system of record**, one owner per (transactional)
object, agents reconcile fragmented truth. A centralized store everyone silently
reads from looks like it undoes that.

It doesn't, because it governs a **different category of data**:

| | Transactional (ADR-002's domain) | Master / reference (this ADR's domain) |
| --- | --- | --- |
| Examples | RFQ, Quote, RouteOption, ExchangeRate | Party, Location, Currency, Incoterm, Commodity, Equipment, UoM, DG class, Payment term |
| Volatility | changes per request/event | changes rarely (days/months/years) |
| Ownership today | fragmented on purpose (CRM/TMS/Rate/CPQ/FX/Workflow) | **nowhere** — scattered as bare strings, no owner at all |
| Pattern | reconcile across owners (the showcase's whole point) | **one** canonical registry, referenced by id everywhere |

Master Data Management is a textbook-distinct layer specifically *because*
transactional systems reference it rather than each inventing their own copy.
Building it doesn't contradict "no single SoR for transactional objects" — it
fills a gap ADR-002 never addressed.

## Decision

**Build a masterdata source** — a new mock system, `mock-masterdata`, same shape
as `mock-fx` (REST API + Typer CLI on `rfq_common`), serving 9 v1 reference
domains:

1. **Party** — Customer/Carrier/Forwarder/Consignee identity
2. **Location** — real UN/LOCODE (migrated from `systems/tms/fixtures/locations.yaml`)
3. **Currency** — ISO 4217
4. **Incoterm** — Incoterms® 2020
5. **Commodity** — HS-code-level classification (+ dangerous-goods flag)
6. **Equipment** — container/vehicle types
7. **Unit of Measure** — weight/volume/count codes
8. **Dangerous-goods class** — IMDG classes 1–9
9. **Payment term** — NET30/COD/LC/…

**Other systems reference by id/code — never copy the value.** `RFQ.customer_id`,
`Quote.customer_id`, `RouteOption.carrier_id` point at Party; `RouteOption.lane_id`
already points at Location-composed lane strings; `Quote.currency` becomes a
Currency code validated against the masterdata list.

**Explicit exclusion:** policy parameters (margin floor %, FX-variance threshold,
transit-day threshold) stay in `policies.cedar` (ADR-004). Masterdata ≠ business
rules — pulling thresholds in here would let this layer swallow authorization logic.

**Serving mechanism:** a real service (not just a shared library), because
"transparently used by other systems" means a network-callable source of truth,
not nine copy-pasted fixture files. Same auth posture as FX — **APIKEY, no SSO**
(machine/agent consumers, not human-approval-touching).

## Rationale

- Closes the actual gap that triggered this (no customer/carrier reference at all).
- One generic `rfq_common.codelist.CodeListStore[M]` backs all 9 domains — avoids
  nine bespoke stores (mirrors `FxStore`'s shape, generalized).
- Freshness/staleness still governed by `systems/data-provenance.md`'s existing
  discipline — reference data is fetched or cached with a documented TTL, same as
  any other cross-system fact, not exempted from that rule.

## Consequences

- `rfq_common.models` gains 9 new Pydantic models + a `CodeListStore`.
- `RFQ`, `Quote`, `RouteOption` gain `customer_id`/`carrier_id` fields; the
  `RFQ-1001` fixture updates to reference a real Party id instead of a bare
  `customer: ACME` string.
- `systems/systems-of-record.yaml` gains `masterdata` as the owner of all 9 domains.
- Real UN/LOCODE locations move from being TMS-only fixtures to the masterdata
  service; TMS references them by code instead of embedding.
