# Authorization decisions log — repricing subprocess

Step 1 of the domain-to-cedar method (`docs/policies/domain-to-cedar-runbook.md` in
cpm-eaop): start from concrete authorization questions, not ontology classes. Same
table shape as cpm-eaop `docs/policies/decisions.md`. Status: `proposed → modeled →
enforced`.

> A decision reads: **"May principal P perform action A on resource R under context C?"**

## Decisions

| #   | Question                                                                                           | action                      | principal                    | resource            | context                                                          | status   | policy id(s)                                                 |
| --- | -------------------------------------------------------------------------------------------------- | --------------------------- | ---------------------------- | ------------------- | ---------------------------------------------------------------- | -------- | ------------------------------------------------------------ |
| D1  | May the commercial agent read the FX rate if it is fresh enough?                                   | `fx-rate.read`              | CommercialNormalizationAgent | ExchangeRate        | `fx_age_seconds`, `quote_currency`                               | modeled  | `commercial-may-read-fresh-fx`                               |
| D2  | May the commercial agent normalize a route cost with a referenced FX snapshot?                     | `route-cost.normalize`      | CommercialNormalizationAgent | RouteOption         | `fx_age_seconds`, `target_currency`                              | modeled  | `commercial-may-normalize`                                   |
| D3  | May the decision agent recommend a non-contracted lane? (permit + obligation)                      | `route.recommend`           | RouteDecisionAgent           | RFQ                 | `non_contracted_lane`, `cost_variance_pct_x10`, `margin_pct_x10` | modeled  | `recommend-lane`, `oblig-lane-deviation`                     |
| D4  | Must automatic quote replacement be blocked when FX moved > 2%? (forbid)                           | `quote.submit-for-approval` | CommercialNormalizationAgent | Quote               | `fx_variance_pct_x10`                                            | modeled  | `forbid-auto-replace-on-fx`                                  |
| D5  | May a below-floor margin quote be proposed at all? (permit + obligation)                           | `quote.submit-for-approval` | CommercialNormalizationAgent | Quote               | `margin_pct_x10`                                                 | modeled  | `propose-below-floor`, `oblig-commercial-approval`           |
| D6  | May a commercial manager approve a route deviation within their limit?                             | `route-deviation.approve`   | CommercialManager (Human)    | RouteRecommendation | `quote_value_eur_cents`, `margin_pct_x10`                        | modeled  | `manager-may-approve-within-limit`                           |
| D8  | May the decision agent recommend a route whose cost exceeds baseline by >8%? (permit + obligation) | `route.recommend`           | RouteDecisionAgent           | RFQ                 | `cost_variance_pct_x10`                                          | modeled  | `recommend-high-cost-variance`, `oblig-cost-variance-review` |
| D9  | May the decision agent recommend a route adding >3 transit days? (permit + obligation)             | `route.recommend`           | RouteDecisionAgent           | RFQ                 | `transit_variance_days`                                          | modeled  | `recommend-slower-transit`, `oblig-transit-review`           |
| D10 | May an active agent check route capacity? (read-only, informational — no obligation)               | `capacity.check`            | LaneEvaluationAgent          | RouteOption         | —                                                                | enforced | `agent-may-check-capacity`                                   |
| D11 | May an active agent evaluate lane options for an RFQ? (read-only, informational — no obligation)   | `lane.evaluate`             | LaneEvaluationAgent          | RFQ                 | —                                                                | enforced | `agent-may-evaluate-lane`                                    |
| D12 | May a quote be submitted when FX is quiet and margin is at/above floor? (baseline permit)          | `quote.submit-for-approval` | CommercialNormalizationAgent | Quote               | `fx_variance_pct_x10`, `margin_pct_x10`                          | modeled  | `submit-quote-when-within-thresholds`                        |
| D7  | Inactive principals must not perform any controlled action. (cross-cutting forbid)                 | *                           | *                            | *                   | —                                                                | enforced | `forbid-inactive`                                            |
| D19 | May a commercial manager approve a submitted quote within their limit?                             | `quote.approve`             | CommercialManager (Human)    | Quote               | `quote_value_eur_cents`                                          | modeled  | `commercial-manager-may-approve-quote`                       |
| D20 | May a commercial manager reject a submitted quote?                                                 | `quote.reject`              | CommercialManager (Human)    | Quote               | —                                                                 | modeled  | `commercial-manager-may-reject-quote`                        |
| D21 | May a commercial manager send a submitted quote back for revision?                                 | `quote.request-revision`    | CommercialManager (Human)    | Quote               | —                                                                 | modeled  | `commercial-manager-may-request-quote-revision`              |

*D10/D11 found + fixed during the policy-evaluation spike: scenarios 02/03 exercised
these actions but no policy existed yet — both would have wrongly default-denied.
D12 found the same way: the "nothing is wrong" case for `quote.submit-for-approval`
(FX quiet, margin at/above floor) had no permit at all — only a forbid (D4b) and a
permit for the below-floor case (D5) — so scenario 02's happy path incorrectly
default-denied until D12 was added.*

*D5's principal was corrected from RouteDecisionAgent to
CommercialNormalizationAgent (capability-profile review, Finding 1) — it had
disagreed with D4/D12 on the same action's principal since this decision log's
inception; `agents/catalog.yaml` had independently resolved the disagreement
the other way, undetected until the capability-profile exercise cross-checked
the two files. D19-D21 fill the gap the same review's Finding 3 found:
`mock_qms`'s real decision endpoint (`mock_qms/store.py:378`) has always
supported `approved`/`rejected`/`revise`; Cedar previously only modeled the
approve case, and only indirectly (via D6's `route-deviation.approve`, whose
resource type is RouteRecommendation, not Quote). `mock_qms/templates/
quote_detail.html:129`'s "D19-candidate" comment, written before this action
existed, is honored by D19's number. Finding 2 (should `approval.request` be
a separate agent-commanded action) was resolved by removing agent ownership
of it entirely, not reassigning it — see `agents/catalog.yaml`'s
`route-decision-agent` comment.*

