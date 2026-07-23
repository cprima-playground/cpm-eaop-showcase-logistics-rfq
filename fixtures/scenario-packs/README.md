# Scenario packs

Reproducible world states — **not** one permanently drifting random world. Each pack
pins the system-of-record state + a triggering event, so a run is deterministic.
Reference data (real UN/LOCODE locations, topology, cost model) is shared; a pack
only supplies **overlay overrides + the event + expectations**.

Each pack contains:
- **initial state** — RFQ + baseline fixtures + any overlay/rate overrides
- **triggering event** — the business event that wakes the process
- **expected agent discoveries** — what the Lane/Commercial/Decision agents should find
- **permitted alternatives** — which routes are viable under the event
- **policy thresholds** — which of D1–D9 fire
- **expected human decision points** — where a `Quote.status` transition is required

| Pack | Trigger | Exercises |
| --- | --- | --- |
| `baseline.yaml` | none | contracted lane cheapest; no human needed |
| `hamburg-port-closure.yaml` | TERMINAL_CLOSURE @ DEHAM | reroute (route only) |
| `rail-capacity-exhausted.yaml` | CAPACITY_EXHAUSTED @ DEHAM-DEMUC rail | reroute (operational) |
| `cny-eur-threshold.yaml` | FX move > 2% | repricing (financial) |
| `combined-route-and-fx-shock.yaml` | Hamburg closed **+** EUR reroute rate | **flagship** — route + FX in one event |

The flagship drives `../../scenarios/04-combined-route-fx-shock.*`. Packs map to the
authz scenarios: `cny-eur-threshold`→01 · `hamburg-port-closure`→02 · combined→04.
