"""Answers a later 'why did this price change': which rate_refs/FX
observations fed a price calculation, when, under which policy. Built from
facts already available at price-time (rfq_common.clock.now(), the actual
fx.convert() response) -- no new fixture data.

Provenance records OBSERVED FACTS/INPUTS ONLY (which rate, which FX
snapshot, which policy version) -- never outputs like margin, total cost,
or sell price. Those belong on PricingCalculationResult itself, not here;
keeping this distinction stops provenance from slowly turning into a
second copy of the result.

Not persisted onto QuoteVersion in this pass (the wire shape doesn't
change) -- available on PricingCalculationResult for a future consumer
(an audit-log route, GET .../pricing-breakdown) without requiring another
refactor to obtain it."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class FxConversionFact:
    """One FX conversion actually observed while pricing a version."""

    from_currency: str
    to_currency: str
    rate: float
    observed_at: str  # ISO-8601, via rfq_common.clock.now()


@dataclass(frozen=True, slots=True)
class PricingProvenance:
    rate_refs: list[str]
    fx_conversions: list[FxConversionFact] = field(default_factory=list)
    policy_ref: str = ""
    priced_at: str = ""
