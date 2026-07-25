# Operations Coordinator — capability profile

Seventh application of the golden template (schema: `business/
capability-profiles/README.md`). Grounds `job_title_id: operations-
coordinator` (`business/job-titles.yaml`), actor
`human.sofia.operations` (`identity/actors.yaml`), department
`operations` (`business/departments.yaml`).

Written as a domain-boundary investigation, not a routine profile
application, per explicit instruction: does not assume Booking
Coordinator → Operations Coordinator is a clean handoff just because it
sounds organizationally plausible, and specifically tests whether
`booking-coordinator.md`'s Finding 6 ("quote-to-booking lifecycle
absent") is one missing domain or several.

## Verified starting point

Nothing new to search for — `booking-coordinator.md` already confirmed
zero `Booking`/`Shipment`/execution vocabulary anywhere in `src/
mock-tms/` or `authorization/authz-projection.yaml`. This profile
reasons from that absence, plus real logistics-domain practice and this
repo's own established modeling conventions (the Hamburg-scenario
immutability pattern, the `quote.create-version`/`quote.supersede`
new-version-on-change convention), not from any code that exists.

## 1. Mission

Own operational execution truth once a shipment moves from "planned/
booked" to "in motion" — feasibility was Planning's job; this is
whether it's actually happening as planned, and what to do when it
isn't.

## 5. Decisions — the domain-boundary questions, answered

