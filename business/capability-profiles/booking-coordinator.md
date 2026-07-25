# Booking Coordinator — capability profile

Sixth application of the golden template (schema: `business/
capability-profiles/README.md`). Grounds `job_title_id: booking-
coordinator` (`business/job-titles.yaml`), actor `human.tariq.booking`
(`identity/actors.yaml`), department `operations` (`business/
departments.yaml`) — the department's first actor.

Written specifically to pressure-test what happens after commercial
success: `RFQ → route → price → internal approval → [missing] → 
executable shipment`. Verified, not assumed, against the actual code:
**Finding 6 — the quote-to-booking lifecycle is completely absent.**
`approved` is `QuoteVersion`'s terminal status
(`src/mock-qms/mock_qms/store.py` — confirmed by
`test_scenario_approval_decision.py`'s "re-deciding an already-decided
version is rejected — approved is terminal here"). Nothing consumes an
`approved` `QuoteVersion` to produce anything else. No `Booking` or
`Shipment` entity exists anywhere in this showcase — verified by
searching `src/mock-tms/mock_tms/` (zero matches for
`booking`/`shipment`) and `authorization/authz-projection.yaml` (no
such entity type).

## 1. Mission

Convert a commercially accepted quote into an executable booking,
carrying every commercial fact that must survive the QMS→TMS boundary.

## 2. Primary systems

- **`qms`** — source of the accepted `QuoteVersion`. Read-only for this
  role (verified: `approved` is terminal, nothing writes past it).
- **`tms`** — the presumed booking owner, **not confirmed by the code**.
  `systems/systems-of-record.yaml:28-31` lists `tms`'s ownership as
  `RouteTopology`, `FeasibleLane`, `TransitTime`, `Capacity` — no
  `Booking`/`Shipment` in that list either. So the presumption "TMS
  owns booking" is **unverified — nothing in this showcase owns it**,
  not even nominally.
- **`workflow`** — owns `ApprovalTask` only (the mechanism, per its own
  note); no booking-adjacent responsibility.

## 3. Consumes

| Input | Produced by |
|---|---|
| Accepted `QuoteVersion` (`status == approved`) | Pricing Manager's decision (D19) |
| *(missing — see §5)* Customer acceptance record | Nothing produces this; doesn't exist |

## 4. Produces

Intended, **none of it implemented**:

| Output | Consumed by |
|---|---|
| `Booking`/`Shipment` | Operations Coordinator (next profile) — no entity exists to produce |
| Immutable snapshot of commercial facts at conversion time | Downstream execution — no snapshot mechanism exists |

## 5. Decisions — answering the eleven pressure-test questions against what's verified

1. **What constitutes a commercially accepted quote?** Undefined.
   `approved` (internal governance, D19) is the only terminal positive
   state that exists. There is no separate "customer accepted" state —
   confirmed by `mock_qms/store.py`'s status vocabulary
   (`draft → priced → approval_required → approved|rejected|revise`,
   no state after `approved`). The Account Manager profile's §5 already
   named this gap; this profile confirms it against the actual code,
   not just the schema.
2. **Is acceptance recorded against `Quote`, `QuoteVersion`, RFQ, or a
   separate artifact?** Moot — nothing records it at all, against
   anything.
3. **Which quote version is converted?** Undefined — no conversion
   action exists to have a "which version" question. If built,
   `QuoteVersion` is the natural candidate (it's already the unit
   `approved` applies to), not `Quote` (the parent) or `RFQ` (upstream
   of pricing entirely).
4. **What facts become immutable at conversion?** Undefined. Worth
   naming what already *is* immutable upstream, as the pattern to
   extend: `test_scenario_hamburg_closure.py`'s finding that "the
   original priced version remains immutable" (per this repo's own
   established business-test pattern, `business/capability-profiles/
   README.md`'s baseline reference) — conversion should snapshot at
   least route, price, and commercial terms the same way, not just
   copy a live reference that could later change.
5. **New `Shipment`/`Booking`, or does the quotation evolve into one?**
   Undefined — no precedent either way exists in this codebase. The
   existing `quote.create-version`/`quote.supersede` pattern (D16/D17,
   proposed, not modeled) suggests this codebase's convention is
   *new-version-on-change*, not in-place mutation — if booking follows
   that convention, it's a new entity referencing the source
   `QuoteVersion`, not a mutation of it.
6. **Which system owns booking?** **Verified: none does** — see §2.
   The "presumably TMS" framing in the request that prompted this
   profile is not confirmed by `systems/systems-of-record.yaml`; stated
   here explicitly so nobody treats the presumption as fact later.
7. **Which commercial facts must cross the QMS→TMS boundary?** Not
   modeled, but derivable from what `QuoteVersion` and `RouteOption`
   already carry: parties (not modeled — masterdata `Party` exists but
   isn't linked to `Quote` today), route (`RouteOption`/
   `RouteRecommendation`), price (`Quote.status`-adjacent fields, not
   fully inspected here — out of this profile's scope), Incoterm
   (`masterdata` owns `Incoterm` per `systems/systems-of-record.
   yaml:13`, not linked to `Quote`), validity (no validity window
   exists on `Quote` at all — same gap Carrier Procurement's Finding 4
   found on the rate side).
8. **What happens if operational conditions change after acceptance
   but before booking?** Undefined — no state exists between
   "accepted" (itself undefined, §5.1) and "booked" (undefined, §5.5)
   for a change to occur in.
9. **Is booking conversion idempotent?** Undefined — same category as
   Finding 2's original obligation (test the transition as one atomic
   outcome, no duplicates) — worth stating now as a requirement for
   whenever this is built, not just for `approval.request`.
10. **Who may initiate conversion?** Undefined. Organizationally, this
    role, per real job postings (§7) — "ensure ocean carrier timely
    receipt/response of bookings," "coordinate shipments with
    forwarders." Whether Account Manager or system automation could
    also trigger it is unanswerable without the action existing first.
11. **What evidence links the resulting booking back to the exact
    accepted `QuoteVersion`?** Undefined — no linkage mechanism exists
    because neither side of the link exists yet.

## 6. Business rules

None modeled — no action exists for this role to be bound by any rule.

## 7. KPIs

Industry-typical, **not computed by anything in this showcase today**:

- Booking-to-departure lead time
- Booking accuracy (documentation matches accepted quote terms)
- On-time booking confirmation rate

Sources: [Velvet Jobs International Logistics Coordinator](https://www.velvetjobs.com/job-descriptions/international-logistics-coordinator)

## 8. Authority

None modeled — same category as Carrier Procurement's §8 and Account
Manager's §8: no Cedar action exists for this role to hold authority
over.

## 9. Reports to / Manages

`human.tariq.booking`'s `manager` is `diane.delgado` (Regional
Commercial Director), direct — first Operations department actor, no
intermediate manager exists yet (`business/job-titles.yaml` has no
Operations-department manager title at all, not even a placeholder —
a smaller gap than Planning's `operations-planner` placeholder, worth
noting as a job-titles.yaml completeness gap, not fixed here).

Manages: nobody (individual contributor).

## 10. Collaborates with

- **Pricing Manager** (Commercial) — source of the `approved`
  `QuoteVersion` this role would convert.
- **Account Manager** (Commercial) — the customer-facing release/
  acceptance step (Finding 5) sits between Pricing Manager's decision
  and this role's conversion; until that's built, there's no verified
  handoff between Account Manager and Booking Coordinator, only an
  inferred one.
- **Operations Coordinator** (next profile) — the natural downstream
  collaborator once a `Booking`/`Shipment` exists for them to execute
  against.

## 11. Candidate agent responsibilities

None — matches Carrier Procurement's and Account Manager's §11
reasoning: no agent should be assigned responsibilities that aren't
modeled business capabilities yet.

## 12. Must remain human

**Human-accountable:**
- Confirming a booking against a carrier — commitment/relationship
  work, same category as carrier-negotiation and customer-negotiation
  in earlier profiles.

**Human-only today:**
- Everything in §5 — no system representation exists for any of it,
  same literal reading as Account Manager's §12.

**Potentially agent-assisted:**
- Documentation generation (bills of lading, shipping labels) once the
  underlying `Booking` entity exists — mechanical, not judgment work.

## 13. Finding 6, consolidated

The quote-to-booking lifecycle boundary is **absent, not thin** — no
entity, no action, no owning system, verified against the actual
`mock-tms`/`mock-qms` code, not inferred from schema gaps alone. This
is the third and final boundary in the three-boundary map
`offer-to-execution-domain-review.md` predicted:

```text
Upstream:   Customer -> CRM/RFQ                  Finding 5
Buy side:   Carrier -> Procurement -> Rate        Finding 4
Downstream: Accepted Quote -> Booking/Shipment    Finding 6
```

Not scoped into any fix this session — new bounded-domain design, same
treatment as Findings 4/5. Human actor added (`human.tariq.booking`),
system parked, per the now-standing pattern from Findings 4/5:
organizational completeness doesn't wait for implementation.
