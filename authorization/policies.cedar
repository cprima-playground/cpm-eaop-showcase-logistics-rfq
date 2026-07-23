// Cedar policies — repricing subprocess.
//
// MIRRORS cpm-eaop data/policies/policies.cedar conventions:
//   - every policy carries @id / @version / @owner / @description
//   - permit policies that emit obligations add @obligations("id1,id2")
//     (resolved via authorization/obligations.yaml, Python-side; Cedar never sees them)
//   - conditions read RESOLVED attributes + context, never raw group strings
//   - forbid beats permit (deny-precedence)
//   - uids are Agentic::Type::"id"
//
// Percents are integer tenths-of-a-percent (6% == 60). Money is EUR cents.
// The FX freshness window is 900s. Realizes business/decisions.md D1..D7.

// ---- D1: commercial agent may read a FRESH exchange rate --------------------
@id("commercial-may-read-fresh-fx")
@version("1")
@owner("commercial")
@description("Commercial normalization agent may read an FX rate only within the freshness window.")
permit(
  principal is Agentic::AgentPrincipal,
  action == Agentic::Action::"fx-rate.read",
  resource is Agentic::ExchangeRate
) when { context.fx_age_seconds <= 900 };

// ---- D2: commercial agent may normalize with a fresh FX snapshot ------------
@id("commercial-may-normalize")
@version("1")
@owner("commercial")
@description("Normalize a route cost only when the referenced FX snapshot is fresh.")
permit(
  principal is Agentic::AgentPrincipal,
  action == Agentic::Action::"route-cost.normalize",
  resource is Agentic::RouteOption
) when { context.fx_age_seconds <= 900 };

// ---- D3a: recommend a CONTRACTED lane (no obligation) -----------------------
@id("recommend-contracted-lane")
@version("1")
@owner("routing")
@description("Recommending the contracted lane needs no downstream review.")
permit(
  principal is Agentic::AgentPrincipal,
  action == Agentic::Action::"route.recommend",
  resource is Agentic::RFQ
) when { context.non_contracted_lane == false && principal.active == true };

// ---- D3b: recommend a NON-CONTRACTED lane (permit + obligation) -------------
@id("recommend-noncontracted-lane")
@version("1")
@owner("routing")
@description("Recommending a lane deviation is allowed but requires customer-service review.")
@obligations("oblig-lane-deviation")
permit(
  principal is Agentic::AgentPrincipal,
  action == Agentic::Action::"route.recommend",
  resource is Agentic::RFQ
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
  principal is Agentic::AgentPrincipal,
  action == Agentic::Action::"route.recommend",
  resource is Agentic::RFQ
) when { context.cost_variance_pct_x10 > 80 && principal.active == true };

// ---- D9: recommend a route adding > 3 transit days --------------------------
@id("recommend-slower-transit")
@version("1")
@owner("operations")
@description("A route adding more than 3 transit days may be recommended but owes an operations review.")
@obligations("oblig-transit-review")
permit(
  principal is Agentic::AgentPrincipal,
  action == Agentic::Action::"route.recommend",
  resource is Agentic::RFQ
) when { context.transit_variance_days > 3 && principal.active == true };

// ---- D4a: FX moved > 2% -> recalculation permitted, notify pricing manager --
@id("fx-permit-recalc")
@version("1")
@owner("commercial")
@description("A large FX move permits recalculation but obliges notifying the pricing manager.")
@obligations("oblig-notify-pricing-manager")
permit(
  principal is Agentic::AgentPrincipal,
  action == Agentic::Action::"quote-variance.evaluate",
  resource is Agentic::Quote
) when { context.fx_variance_pct_x10 > 20 };

// ---- D4b: FX moved > 2% -> FORBID automatic quote replacement ---------------
// deny-precedence: the agent may recalc (D4a) but may NOT auto-submit; the human
// approval path (D6) is the only way forward.
@id("forbid-auto-replace-on-fx")
@version("1")
@owner("commercial")
@description("When FX moved more than 2%, an agent must not auto-submit a replacement quote.")
forbid(
  principal is Agentic::AgentPrincipal,
  action == Agentic::Action::"quote.submit-for-approval",
  resource is Agentic::Quote
) when { context.fx_variance_pct_x10 > 20 };

// ---- D5: below-floor margin -> proposal permitted, commercial approval owed --
@id("propose-below-floor")
@version("1")
@owner("commercial")
@description("A below-floor-margin quote may be proposed but owes a commercial approval.")
@obligations("oblig-commercial-approval")
permit(
  principal is Agentic::AgentPrincipal,
  action == Agentic::Action::"quote.submit-for-approval",
  resource is Agentic::Quote
) when { context.margin_pct_x10 < 60 };

// ---- D6: commercial manager may approve a deviation within their limit ------
@id("manager-may-approve-within-limit")
@version("1")
@owner("commercial")
@description("A commercial manager may approve a route deviation within a 10,000 EUR limit.")
permit(
  principal is Agentic::Principal,
  action == Agentic::Action::"route-deviation.approve",
  resource is Agentic::RouteRecommendation
) when {
  principal in Agentic::Group::"rfq-commercial-emea"
  && context.quote_value_eur_cents <= 1000000
};

// ---- D7: cross-cutting -> inactive principals do nothing --------------------
@id("forbid-inactive")
@version("1")
@owner("platform")
@description("Inactive principals must not perform any controlled action.")
forbid( principal, action, resource ) when { principal.active == false };
