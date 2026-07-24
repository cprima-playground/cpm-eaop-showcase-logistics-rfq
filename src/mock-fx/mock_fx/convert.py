"""Currency conversion math -- FX is the correct place to round fractional
units, because it's the only system that holds both the rate and (via
masterdata) each currency's minor_unit. NOT every currency has 2 decimal
places: JPY has minor_unit=0 (a whole-yen amount, not yen-cents). Rounding to a
hardcoded 2 decimals here would silently corrupt a JPY conversion.

Scope note: this returns a locale-NEUTRAL decimal string (e.g. "5014.80").
Locale-specific display formatting (thousands separators, "1.234,56" vs
"1,234.56") is a frontend concern (Phase 5), deliberately not done here --
FX's job is correct precision, not i18n/l10n presentation.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


def convert_amount(amount: Decimal, rate: float, *, target_minor_unit: int) -> Decimal:
    """amount is in the FROM currency's major units; returns the converted
    amount in the TO currency's major units, rounded to its own decimal
    precision (target_minor_unit decimal places -- 0 for JPY, 2 for most)."""
    converted = amount * Decimal(str(rate))
    quantum = Decimal(1).scaleb(-target_minor_unit)  # e.g. 0.01 for minor_unit=2, 1 for minor_unit=0
    return converted.quantize(quantum, rounding=ROUND_HALF_UP)
