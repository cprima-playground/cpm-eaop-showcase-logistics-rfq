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
from datetime import datetime
from pathlib import Path

from rfq_common.clock import seeded_rng
from rfq_common.masterdata_client import MasterdataClient, MasterdataUnavailableError
from rfq_common.models import ExchangeRate

from .generator import generate_history

HISTORY_DAYS = 28


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


class UnknownCurrencyError(ValueError):
    pass


class FxStore:
    def __init__(self, fixtures_dir: str | Path, masterdata_client: MasterdataClient | None = None):
        self._fixtures_dir = Path(fixtures_dir)
        self._masterdata = masterdata_client
        self._minor_unit_cache: dict[str, int] = {}
        self._rates: list[ExchangeRate] = []
        self.reload()

    def reload(self) -> None:
        """Reload every *.json fixture in the fixtures dir -- the admin `reset`.
        Every currency in every fixture is validated against the masterdata API
        (fail closed: unreachable masterdata or an unknown currency code both
        raise -- this store never falls back to assuming a currency is valid).
        Then generates HISTORY_DAYS of synthetic history per real pair, ending
        the day before that pair's EARLIEST real fixture (the existing
        today/yesterday snapshots stay the exact, untouched anchor and the
        project's one real documented breakout -- see generator.py)."""
        rates = []
        for path in sorted(self._fixtures_dir.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            rate = ExchangeRate.model_validate(data)
            if self._masterdata is not None:
                for code in rate.pair.split("/"):
                    self._validate_currency(code)
            rates.append(rate)

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

        self._rates = rates

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
