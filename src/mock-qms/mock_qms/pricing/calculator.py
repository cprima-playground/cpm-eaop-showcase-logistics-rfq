"""The pure calculation core of price_version(), split out of store.py.
Takes already-resolved facts (no I/O: no self._rate, no self._fx, no
_replace_version) and returns a result object -- independently testable
without stubbing an HTTP client."""

from __future__ import annotations

from dataclasses import dataclass, field

from rfq_common.models import RuleResult

from .. import pricing_policy
from .money import Money
from .provenance import FxConversionFact, PricingProvenance

# R2's threshold (qms-pricing-rules.md): fx_variance_pct_x10 > 20 (2.0%) is
# over threshold. R3/R4/R5 need a contracted-lane baseline route that isn't
# QMS-owned data -- always "not_evaluated" with an honest reason, never a
# fabricated result.
_R2_THRESHOLD_PCT_X10 = 20
_NOT_EVALUATED_NO_BASELINE = (
    "no contracted-lane baseline route stored on Quote -- RFQ isn't QMS-owned "
    "data, see store.py's module docstring"
)


@dataclass(frozen=True, slots=True)
class RateResolution:
    """One rate_ref's resolved cost. Invariant the calculator depends on:
    `cost` is ALWAYS already normalized into the quote currency (EUR
    today) -- never a raw carrier-currency amount. `fx_conversion` is only
    set when a real conversion happened to reach that normalized cost;
    None means the rate was already in the quote currency."""

    route_id: str
    cost: Money
    fx_conversion: FxConversionFact | None = None


@dataclass(frozen=True, slots=True)
class PriorPricingSnapshot:
    """The one fact R2 needs from a prior priced version."""

    fx_rate_snapshot: float | None


@dataclass(frozen=True, slots=True)
class PricingCalculationResult:
    total_cost: Money
    sell_price: Money
    margin_pct_x10: int
    fx_rate_used: float | None
    rule_results: list[RuleResult] = field(default_factory=list)  # R1, R2, R3, R4, R5 in that order
    provenance: PricingProvenance | None = None


def calculate_pricing(
    *,
    rate_resolutions: list[RateResolution],
    prior: PriorPricingSnapshot | None,
    margin_floor_ref: str | None,
    priced_at: str,
) -> PricingCalculationResult:
    quote_currency = rate_resolutions[0].cost.currency
    quote_minor_unit = rate_resolutions[0].cost.minor_unit
    total_cost = Money.zero(quote_currency, quote_minor_unit)
    for res in rate_resolutions:
        total_cost = total_cost + res.cost

    fx_conversions = [r.fx_conversion for r in rate_resolutions if r.fx_conversion is not None]
    fx_rate_used = fx_conversions[-1].rate if fx_conversions else None

    if fx_rate_used is None:
        fx_over_threshold = False
        r2 = RuleResult(
            rule_id="R2", result="not_evaluated",
            reason="every rate_ref was already in EUR -- no FX conversion occurred to compare",
        )
    elif prior is None or prior.fx_rate_snapshot is None:
        fx_over_threshold = False
        r2 = RuleResult(
            rule_id="R2", result="not_evaluated",
            reason="no prior priced version's FX snapshot to compare against (qms-pricing-rules.md: never a live re-fetch)",
        )
    else:
        variance = round(abs(fx_rate_used - prior.fx_rate_snapshot) / prior.fx_rate_snapshot * 1000)
        fx_over_threshold = variance > _R2_THRESHOLD_PCT_X10
        r2 = RuleResult(
            rule_id="R2", actual_pct_x10=variance, threshold_pct_x10=_R2_THRESHOLD_PCT_X10,
            result="over_threshold" if fx_over_threshold else "within_threshold",
        )

    profile = pricing_policy.resolve_profile(margin_floor_ref)
    target_margin = pricing_policy.target_margin_pct_x10(profile, fx_over_threshold=fx_over_threshold)
    unrounded_sell = pricing_policy.calculate_sell_price(total_cost, target_margin)
    sell_price = pricing_policy.commercial_round_up(unrounded_sell)
    actual_margin = pricing_policy.calculate_margin_pct_x10(total_cost, sell_price)

    r1 = RuleResult(
        rule_id="R1", actual_pct_x10=actual_margin, threshold_pct_x10=profile.base_margin_pct_x10,
        result="within_threshold" if actual_margin >= profile.base_margin_pct_x10 else "below_floor",
        reason=(
            f"demo policy {pricing_policy.POLICY_REF}, profile {profile.profile_id!r}: "
            f"target {target_margin / 10}% (base {profile.base_margin_pct_x10 / 10}%"
            f"{' + 2.0% FX risk' if fx_over_threshold else ''}), "
            f"sell price €{sell_price.major:.2f} rounded up from €{unrounded_sell.major:.2f}"
        ),
    )

    rule_results = [r1, r2]
    for rule_id in ("R3", "R4", "R5"):
        rule_results.append(RuleResult(rule_id=rule_id, result="not_evaluated", reason=_NOT_EVALUATED_NO_BASELINE))

    provenance = PricingProvenance(
        rate_refs=[r.route_id for r in rate_resolutions],
        fx_conversions=fx_conversions,
        policy_ref=pricing_policy.POLICY_REF,
        priced_at=priced_at,
    )
    return PricingCalculationResult(
        total_cost=total_cost, sell_price=sell_price, margin_pct_x10=actual_margin,
        fx_rate_used=fx_rate_used, rule_results=rule_results, provenance=provenance,
    )
