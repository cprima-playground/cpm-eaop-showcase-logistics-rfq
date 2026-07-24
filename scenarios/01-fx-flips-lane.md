# Scenario 01 — FX movement changes the preferred lane

The central verification artifact for the spike. One changing external fact — the FX
rate — cascades into cost recalculation → route-ranking change → policy threshold →
human intervention → durable business-state transition. Machine companion:
`01-fx-flips-lane.yaml`.

## Business intent

Freight Shanghai → Munich, quote currency EUR. Two feasible lanes; yesterday Route A
(contracted, CNY-priced) was cheaper after conversion. Today CNY/EUR moved enough
that Route A is now more expensive; Route B (EUR-priced, faster, limited capacity)
would win but falls below the margin floor unless the sell price rises.

## Initial state

| Option | Route | Carrier cost | Currency | Transit |
| --- | --- | --- | --- | --- |
| A (contracted) | Shanghai → Hamburg → Munich | 42,000 | CNY | 31 d |
| B | Shanghai → Rotterdam → Munich | 5,650 | EUR | 27 d |

- Quote currency EUR; prior quote version exists.
- New FX `CNY/EUR = 0.1194`, `observed_at` 12 min ago; prior-quote FX differs by 2.7%.

## Actors / systems / objects

- Actors: `lane-evaluation-agent`, `commercial-normalization-agent`,
  `route-decision-agent`, `mona.commercial` (CommercialManager).
- Systems: CRM, TMS, Rate, QMS, FX service, Workflow (all mocked).
- Objects: `RFQ-1001`, `Quote v2`, `RouteOption route-a/route-b`, `ExchangeRate CNY-EUR`,
  `RouteRecommendation REC-1001-v2`, `ApprovalTask`.

## Steps

1. FX-change event → Lane agent retrieves both options (TMS + Rate MCP).
2. Commercial agent reads FX (**D1**, age 12 min < 15 → permit) and normalizes both
   costs to EUR (**D2** permit).
3. Recompute margins → route ranking flips: Route B now ranks above Route A.
4. Route agent recommends **Route B** (`route.recommend`, `non_contracted_lane=true`
   → **D3b** permit + obligation *customer-service review*). Route B's cost also
   exceeds the baseline by 9.3% (> 8%) → **D8** also fires, adding *cost-variance
   review* — obligations **merge**.
5. Agent attempts `quote.submit-for-approval`. Two policies bear on it:
   - **D4b forbid** (FX variance 2.7% > 2%) → **deny-precedence wins** → agent cannot
     auto-submit; **D4a** already obliged *notify pricing manager*.
   - (Had submit been permitted, **D5** would attach *commercial approval* as margin 5% < 6%.)
6. Route agent creates a human review task with full evidence (`approval.request`).
7. `mona.commercial` approves Route B within her 10,000 EUR limit (**D6** permit).
8. Decision written back to Quote + route-evaluation records → durable transition.

## Expected authorization decisions

| # | action | principal | resource | effect | obligations |
| - | --- | --- | --- | --- | --- |
| D1 | fx-rate.read | commercial-norm-agent | ExchangeRate::CNY-EUR | allow | — |
| D2 | route-cost.normalize | commercial-norm-agent | RouteOption::route-b | allow | — |
| D3b+D8 | route.recommend | route-decision-agent | RFQ::RFQ-1001 | allow | oblig-lane-deviation, oblig-cost-variance-review |
| D4a | quote-variance.evaluate | commercial-norm-agent | Quote::Q-1001-v2 | allow | oblig-notify-pricing-manager |
| D4b | quote.submit-for-approval | commercial-norm-agent | Quote::Q-1001-v2 | **deny** | — (forbid, deny-precedence) |
| D6 | route-deviation.approve | mona.commercial | RouteRecommendation::REC-1001-v2 | allow | — |

## Human review package (evidence, not a bare button)

```yaml
recommended_option: route-b
reasoning:
  - route-b is now cheaper after the FX move
  - route-b is faster (27 vs 31 days) but capacity is limited
  - route-b falls below the 6% margin floor unless the sell price rises
  - route-b deviates from the contracted Hamburg lane
triggered_thresholds:
  - {id: FX_VARIANCE,        actual_pct_x10: 27, threshold_pct_x10: 20}
  - {id: MARGIN_FLOOR,       actual_pct_x10: 50, threshold_pct_x10: 60}
  - {id: NON_CONTRACTED_LANE, actual: true,      threshold: false}
```

The human resolves it by setting `Quote.status` in QMS (the decision record):
`approval_required → approved` (with a raised sell price).

## Expected system-of-record changes

- QMS: **`Quote.status` transition** `approval_required → approved`; new Quote
  version (Route B, increased sell price). This status change *is* the human decision.
- Route-evaluation record: recommendation + FX snapshot ref.

## Expected audit events

`fx.requested` · `route-cost.normalized` · `quote.recalculated` ·
`authorization.denied` (D4b) · `approval.requested` · `route-deviation.approved` ·
`quote.version.written`.

## Failure injection

- Stale FX (age > 900s) → D1 **deny**; process fetches a new snapshot.
- Inactive agent principal → D7 **deny** (cross-cutting).
- Kill switch on `commercial-normalization-agent` → normalization blocked, fail closed.

## Acceptance criteria

The FX change alone flips the ranking; D4b denies the auto-submit (deny-precedence);
the human approval (D6) is the only path forward and it succeeds within limit; the
quote version is written back with the FX snapshot reference.
