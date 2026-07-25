# Carrier Procurement Specialist — capability profile

Fourth application of the golden template (schema: `business/
capability-profiles/README.md`). Grounds `job_title_id: carrier-
procurement-specialist` (`business/job-titles.yaml`), actor
`human.felix.procurement` (`identity/actors.yaml`), department
`carrier-procurement` (`business/departments.yaml`).

This profile was written specifically to answer: **who owns the
commercial buy-side truth**, and is `rate_management` currently a real
procurement system of record or just fixture data standing in for one?
Short answer, evidenced below: **fixture data only** — no procurement
provenance or lifecycle is modeled anywhere in this showcase today.

## 1. Mission

Source, negotiate, and maintain the carrier buy rates that Planning and
Pricing consume — the commercial buy-side counterpart to what Pricing
does on the sell side.

## 2. Primary systems

- **`rate_management`** — owns `ContractRate`, `CarrierSpotRate`,
  `LaneSurcharge` per `systems/systems-of-record.yaml:33-39`. This
  role's intended home system. **Finding, verified against the actual
  fixture file** (`systems/rate/fixtures/rates.yaml`): the real data
  shape is `{route_id, carrier_id, currency, base_cost, surcharges,
  capacity_status}` — flat, undifferentiated numbers. No `contract_id`,
  no `valid_from`/`valid_to`, no `negotiated_by`, no field
  distinguishing a negotiated contract rate from an ad-hoc spot rate.
  `ContractRate` and `CarrierSpotRate` are named as two entities in
  `systems-of-record.yaml`'s ownership list, but nothing in the actual
  data or code represents them as two different things — there is one
  undifferentiated rate row per route/carrier. **`rate_management` is a
  Rate SoR *fixture*, not yet a procurement system with real
  provenance or lifecycle.**
- **`masterdata`** — owns `Party` (carrier identity, referenced by
  `carrier_id`, per `systems/systems-of-record.yaml:38-39` — carrier
  identity was deliberately moved out of the rate fixture itself,
  ADR-010).

## 3. Consumes

| Input | Produced by |
|---|---|
| Carrier market offers (RFQ from carriers, spot-market postings) | External — not represented by any system in this showcase |
| Carrier identity (`Party`) | `masterdata` |
| Lane/volume forecast (what routes need rate coverage) | Transport Planner, informally — no explicit action or message models this handoff |

## 4. Produces

Intended (per real job-posting responsibilities, `business/job-titles.
yaml`), **none of it Cedar-modeled or system-implemented today**:

| Output | Consumed by |
|---|---|
| Negotiated `ContractRate` | `rate_management` — in principle; in practice, `rates.yaml` is hand-authored fixture data, not written by any procurement action |
| `CarrierSpotRate` (ad hoc, shorter validity) | Same gap |
| Rate-validity/expiry status | Transport Planner, Commercial Pricing Specialist — neither currently receives an expiry signal; `capacity_status` is the only lifecycle-adjacent field that exists, and it's a capacity flag, not a rate-validity one |

## 5. Decisions

This is the profile section that most clearly shows the modeling gap.
The responsibilities a real Carrier Procurement Specialist has, broken
into the granularity the user asked this profile to distinguish, and
what (if anything) represents each today:

| Responsibility | Modeled today? |
|---|---|
| Sourcing a carrier offer | No — no system, no action |
| Negotiating the buy rate | No — no system, no action |
| Accepting/selecting a carrier offer | No — `rates.yaml` has one rate per route/carrier pair; there's no "offer" concept to select among, no alternative-offer comparison |
| Validating validity/capacity conditions | Partial — `capacity_status` (`available`/`limited`) exists as a fixture field, but nothing *validates* it; it's read, not maintained through a decision |
| Maintaining contracted rates | No — `rates.yaml` is static fixture content, edited by a developer, not through any modeled business capability |
| Requesting spot rates | No |
| Publishing an approved rate into Rate Management | No — there's no "approved" state; a rate exists or it doesn't |
| Monitoring expiry/market changes | No — no validity window field exists to expire |

Contrast with `business/decisions.md`'s "Proposed — not yet modeled"
section: **D14** (`rate.read`, `LaneEvaluationAgent` reads a
`CarrierRate`) and **D15** (`buy-rate.read`, `CommercialNormalizationAgent`
reads the underlying buy rate, confidentiality-scoped) both already
anticipate a `CarrierRate` entity distinct from today's schema's
`RouteOption` — but both are read-side, proposed, and unimplemented.
**Nothing in `decisions.md`, proposed or modeled, addresses the
write/negotiate/publish side this role actually owns.** D13-D18 cover
what agents may *read*; this profile's §5 table is empty on the
*write* side because no one has proposed it yet, not because it was
proposed and rejected.

