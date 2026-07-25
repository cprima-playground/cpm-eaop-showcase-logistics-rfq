# Account Manager — capability profile

Fifth application of the golden template (schema: `business/
capability-profiles/README.md`). Grounds `job_title_id: account-
manager` (`business/job-titles.yaml`), actor `human.nadia.account`
(`identity/actors.yaml`), department `commercial` (`business/
departments.yaml`).

Written specifically to pressure-test the upstream boundary of the
chain the last four profiles established, and to answer: is `crm`
currently a real system of record, or a declared future boundary only?
Short answer, verified below: **declared future boundary only — no
`mock-crm` system exists anywhere in this showcase.**

## 1. Mission

Own the customer relationship; qualify and hand off an RFQ that the
offer-creation chain (Planning → Pricing → Commercial Governance) can
act on.

## 2. Primary systems

- **`crm`** — per `systems/systems-of-record.yaml:23-26`, owns `RFQ`
  and `ContractedLane`, interface `MCP` marked `TARGET`. **Verified: no
  `src/mock-crm/` directory exists** (confirmed against the actual
  business-system roster: `mock-fx`, `mock-masterdata`, `mock-qms`,
  `mock-rate`, `mock-tms`, `ops-dashboard` — six systems, none of them
  CRM). Unlike `rate_management` (Finding 4 — fixture data with no
  procurement lifecycle, but at least *data exists*), `crm` has **no
  data, no fixture, no API, nothing** — a purer gap than Finding 4, not
  a milder version of it.
- The `RFQ` **entity** already exists in `authorization/authz-
  projection.yaml` (`region`, `contracted_lane` attributes) and is
  consumed by real, tested actions (`lane.evaluate`, `route.recommend`)
  — so the *authorization model* is ahead of the *system of record*:
  Cedar can reason about an RFQ that no system actually produces.

## 3. Consumes

| Input | Produced by |
|---|---|
| Customer inquiry / shipment requirements | External — no system representation |
| Contract terms, existing lane agreements | `crm`'s `ContractedLane` — not implemented |

## 4. Produces

| Output | Consumed by |
|---|---|
| `RFQ` (qualified) | Transport Planner (`lane.evaluate`), and transitively the whole chain — **the entire offer-creation chain's input has no producer in this showcase today** |

## 5. Decisions — the questions this profile was asked to pressure-test

Answered against what actually exists, not hypothetically:

- **Who owns RFQ creation and qualification?** Organizationally, this
  role, per real job postings (§7 sources: "manage RFQs for large-scale
  logistics contracts," "prepare quotes... select carriers, set profit
  margins" — note the last one is Account-Executive-flavored postings
  blending into pricing work at smaller forwarders, a real-world
  blurring worth naming, not resolving). **Mechanically: nobody** — no
  action, no system, no test creates an `RFQ` anywhere in this
  showcase. Every `RFQ` referenced in the existing test suite (`Q-1001`
  etc.) is fixture/test data, not a system-produced artifact.
- **Customer requirements vs. operational constraints** — not
  distinguished anywhere. The `RFQ` entity's two attributes (`region`,
  `contracted_lane`) don't separate "what the customer asked for" from
  "what Planning determined is feasible" — both would currently have to
  live on the same entity or be inferred, since there's no `RFQ` vs.
  `RouteRecommendation` provenance link modeled beyond the bare
  entities themselves.
- **Who may change shipment assumptions after pricing starts?** No
  action exists for amending an in-flight `RFQ`. `business/decisions.
  md`'s proposed section (D16/D17 — `quote.create-version`,
  `quote.supersede`) covers re-versioning a *Quote* after a trigger
  event, but nothing covers amending the *RFQ* itself mid-pipeline.
