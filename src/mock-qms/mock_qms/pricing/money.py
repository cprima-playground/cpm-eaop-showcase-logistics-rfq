"""Money -- an amount inseparable from its currency AND its minor-unit
scale, always stored as an integer count of minor units. Fixes a real bug:
the old price_version() hand-converted CarrierRate.base_cost/surcharges
(MAJOR currency units -- systems/rate/fixtures/cost-model.md's own worked
example: 42000 means CNY 42,000) to EUR-cents two different, inconsistent
ways depending on the EUR-vs-non-EUR branch, with a hardcoded assumption
of 2 decimal places for every currency. That assumption is itself wrong --
rfq_common.models.masterdata.Currency.minor_unit is 0 for JPY -- so Money
never hardcodes it: minor_unit is a required constructor argument, always
supplied by a caller that already resolved it (store.py, via real
masterdata, or an FX conversion response that already carries it).

Money is intentionally masterdata-agnostic: it never imports or calls
MasterdataClient. Resolving currency metadata is the caller's job; Money
only carries the already-resolved values needed for arithmetic and
formatting. minor_unit is captured at construction time (not re-resolved
by `.major`) so a historical Money value stays interpretable even if
masterdata's minor_unit for that currency were ever revised later -- this
is deliberate, not redundant with `currency`, and should not be
"deduplicated" away in a future cleanup.

No operators beyond `__add__` -- no `*`/`/`/`-`. Those all carry business
semantics that are easy to misuse (e.g. `money * 0.18` hiding a margin
calculation that belongs in pricing_policy, not here)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .exceptions import CurrencyMismatchError, MoneyScaleMismatchError, NegativeAmountError


@dataclass(frozen=True, slots=True)
class Money:
    amount_minor: int
    currency: str
    minor_unit: int

    def __post_init__(self) -> None:
        if self.amount_minor < 0:
            raise NegativeAmountError(f"Money cannot be negative: {self.amount_minor} {self.currency}")

    @classmethod
    def zero(cls, currency: str, minor_unit: int) -> "Money":
        return cls(0, currency, minor_unit)

    @classmethod
    def from_major(cls, amount_major: Decimal | int | float | str, currency: str, minor_unit: int) -> "Money":
        """One code path for major->minor conversion -- via Decimal(str(x)),
        never Decimal(float), which would import binary-float noise."""
        scaled = Decimal(str(amount_major)) * (10 ** minor_unit)
        return cls(int(scaled.to_integral_value()), currency, minor_unit)

    @property
    def major(self) -> Decimal:
        return Decimal(self.amount_minor) / (10 ** self.minor_unit)

    def __add__(self, other: "Money") -> "Money":
        if other.currency != self.currency:
            raise CurrencyMismatchError(f"cannot add {other.currency} to {self.currency}")
        if other.minor_unit != self.minor_unit:
            raise MoneyScaleMismatchError(
                f"cannot add {self.currency} amounts with different minor_unit "
                f"({self.minor_unit} vs {other.minor_unit})"
            )
        return Money(self.amount_minor + other.amount_minor, self.currency, self.minor_unit)