## 6. Business rules

None modeled. No margin/threshold/validity rule exists for this role
in `authorization/policies.cedar` or `business/actions.yaml` — there is
no `business/actions.yaml` entry for carrier-rate negotiation at all
(only `carrier-rate.read` exists, and per §8 below, that's not this
role's action).

## 7. KPIs

Industry-typical, **not computed by anything in this showcase today**:

- Buy-rate savings vs. prior contract / market benchmark
- Contract coverage ratio (% of active lanes with a negotiated rate vs. spot-only)
- Carrier on-time/service-failure rate (informs future negotiation)
- Rate-sheet currency (days since last update)

Sources: [RXO Carrier Procurement Specialist](https://simplify.jobs/p/f2609f31-2e54-468c-a0cf-7fd0286f046f/Carrier-Procurement-Specialist), [Skypace Ocean Freight Carrier Representative](https://skypace.com/careers/carrier-representative-procurement-specialist-ocean-freight-woodlands-onsite)

## 8. Authority

None modeled — no Cedar action exists for this role to hold authority
over. `identity/actors.yaml`'s `human.felix.procurement` correctly has
no `member_of`, no `approval_limit`, per `business/departments.yaml`'s
honest `maturity: {apis: future, mcp: future, agents: none}` flag.

**On `carrier-rate.read` specifically — do not assign it here.** Per
this session's explicit instruction: `carrier-rate.read`'s resource
type is `RouteOption` (`business/actions.yaml`), not a `CarrierRate`
entity — it doesn't exist yet even in the schema (only proposed, §5).
`carrier-rate.read` is Transport Planner's action (already correctly
placed in `transport-planner.md` §11, owned by `lane-evaluation-agent`)
— it's "read the rate info attached to this route option while
evaluating routes," not "manage a carrier rate." Reading a number and
owning its negotiation/lifecycle are different capabilities; the name
containing "carrier rate" is not evidence they're the same one.

## 9. Reports to / Manages

`human.felix.procurement`'s `manager` is `diane.delgado` (Regional
Commercial Director) — same as Transport Planner: no intermediate
manager actor exists (`carrier-procurement-manager` in `business/
job-titles.yaml` is a placeholder, `exists_today: false`). Same
honest framing as `transport-planner.md` §9 — currently modeled state,
not a validated claim about the layer being unnecessary.

Manages: nobody (individual contributor).

## 10. Collaborates with

- **Transport Planner** (Planning) — supplies the rate data Planning's
  `capacity.check`/`carrier-rate.read` reads (§8's boundary: Planning
  reads, this role would own the write side if it existed).
- **Commercial Pricing Specialist** (Pricing) — per `business/
  departments.yaml`'s explicit distinction: Pricing *consumes* buy
  rates, Carrier Procurement *negotiates* them. Confirmed, not just
  asserted, by this profile: nothing in `commercial-pricing-
  specialist.md`'s `owned_actions` writes to `rate_management`, only
  reads (`carrier-rate.read` is Planning's, not even Pricing's).

## 11. Candidate agent responsibilities

None — matches Pricing Manager's profile (§11 there): no agent should
be assigned responsibilities that don't exist as modeled business
capabilities yet. Building an agent for carrier negotiation before the
underlying `rate_management` domain model (contract vs. spot, validity,
provenance) exists would be automating a capability the system can't
yet represent, not a bounded subset of a real one.

## 12. Must remain human

**Human-accountable:**
- Negotiating carrier rates — commercial relationship/trust work, not
  computation, same category as customer negotiation in the Pricing
  profile.

**Human-only today:**
- Everything in §5's table — not because it's judgment-only in
  principle, but because none of it has a system representation yet
  for an agent to act through. This is the "human-only today" category
  at its most literal: not a scope limit on an existing agent, an
  absence of any capability to bound one against.

**Potentially agent-assisted:**
- Monitoring expiry/market changes, once a validity field exists —
  plausibly the first candidate for automation once `rate_management`'s
  domain model catches up, since it's read/alert work, not negotiation.

## 13. Finding, for the four-role review

`rate_management` is a **Rate SoR fixture**, not a procurement system
with real provenance or lifecycle, per §2/§5's evidence. This is a
larger gap than Findings 1-3 from `planning-pricing-governance-review.
md` — those were *ownership* disagreements between existing documents;
this is an **absent domain model** — there's no `CarrierRate` entity in
`authorization/authz-projection.yaml` even as a stub, no write-side
action in `business/actions.yaml`, and the fixture data itself has no
provenance fields to build one from later without a real schema change
to `systems/rate/fixtures/rates.yaml`. Feeds into the four-role review
below, not resolved here.
