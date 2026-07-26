// Cedar policies — repricing subprocess.
//
// MIRRORS cpm-eaop data/policies/policies.cedar conventions:
//   - every policy carries @id / @version / @owner / @description
//   - permit policies that emit obligations add @obligations("id1,id2")
//     (resolved via authorization/obligations.yaml, Python-side; Cedar never sees them)
//   - conditions read RESOLVED attributes + context, never raw group strings
//   - forbid beats permit (deny-precedence)
//   - uids are Agentic::Type::"id"
//   - NO `is` type-scope in the head (cedar-agent rejects it: "unexpected token
//     `is`" — same issue hit in cpm-eaop). Principal/resource types are enforced
//     by the schema's per-action `appliesTo` + by which entities the caller ever
//     sends for a given action; policy heads use bare principal/resource or
//     `principal in Group`, with all discrimination in `when`.
//
// Percents are integer tenths-of-a-percent (6% == 60). Money is EUR cents.
// The FX freshness window is 900s. Realizes business/decisions.md D1..D9, D10, D11.

// ---- ADR-001: an active agent may open an MCP session with a workload in its
// own trust domain (transport-level check, independent of any tool call) ----
@id("agent-may-connect-same-trust-domain")
@version("1")
@owner("platform")
@description("An active agent may open an MCP session with a workload sharing its trust domain.")
permit(
  principal,
  action == Agentic::Action::"mcp.connect",
  resource
) when {
  principal.active == true &&
  resource.active == true &&
  principal has trust_domain &&
  resource has trust_domain &&
  principal.trust_domain == resource.trust_domain
};

// ---- M3.5: an active agent may delegate to a callee in its can_call list ----
@id("agent-may-delegate-per-catalog")
@version("1")
@owner("platform")
@description("An active agent may hand off to another agent named in its can_call list (agents/catalog.yaml).")
permit(
  principal,
  action == Agentic::Action::"agent.delegate",
  resource
) when {
  principal.active == true &&
  resource.active == true &&
  resource has canonical_id &&
  principal has can_call &&
  principal.can_call.contains(resource.canonical_id)
};

// ---- M4a second checkpoint: delegated route.recommend must stay within
// the executing agent's delegatable_actions -- a FORBID, not a permit, so
// non-delegated calls (no context.delegated_by) are completely unaffected
// by this rule; only present-but-out-of-scope delegation is blocked.
@id("forbid-delegation-outside-scope")
@version("1")
@owner("platform")
@description("A delegated route.recommend call must be within the executing agent's delegatable_actions.")
// Cedar's strict validator requires `has` to directly guard the attribute
// access (no flow-sensitive narrowing across ||) -- `principal has
// delegatable_actions` is a REQUIRED conjunct, not a fallback: an agent
// entity with no delegatable_actions attribute at all would NOT be caught
// by this forbid. Not a live gap -- tools/identity/gen_cedar_entities.py
// always populates it (empty list, never absent) for every real agent --
// but a real one if an entity were ever manually seeded without it.
forbid(
  principal,
  action == Agentic::Action::"route.recommend",
  resource
) when {
  context has delegated_by &&
  principal has delegatable_actions &&
  !(principal.delegatable_actions.contains("route.recommend"))
};

// ---- D10: an active agent, within the internal trust domain, may check
// route capacity (read-only, informational). Trust-domain condition added
// M6a (Integration Checkpoint 1's deny leg) -- route capacity is internal
// operational data, not something an external-trust-domain caller should
// read regardless of what it owns. Same has-guard shape as
// agent-may-connect-same-trust-domain above (required conjunct, not a
// flow-sensitive fallback).
@id("agent-may-check-capacity")
@version("2")
@owner("routing")
@description("An active internal-trust-domain agent principal may check capacity on any route option.")
permit(
  principal,
  action == Agentic::Action::"capacity.check",
  resource
) when {
  principal.active == true &&
  principal has trust_domain &&
  principal.trust_domain == "internal"
};

// ---- M6: an active internal-trust-domain agent may read a carrier rate
// (read-only, informational). Same has-guard/trust_domain shape as
// agent-may-check-capacity above (D10) -- carrier rate data is internal
// commercial data, not something an external-trust-domain caller should
// read regardless of what it owns.
@id("agent-may-read-carrier-rate")
@version("1")
@owner("routing")
@description("An active internal-trust-domain agent principal may read a carrier rate on any route option.")
permit(
  principal,
  action == Agentic::Action::"carrier-rate.read",
  resource
) when {
  principal.active == true &&
  principal has trust_domain &&
  principal.trust_domain == "internal"
};

