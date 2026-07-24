# Glossary — repricing subprocess

Short reference for terms used across `business/`, `decisions/`, and the mock
systems. Fills the `TODO.md` "Should-have" gap. Not exhaustive — covers the
terms a reader hits first when following the RFQ→repricing story.

| Term | Meaning |
| --- | --- |
| **RFQ** | Request for Quote — the customer-facing ask that starts the process (rate + terms for a lane). |
| **Lane** | An origin→destination trade corridor (e.g. `CNSHA-DEMUC`), independent of which specific route carries it. |
| **Route** | One concrete path over a lane (specific ports/legs/mode, e.g. `SHA-HAM-MUC` via Hamburg). A lane can have several routes. |
| **Contracted lane** | The lane's pre-agreed, standing carrier arrangement — the baseline the process compares any deviation against. |
| **Baseline lane** | Synonym for contracted lane in `decisions.md`/`process.md` — the reference point a recommendation is measured as a *deviation from*. |
| **Route deviation** | An agent recommendation that picks a non-contracted route/lane — requires the `route-deviation.approve` obligation. |
| **Incoterm** | ICC-standard delivery term (e.g. FOB, DAP) fixing where cost/risk transfers between buyer and seller. Sourced from masterdata (ADR-010), never hardcoded. |
| **Margin floor** | The minimum acceptable margin (region/customer-specific) below which a quote requires commercial approval, not just agent recommendation. |
| **Freshness window** | How old an FX rate snapshot may be before it's refused as stale (fail-closed: `D1`/`D2` deny outside the window). |
| **Availability (route)** | The volatile operational status of a route (`available`/`limited`/`degraded`/`unavailable`) — separate system of record from route topology (`systems/reference-data.md`). |
| **Obligation** | A Cedar policy annotation resolved **outside** Cedar (Python-side) — e.g. `oblig-lane-deviation` — never a Cedar-internal side effect. |
| **Masterdata** | The reference-data layer (Party/Location/Currency/Incoterm/…) every transactional system consumes via a real API call, never a duplicated copy (ADR-010). |
| **Principal** | The resolved caller identity (human or agent/service) a Cedar decision authorizes against — see `identity/claims-contract.md`. |
