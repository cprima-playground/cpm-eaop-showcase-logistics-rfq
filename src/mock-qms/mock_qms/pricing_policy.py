"""DEMO-ONLY pricing policy (`demo-cost-plus-margin-v1`) -- QMS owns
sell-price calculation via this versioned, EXPLICITLY SYNTHETIC formula.
Nothing in business/decisions.md or business/qms-pricing-rules.md specifies
a sell-price formula (QuoteVersion.proposed_sell_price_eur_cents was
deliberately left null for that reason); leaving it permanently null,
though, disables too much of the real workflow to ever demo an approval.
This fills the gap for demo purposes only -- named, versioned
(`pricing_policy_ref` on the written QuoteVersion), and never represented
as a decided commercial policy. Replace or delete this module the day a
real pricing-terms source exists.

Governed by PROFILE, not one hardcoded number: `margin_floor_ref`
(already a real QuoteVersion field, composed via PUT .../pricing-inputs)
selects which PricingProfile applies -- the same field a real system would
use to point at a negotiated/customer-specific margin-floor revision. Two
profiles exist to prove the governance surface, not because two is
special; add more the same way. Exposed for real via the "Pricing
Configuration" routes (GET /pricing-terms/{id}, /margin-floors/{id}, and
the customer-scoped variants) -- api.py.

Target-margin math: sell_price = cost / (1 - target_margin), NOT
cost * (1 + target_margin) -- the latter under-delivers the requested
margin (a 20% "markup" is only a 16.67% gross margin)."""

from __future__ import annotations

from decimal import ROUND_CEILING, Decimal

from pydantic import BaseModel

POLICY_REF = "demo-cost-plus-margin-v1"


class PricingProfile(BaseModel):
    profile_id: str
    name: str
    base_margin_pct_x10: int  # also R1's floor
    fx_risk_adjustment_pct_x10: int = 20  # +2pp when R2 is over_threshold
    max_target_margin_pct_x10: int = 300  # 30% cap


# Route/transit risk adjustments (R3-R5) are always 0 in this build -- there
# is no real contracted-lane baseline to derive them from (see store.py's
# module docstring); no profile fabricates a value for them.
PROFILES: dict[str, PricingProfile] = {
    "standard": PricingProfile(profile_id="standard", name="Standard", base_margin_pct_x10=180),
    "strategic-account": PricingProfile(
        profile_id="strategic-account", name="Strategic Account",
        base_margin_pct_x10=120, max_target_margin_pct_x10=250,
    ),
}
DEFAULT_PROFILE_ID = "standard"


def resolve_profile(margin_floor_ref: str | None) -> PricingProfile:
    """Unrecognized/absent ref falls back to `standard` -- never raises, a
    quote must always be priceable even if its ref doesn't match a known
    profile (e.g. legacy/typo'd refs from before a profile was renamed)."""
    return PROFILES.get(margin_floor_ref or "", PROFILES[DEFAULT_PROFILE_ID])


def target_margin_pct_x10(profile: PricingProfile, *, fx_over_threshold: bool) -> int:
    adjustment = profile.fx_risk_adjustment_pct_x10 if fx_over_threshold else 0
    return min(profile.base_margin_pct_x10 + adjustment, profile.max_target_margin_pct_x10)


def calculate_sell_price(total_cost_eur_cents: int, target_margin_pct_x10: int) -> int:
    if total_cost_eur_cents < 0:
        raise ValueError("total cost cannot be negative")
    if not 0 <= target_margin_pct_x10 < 1000:
        raise ValueError("target margin must be between 0% and 99.9%")
    margin = Decimal(target_margin_pct_x10) / Decimal(1000)
    raw_sell_price = Decimal(total_cost_eur_cents) / (Decimal(1) - margin)
    return int(raw_sell_price.quantize(Decimal("1"), rounding=ROUND_CEILING))


def commercial_round_up(cents: int) -> int:
    """Under €1,000 -> nearest €5. €1,000-9,999 -> nearest €10. >=€10,000 ->
    nearest €50. A customer-facing price, not the raw mathematical minimum."""
    if cents < 100_000:
        band = 500
    elif cents < 1_000_000:
        band = 1_000
    else:
        band = 5_000
    remainder = cents % band
    return cents if remainder == 0 else cents + (band - remainder)


def calculate_margin_pct_x10(total_cost_eur_cents: int, proposed_sell_price_eur_cents: int) -> int:
    """The ACTUAL margin after commercial rounding -- R1 evaluates this,
    not the pre-rounding target."""
    if proposed_sell_price_eur_cents <= 0:
        raise ValueError("sell price must be positive")
    margin = (
        Decimal(proposed_sell_price_eur_cents - total_cost_eur_cents)
        / Decimal(proposed_sell_price_eur_cents)
    )
    return int((margin * Decimal(1000)).quantize(Decimal("1"), rounding=ROUND_CEILING))
