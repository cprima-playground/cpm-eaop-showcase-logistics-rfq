> **Status: Findings 1-3 resolved.** See
> `offer-to-execution-domain-review.md`'s "Findings 1-3, resolved" section
> for the applied fix. This document is kept as the original evidence
> trail — findings below are described as they were when discovered,
> not retroactively edited to read as already-fixed.

# Three-profile responsibility-boundary review

Synthesis across `transport-planner.md`, `commercial-pricing-
specialist.md`, and `pricing-manager.md` — the three profiles
requested specifically to pressure-test one question the Transport
Planner profile raised: does `agents/catalog.yaml` assign
`quote.submit-for-approval`/`approval.request` to the right agent?

**Nothing in `agents/catalog.yaml`, `business/decisions.md`, or
`authorization/policies.cedar` is changed by this document.** Findings
only — a recommendation for a future, separate change.

## The intended collaboration, as the three profiles converge on it

```text
Transport Planner (Planning)
    -> produces RouteRecommendation, feasible-lane/capacity facts

Commercial Pricing Specialist (Pricing)
    -> prices QuoteVersion
    -> determines commercial exception state (FX variance, margin floor)
    -> [intended] submits QuoteVersion for approval

Pricing Manager (Commercial)
    -> receives the submission
    -> decides: approve | reject | revise (real mock_qms vocabulary)
    -> QuoteVersion.status becomes authoritative
```

Each arrow above is independently well-grounded (Cedar policy or a
system-of-record fact) except the one that turned out to be contested:
Pricing "submits."

## Finding 1 (primary): `quote.submit-for-approval` ownership is documented three different ways

| Source | Says the principal for `quote.submit-for-approval` is |
|---|---|
| `business/decisions.md` D4 (`forbid-auto-replace-on-fx`) | `CommercialNormalizationAgent` |
| `business/decisions.md` D12 (`submit-quote-when-within-thresholds`) | `CommercialNormalizationAgent` |
| `business/decisions.md` D5 (`propose-below-floor`) | `RouteDecisionAgent` |
| `agents/catalog.yaml` `owned_actions`/`prohibited_actions` | `RouteDecisionAgent` only; `CommercialNormalizationAgent` explicitly prohibited |
| `authorization/policies.cedar` (`forbid-auto-replace-on-fx`, `submit-quote-when-within-thresholds`, `propose-below-floor`) | Unscoped (`principal` bare) — silent on which agent |

Three sources, three different answers, and Cedar itself doesn't
adjudicate because none of its `quote.submit-for-approval` policies
restrict the principal type. This is why the inconsistency has produced
no failing test: nothing currently checks it.

**Weight of evidence** (from the three capability profiles):
- `pricing-manager.md` §2: `qms` is explicitly the system of record for
  the human *decision* (`systems/systems-of-record.yaml:46-48`) —
  submission into that decision process is a natural extension of the
  same domain, not Planning's.
- `pricing-manager.md` §8/D6: the *decide* side is unambiguously
  Pricing-Manager-owned (`route-deviation.approve` scoped to
  `rfq-commercial-*`).
- `commercial-pricing-specialist.md` §5/§8: the specialist already owns
  the pricing/variance calculation that determines *whether*
  submission is even permitted (D4/D5/D12's thresholds) — being the one
  who then submits is a smaller conceptual leap than Planning's agent,
  which has no other involvement with `Quote`/`qms` at all except this
  one action.
- `transport-planner.md` §5/§11: `route-decision-agent`'s other three
  `owned_actions` (`route.recommend`, `route-deviation.propose`,
  `approval.request`) are all legitimately route/recommendation-domain
  — `quote.submit-for-approval` is the one outlier that reaches into
  `qms`, not `tms`.

**Recommendation** (not applied): reassign `quote.submit-for-approval`
from `route-decision-agent` to `commercial-normalization-agent` in
`agents/catalog.yaml`, matching D4/D12 (2 of 3 `decisions.md` entries)
rather than D5's outlier. D5 itself would then need a corresponding
correction (its principal column changed to
`CommercialNormalizationAgent`) to stop being the source of the
original split. This is a business/registry-level change — no Cedar
schema or policy change required, since the existing policies are
already principal-unscoped.

## Finding 2 (secondary): `approval.request` has no `decisions.md` entry to check against at all

Unlike `quote.submit-for-approval`, `approval.request`
(`route-decision-agent`'s `owned_actions`) has **no corresponding row**
in `business/decisions.md`'s decision table — there's nothing to
cross-check its current assignment against, favorable or not. If
Finding 1's reassignment happens, this action's ownership should be
decided explicitly at the same time (does creating the `ApprovalTask`
belong with the submission, i.e. also move to
`commercial-normalization-agent`, or stay with Planning as a distinct
"flag this for review" capability separate from "submit the quote"?)
rather than carried over by default.

## Finding 3 (from the Pricing Manager profile): Cedar under-covers the real decision vocabulary

Separate from the ownership question — `mock_qms`'s real decision
endpoint supports `approved`/`rejected`/`revise`
(`mock_qms/store.py:378`), but Cedar's D6 only models `approve`.
`reject`/`revise` are gated at the application layer only (role-checked
in `mock_qms/templates/quote_detail.html:160`), with the `revise` path
carrying an explicit code comment marking it as an unfilled `D19`
candidate. Not the ownership question this review was scoped to answer,
but a real gap worth its own future work item: Cedar modeling `reject`/
`revise` as first-class actions, each with a clear principal, the same
way D6 models `approve`.

## What this review does NOT recommend

- Does not touch `identity/actors.yaml`, `identity/groups.yaml`,
  `authorization/*`, or `agents/catalog.yaml` — all three findings are
  documentation-and-registry-level, discovered by cross-referencing
  existing files, not requiring new Cedar entities or policies to
  resolve.
- Does not treat Transport Planner's `manager: diane.delgado` (flat
  reporting, no Operations Planner actor) as related to this review —
  that's a separate, already-flagged (`transport-planner.md` §9)
  organizational-completeness gap, not an authorization-boundary one.

## Next

Per the original ordering, Carrier Procurement Specialist is next.
Findings 1/2 above are ready to act on whenever a change to
`agents/catalog.yaml`/`business/decisions.md` is separately authorized
— they don't block continuing the profile series.
