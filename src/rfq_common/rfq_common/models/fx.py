"""FX -- corporate exchange rate service (systems/fx/, src/mock-fx/)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ExchangeRate(BaseModel):
    pair: str  # e.g. "CNY-EUR"
    system_of_record: Literal["fx_service"] = "fx_service"
    rate: float | None = None
    rate_type: str | None = None
    source: str | None = None
    observed_at: str | None = None
    valid_until: str | None = None
    rate_ref: str | None = None
