"""Rate -- carrier rates per route (systems/rate/, src/mock-rate/). Distinct
from qms.CarrierRateView: this is the storage/quoting shape (route_id,
base_cost + surcharges as separate line items); the QMS one is a
disclosure-gated READ PROJECTION (D14/D15: rate.read vs buy-rate.read) with
its own confidentiality_class -- same real-world concept, two different
concerns, not a naming accident.

carrier_id -> masterdata Party (kind=carrier); currency -> masterdata
Currency. Both validated via the masterdata API, never embedded (ADR-010)."""

from __future__ import annotations

from pydantic import BaseModel

from .tms import RouteAvailabilityStatus


class CarrierRate(BaseModel):
    route_id: str
    carrier_id: str
    currency: str
    base_cost: int
    surcharges: int
    capacity_status: RouteAvailabilityStatus
