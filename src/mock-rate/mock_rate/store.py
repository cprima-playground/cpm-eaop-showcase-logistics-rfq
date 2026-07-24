"""In-memory Rate store: carrier rates per route. Every carrier_id (masterdata
Party, kind=carrier) and currency (masterdata Currency) is validated via a REAL
masterdata API call at load (ADR-010: never a duplicated file) -- exercises
BOTH masterdata domains Rate touches, not just Currency like FX did.
"""

from __future__ import annotations

import yaml
from pathlib import Path

from rfq_common.masterdata_client import MasterdataClient
from rfq_common.models import CarrierRate


class UnknownCarrierError(ValueError):
    pass


class UnknownCurrencyError(ValueError):
    pass


class RateStore:
    def __init__(self, fixtures_dir: str | Path, masterdata_client: MasterdataClient | None = None):
        self._fixtures_dir = Path(fixtures_dir)
        self._masterdata = masterdata_client
        self._carrier_cache: set[str] = set()
        self._currency_cache: set[str] = set()
        self._rates: list[CarrierRate] = []
        self.reload()

    def reload(self) -> None:
        doc = yaml.safe_load((self._fixtures_dir / "rates.yaml").read_text(encoding="utf-8"))
        rates = [CarrierRate.model_validate(r) for r in doc["rates"]]
        if self._masterdata is not None:
            for rate in rates:
                self._validate_carrier(rate.carrier_id)
                self._validate_currency(rate.currency)
        self._rates = rates

    def _validate_carrier(self, carrier_id: str) -> None:
        if carrier_id in self._carrier_cache:
            return
        party = self._masterdata.get("parties", carrier_id)
        if party is None or party.get("kind") != "carrier":
            raise UnknownCarrierError(f"masterdata has no carrier Party for {carrier_id!r}")
        self._carrier_cache.add(carrier_id)

    def _validate_currency(self, code: str) -> None:
        if code in self._currency_cache:
            return
        if not self._masterdata.exists("currencies", code):
            raise UnknownCurrencyError(f"masterdata has no currency entry for {code!r}")
        self._currency_cache.add(code)

    def list(self) -> list[CarrierRate]:
        return list(self._rates)

    def get_rate(self, route_id: str) -> CarrierRate | None:
        return next((r for r in self._rates if r.route_id == route_id), None)

    def surcharges(self, route_id: str) -> int | None:
        rate = self.get_rate(route_id)
        return rate.surcharges if rate else None