// ---- M6 (qms-mcp): pricing may only be calculated against a DRAFT quote
// version -- mirrors mock-qms's own real precondition (store.py's
// _draft_version: price_version raises InvalidStateError for anything
// else). NOT a blanket "active internal agent" permit like D10/D11 --
// resource.status is a LIVE fact fetched from mock-qms per request and
// supplied via additional_entities (rfq_common.pdp.entities.entity()),
// never pre-loaded into the persisted entity store. A priced/approval_
// required/approved/rejected version has nothing left to (re)calculate;
// recalculation on an existing priced version is create_next_quote_
// version's job (a different, unmapped-to-MCP operation today), not
// this action's.
@id("agent-may-calculate-quote-price-when-draft")
@version("1")
@owner("commercial")
@description("An active internal-trust-domain agent may calculate a quote's price only while its version is still draft.")
permit(
  principal,
  action == Agentic::Action::"quote-price.calculate",
  resource
) when {
  principal.active == true &&
  principal has trust_domain &&
  principal.trust_domain == "internal" &&
  resource has status &&
  resource.status == "draft"
};

// ---- M6 (qms-mcp): variance can only be evaluated once a version has
// actually been PRICED -- there is nothing to compare against on a
// draft (mock-qms's own price_version computes R2/FX-variance only
// against a prior PRICED snapshot, per its own docstring: "evaluates R2
// (FX variance) when a prior priced version's snapshot exists"). Same
// additional_entities mechanism as agent-may-calculate-quote-price-when-
// draft above -- resource.status is a live fact, not a stored one.
@id("agent-may-evaluate-quote-variance-when-priced")
@version("1")
@owner("commercial")
@description("An active internal-trust-domain agent may evaluate a quote's FX/price variance only once its version has been priced (or later).")
permit(
  principal,
  action == Agentic::Action::"quote-variance.evaluate",
  resource
) when {
  principal.active == true &&
  principal has trust_domain &&
  principal.trust_domain == "internal" &&
  resource has status &&
  resource.status != "draft"
};

// ---- M6 (approval-mcp): a route deviation may only be RECORDED against a
// quote version that's still draft -- mirrors mock-qms's own real
// precondition for attaching a RouteRecommendation (store.py's
// compose_route_recommendation: _draft_version-gated). Same additional_
// entities mechanism as qms-mcp's quote-price.calculate/quote-variance.
// evaluate above -- the underlying QuoteVersion's live status is fetched
// per request, never pre-loaded into the persisted store. NOT a blanket
// D10/D11-style check: once a version has moved past draft (priced,
// submitted, decided), there's nothing left to record a deviation
// against -- recording belongs to the NEXT version (quote.supersede),
// not a mutation of this one.
@id("agent-may-record-route-deviation-when-draft")
@version("1")
@owner("routing")
@description("An active internal-trust-domain agent may record a route deviation only while the referenced quote version is still draft.")
permit(
  principal,
  action == Agentic::Action::"route-deviation.propose",
  resource
) when {
  principal.active == true &&
  principal has trust_domain &&
  principal.trust_domain == "internal" &&
  resource has quote_status &&
  resource.quote_status == "draft"
};

// ---- D11: an active agent may evaluate lane options (read-only, informational) --
@id("agent-may-evaluate-lane")
@version("1")
@owner("routing")
@description("An active agent principal may evaluate lane options for an RFQ.")
permit(
  principal,
  action == Agentic::Action::"lane.evaluate",
  resource
) when { principal.active == true };

// ---- D1: commercial agent may read a FRESH exchange rate --------------------
@id("commercial-may-read-fresh-fx")
@version("1")
@owner("commercial")
@description("Commercial normalization agent may read an FX rate only within the freshness window.")
permit(
  principal,
  action == Agentic::Action::"fx-rate.read",
  resource
) when { context.fx_age_seconds <= 900 };

// ---- D2: commercial agent may normalize with a fresh FX snapshot ------------
@id("commercial-may-normalize")
@version("1")
@owner("commercial")
@description("Normalize a route cost only when the referenced FX snapshot is fresh.")
permit(
  principal,
  action == Agentic::Action::"route-cost.normalize",
  resource
) when { context.fx_age_seconds <= 900 };

// ---- D3a: recommend a CONTRACTED lane (no obligation) -----------------------
@id("recommend-contracted-lane")
@version("1")
@owner("routing")
@description("Recommending the contracted lane needs no downstream review.")
permit(
  principal,
  action == Agentic::Action::"route.recommend",
  resource
) when { context.non_contracted_lane == false && principal.active == true };

// ---- D3b: recommend a NON-CONTRACTED lane (permit + obligation) -------------
@id("recommend-noncontracted-lane")
@version("1")
@owner("routing")
@description("Recommending a lane deviation is allowed but requires customer-service review.")
@obligations("oblig-lane-deviation")
permit(
  principal,
  action == Agentic::Action::"route.recommend",
  resource
) when { context.non_contracted_lane == true && principal.active == true };

