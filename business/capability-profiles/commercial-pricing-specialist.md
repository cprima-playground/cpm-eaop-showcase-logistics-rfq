# Commercial Pricing Specialist — capability profile

Golden template (schema: `business/capability-profiles/README.md`).
Grounds `job_title_id: commercial-pricing-specialist`
(`business/job-titles.yaml`), actor `sam.pricing` + 2 regional peers
(`identity/actors.yaml`), department `pricing`
(`business/departments.yaml`).

## 1. Mission

Turn a feasible route and a raw cost basis into a commercially viable,
policy-compliant quotation the customer can accept.

## 2. Primary systems

Per `systems/systems-of-record.yaml`'s canonical ids:

- **`qms`** — owns `CustomerPricingTerms`, `MarginFloor`, `QuoteVersion`,
  `QuoteStatus`. The specialist's home system; every quotation action
  writes here.
- **`rate_management`** — owns `ContractRate`, `CarrierSpotRate`,
  `LaneSurcharge`. Read-only input.
- **`fx_service`** — owns `ExchangeRate`. Read-only input, freshness-
  gated (see §6).
- **`tms`** — read-only input for route/transit facts the Transport
  Planner already established; this role doesn't plan routes.
- **`crm`** — owns the originating `RFQ`. Upstream, read-only, and per
  `systems/systems-of-record.yaml:26` its MCP interface is still
  `TARGET` — not reachable from this role in the showcase today.

## 3. Consumes

| Input | Produced by |
|---|---|
| `RFQ` | Account Manager (Commercial, not yet modeled) via `crm` |
| Feasible route / capacity facts | Transport Planner via `tms` (`lane.evaluate`, `capacity.check`) |
| `ContractRate` / `CarrierSpotRate` | Organizationally produced by Carrier Procurement; represented in the current showcase as pre-existing `rate_management` fixture data (`systems/rate/fixtures/rates.yaml`), not as a modeled procurement transaction — same limitation as `crm` above, not an implemented upstream workflow |
| `ExchangeRate` | `fx_service` (external, corporate-managed) |
| `CustomerPricingTerms` / `MarginFloor` | Pricing Manager (policy owner) via `qms` |

## 4. Produces

| Output | Consumed by |
|---|---|
| `QuoteVersion` (priced) | Pricing Manager, for approval when required |
| `ApprovalTask` (via `approval.request`) | `workflow` system, surfaced to Pricing Manager |
| Pricing assumptions / variance explanation | Customer (via Account Manager), Pricing Manager (for exception review) |

## 5. Decisions

