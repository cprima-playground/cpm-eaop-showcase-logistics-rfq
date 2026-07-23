# Reference data — real geography, synthetic commercial operations

**Rule:** use **real geography** with **synthetic commercial operations**. Do not
invent random routes; do not pretend mock schedules are live carrier data. Location
codes are real (UN/LOCODE); costs, rates, and availability are synthetic but
**correlated and reproducible** (fixed seed), not random.

Sources: **UN/LOCODE** for location codes/functions/coordinates; **OpenStreetMap**-
derived geography for road/rail plausibility; **TEN-T corridors** for realistic
European freight connections.

## Three datasets (separated on purpose)

| Dataset | File | Nature | Owner |
| --- | --- | --- | --- |
| **Reference locations** | `tms/fixtures/locations.yaml` | real (UN/LOCODE), stable | TMS |
| **Route topology** | `tms/fixtures/routes.yaml` | stable graph of legs | TMS |
| **Operational overlays** | `tms/fixtures/route-availability.yaml` + per-pack overrides | changing state (the trigger) | TMS |
| **Rates (derived)** | `rate/fixtures/rates.yaml` via `rate/fixtures/cost-model.md` | correlated, seeded | Rate |

Keep topology **separate** from operational state: topology is stable; availability
changes and is what *wakes* the agentic process.

Target size (enough for interesting agent behavior, small enough to reason about):
**~15 locations · ~25 legs · 8 complete routes · 3 alternatives per important lane.**

## Correlated, not random

Transit, cost, reliability, and emissions relate to route characteristics:

```text
cost = mode_base_cost × distance × weight_factor × capacity_factor
     + handling_costs + port_surcharges
```

Then bounded noise (±5%) with a **fixed seed** (reproducible). Typical relationships:

- **Air** fast · expensive · lower capacity.
- **Ocean** slow · cheap · disruption-prone.
- **Rail** medium cost + duration.
- **Road** flexible · distance/border-sensitive.
- More transshipments → higher delay risk + handling cost.
- Limited capacity → higher spot price.
- Route unavailable → alternatives become more expensive or slower.

Full parameters in `rate/fixtures/cost-model.md`.

## Operational overlay = the trigger

`route-availability` carries status + reason + validity + affected leg. Event kinds:
`CAPACITY_EXHAUSTED` · `VESSEL_CANCELLATION` · `TERMINAL_CLOSURE` · `RAIL_STRIKE` ·
`CUSTOMS_RESTRICTION` · `WEATHER_DELAY` · `SERVICE_SUSPENDED` ·
`DANGEROUS_GOODS_RESTRICTION`. This overlay is the business event that triggers the
repricing process (`business/process.md`).

## Scenario packs (reproducible, not a permanently random world)

Do not maintain one drifting random world. Each pack = a **reproducible** world
state + event. Packs live in `../fixtures/scenario-packs/`:

```text
baseline.yaml                    all available; contracted lane cheapest
hamburg-port-closure.yaml        DEHAM closed -> reroute via NLRTM
rail-capacity-exhausted.yaml     DEHAM-DEMUC rail exhausted
cny-eur-threshold.yaml           FX move > 2% flips ranking
combined-route-and-fx-shock.yaml FLAGSHIP: Hamburg closed + carrier rate in another currency
```

Each pack contains: initial system-of-record state · triggering event · expected
agent discoveries · permitted alternatives · policy thresholds · expected human
decision points.

**Flagship — `combined-route-and-fx-shock`:** *Hamburg becomes unavailable, forcing
rerouting through Rotterdam. The replacement carrier rate is denominated in another
currency, so the pricing agent fetches an FX rate, recalculates margin, and requests
approval when the route and commercial thresholds are exceeded.* One realistic event
exercises routing, MCP access, an external API, Cedar, multiple agents, and human
review. Drives `../scenarios/04-combined-route-fx-shock.*`.
