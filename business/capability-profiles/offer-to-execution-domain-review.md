# Offer-to-execution domain review

Renamed from "Four-role review: the core offer-creation chain" — that
name stopped fitting once Account Manager, Booking Coordinator, and
Operations Coordinator's findings (5, 6, and 6's split) extended it
past four roles and past "offer creation" into the pre-execution
boundary. Content preserved below; only the title and this framing
paragraph changed. Supersedes nothing in `planning-pricing-governance-
review.md` (the original 3-role review) — this document is the
architecture map for the whole discovery pass, not a replacement.

## Landscape (7 profiles, 6 findings)

```text
                    Finding 5
Customer  ------>  CRM/RFQ
                       |
                       v
          [implemented core, coherent after Findings 1-3]
Planning  ------>  Pricing  ------>  Commercial Governance
                       |
                       v
                    Finding 6 (split into 5 sub-stages)
Accepted Quote -> Booking -> Shipment -> Execution -> OperationalException

Buy-side parallel:
Carrier  ------>  Procurement  ------>  Rate
                    Finding 4
```

## Pause point

Per explicit instruction: **pause persona expansion here.** The
template validated itself across 7 role shapes (production specialist,
planning specialist, governance manager, procurement specialist,
account management, booking/operations boundary) — further profiles
(Sales Manager, Billing, Customs) are deferred until the showcase
scope actually extends from the current "offer creation → approval →
pre-execution boundary" into full offer-to-cash. Not doing that
extension by default; a deliberate future scope decision.

## Domain-boundary synthesis, Findings 4-6 (decision backlog, no code changes)

| Boundary | Aggregate candidates | Likely SoR | Current evidence | Open decisions |
|---|---|---|---|---|
| Procurement → Rate (Finding 4) | `CarrierOffer`, `CarrierRate`, `RateAgreement` | Rate Management (`rate_management`) | Fixtures exist (`systems/rate/fixtures/rates.yaml`), flat/undifferentiated, no provenance | Contract vs. spot distinction; negotiation provenance; validity windows; offer-vs-selected-rate split |
| CRM → RFQ (Finding 5) | `CustomerInquiry`, `RFQ`, `ContractedLane` | CRM (`crm`) | Cedar `RFQ` entity only — no system, no data, nothing produces one | Qualification lifecycle; amendment after pricing starts; customer-requirements-vs-operational-constraints separation |
| Quote → Booking/Shipment (Finding 6) | `CustomerAcceptedQuote`, `Booking`, `Shipment`, `Execution`, `OperationalException` | Unresolved (Booking) / plausibly TMS (Shipment/Execution), unverified | Nothing exists — `approved` is `QuoteVersion`'s terminal status, zero booking/shipment vocabulary anywhere in `mock-tms` | Ownership (who owns Booking if not TMS or QMS); commitment/execution snapshot boundary; idempotent conversion; multi-booking-per-quote; disruption → replanning vs. re-pricing trigger |

This table is the decision backlog for whichever boundary gets scoped
for real design later — not a design itself, no aggregates chosen, no
code touched producing it.

## What not to build next, by default

Per instruction: do not build CRM, `CarrierRate`, Booking, or Shipment
off the back of this discovery pass alone — each needs its own
deliberate scoping/design pass (matching how M1-M7's implementation
plan already treats new domain work: ADR first, then implementation),
not a reflexive "we found a gap, fill it" reaction.

## The chain

```text
Carrier Procurement Specialist
    -> [not modeled] negotiate/publish ContractRate, CarrierSpotRate
    -> rate_management (currently: fixture data, no provenance/lifecycle)
            |
            v
Transport Planner
    -> reads rate_management (carrier-rate.read) + tms
    -> produces RouteRecommendation, feasible-lane/capacity facts
            |
            v
Commercial Pricing Specialist
    -> prices QuoteVersion
    -> determines commercial exception state (FX variance, margin floor)
    -> [contested — Finding 1] submits QuoteVersion for approval
            |
            v
Pricing Manager (Commercial governance)
    -> decides: approve | reject | revise (mock_qms's real vocabulary)
    -> QuoteVersion.status becomes authoritative
```

## Per-role summary

| Role | Mission | Cedar authority | Agent coverage | Headline finding |
|---|---|---|---|---|
| Carrier Procurement Specialist | Source/negotiate buy rates | None modeled | None (nothing to bound an agent against) | `rate_management` is fixture data, not a procurement SoR |
| Transport Planner | Feasible, capacity-checked routes | Read-only informational (D10/D11) + recommend w/ obligations (D3/D8/D9) | `lane-evaluation-agent` + `route-decision-agent` | `route-decision-agent` also owns `quote.submit-for-approval`/`approval.request` — reaches into `qms`/`workflow`, contested (Finding 1) |
| Commercial Pricing Specialist | Price a compliant quotation | Gated by D1/D2/D4/D5/D12's thresholds, no approval authority | `commercial-normalization-agent` | `decisions.md` D4/D12 say *this* role's agent should submit — contradicted by `catalog.yaml` |
| Pricing Manager | Decide the commercial exception | D6 (approve only, 10k EUR limit) | None (structurally excluded from every agent) | Real system supports 3 decision outcomes; Cedar models 1 |