- **Customer-facing release vs. internal quote approval** — already
  distinguished correctly by the Commercial Pricing Specialist profile
  (§5's three-operations split: price / submit-internally / release).
  This role would own "release," but no action or system represents it
  — same absence as RFQ creation, not a new one.
- **Acceptance/rejection/revision from the customer side** — nothing
  modeled. `quote.approve`/`quote.reject`/`quote.request-revision`
  (D19-D21, this session's fix) are explicitly the **internal**
  commercial-governance decision (`Principal` = the Pricing Manager's
  group). Whether the *customer* separately accepts/rejects the
  released quote is an entirely different, currently unmodeled,
  decision — conflating the two would be a mistake symmetrical to
  Finding 3's original one (reusing one action for two different
  business decisions).

## 6. Business rules

None — no action exists for this role to be bound by any rule.

## 7. KPIs

Industry-typical, **not computed by anything in this showcase today**:

- New-RFQ-to-qualified-RFQ cycle time
- RFQ-to-quote conversion rate
- Customer retention / relationship-health score
- Pipeline value under active RFQ

Sources: [Indeed Freight Forwarder Customer Service](https://www.indeed.com/q-freight-forwarder-customer-service-jobs.html), [Staffmark Account Executive](https://staffmark.com/jobs/detail/1001993831/account-executive-freight-forwarding-chandler-az/)

## 8. Authority

None modeled — symmetrical to the Carrier Procurement profile's §8: no
Cedar action exists for this role to hold authority over.

## 9. Reports to / Manages

`human.nadia.account`'s `manager` is `diane.delgado` (Regional
Commercial Director), direct — no intermediate Sales Manager actor
exists yet (`job-titles.yaml`'s `sales-manager` is a placeholder), same
honest framing as Transport Planner's §9 and Carrier Procurement's §9:
currently modeled state, not a validated claim the layer is
unnecessary.

Manages: nobody (individual contributor).

## 10. Collaborates with

- **Transport Planner** (Planning) — the intended handoff (§4), not
  currently backed by any action or system.
- Every other role in the chain, transitively — this role is the
  chain's origin point, per the diagram in `offer-creation-chain-
  review.md`, now extended one step further upstream.

## 11. Candidate agent responsibilities

None — matches Carrier Procurement's §11 reasoning exactly: no agent
should be assigned responsibilities that don't exist as modeled
business capabilities. "Qualify an RFQ" isn't yet a bounded capability
to delegate a subset of.

## 12. Must remain human

**Human-accountable:**
- The customer relationship itself, and the commercial commitment
  implied by qualifying an RFQ — same category as commercial-pricing-
  specialist.md's customer negotiation.

**Human-only today:**
- Everything else in this profile — no system exists for an agent to
  act through, the most literal instance of this category across all
  five profiles so far.

**Potentially agent-assisted:**
- RFQ intake triage/qualification against structured criteria, once
  `crm` exists as a real system — plausible first candidate, mirrors
  Carrier Procurement's "monitoring" candidate (read/classify work, not
  relationship work).

## 13. Finding 5: CRM/RFQ lifecycle absent — actor added, system parked separately

Two separate questions, resolved differently, per explicit instruction:
organizational completeness (add the human — done, `human.nadia.
account`) is independent of implementation completeness (the `crm`
system itself — not built, parked as Finding 5). The organization
represents the company as it exists; the human role doesn't need the
system to exist first, any more than Carrier Procurement's Felix needed
a procurement workflow to exist before being added.

```text
Account Manager   organization  YES     data/system  NO      lifecycle  NO
Carrier Proc.      organization  YES     data/system  YES     lifecycle  NO
```

Different maturity levels, both correctly represented now: Carrier
Procurement (Finding 4) has real fixture data but no lifecycle;
Account Management (Finding 5) has neither data nor system at all — a
bigger gap, not a milder version of the same one.

**Finding 5, stated plainly:** Cedar has an `RFQ` entity
(`authorization/authz-projection.yaml`) and real, tested downstream
actions that consume it (`lane.evaluate`, `route.recommend`), but no
system of record produces one — `crm` doesn't exist as `mock-crm` or
anywhere else in this showcase. Every `RFQ` in the test suite is
fixture/test data standing in for a producer that isn't there. Parked
alongside Finding 4, not scoped into any fix this session — a new
bounded-domain design, not a correction of disagreeing documents.

**Preserved for whenever CRM is built:** internal commercial approval
(`quote.approve`/`reject`/`request-revision`, D19-D21) and a future
customer-facing quote acceptance/rejection are **distinct lifecycle
decisions** (§5) — the future CRM/customer-facing work must get its own
actions and states, not reuse D19-D21, or it repeats Finding 3's
original mistake in a new place.