## Proposed — the quote-authoring pipeline (not yet modeled)

D1–D12 govern evaluation, normalization, recommendation, and submission --
but not access to the pipeline's *inputs*, nor creation of the priced
artifact itself. `Quote`'s identity is already `[quote_id, version]` with a
`prior_version` pointer, i.e. it already represents a single, immutable quote
*version* -- D16-D18 use it as-is (see the NOTE on `Quote` in
`domain-model.yaml`); no new `QuoteVersion` noun is introduced solely to
satisfy this table.

| #   | Question                                                                      | action                 | principal                    | resource    | context                                                                           | status   |
| --- | ----------------------------------------------------------------------------- | ---------------------- | ---------------------------- | ----------- | --------------------------------------------------------------------------------- | -------- |
| D13 | May the lane agent read this RFQ?                                             | `rfq.read`             | LaneEvaluationAgent          | RFQ         | `customer_id`, `region`, `assignment`, `rfq_status`                               | proposed |
| D14 | May the lane agent read this carrier or customer-specific rate?               | `rate.read`            | LaneEvaluationAgent          | CarrierRate | `customer_id` (scope), `contract_scope`, `rate_type`                              | proposed |
| D15 | May the commercial agent read the underlying buy rate?                        | `buy-rate.read`        | CommercialNormalizationAgent | CarrierRate | `purpose`, `customer_id`, `confidentiality_class`                                 | proposed |
| D16 | May the commercial agent create a new quote version from this recommendation? | `quote.create-version` | CommercialNormalizationAgent | Quote       | `rfq_id`, `recommendation_id`, `fx_rate_ref`, `pricing_terms_ref`                 | proposed |
| D17 | May the commercial agent supersede this quote version?                        | `quote.supersede`      | CommercialNormalizationAgent | Quote       | `quote_id`, `current_version`, `current_status`, `prior_version`, `trigger_event` | proposed |
| D18 | May this principal expose underlying buy-cost details?                        | `buy-rate.disclose`    | Agent or Human               | Quote       | `audience`, `channel`, `disclosure_purpose`                                       | proposed |

The read/disclose split (D15 vs D18) matters: an agent may need the buy rate
to compute margin while still being forbidden from placing it in
customer-facing output. `quote.supersede` (D17) is the version-creation gate
-- the data model should reflect *this* decision, not define supersession
merely because `prior_version` exists as a field.

## Human-in-the-loop = a status change in the quote system of record

The human decision is **not** owned by a separate workflow store — it is a **status
transition on the Quote in the quote SoR (QMS)**: `approval_required →
approved | rejected | revise`. The approval task/MCP is only the *mechanism* that
surfaces the decision to a human; the durable, authoritative truth is the quote
status. The process resumes when it observes that status change (see
`scenarios/03-approval-loop`). This keeps agents non-authoritative — they read/write
via the SoR, they do not own the decision.

## SoR boundary: RFQ vs Quote

`RFQ.lifecycle` (domain-model.yaml, CRM-owned) and `Quote.status` (QMS-owned)
both include `accepted`/`rejected`/`expired` — a real duplication risk (ADR-002
SoR boundaries exists precisely to prevent two systems each independently
writing the same fact) unless the relationship between them is explicit:

- **RFQ is a CASE** (a multi-week engagement -- solicit rates, iterate,
  negotiate), not a document. Its lifecycle tracks the case's own progress
  (`sourcing_rates`, `pricing`, `issued`, ...).
- **`Quote.accepted` is the primary fact** — QMS is the sole writer. A specific
  priced quote *version* was accepted.
- **`RFQ.accepted` is derived, never independently written** — CRM sets it
  (or, until CRM exists, it's understood as a projection) only in response to
  observing `Quote.status == accepted`, the same "SoR reads/writes via its own
  boundary" discipline the rest of this file already applies to agents.

CRM doesn't exist yet (`systems/crm/README.md` is a bare stub) — this is the
intended relationship for when it's built, not a currently-enforced rule.

## Threshold coverage (the seven from the business process)

| Threshold                             | Decision                                    |
| ------------------------------------- | ------------------------------------------- |
| FX movement > 2% since prior quote    | D4a permit+notify · D4b forbid auto-replace |
| Route cost > 8% of baseline           | D8 permit + cost-variance review            |
| Margin < 6% floor                     | D5 permit + commercial approval             |
| Recommended lane ≠ contracted lane    | D3b permit + customer-service review        |
| Transit time > +3 days                | D9 permit + transit review                  |
| FX rate older than freshness window   | D1/D2 deny (fail closed)                    |
| Quote value > agent's delegated limit | D6 (human approval within limit)            |

## Proposed (not yet modeled)

| #   | Question                                                                  | action           | principal           | resource       | status   |
| --- | ------------------------------------------------------------------------- | ---------------- | ------------------- | -------------- | -------- |
| P1  | May the lane agent delegate to the commercial agent (A2A) within depth 1? | `agent.delegate` | LaneEvaluationAgent | Agent          | proposed |
| P2  | May an operations admin disable the pricing agent (kill switch)?          | `agent.disable`  | OperationsAdmin     | AgentPrincipal | proposed |

## Template (copy for a new decision)

```text
May <principal> perform <action> on <resource> when <context conditions>?
principal: … | action: … | resource: … | context: … | status: proposed
```

Downstream order (per the runbook): decision question → `actions.yaml` →
`authz-projection.yaml` → schema (generated) → request fixtures → `policies.cedar`
→ provenance map → tests.