## Consolidated findings (renumbered across all four profiles)

1. **`quote.submit-for-approval` ownership contradiction** — `decisions.
   md` D4/D12 (CommercialNormalizationAgent) vs. D5 + `catalog.yaml`
   (RouteDecisionAgent). Cedar silent (unscoped principal). Evidenced
   in `planning-pricing-governance-review.md`, reinforced here: the
   role that should submit (per weight of evidence) is the one whose
   entire mission is producing the thing being submitted (Pricing), not
   the one whose domain is routes (Planning).
2. **`approval.request` has no `decisions.md` entry** — currently
   `route-decision-agent`'s, unchecked against anything.
3. **Cedar under-covers the real QMS decision vocabulary** —
   `approved`/`rejected`/`revise` exist and are role-gated in
   `mock_qms`; Cedar only models `approve` (D6). `revise` has an
   explicit unfilled-`D19` code comment.
4. **`rate_management` has no procurement domain model** — no
   `CarrierRate` entity (even proposed ones, D14/D15/D18, are read-side
   only), no contract-vs-spot distinction, no provenance, no validity
   window. The write/negotiate/publish side of Carrier Procurement's
   job has literally nothing to attach to. Larger in kind than Findings
   1-3: those are disagreements between existing documents, this is an
   absent domain model.

## What's solid, not just what's broken

Worth stating plainly since four findings in a row reads as "everything
is wrong" — it isn't:

- The **read-side** of the chain is consistently well-modeled:
  `capacity.check`/`lane.evaluate` (D10/D11), `fx-rate.read`/
  `route-cost.normalize` (D1/D2) are all real, tested, unambiguous.
- The **approval boundary** (D6, `route-deviation.approve`) is
  unambiguous and consistently enforced — every agent's
  `prohibited_actions` respects it, no exceptions found across four
  profiles.
- The **obligation pattern** (D3b/D4a/D5/D8/D9 — permit-with-review) is
  applied consistently across both Planning's and Pricing's
  recommendation/submission paths.
- The capability-profile template itself held across four genuinely
  different role shapes (production specialist, governance manager,
  cross-boundary specialist with no implementation at all) without
  forcing — that was the standing question from the second profile
  onward, and it's answered.

## Findings 1-3, resolved

Per explicit instruction: fix 1-3 now (existing, already-exercised
capabilities disagreeing across documents), defer 4 (a real new
domain-model design, not a correction). Applied:

**Finding 1** — `quote.submit-for-approval` reassigned to
`commercial-normalization-agent`; removed from `route-decision-agent`.
`business/decisions.md` D5's principal corrected from
`RouteDecisionAgent` to `CommercialNormalizationAgent`, matching D4/D12
(2 of 3 entries were already right — D5 was the outlier, not
`catalog.yaml`'s original assignment). Files: `agents/catalog.yaml`,
`business/decisions.md`.

**Finding 2** — `approval.request` removed from `route-decision-agent`
entirely, not reassigned. Reasoning applied as given: ApprovalTask
creation is a system-internal consequence of `quote.submit-for-
approval`'s QMS state transition to `approval_required`, not an
independent agent-commanded action — avoids the submitted-but-no-task /
task-but-never-submitted divergence risk. `interfaces/mcp/tools.yaml`'s
`create_approval_task` tool flagged as needing reassignment when the
system-internal trigger is actually implemented (not done here — no
workflow-triggering code exists in this showcase to wire it into).

**Finding 3** — three new Cedar actions on the actual `Quote` resource,
replacing the ad hoc reuse of `route-deviation.approve`:
`quote.approve` (D19, same 10,000 EUR limit as D6), `quote.reject`
(D20, no value limit), `quote.request-revision` (D21, no value limit —
honors `mock_qms/templates/quote_detail.html:129`'s pre-existing
"D19-candidate" code comment by giving `revise` its real number, D21).
All three `Principal`-only in `business/actions.yaml`'s schema — an
`AgentPrincipal` can't structurally hold them, not just
policy-forbidden, verified by a new test
(`test_agent_cannot_approve_quote`). `mock_qms`'s decision-endpoint UI
comments updated to cite the real decision numbers; the endpoint itself
is not yet wired to call the PDP (that's M4a's job, not this fix's).
Files: `business/actions.yaml`, `authorization/agentic.cedarschema`
(regenerated), `authorization/policies.cedar`, `business/decisions.md`,
`src/mock-qms/mock_qms/{api.py,templates/quote_detail.html}`.

Verification: `src/rfq_common/tests/test_pdp_integration.py`, 11/11
passing (4 new tests for D19/D20/D21 + the AgentPrincipal-structurally-
denied case). All four capability-profile documents
(`commercial-pricing-specialist.md`, `transport-planner.md`,
`pricing-manager.md`) updated to describe the resolved state rather
than the original finding as still-open.

## Future obligations created by Finding 2's fix

Removing `approval.request` as an agent action doesn't remove the
divergence risk it was protecting against (submitted-but-no-task /
task-but-never-submitted) — it moves that risk into the application
layer, where it becomes an implementation obligation for whenever the
workflow-side trigger is actually built (not now — no such trigger
exists in this showcase yet):

1. **Test the transition as one atomic business outcome**, not two
   independent calls: `quote.submit-for-approval` → `QuoteVersion.
   status == approval_required` → exactly one `ApprovalTask` exists.
   Idempotent retry must not create duplicates.
2. **`interfaces/mcp/tools.yaml`'s `create_approval_task` is invalid,
   not merely stale**, once that trigger exists — remove it from the
   agent-facing MCP surface entirely, or redefine it as an internal-only
   workflow capability never callable by business agents. Leaving it
   advertised as an agent tool would have the interface catalog
   contradict the domain model this fix just established.

## Finding 5 (Account Manager profile): CRM/RFQ lifecycle absent entirely

A bigger gap than Finding 4, not a milder version: `rate_management`
(Finding 4) at least has real fixture data with no lifecycle; `crm` has
**no data, no system, nothing** — confirmed against the actual 6-system
roster (`mock-fx`/`mock-masterdata`/`mock-qms`/`mock-rate`/`mock-tms`/
`ops-dashboard`, no CRM). Cedar's `RFQ` entity and its consuming actions
(`lane.evaluate`, `route.recommend`) are real and tested, but nothing
in this showcase produces an `RFQ` — every one in the test suite is
fixture data standing in for an unbuilt producer.

**Resolved differently from Finding 4's "park everything":** the human
actor (`human.nadia.account`, Account Manager) was added this session —
organizational completeness doesn't require the system to exist first,
same treatment as Carrier Procurement's Felix. The `crm` system itself
remains parked alongside Finding 4, unscoped.

**Also preserved from this profile:** internal commercial approval
(D19-D21) and a future customer-facing quote acceptance/rejection are
distinct lifecycle decisions — whenever `crm`/customer-facing work is
built, it needs its own actions, not reuse of D19-D21.

## Finding 6 (Booking Coordinator profile): quote-to-booking lifecycle absent

The third and final boundary predicted after Finding 5 — verified
against actual code, not inferred from schema gaps: `approved` is
`QuoteVersion`'s terminal status (`src/mock-qms/mock_qms/store.py`,
confirmed by `test_scenario_approval_decision.py`), nothing consumes
it. No `Booking`/`Shipment` entity exists anywhere — zero matches
searching `src/mock-tms/mock_tms/`, none in `authorization/
authz-projection.yaml`. The presumption "TMS owns booking" is
explicitly **not confirmed** — `systems/systems-of-record.yaml`'s `tms`
ownership list doesn't include it either; nobody owns it, not even
nominally.

Human actor added (`human.tariq.booking`, first Operations department
actor), same organizational-completeness-independent-of-implementation
treatment as Findings 4/5. `booking-coordinator.md` §5 answers all
eleven pressure-test questions the request posed — all eleven resolve
to "undefined, verified" rather than "assumed."

## Three-boundary map (Findings 4-6) — Finding 6 split by the Operations Coordinator profile

```text
Upstream:   Customer -> CRM/RFQ                  Finding 5  (no data, no system)
Buy side:   Carrier -> Procurement -> Rate        Finding 4  (data exists, no lifecycle)
Downstream: Accepted Quote -> ... -> Execution    Finding 6  (5 distinct sub-stages, not one gap)
```

`operations-coordinator.md`'s domain-boundary investigation (explicit
instruction: don't assume Booking→Operations is a clean handoff)
determined Finding 6 isn't one missing "booking" concept — it's five
distinct lifecycle stages with different owners and immutability needs:

```text
CustomerAcceptedQuote -> Booking -> Shipment -> Execution -> OperationalException
```

Booking (commercial/carrier commitment) and Shipment (operational
execution object) are the clearest evidence of genuinely different
aggregates — different write frequency, different owner candidates
(Booking's owner unresolved; Shipment plausibly TMS, unverified,
reasoned from the SoR-fragmentation pattern already used elsewhere in
this repo). Recommendation: design the Booking/Shipment boundary first
when this gets real design work, not one undifferentiated entity.

The implemented core (Planning → Pricing → Commercial Governance,
internally consistent after Findings 1-3) sits between three
consistently thin boundaries — this map, now corrected for Finding 6's
internal structure, is the useful artifact this review round produced.

## Finding 4 — still deferred

Explicitly not scoped into the fix above, per instruction: `rate_
management`'s domain model (`CarrierRate`/`CarrierOffer` distinction,
contract vs. spot, validity periods, provenance, publication lifecycle)
is new design work, not a correction of disagreeing documents. Parked
as its own future milestone, alongside Findings 5 and 6.

## Next

Nothing scheduled. Per the pause-point above: choose which boundary
(Finding 4, 5, or 6) best advances the showcase narrative when ready
for real design, or extend into full offer-to-cash (Sales Manager,
Billing, Customs) as a deliberate scope decision — neither decided
here.
