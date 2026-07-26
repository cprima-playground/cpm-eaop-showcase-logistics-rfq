# Cost model — correlated, seeded (not random)

Rates in `rates.yaml` are **derived** from route characteristics, not invented.
Reproducible: a fixed seed drives the ±5% noise, so the same fixtures regenerate
byte-stable numbers. Carrier currency depends on the operating carrier's domicile —
that is what makes the lane **cross-currency**.

## Formula

```text
cost = mode_base_cost × distance_factor × weight_factor × capacity_factor
     + handling_costs + port_surcharges
then × (1 ± noise)          # noise ≤ 5%, fixed seed = 42
```

## Parameters (synthetic, plausible)

| Mode | base_cost | speed | capacity | disruption |
| --- | --- | --- | --- | --- |
| air | very high | fast | low | low |
| ocean | low | slow | high | high |
| rail | medium | medium | medium | medium |
| road | medium-high | flexible | low-med | border-sensitive |

Correlation rules (applied on top of the formula):
- more transshipments → higher `handling_costs` + higher delay risk
- limited capacity → higher `capacity_factor` (spot premium)
- a route made unavailable → its alternatives' `capacity_factor` rises (demand shifts)

## Carrier currency by lane

| Route | Carrier domicile | Rate currency |
| --- | --- | --- |
| SHA-HAM-MUC (contracted) | CN ocean carrier | **CNY** |
| SHA-RTM-MUC | EU ocean carrier | **EUR** |
| SHA-ANR-MUC | EU ocean carrier | EUR |
| PVG-FRA-MUC (air) | EU air carrier | EUR |
| SHA-PIR-MUC / SHA-GOA-MUC | EU ocean carrier | EUR |
| SHA-CPE-MUC (Cape of Good Hope, Suez-blocked escalation) | EU ocean carrier | EUR |

The contracted Hamburg lane is CNY-priced; the Rotterdam alternative is EUR-priced.
That single fact is why a route reroute forces an FX normalization
(`../../reference-data.md`, flagship scenario).

## Consistency with the RFQ fixture

The model is tuned so the two options in `../../../fixtures/rfqs/RFQ-1001.yaml`
reproduce: SHA-HAM-MUC ≈ **42,000 CNY**, SHA-RTM-MUC ≈ **5,650 EUR**. See
`../../../fixtures/normalized-options.yaml` for the FX-normalized golden output.
