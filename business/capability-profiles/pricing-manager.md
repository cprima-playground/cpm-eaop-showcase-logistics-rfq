# Pricing Manager — capability profile

Third application of the golden template (schema: `business/
capability-profiles/README.md`). Grounds `job_title_id: pricing-
manager` (`business/job-titles.yaml`), actor `mona.commercial` + 2
regional peers (`identity/actors.yaml`), department `commercial`
(`business/departments.yaml`).

This profile was written specifically to investigate an ownership
question the Transport Planner profile surfaced: does it make
organizational sense that `route-decision-agent` (Planning) owns
`quote.submit-for-approval` and `approval.request` — actions that write
to `qms`/`workflow`, not `tms`? §13 documents what the investigation
found. **Since resolved** (`agents/catalog.yaml`,
`business/decisions.md`, `authorization/{actions.yaml,policies.cedar}`
all updated — see `offer-to-execution-domain-review.md`'s "Findings 1-3,
resolved").

## 1. Mission

Own the commercial-exception decision: review a submitted quote against
policy and either approve it, reject it, or send it back for revision.

## 2. Primary systems

- **`qms`** — owns `QuoteVersion`/`QuoteStatus`, **and is explicitly
  the system of record for the human decision itself**
  (`systems/systems-of-record.yaml:46-48`: "the approval outcome is a
  Quote.status transition here... not a record owned by the workflow
  system"). This is the home system for this role's actual authority.
- **`workflow`** — owns `ApprovalTask` (the task *mechanism* only, per
  the same file's note). Surfaces the decision, doesn't own it.

## 3. Consumes

| Input | Produced by |
|---|---|
| Submitted `QuoteVersion` | Commercial Pricing Specialist's agent (`commercial-normalization-agent`), matching D4/D12 — see §13 for the fix |
| `ApprovalTask` | `workflow`, now a system-internal consequence of submission rather than an agent-commanded action (Finding 2, §13) |
| `RouteRecommendation` context (`non_contracted_lane`, cost/transit variance) | Transport Planner, when D3b/D8/D9 obligations attach |
| `fx_variance_pct_x10` / `margin_pct_x10` context | Commercial Pricing Specialist's normalization step |

## 4. Produces

| Output | Consumed by |
|---|---|
| Decision record (`approved`/`rejected`/`revise` — real API vocabulary, `mock_qms/store.py:378`) | `qms` (authoritative `QuoteVersion.status`), visible to the Commercial Pricing Specialist and, transitively, the customer |
| Pricing policy / approval-limit changes | Commercial Pricing Specialist, as the `CustomerPricingTerms`/`MarginFloor` they operate under |

## 5. Decisions — the real vocabulary, now fully modeled (Finding 3, resolved)

`mock_qms`'s real, implemented decision endpoint (`POST .../decisions`,
tested in `src/mock-qms/tests/business/test_scenario_approval_decision.
py`) supports **three** outcomes: `approved` | `rejected` | `revise`
(`mock_qms/store.py:378`, `mock_qms/api.py:639`). Cedar previously
modeled only the first (D6, and even that indirectly — via
`route-deviation.approve`, a different resource type). Now modeled
directly, one Cedar action per outcome, all on the actual `Quote`
resource:

- **D19** (`commercial-manager-may-approve-quote`, action
  `quote.approve`) — same group + 10,000 EUR `quote_value_eur_cents`
  gate as D6 always had for the deviation case.
- **D20** (`commercial-manager-may-reject-quote`, action `quote.reject`)
  — no value-limit gate: declining doesn't commit the company to
  anything.
- **D21** (`commercial-manager-may-request-quote-revision`, action
  `quote.request-revision`) — same, no value-limit gate. The template's
  code comment that named this "D19-candidate"
  (`mock_qms/templates/quote_detail.html:129`, written before this
  action existed) is now updated to cite D21 by its actual number.

All three are `Principal`-only in `business/actions.yaml`'s schema
(`appliesTo.principalTypes`) — an `AgentPrincipal` structurally cannot
hold them, verified by `test_agent_cannot_approve_quote` in
`test_pdp_integration.py`, not just asserted by a `forbid` policy.

Not yet done (out of this fix's scope, flagged not silently skipped):
`mock_qms`'s live `/decisions` endpoint doesn't call the PDP yet — these
policies exist and are tested against the isolated cedar-agent, but
aren't wired into the running application. That's the PEP-wiring work
scoped for the implementation plan's M4a, not this capability-profile
fix.

## 6. Business rules

- Approval limit: `quote_value_eur_cents <= 1000000` (10,000 EUR) — D19
  (and D6, for the deviation case).
- `reject`/`revise` (D20/D21) have no value threshold, by design (§5).

## 7. KPIs

Industry-typical, **not computed by anything in this showcase today**:

- Approval cycle time (submission → decision)
- Exception rate (% of quotes requiring escalation at all)
- Override/reject rate by reason category
- Portfolio-level realized margin vs. floor

Sources: [ISS Global Forwarding Pricing Manager](https://iss-globalforwarding.com/jobs/pricing-manager-malaysia/), [Indeed Freight Pricing Manager](https://www.indeed.com/q-freight-pricing-manager-jobs.html)

## 8. Authority

- May approve within the 10,000 EUR limit — Cedar-enforced (D6, D19).
- May reject or request revision — implemented, role-gated in
  `mock_qms`, and now Cedar-modeled too (D20/D21), though not yet
  wired into the live endpoint (§5).
- Nothing above the limit is modeled for this role at all — no escalate-
  to-Director action exists in Cedar or `mock_qms` today. The Regional
  Commercial Director's profile-worthy authority (per the Transport
  Planner profile's §1/personas.md) is undemonstrated by any decision
  in this repo.

## 9. Reports to / Manages

Reports to Regional Commercial Director (`diane.delgado` et al. — this
chain was never in question, only the specialist layer was).

**Manages:** Commercial Pricing Specialist (`sam.pricing` et al.) — this
is the reporting line fixed in the Commercial Pricing Specialist
profile's review, now consistent from both directions:
`job-titles.yaml`'s `commercial-pricing-specialist.reports_to_job_
title_id: pricing-manager`, enforced by `tools/identity/validator.py`.

## 10. Collaborates with

- **Commercial Pricing Specialist** (Pricing) — the specialist submits
  (in the *intended* org design — §13), this role decides.
- **Transport Planner** (Planning) — obligation reviews (D3b/D8/D9)
  route through here when a recommendation is non-contracted or high-
  variance.
- **Carrier Procurement Specialist** (Carrier Procurement) — indirect,
  via the rate data both Pricing and Planning consume.

## 11. Candidate agent responsibilities

None. No `owned_actions` in `agents/catalog.yaml` are assigned to a
Pricing-Manager-tier agent, and none should be, per the pattern already
established twice: `route-deviation.approve` is excluded from every
agent's `owned_actions` (`agents/catalog.yaml:25,43,60`). This role's
entire mission (§1) is the one decision every agent in this showcase is
explicitly barred from making.

## 12. Must remain human

**Human-accountable** (the whole role, not a subset):
- Approve/reject/revise is the accountability boundary the entire
  agent architecture is built around — every agent's `prohibited_
  actions` protects exactly this line. There is no "human-only today"
  or "potentially agent-assisted" category here; this is the one
  responsibility that is structurally, not temporarily, human.

## 13. Finding, now resolved: `quote.submit-for-approval` ownership

**Fixed** (post-review; see `offer-to-execution-domain-review.md`'s
"Findings 1-3, resolved" section for the full change list). Was a
three-way documented disagreement, not just a documentation nit:

1. **`business/decisions.md`** (the decision log itself, `#`
   column D4/D5/D12) is **internally split** on `quote.submit-for-
   approval`'s principal:
   - **D4** (`forbid-auto-replace-on-fx`) and **D12** (`submit-quote-
     when-within-thresholds`) both name `CommercialNormalizationAgent`
     as principal — the Pricing-side agent.
   - **D5** (`propose-below-floor`) names `RouteDecisionAgent` — the
     Planning-side agent — for the *same action*.
2. **`agents/catalog.yaml`** resolved that split unilaterally, and in
   one direction only: `quote.submit-for-approval` is `route-decision-
   agent`'s `owned_actions` (`catalog.yaml:58`), and
   `commercial-normalization-agent` is **explicitly prohibited** from
   it (`prohibited_actions`, `catalog.yaml:43`) — contradicting D4/D12's
   own documented principal.
3. **Cedar enforcement is silent on the question** — `forbid-auto-
   replace-on-fx` and `submit-quote-when-within-thresholds` both use
   bare `principal` in `authorization/policies.cedar`, no type/identity
   restriction — so this inconsistency produces no failing test and no
   Cedar-level error today. It's invisible unless someone reads
   `decisions.md` and `catalog.yaml` side by side, which this profile
   exercise is the first time anyone has.

Combined with §2's SoR fact (`qms` is the decision's system of record)
and §8/D6's fact (the *decide* side is unambiguously Pricing-owned),
the weight of evidence favored `decisions.md`'s D4/D12 (Pricing
submits) — that's what got applied: `agents/catalog.yaml`'s
`commercial-normalization-agent` now owns `quote.submit-for-approval`,
`route-decision-agent` no longer does, and D5's principal was corrected
to match D4/D12. §5 above is unchanged (still correct — this was always
about *who submits*, not the thresholds themselves).