(Numbering follows the template's Decisions section; answered first
since this profile's value is the investigation, not the org chart.)

**Are Booking and Shipment the same aggregate?** No — real logistics
practice (and this repo's own convention) argues they're distinct:
- A **Booking** is a *commercial/carrier commitment* — "carrier X has
  agreed to move this cargo on this service" — closer in kind to
  `Quote`/`QuoteVersion` (a commitment record) than to something that
  changes hour by hour.
- A **Shipment** is the *operational execution object* — the actual
  physical movement, with milestones, exceptions, and live state that
  changes continuously once cargo moves.
- Conflating them would repeat this session's Finding 3 mistake in a
  new place: one action/entity standing in for two genuinely different
  business decisions (commit vs. execute) with different write
  frequency, different owners, and different immutability needs.

**Can one accepted quote create multiple bookings/shipments?** Very
likely yes, organizationally — split shipments (partial loads, multiple
legs, multiple carriers for one RFQ) are routine in freight forwarding.
This alone is evidence Booking/Shipment can't be a 1:1 mutation of
`QuoteVersion` — it has to be a new entity type with a reference back,
consistent with the `quote.create-version`/`quote.supersede` (D16/D17)
convention already established for the *Quote* side.

**Who owns pickup/delivery instructions, equipment, milestones,
documents, exceptions?** Split by nature, not one owner:
- Equipment (container/vehicle type) references `masterdata`'s
  `Equipment` entity (`systems/systems-of-record.yaml:13`) — reference
  data, already has a home, just not linked to anything booking-shaped
  yet.
- Pickup/delivery instructions, milestones, documents, exceptions —
  none have any home today. These are naturally *this role's*
  candidate ownership (Operations), distinct from Booking Coordinator's
  commitment-side ownership.

**When does route planning stop and execution start?** At the moment a
`RouteRecommendation` gets attached to a live movement, not before.
Planning's outputs (`RouteOption`, `RouteRecommendation`) are
evaluation-time artifacts — they answer "could this work," not "is this
happening." The transition point is exactly where Booking would sit if
it existed: recommendation → commitment → execution, three stages, not
two.

**Does TMS own execution truth even without owning the commercial
booking?** Plausible and consistent with this repo's SoR-fragmentation
principle (`systems/systems-of-record.yaml`'s header: "truth is
fragmented... name exactly one authoritative owner" per object, not
per system) — TMS already owns `Capacity`/`TransitTime` (planning-time
facts); it's a reasonable extension for TMS to also own live execution
facts (milestones, ETAs) while a *different* system (today, nothing)
owns the commercial booking commitment. Not verified by any code —
reasoned from the existing ownership-fragmentation pattern, flagged as
reasoning, not fact.

**What happens when execution deviates from the accepted route/price?**
Two genuinely different response paths, not one:
- Operational replanning (find another route/carrier) — Planning's
  domain, re-running `lane.evaluate`/`route.recommend`, same as the
  Transport Planner profile's already-documented "revise vs. request
  new operational inputs" handoff.
- Commercial re-evaluation (does the deviation change the price/margin
  enough to need Pricing Manager involvement) — Pricing's domain,
  D3b/D8/D9's obligation pattern already exists for exactly this at
  the *recommendation* stage; whether it should re-trigger post-
  booking is a real open question this profile surfaces, not answers.

**Does post-booking disruption trigger operational replanning,
commercial re-evaluation, or both?** Per the above: **both are
plausible, depending on disruption severity**, and nothing in this
repo currently has a threshold or trigger to decide which. This is a
genuine new decision, not covered by extending D8/D9 (those gate a
*recommendation*, not a live deviation from an already-committed one).

**Which facts are snapshots vs. live operational facts?** The Hamburg-
scenario pattern (`test_scenario_hamburg_closure.py`,
`commercial-pricing-specialist.md`'s baseline reference) already
establishes the convention: **the accepted commercial terms are
immutable at the point of commitment**; operational facts (route
status, milestones, ETAs) are live and can diverge from what was
committed. Booking should snapshot price/route/terms at commitment
time; Shipment should carry live operational state referencing that
snapshot, not replacing it.

**What may Operations change without reopening commercial approval?**
Operational facts only (§ above) — carrier substitution within the same
commercial terms, milestone updates, exception handling that doesn't
change price or route commitment. Anything that changes price, route,
or carrier in a way that affects the accepted commercial terms should
re-trigger Pricing/Planning, not be silently absorbed as an operational
update — same principle as Finding 3's original lesson (don't let one
role's action silently stand in for a different role's decision).

## Finding 6 is split, not one thing

Per this investigation: **yes, split it.** Five distinct
domain/lifecycle stages, not one missing "booking" concept:

```text
CustomerAcceptedQuote   (Finding 5's missing piece -- customer
                          acceptance itself, distinct from D19's
                          internal approval)
        |
        v
Booking                 (commercial/carrier commitment -- owner: TBD,
                          not TMS per §5's "who owns booking" answer,
                          not QMS since QuoteVersion is terminal at
                          `approved`)
        |
        v
Shipment                (operational execution object -- owner:
                          plausibly TMS, per SoR-fragmentation
                          reasoning, unverified)
        |
        v
Execution               (live milestones/state -- same owner as
                          Shipment, most likely)
        |
        v
OperationalException     (deviation handling -- may trigger Planning
                          re-evaluation, Pricing re-evaluation, or
                          both -- no threshold exists to decide which)
```

**Recommendation, not applied:** retire "Finding 6" as a single item in
future references; the three-boundary map in `offer-creation-chain-
review.md` should note Finding 6 as "5 sub-stages, distinct ownership
questions" rather than one. Do not design a single "booking" entity —
design the boundary between commitment (Booking) and execution
(Shipment) first, since that's the one with the clearest evidence of
being genuinely different aggregates (different write frequency,
different immutability needs, plausibly different owning systems).

## 9. Reports to / Manages — the organizational-structure question

`human.sofia.operations`'s `manager` is `diane.delgado`, same as
`human.tariq.booking` — both Operations actors report directly to the
Director, because **no Operations Manager actor exists**.

Per instruction, not fixed by inventing one — but the structure is now
named, not silently absent: `business/job-titles.yaml` gained an
`operations-manager` placeholder (level: manager, department:
operations, `responsibilities: []`, no actor) — the recognizable shape
this investigation supports:

```text
Operations Manager
   |-- Booking Coordinator
   |-- Operations Coordinator
```

This mirrors Commercial's already-fixed Specialist→Manager→Director
pattern, but **no actor is added** — unlike Account Manager/Carrier
Procurement/Booking Coordinator, there's no equivalent "the organization
needs this specific person to be recognizable" justification yet for a
manager role neither of Operations' two ICs currently need for their
own profiles to make sense. Add the actor only if a future profile
finds a concrete reason (e.g. an escalation/authority decision that
needs a manager-tier principal), not preemptively.

## 2-4, 6-8, 10-12: template sections deferred

This profile's value is the domain-boundary investigation above (§5)
and the org-structure finding (§9) — the remaining template sections
(Primary systems detail, Consumes/Produces tables, Business rules,
KPIs, Authority, Collaborates-with, Candidate agent responsibilities,
Must-remain-human) would currently just restate "undefined, no system
exists" seven more times, the same way `booking-coordinator.md`'s did.
Deliberately skipped rather than padded — fill in once the
Booking/Shipment split above gets real design, at which point they'll
have real content to describe rather than another round of absence.
