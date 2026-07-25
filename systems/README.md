# Systems of record

- `systems-of-record.yaml` — the ownership map (which system owns which object).
- `data-provenance.md` — per authz fact: source · freshness · fail=deny.
- **One subfolder per system** — its own space for the system's interface contract,
  fixtures, and mock spec:

| Folder | System | Owns | Interface |
| --- | --- | --- | --- |
| `masterdata/` | **Masterdata Source (built)** | Party · Location · Currency · Incoterm · Commodity · Equipment · UnitOfMeasure · DangerousGoodsClass · PaymentTerm | REST, APIKEY — `src/mock-masterdata/` |
| `crm/` | Mock CRM | RFQ · ContractedLane (Customer identity → masterdata Party) | crm-mcp (TARGET) |
| `tms/` | Mock TMS | RouteTopology · FeasibleLane · TransitTime · Capacity | tms-mcp (TARGET) |
| `rate/` | Mock Rate Service | ContractRate · CarrierSpotRate · LaneSurcharge | rate-mcp (TARGET) |
| `qms/` | Mock QMS | PricingTerms · MarginFloor · QuoteVersion · **QuoteStatus (human decision)** | qms-mcp (TARGET) |
| `fx/` | Corporate FX Service | ExchangeRate | fx-api / REST (TARGET) |
| `workflow/` | Mock Approval/Workflow | ApprovalTask (mechanism only) | approval-mcp (TARGET) |

Each subfolder holds that system's **contract** (what it exposes), **fixtures** (its
seed data for the scenarios), and **mock spec** (what the spike implements). Nothing
is implemented in this pass — these are homes to fill.

> The human decision is a `Quote.status` transition in **`qms/`**, not a record in
> `workflow/` (see `systems-of-record.yaml`).

> **Masterdata is a different category** (ADR-010) — slow-changing reference data,
> not a transactional object. Every other system references it by id/code
> (`customer_id`, `carrier_id`, `locode`, currency code) instead of embedding a
> copy — the fix for the "no customer/carrier reference at all" gap.
