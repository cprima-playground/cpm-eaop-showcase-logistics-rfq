"""TMS: route topology + operational overlay (systems/tms/). Two systems of
record, deliberately separate (systems/reference-data.md): topology is
stable, availability is volatile. Route.legs reference masterdata Location
codes -- validated via the masterdata API (ADR-010), never embedded."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

TransportMode = Literal["ocean", "rail", "road", "air"]


class RouteLeg(BaseModel):
    from_: str = Field(alias="from")  # masterdata Location code
    to: str  # masterdata Location code
    mode: TransportMode
    duration_days: int

    model_config = {"populate_by_name": True}


class Route(BaseModel):
    """Stable topology -- TMS's system of record."""

    id: str
    lane: str
    contracted: bool = False
    legs: list[RouteLeg]


RouteAvailabilityStatus = Literal["available", "limited", "unavailable", "degraded"]


class RouteAvailability(BaseModel):
    """Volatile operational overlay -- changes independently of topology."""

    route_id: str
    status: RouteAvailabilityStatus
    reason: str | None = None
    effective_from: str | None = None
    expected_until: str | None = None
    affected_leg: str | None = None