Cross-referenced to `business/decisions.md` (as reflected in
`authorization/policies.cedar`'s `@id`s):

- **D1/D2** — is the FX snapshot fresh enough to price with (`fx_age_
  seconds <= 900`)? Not a judgment call — hard-gated.
- **D4a/D4b** — has FX moved more than 2% since the base quote? If so,
  recalculation is permitted but auto-*submission* is forbidden
  (`forbid-auto-replace-on-fx`) — the specialist must route to the
  Pricing Manager's approval path (D6), not decide alone.
- **D5** — is margin below the floor? Permitted to propose, but owes
  commercial approval (`oblig-commercial-approval`) — again routed, not
  decided unilaterally.
- **D12** — is the quote within both thresholds (FX quiet, margin at/
  above floor)? Then internal submission needs no escalation.

These are three distinct business operations, not one — collapsing them
overstates what's automated:

```text
Price (quote-price.calculate)
  -> determine whether approval is required (D4/D5/D12's thresholds)
  -> submit for internal approval (quote.submit-for-approval)
     OR proceed without escalation when D12 holds
```

**Calculating** a priced `QuoteVersion` and **submitting it for internal
approval** are both modeled today (Cedar actions exist for both,
distinct policies gate each). **Releasing/sending the quotation to the
customer** is not modeled as a distinct Cedar action anywhere in this
showcase — don't read "submission needs no escalation" as "the agent
sends the customer a quote," it means the internal QMS approval gate is
satisfied, nothing about the customer-facing step.

The specialist's real decision, in plain terms: **submit directly,
revise, or escalate to the Pricing Manager** — and which of the three is
correct is largely determined by D1/D2/D4/D5/D12's thresholds, not open
judgment. The judgment that remains is explaining *why* to the customer
and choosing *how* to revise, not *whether* to escalate.

## 6. Business rules

- FX freshness window: 900 seconds (`commercial-may-read-fresh-fx`,
  `commercial-may-normalize`).
- FX variance threshold: 2% (`fx_variance_pct_x10 > 20`) triggers both
  the auto-submit forbid (D4b) and a `oblig-notify-pricing-manager`
  obligation (D4a).
- Margin floor: `margin_pct_x10 >= 60` (6.0%) is the "no escalation
  needed" threshold (D12); below it, `oblig-commercial-approval` fires
  (D5).
- Every rule above is enforced by Cedar today, not merely documented —
  verified by `src/rfq_common/tests/test_pdp_integration.py`.

## 7. KPIs

Industry-typical, **not computed by anything in this showcase today** —
listed because a real Pricing Specialist is measured this way, not as a
claim of implementation:

- Quote turnaround time (RFQ receipt → quote sent)
- Quote-to-win conversion rate
- Realized gross margin vs. quoted margin
- Rate-sheet/tariff currency (how stale the specialist's own reference data is)

Sources: [ZipRecruiter Freight Forwarding Pricing Specialist](https://www.ziprecruiter.com/Jobs/Freight-Forwarding-Pricing-Specialist)

## 8. Authority

- May submit a quote directly when both D12 thresholds hold — no
  escalation, no approval step required.
- May **not** auto-submit when FX moved > 2% — hard `forbid`
  (`forbid-auto-replace-on-fx`), not a guideline.
- May **not** approve their own escalated quote — `route-deviation.
  approve` (D6) is scoped to `principal in Agentic::Group::"rfq-
  commercial-*"` (the Pricing Manager's group), which this role is not
  a member of (`sam.pricing`'s `member_of` is `rfq-pricing-emea`, a
  different group — see `identity/groups.yaml`).

  **Resolved** (was flagged here as an action-name mismatch, then fixed
  via the four-role capability-profile review's Finding 3): `route-
  deviation.approve` (D6) was being reused for the FX-variance/margin-
  floor commercial-exception approval it wasn't really named for.
  `quote.approve`/`quote.reject`/`quote.request-revision` (D19-D21,
  `authorization/policies.cedar`) now exist as the dedicated actions on
  the actual `Quote` resource, matching `mock_qms`'s real `approved`/
  `rejected`/`revise` decision vocabulary. D6 still exists, unchanged,
  for its original RouteRecommendation-specific case.

## 9. Reports to / Manages

Fixed this session (was a discrepancy this profile surfaced):
`identity/actors.yaml`'s `sam.pricing.manager` now points to
`mona.commercial` (Pricing Manager), who reports to `diane.delgado`
(Regional Commercial Director) — Specialist → Manager → Director, not
a flat line to the Director for both. Same fix applied to the APAC/AMER
peers. `business/job-titles.yaml` now declares this chain explicitly
(`reports_to_job_title_id`), and `tools/identity/validator.py` enforces
it — a specialist skipping the manager layer is a validation error
(`test_management_layer_skip_rejected`).

Manages: nobody (individual contributor).

## 10. Collaborates with

- **Pricing Manager** (Pricing — approval/escalation path; the
  authority tier within this same department, not a separate
  Commercial-department role, despite `persona: CommercialManager`
  being the internal Cedar-facing label for that tier — see
  `identity/actors.yaml`'s header comment on why `persona` and
  `job_title_id`/`department_id` intentionally don't always line up).
- **Transport Planner** (Planning) — consumes their route/capacity
  output; see `business/personas.md`'s Transport Planner section for
  the reverse direction of this same collaboration.
- **Carrier Procurement Specialist** (Carrier Procurement) — consumes
  negotiated rates; per `business/departments.yaml`, Pricing *consumes*
  rates, Carrier Procurement *negotiates* them — this is that
  relationship in practice.

## 11. Candidate agent responsibilities

Already implemented, not hypothetical — `commercial-normalization-
agent` (`agents/catalog.yaml:30-46`). Mapped to human responsibility
bullets (`business/job-titles.yaml`'s sourced list for this title), not
presented as bare action names, so it's visible the agent covers 3
bounded responsibilities, not the role:

| Human responsibility (from `business/job-titles.yaml`) | Agent contribution |
|---|---|
| "Analyze market trends and freight rate fluctuations" | `fx-rate.read` + `route-cost.normalize` (D1/D2 freshness-gated normalization) |
| "Prepare freight quotations" (mechanical half — price/variance) | `quote-price.calculate`, `quote-variance.evaluate` |
| "Submit the quote once priced" (Finding 1, capability-profile review — moved here from `route-decision-agent`) | `quote.submit-for-approval`, still hard-blocked by `forbid-auto-replace-on-fx` when FX moved > 2% |
| *(deliberately not covered)* "Coordinate with ... for competitive rates", "Maintain/update rate sheets", "Ensure quotations comply with company policy" | — no `owned_actions` map here; stays human |

The agent is explicitly prohibited from `route-deviation.approve`,
`quote.approve`, and `quote.reject` (`agents/catalog.yaml`) — it
computes and submits, it never decides the outcome.

## 12. Must remain human

Three different kinds of "human," not one — conflating them freezes
today's technical limitation into a permanent organizational claim:

**Human-accountable** (structural, not a current limitation):
- The revise-vs-escalate decision when D5's margin-floor obligation
  fires — someone is accountable for that call regardless of how much
  of the surrounding computation is automated.

**Human-only today** (limited by current agent scope, not principle):
- Explaining pricing assumptions and variance to the customer — no
  agent/tool exists for this in the showcase yet; plausibly
  agent-assisted (drafting an explanation) later without changing who's
  accountable for it.

**Potentially agent-assisted** (not currently modeled, no barrier to
building it):
- Coordinating with carriers for competitive rates, maintaining rate
  sheets — real bullets from `business/job-titles.yaml`'s source
  postings, outside this subprocess's current scope, but nothing about
  them requires a human specifically.