// ---- D8: recommend a route whose cost exceeds baseline by > 8% --------------
// permit + obligation (obligations from all determining permits merge; a
// non-contracted, high-cost recommendation carries BOTH lane-deviation + cost-review).
@id("recommend-high-cost-variance")
@version("1")
@owner("routing")
@description("A route costing >8% over baseline may be recommended but owes a cost-variance review.")
@obligations("oblig-cost-variance-review")
permit(
  principal,
  action == Agentic::Action::"route.recommend",
  resource
) when { context.cost_variance_pct_x10 > 80 && principal.active == true };

// ---- D9: recommend a route adding > 3 transit days --------------------------
@id("recommend-slower-transit")
@version("1")
@owner("operations")
@description("A route adding more than 3 transit days may be recommended but owes an operations review.")
@obligations("oblig-transit-review")
permit(
  principal,
  action == Agentic::Action::"route.recommend",
  resource
) when { context.transit_variance_days > 3 && principal.active == true };

// ---- D4a: FX moved > 2% -> recalculation permitted, notify pricing manager --
@id("fx-permit-recalc")
@version("1")
@owner("commercial")
@description("A large FX move permits recalculation but obliges notifying the pricing manager.")
@obligations("oblig-notify-pricing-manager")
permit(
  principal,
  action == Agentic::Action::"quote-variance.evaluate",
  resource
) when { context.fx_variance_pct_x10 > 20 };

// ---- D4b: FX moved > 2% -> FORBID automatic quote replacement ---------------
// deny-precedence: the agent may recalc (D4a) but may NOT auto-submit; the human
// approval path (D6) is the only way forward.
@id("forbid-auto-replace-on-fx")
@version("1")
@owner("commercial")
@description("When FX moved more than 2%, an agent must not auto-submit a replacement quote.")
forbid(
  principal,
  action == Agentic::Action::"quote.submit-for-approval",
  resource
) when { context.fx_variance_pct_x10 > 20 };

// ---- D12: submit-for-approval is fine when FX is quiet and margin is healthy --
// Baseline permit -- without this, the "nothing is wrong" case has no permit at
// all (D4b is a forbid; D5 only permits the below-floor case) and would
// incorrectly default-deny. Found via the policy-evaluation spike (scenario 02).
@id("submit-quote-when-within-thresholds")
@version("1")
@owner("commercial")
@description("A quote may be submitted when FX is within threshold and margin is at/above floor.")
permit(
  principal,
  action == Agentic::Action::"quote.submit-for-approval",
  resource
) when { context.fx_variance_pct_x10 <= 20 && context.margin_pct_x10 >= 60 };

// ---- D5: below-floor margin -> proposal permitted, commercial approval owed --
@id("propose-below-floor")
@version("1")
@owner("commercial")
@description("A below-floor-margin quote may be proposed but owes a commercial approval.")
@obligations("oblig-commercial-approval")
permit(
  principal,
  action == Agentic::Action::"quote.submit-for-approval",
  resource
) when { context.margin_pct_x10 < 60 };

// ---- D6: commercial manager may approve a deviation within their limit ------
@id("manager-may-approve-within-limit")
@version("1")
@owner("commercial")
@description("A commercial manager may approve a route deviation within a 10,000 EUR limit.")
permit(
  principal in Agentic::Group::"rfq-commercial-emea",
  action == Agentic::Action::"route-deviation.approve",
  resource
) when {
  context.quote_value_eur_cents <= 1000000
};

// ---- D19: commercial manager may approve a submitted quote within limit -----
// Finding 3 (capability-profile review): distinct from D6 (route-deviation.
// approve, resource RouteRecommendation) -- this is the actual QMS decision
// (resource Quote), matching mock_qms's real approved|rejected|revise
// vocabulary. Same group + value-limit gate as D6.
@id("commercial-manager-may-approve-quote")
@version("1")
@owner("commercial")
@description("A commercial manager may approve a submitted quote within a 10,000 EUR limit.")
permit(
  principal in Agentic::Group::"rfq-commercial-emea",
  action == Agentic::Action::"quote.approve",
  resource
) when {
  context.quote_value_eur_cents <= 1000000
};

// ---- D20: commercial manager may reject a submitted quote -------------------
// No value-limit gate: declining a quote doesn't commit the company to
// anything, unlike approving one.
@id("commercial-manager-may-reject-quote")
@version("1")
@owner("commercial")
@description("A commercial manager may reject a submitted quote.")
permit(
  principal in Agentic::Group::"rfq-commercial-emea",
  action == Agentic::Action::"quote.reject",
  resource
);

// ---- D21: commercial manager may request revision on a submitted quote -----
@id("commercial-manager-may-request-quote-revision")
@version("1")
@owner("commercial")
@description("A commercial manager may send a submitted quote back for revision.")
permit(
  principal in Agentic::Group::"rfq-commercial-emea",
  action == Agentic::Action::"quote.request-revision",
  resource
);

// ---- D7: cross-cutting -> inactive principals do nothing --------------------
@id("forbid-inactive")
@version("1")
@owner("platform")
@description("Inactive principals must not perform any controlled action.")
forbid( principal, action, resource ) when { principal.active == false };
