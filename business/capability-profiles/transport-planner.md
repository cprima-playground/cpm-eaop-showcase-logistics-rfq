# Transport Planner — capability profile

Second application of the golden template (schema: `business/
capability-profiles/README.md`). Grounds `job_title_id: transport-
planner` (`business/job-titles.yaml`), actor `human.wei.planning` + 2
regional peers (`identity/actors.yaml`), department `planning`
(`business/departments.yaml`).

## 1. Mission

Turn an RFQ's origin/destination and constraints into a feasible,
capacity-checked route, and carry that route through to a commercial
recommendation.

## 2. Primary systems

Per `systems/systems-of-record.yaml`'s canonical ids:

- **`tms`** — owns `RouteTopology`, `FeasibleLane`, `TransitTime`,
  `Capacity`. The planner's home system.
- **`rate_management`** — owns `ContractRate`, `CarrierSpotRate`,
  `LaneSurcharge`. Read-only input, same procurement caveat as the
  Commercial Pricing Specialist profile (organizationally produced by
  Carrier Procurement, represented today as fixture data).
- **`qms`**/**`workflow`** — **no longer written to by this role's
  agents**, as of the capability-profile review's Finding 1/2 (§5): this
  profile originally found `route-decision-agent` reaching into `qms`
  (`quote.submit-for-approval`) and `workflow` (`approval.request`),
  which is what triggered the four-role review. Both were reassigned/
  removed — see §5.
- **`crm`** — owns the originating `RFQ`. Same `TARGET`-only caveat as
  the Commercial Pricing Specialist profile
  (`systems/systems-of-record.yaml:26`).

## 3. Consumes

| Input | Produced by |
|---|---|
| `RFQ` | Account Manager (Commercial, not yet modeled) via `crm` |
| `ContractRate` / `CarrierSpotRate` | Organizationally produced by Carrier Procurement; represented today as pre-existing `rate_management` fixture data, not a modeled procurement transaction |
| Pricing/margin context for the recommendation decision | Commercial Pricing Specialist (indirectly — `route.recommend`'s context carries `margin_pct_x10`, sourced from the pricing side) |

## 4. Produces

| Output | Consumed by |
|---|---|
| Feasible lane / capacity result (`lane.evaluate`, `capacity.check`) | Commercial Pricing Specialist, as routing input to their own pricing calculation |
| `RouteRecommendation` (`route.recommend`, `route-deviation.propose`) | Pricing Manager, when an obligation routes it there (§5) |

Quote submission and `ApprovalTask` creation are **no longer this
role's output** — see §5's Finding 1/2 resolution; they moved to the
Commercial Pricing Specialist / became a system-internal consequence,
respectively.

## 5. Decisions

Cross-referenced to `business/decisions.md` (as reflected in
`authorization/policies.cedar`'s `@id`s):

- **D10/D11** — read-only, informational: check capacity, evaluate lane
  options. No approval gate; any active agent may do this.
- **D3a/D3b** — is the recommended lane contracted or not? A
  non-contracted lane is permitted but owes `oblig-lane-deviation`
  (customer-service review) — routed, not decided unilaterally.
- **D8** — does the recommended route exceed baseline cost by >8%?
  Permitted but owes `oblig-cost-variance-review`.
- **D9** — does the route add >3 transit days? Permitted but owes
  `oblig-transit-review`.
- **Finding 1/2, resolved.** This profile originally found
  `route-decision-agent` owning `quote.submit-for-approval` (writes
  `qms`) and `approval.request` (writes `workflow`) — neither is a
  `tms` action, which is what made it worth investigating rather than
  accepting because Cedar permitted it. The four-role review
  (`offer-to-execution-domain-review.md`) confirmed it: `business/
  decisions.md` D4/D12 (2 of 3 entries) already named
  `CommercialNormalizationAgent`, not `RouteDecisionAgent`, as this
  action's principal — `agents/catalog.yaml` had silently contradicted
  its own source document. Fixed: `quote.submit-for-approval` moved to
  `commercial-normalization-agent` (D5 corrected to match D4/D12);
  `approval.request` removed from `route-decision-agent` entirely,
  reasoned as a system-internal consequence of submission rather than a
  second agent-commanded action (avoids a QuoteVersion/ApprovalTask
  divergence risk). This role's agents now touch only `tms` and
  read-only `rate_management`/`qms` inputs — no write access outside
  Planning's own domain.

**Revise vs. request new operational inputs** — a distinction the
Commercial Pricing Specialist profile flagged as needing to be made
explicit from this side (`business/capability-profiles/README.md`'s
"Known refinement" note): when Pricing's calculation is blocked because
the *route itself* is the problem (infeasible, capacity-constrained, a
contracted lane no longer available), the correct response isn't a
local pricing revision — it's a re-evaluation request back to this
role, i.e. re-running `lane.evaluate`/`capacity.check`/`route.
recommend` with updated constraints, not adjusting a price against a
route that no longer holds. Not modeled as a distinct Cedar action or
message type today — this is the natural collaboration handoff (§10),
named so it isn't silently absorbed into "revise."

## 6. Business rules

- Same FX/margin thresholds as the Commercial Pricing Specialist
  profile's §6 — this role doesn't own those numbers, but is bound by
  them when it submits.
- Cost-variance threshold: >8% of baseline triggers `oblig-cost-
  variance-review` (`cost_variance_pct_x10 > 80`).
- Transit-time threshold: >3 days added triggers `oblig-transit-
  review` (`transit_variance_days > 3`).
- All enforced by Cedar today, verified by `src/rfq_common/tests/
  test_pdp_integration.py`.

## 7. KPIs

Industry-typical, **not computed by anything in this showcase today**:

- On-time load departure rate
- Lowest-cost-mode selection rate
- Load tender acceptance/rejection rate
- Route disruption/reroute frequency

Sources: [Velvet Jobs Transportation Planner](https://www.velvetjobs.com/job-descriptions/transportation-planner), [JobDescription.org Load Planner](https://jobdescription.org/jobs/transportation/load-planner)

## 8. Authority

- May evaluate/check capacity freely (D10/D11) — read-only, no approval
  gate at all. Notably **less approval authority** than the Commercial
  Pricing Specialist for the informational half of the job — nothing
  here requires escalation because nothing here commits the company to
  anything yet.
- May recommend a route (contracted or not) — always permitted, but
  non-contracted/high-variance recommendations carry obligations (D3b/
  D8/D9), same "permit + owe a review" pattern as the pricing side's
  D4a/D5.
- May **not** submit a quote at all, as of Finding 1's fix — that
  action moved to Pricing entirely, not merely gated for this role.
- May **not** approve — `route-deviation.approve` (D6) stays scoped to
  the Pricing Manager's `rfq-commercial-*` group; this role has no path
  to it.

## 9. Reports to / Manages

`identity/actors.yaml` today: `human.wei.planning`'s `manager` is
`diane.delgado` (Regional Commercial Director) directly. Unlike the
Pricing profile, this is **not flagged as a discrepancy to fix** — but
it should also not be read as validated: it's the *currently modeled
state*, not a researched claim about real logistics-org structure the
way the Pricing chain now is. The difference from Pricing is
specifically that no manager actor exists to report to yet (below),
not that flat-to-Director has been confirmed correct. `business/
job-titles.yaml`'s `operations-planner` (the natural management layer
for this department) is a researched-placeholder title with **no actor
in `identity/actors.yaml` yet** — so `transport-planner` deliberately
does **not** declare a `reports_to_job_title_id` in
`job-titles.yaml`. Declaring one now, with no manager actor to satisfy
it, would make `tools/identity/validator.py`'s management-chain check
fail against real data — the honest state is "no management layer
exists yet," not "the layer exists and is being skipped" (the actual
Pricing discrepancy that got fixed). Add `reports_to_job_title_id` here
only alongside an actual Operations Planner actor.

Manages: nobody (individual contributor).

## 10. Collaborates with

- **Commercial Pricing Specialist** (Pricing) — produces the route
  input their pricing calculation consumes (§4); receives re-evaluation
  requests when a route-level blocker surfaces (§5's revise-vs-
  request-new-inputs handoff — this is the receiving end of that
  collaboration).
- **Pricing Manager** (Commercial) — obligation reviews route through
  when D3b/D8/D9 fire, same escalation surface as the pricing side.
- **Carrier Procurement Specialist** (Carrier Procurement) — consumes
  negotiated rates for capacity/cost evaluation, same relationship as
  the Pricing profile's §10.

## 11. Candidate agent responsibilities

Two agents, not one — this role's job doesn't map to a single bounded
agent the way Commercial Pricing Specialist's does:

| Human responsibility (`business/job-titles.yaml`) | Agent contribution |
|---|---|
| "Create optimized shipment routes (distance, time, traffic, customer requirements)" | `lane-evaluation-agent`: `lane.evaluate`, `lane.option.create` |
| "Identify lowest freight cost and best mode to maximize efficiency" | `lane-evaluation-agent`: `capacity.check`, `carrier-rate.read` (thin, read-only — touches Carrier Procurement's territory, not a delegation of it) |
| "Plan, tender, and route daily shipments to meet cost/service parameters" (the recommend half) | `route-decision-agent`: `route.recommend`, `route-deviation.propose` — `quote.submit-for-approval`/`approval.request` removed, Finding 1/2 (§5) |
| *(deliberately not covered)* "Monitor load status; adjust plans for delays", "Communicate with drivers and carriers", "Analyze carrier trends, identify service issues" | — no `owned_actions` map here; stays human |

Neither agent may `route-deviation.approve`, `quote.approve`, or
`quote.reject` (§8).

## 12. Must remain human

**Human-accountable:**
- The recommend-vs-escalate call when D3b/D8/D9's obligations fire —
  same structural pattern as the pricing profile's revise-vs-escalate.

**Human-only today:**
- "Monitor load status; adjust plans for delays" — no disruption-
  monitoring tool/agent exists in this showcase yet.
- "Communicate with drivers and carriers" — no channel modeled.

**Potentially agent-assisted:**
- "Analyze carrier trends, identify service issues" — a real bullet
  from sourced postings, outside this subprocess's current scope, no
  principled barrier to eventual automation.
