"""In-memory FX rate store, loaded from real fixture files at boot, plus a
generated 28-day history per pair (see generator.py -- deterministic, seeded,
never persisted as fixture files).

Point-in-time lookup: `effectiveAt` picks the latest snapshot with
observed_at <= effectiveAt for the pair (or the latest overall if omitted) --
matches interfaces/api/fx-api.md ("Authoritative FX rate for a currency pair at
a point in time"). Deterministic: reload() re-reads the same fixture files and
re-generates history from the same seed (rfq_common.clock.seeded_rng()) --
byte-stable across restarts, no network (except currency validation, which IS
a real API call -- ADR-010: masterdata must be consumed via API, never a
duplicated file).
"""

from __future__ import annotations

import json
import warnings
from datetime import datetime
from pathlib import Path

from rfq_common.clock import seeded_rng
from rfq_common.masterdata_client import MasterdataClient, MasterdataUnavailableError
from rfq_common.models import ExchangeRate
from rfq_common.store_stats import collection_stats

from . import ecb_client
from .generator import generate_history

HISTORY_DAYS = 28
LIVE_CURRENCIES = ("USD", "GBP", "JPY", "CNY")  # vs EUR, ECB's base
TOTAL_HISTORY_DAYS = HISTORY_DAYS + 2  # matches the fixture path's 28 generated + 2 real


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


class UnknownCurrencyError(ValueError):
    pass


class FxStore:
    def __init__(
        self,
        fixtures_dir: str | Path,
        masterdata_client: MasterdataClient | None = None,
        *,
        live_anchor: bool = False,
        ecb_cache_file: str | Path | None = None,
    ):
        self._fixtures_dir = Path(fixtures_dir)
        self._masterdata = masterdata_client
        self._live_anchor = live_anchor
        self._ecb_cache_file = ecb_cache_file
        self._minor_unit_cache: dict[str, int] = {}
        self._rates: list[ExchangeRate] = []
        self.reload()

    def reload(self) -> None:
        """The admin `reset`. If live_anchor is on, tries to anchor every pair
        in real ECB reference rates (three tiers -- live fetch, a manually
        cached copy of the same feed, then the committed fixtures below);
        otherwise (or on total ECB unavailability) loads the committed
        fixtures and generates HISTORY_DAYS of synthetic history per pair,
        ending the day before that pair's EARLIEST real fixture (today/
        yesterday stay the exact, untouched, nominal anchor -- no breakout
        by default, see generator.py). Every currency in the resulting set is
        validated against the masterdata API (fail closed: unreachable
        masterdata or an unknown currency code both raise)."""
        rates: list[ExchangeRate] = []
        if self._live_anchor:
            rates = self._load_live_rates()
        if not rates:
            rates = self._load_fixture_rates()

        if self._masterdata is not None:
            for rate in rates:
                for code in rate.pair.split("/"):
                    self._validate_currency(code)

        self._rates = rates

    def _load_fixture_rates(self) -> list[ExchangeRate]:
        rates = []
        for path in sorted(self._fixtures_dir.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            rates.append(ExchangeRate.model_validate(data))

        rng = seeded_rng()
        for pair in sorted({r.pair for r in rates}):
            earliest = min((r for r in rates if r.pair == pair), key=lambda r: _parse(r.observed_at))
            rates.extend(generate_history(
                pair,
                anchor_rate=earliest.rate,
                before=_parse(earliest.observed_at),
                days=HISTORY_DAYS,
                rng=rng,
            ))
        return rates

    def _load_live_rates(self) -> list[ExchangeRate]:
        """Tier 1 (live fetch) then tier 2 (local cache file). Returns []
        (never raises) on total unavailability -- reload() falls back to
        fixtures in that case."""
        try:
            days = ecb_client.fetch_history(LIVE_CURRENCIES)
        except ecb_client.EcbUnavailableError as exc:
            if self._ecb_cache_file is not None:
                try:
                    days = ecb_client.load_history_from_file(self._ecb_cache_file, LIVE_CURRENCIES)
                except ecb_client.EcbUnavailableError as cache_exc:
                    warnings.warn(
                        f"mock-fx: ECB live fetch failed ({exc}) and cache file "
                        f"unusable ({cache_exc}); falling back to committed fixtures"
                    )
                    return []
            else:
                warnings.warn(f"mock-fx: ECB live fetch failed ({exc}); falling back to committed fixtures")
                return []

        days = days[-TOTAL_HISTORY_DAYS:]
        rates = []
        for date, by_currency in days:
            for currency, ecb_rate in by_currency.items():
                rates.append(ExchangeRate(
                    pair=f"{currency}/EUR",
                    rate=round(1 / ecb_rate, 6),
                    rate_type="corporate",
                    source="ecb-eurofxref",
                    observed_at=f"{date}T08:00:00Z",
                    valid_until=f"{date}T16:00:00Z",
                    rate_ref=f"FX-{date.replace('-', '')}-{currency}-EUR",
                ))
        return rates

    def history(self, base: str, quote: str) -> list[ExchangeRate]:
        """Every point for a pair, oldest first -- the real fixtures plus the
        generated run-up to them."""
        pair = f"{base}/{quote}"
        return sorted((r for r in self._rates if r.pair == pair), key=lambda r: _parse(r.observed_at))

    def _validate_currency(self, code: str) -> None:
        if code in self._minor_unit_cache:
            return
        entry = self._masterdata.get("currencies", code)  # raises MasterdataUnavailableError if unreachable
        if entry is None:
            raise UnknownCurrencyError(f"masterdata has no currency entry for {code!r}")
        self._minor_unit_cache[code] = entry["minor_unit"]

    def minor_unit(self, code: str) -> int:
        """The currency's decimal-place count (0 for JPY, 2 for most), via
        masterdata -- never hardcoded."""
        self._validate_currency(code)
        return self._minor_unit_cache[code]

    def list_latest(self) -> list[ExchangeRate]:
        """The current (latest) rate for every known pair -- an overview list,
        not a point-in-time lookup. Mirrors the list-then-detail pattern
        already used by masterdata/TMS/Rate (`GET /{domain}` before
        `GET /{domain}/{code}`)."""
        pairs = sorted({r.pair for r in self._rates})
        return [max((r for r in self._rates if r.pair == p), key=lambda r: _parse(r.observed_at)) for p in pairs]

    def get(self, base: str, quote: str, *, effective_at: str | None = None) -> ExchangeRate | None:
        pair = f"{base}/{quote}"
        candidates = [r for r in self._rates if r.pair == pair]
        if not candidates:
            return None
        if effective_at is None:
            return max(candidates, key=lambda r: _parse(r.observed_at))
        eff = _parse(effective_at)
        eligible = [r for r in candidates if _parse(r.observed_at) <= eff]
        if not eligible:
            return None
        return max(eligible, key=lambda r: _parse(r.observed_at))

    def stats(self) -> dict:
        return collection_stats(self._rates)
