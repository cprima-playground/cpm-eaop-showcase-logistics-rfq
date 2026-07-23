# Fixtures — deterministic given-state for the scenarios

Static inputs the scenarios consume. Mirrors cpm-eaop's fixture discipline
(`tests/spike/fixtures/entra/`): frozen timestamps, patterned ids, no live data.

```text
rfqs/RFQ-1001.yaml           the RFQ + two lane options + prior quote
fx/CNY-EUR-today.json        today's rate (0.1194)
fx/CNY-EUR-yesterday.json    prior-quote rate (0.1226) — 2.7% move
normalized-options.yaml      golden Commercial-Normalization output for scenario 01
tokens/                      agent + human claim fixtures (see tokens/README.md)
```

Per-system seed data (carrier rates, transit, capacity, margin floor, quote status)
lives under each system's folder — `../systems/<system>/fixtures/`.

Conventions to keep (from cpm-eaop): frozen `observed_at`/`iat`; patterned GUIDs for
identities; money in EUR cents + percents in tenths once inside the authz layer.
