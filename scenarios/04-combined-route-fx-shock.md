# Scenario 04 — Combined route + FX shock (flagship)

The strongest showcase: **one realistic event** — Hamburg becomes unavailable — forces
a reroute through Rotterdam whose carrier rate is **EUR-denominated**, so the pricing
agent must fetch FX, recalculate margin, and request approval when route **and**
commercial thresholds are exceeded. Exercises routing, MCP access, an external API,
Cedar, all three agents, and human review at once. Data: scenario pack
`../fixtures/scenario-packs/combined-route-and-fx-shock.yaml`. Machine companion:
`04-combined-route-fx-shock.yaml`.

## Why it's the flagship

Scenario 01 is FX-only; 02 is route-only. **04 fuses both from a single business
event** and triggers the widest policy surface — a `forbid` (deny-precedence) plus
**merged obligations** from multiple permits.

## Initial state (from the pack)

- `RFQ-1001`, contracted lane `SHA-HAM-MUC` (CNY-priced, real UN/LOCODE topology).
- Event: **Hamburg port congestion** → `SHA-HAM-MUC` unavailable; demand shifts →
  `SHA-RTM-MUC` capacity `limited` (spot premium).
- FX moved **2.7%** (0.1226 → 0.1194); reroute rate is **EUR**.

## Steps

1. Combined event → Lane agent sees `SHA-HAM-MUC` unavailable; retrieves alternatives
   (`SHA-RTM-MUC`, `SHA-ANR-MUC`) from TMS.
2. Reroute is EUR-priced → Commercial agent reads FX (**D1**, fresh) and normalizes
   (**D2**).
3. FX variance 2.7% > 2% → **D4a** permit recalc + `oblig-notify-pricing-manager`.
4. Route agent recommends `SHA-RTM-MUC` (`route.recommend`): non-contracted (**D3b**),
   +transit via Duisburg (**D9**) → obligations **merge**: `oblig-lane-deviation` +
   `oblig-transit-review`.
5. Margin below floor → had submit been allowed, **D5** would add `oblig-commercial-approval`.
6. Agent attempts `quote.submit-for-approval` → **D4b forbid** (FX > 2%) → **deny-
   precedence wins** → no auto-submit.
7. Route agent opens a human review task with full evidence; `Quote.status =
   approval_required`.
8. `mona.commercial` approves within limit (**D6**); sets `Quote.status = approved`
   in CPQ → new quote version written.

## Expected authorization decisions

| # | action | principal | resource | effect | obligations |
| - | --- | --- | --- | --- | --- |
| D1 | fx-rate.read | commercial-norm-agent | ExchangeRate::CNY-EUR | allow | — |
| D2 | route-cost.normalize | commercial-norm-agent | RouteOption::SHA-RTM-MUC | allow | — |
| D4a | quote-variance.evaluate | commercial-norm-agent | Quote::Q-1001-v2 | allow | oblig-notify-pricing-manager |
| D3b+D9 | route.recommend | route-decision-agent | RFQ::RFQ-1001 | allow | oblig-lane-deviation, oblig-transit-review |
| D4b | quote.submit-for-approval | commercial-norm-agent | Quote::Q-1001-v2 | **deny** | — (forbid wins) |
| D6 | route-deviation.approve | mona.commercial | RouteRecommendation::REC-1001-v2 | allow | — |

## Acceptance criteria

A single business event drives a reroute **and** an FX repricing; the forbid denies
auto-submit (deny-precedence); obligations from lane + transit + FX **merge**; the
only path forward is the human `Quote.status` transition, which succeeds within
limit. This is the "one event exercises everything" demonstration.
