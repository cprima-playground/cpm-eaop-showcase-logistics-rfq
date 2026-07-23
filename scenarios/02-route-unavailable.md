# Scenario 02 — Route unavailable (operational trigger)

Same agents, same policies, same systems of record as scenario 01 — a **different
business event**. Proves the point of the design: one agentic architecture responds
to both a financial disruption (FX) and an operational disruption (capacity), because
the trigger is a business event, not a workflow step. Machine companion:
`02-route-unavailable.yaml`.

## Business intent

The contracted lane (Route A, Shanghai → Hamburg → Munich) was selected on the
prepared quote. **After** quote preparation the carrier rejects capacity on Route A.
The process must replan onto a feasible alternative and reprice.

## Initial state

- `RFQ-1001`, contracted lane `CN-SHA-DE-HAM-DE-MUC` (Route A).
- Event: carrier capacity rejection on Route A (`capacity_status: unavailable`).
- Route B (Rotterdam) is feasible but non-contracted and slower-by-nothing here;
  assume +4 transit days vs baseline for this scenario to exercise D9.

## Steps

1. Route-unavailable event → Lane agent re-checks capacity (`capacity.check` on
   Route A → **unavailable**) and retrieves alternatives (Route B).
2. Commercial agent reads FX (fresh) and normalizes Route B cost to EUR (**D1/D2**).
3. Route agent recommends **Route B** (`route.recommend`):
   - non-contracted lane → **D3b** permit + `oblig-lane-deviation`
   - transit +4 days > 3 → **D9** permit + `oblig-transit-review`
   - (obligations merge: customer-service review **and** operations review)
4. `quote.submit-for-approval` — margin still ≥ floor and FX variance ≤ 2% here, so
   **no forbid fires**; but the lane deviation still routes to a human.
5. Human sets `Quote.status = approved` in CPQ (the decision record) → new quote version.

## Expected authorization decisions

| # | action | principal | resource | effect | obligations |
| - | --- | --- | --- | --- | --- |
| — | capacity.check | lane-evaluation-agent | RouteOption::route-a | allow | — |
| D2 | route-cost.normalize | commercial-norm-agent | RouteOption::route-b | allow | — |
| D3b+D9 | route.recommend | route-decision-agent | RFQ::RFQ-1001 | allow | oblig-lane-deviation, oblig-transit-review |
| — | quote.submit-for-approval | route-decision-agent | Quote::Q-1001-v2 | allow | — |
| D6 | route-deviation.approve | mona.commercial | RouteRecommendation::REC-1001-v2 | allow | — |

## Contrast with scenario 01

| | 01 FX flips lane | 02 route unavailable |
| --- | --- | --- |
| trigger class | financial (FX) | operational (capacity) |
| decisive threshold | FX variance → **forbid** auto-submit (deny-precedence) | lane + transit → **permit + obligations** (merge) |
| what changed | commercial viability | physical execution |
| reused unchanged | agents · policies · SoRs · MCP/A2A · human-via-quote-status | same |

## Acceptance criteria

The operational event drives the *same* chain to a human approval with **merged
obligations** (lane + transit) and **no forbid** — demonstrating the architecture is
event-source-agnostic.
