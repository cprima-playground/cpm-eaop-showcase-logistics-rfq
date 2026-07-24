# QMS (mock)

> A Quote Management System is the authoritative system responsible for
> creating, evolving, approving, publishing, accepting, and transferring
> commercial quotations into executable bookings, while preserving an
> immutable history of every commercial commitment.

**Owns:** CustomerPricingTerms · MarginFloor · QuoteVersion · **QuoteStatus**.
**Interface:** `commercial-mcp` (TARGET).

**System of record for the human decision** — the approval outcome is a
`Quote.status` transition here (`approval_required → approved | rejected | revise`),
not a record in `../workflow/`. See `../systems-of-record.yaml`.

Put here: interface contract, fixtures (margin floor 6%, previous quote version,
pricing terms), and the mock spec.

- `contract.yaml` — get_margin_floor · get_previous_quote · get_customer_pricing_terms · calculate_surcharges · store_cost_normalization · set_quote_status
- `fixtures/` — Q-1001-v1 (prior) with its FX, margin floor, pricing terms
- `mock-spec.md` — incl. the status state machine
