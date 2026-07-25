"""Domain-specific pricing exceptions -- replaces the bare ValueError raises
that used to live in pricing_policy.py so a caller can catch a
pricing-calculation failure without accidentally swallowing an unrelated
ValueError (e.g. an int()/Decimal() parse error). Deliberately NOT related
to store.py's UnknownCustomerError/UnknownQuoteError/VersionConflictError/
InvalidStateError/ComposeIncompleteError -- those are QMS-workflow errors
(concurrency, lifecycle state, masterdata lookup), not pricing-calculation
errors, and stay exactly where they are."""

from __future__ import annotations


class PricingError(Exception):
    """Base for every error raised inside mock_qms.pricing."""


class NegativeAmountError(PricingError):
    """A Money amount would be negative -- structurally invalid, not a
    business-rule violation."""


class CurrencyMismatchError(PricingError):
    """Attempted Money arithmetic across two different currencies without
    an explicit FX conversion step."""


class MoneyScaleMismatchError(PricingError):
    """Attempted Money arithmetic between two amounts sharing a currency
    but disagreeing on minor_unit. Should never happen if masterdata is
    internally consistent -- signals corrupted/stale data, not an ordinary
    caller mistake, so it's kept distinct from CurrencyMismatchError."""


class InvalidMarginError(PricingError):
    """A target margin percentage is out of the valid 0%-99.9% range, or a
    sell price isn't positive enough to compute an actual margin against."""
