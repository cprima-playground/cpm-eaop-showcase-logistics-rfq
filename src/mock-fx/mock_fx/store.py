"""In-memory FX rate store, loaded from real fixture files at boot.

Point-in-time lookup: `effectiveAt` picks the latest snapshot with
observed_at <= effectiveAt for the pair (or the latest overall if omitted) --
matches interfaces/api/fx-api.md ("Authoritative FX rate for a currency pair at
a point in time"). Deterministic: reload() re-reads the same fixture files, no
network, no randomness.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from rfq_common.models import ExchangeRate


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


class FxStore:
    def __init__(self, fixtures_dir: str | Path):
        self._fixtures_dir = Path(fixtures_dir)
        self._rates: list[ExchangeRate] = []
        self.reload()

    def reload(self) -> None:
        """Reload every *.json fixture in the fixtures dir -- the admin `reset`."""
        rates = []
        for path in sorted(self._fixtures_dir.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            rates.append(ExchangeRate.model_validate(data))
        self._rates = rates

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
