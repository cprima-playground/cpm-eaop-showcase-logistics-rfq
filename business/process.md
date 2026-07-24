# Business process — Cross-Currency Lane Repricing and Approval

Described independently of agents/implementation. The agents (`agents/catalog.yaml`)
and policies (`authorization/`) realize this process; they do not define it.

## Trigger — a business event, not a workflow step

The process wakes because the business world changed, not because a workflow
reached a stage. Two event classes, one architecture:

| Event | Class | Example |
| --- | --- | --- |
| **Route unavailable** | operational disruption | carrier rejects capacity · vessel/flight cancelled · lane embargo · SLA no longer achievable |
| **Exchange-rate changed** | financial disruption | Treasury publishes a new FX rate · an FX threshold is crossed for a currency used by active quotes |

One changes the **physical execution** of the shipment; the other the **commercial
viability** of the quote. This spike features the FX event (see
`scenarios/01-fx-flips-lane.md`); route-unavailable reuses the same chain.

## Trigger, outcome, preconditions

- **Trigger:** a business event impacting one or more active quotes.
- **Outcome:** each impacted quote is repriced against fresh, authoritative facts;
  a route is recommended; a human approves when a threshold is crossed; the decision
  is written back to the systems of record.
- **Preconditions:** the RFQ exists and carries valid shipment data; a prior quote
  version exists to compare against.

## Happy path

1. Event received; agent discovers the impacted quote(s).
2. Retrieve feasible lane options (TMS) + carrier rates in their local currencies (Rate mgmt).
3. Fetch authoritative exchange rate(s) (corporate FX service).
4. Normalize every route cost into the quote currency; add surcharges; compute margin.
5. Compare options on cost · transit · capacity · contracted-lane preference · risk.
6. **Threshold evaluation** — all within limits → propose route + price, done.

## Alternative / exception paths

- **Threshold exceeded** (any of the three types below) → create a human review task
  carrying the decision evidence; wait for a human decision.
- **Human requests an alternative lane** → the loop:

  ```text
  route recommendation → threshold exceeded → human requests alternative lane
  → lane evaluation resumes → new option → commercial normalization reruns
  → new approval package
  ```
- **FX snapshot too old** (outside freshness window) → refuse to use it; fetch a new one.
- **No feasible lane** → escalate; process cannot recommend.

## Threshold types (kept distinct on purpose)

Do not model "threshold exceeded" as one generic condition — each maps to a distinct
Cedar action/resource + obligation (`authorization/policies.cedar`).

| Type | Condition | Policy result |
| --- | --- | --- |
| **Commercial** | normalized margin < region/customer margin floor | permit proposal · obligation: commercial approval |
| **FX** | \|current FX − prior-quote FX\| > 2% | permit recalculation · **forbid** auto quote replacement · obligation: notify pricing manager |
| **Lane** | recommended lane ≠ contracted lane | permit recommendation · obligation: customer-service review |

## Human intervention

The human sees **decision evidence**, not a bare button: baseline vs recommended vs
alternative lane · original carrier currencies · FX source + timestamp · converted
costs · prior vs current FX · margin impact · transit delta · triggered thresholds ·
agent recommendation. The human may: approve · choose another lane · require a fresh
FX snapshot · adjust margin · reject the carrier rate · request a new route search.

## Termination

The human decision **is a status transition on the Quote in the quote system of
record (QMS/CRM)** — `approval_required → approved | rejected | revise` — not a
record owned by a separate workflow store. The approval task only surfaces the
decision to a human; the process resumes by observing the quote status change.

- `approved` (or auto-permitted within limits) → new quote version written; process ends.
- `rejected` → close / escalate.
- `revise` → human requested another lane → loop back to lane evaluation (see
  `scenarios/03-approval-loop`).

## Audit events

`fx.requested` · `carrier-quote.received` · `route-cost.normalized` ·
`quote.recalculated` · `authorization.denied` · `approval.requested` ·
`route-deviation.approved` · `quote.version.written`.
