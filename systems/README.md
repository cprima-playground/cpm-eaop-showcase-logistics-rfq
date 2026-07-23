# Systems of record

- `systems-of-record.yaml` — the ownership map (which system owns which object).
- `data-provenance.md` — per authz fact: source · freshness · fail=deny.
- **One subfolder per system** — its own space for the system's interface contract,
  fixtures, and mock spec:

| Folder | System | Owns | Interface |
| --- | --- | --- | --- |
| `crm/` | Mock CRM | Customer · RFQ · ContractedLane | crm-mcp (TARGET) |
| `tms/` | Mock TMS | RouteTopology · FeasibleLane · TransitTime · Capacity | tms-mcp (TARGET) |
| `rate/` | Mock Rate Service | ContractRate · CarrierSpotRate · LaneSurcharge | rate-mcp (TARGET) |
| `cpq/` | Mock CPQ | PricingTerms · MarginFloor · QuoteVersion · **QuoteStatus (human decision)** | commercial-mcp (TARGET) |
| `fx/` | Corporate FX Service | ExchangeRate | fx-api / REST (TARGET) |
| `workflow/` | Mock Approval/Workflow | ApprovalTask (mechanism only) | approval-mcp (TARGET) |

Each subfolder holds that system's **contract** (what it exposes), **fixtures** (its
seed data for the scenarios), and **mock spec** (what the spike implements). Nothing
is implemented in this pass — these are homes to fill.

> The human decision is a `Quote.status` transition in **`cpq/`**, not a record in
> `workflow/` (see `systems-of-record.yaml`).
