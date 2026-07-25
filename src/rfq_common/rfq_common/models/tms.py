"""TMS: route topology + operational overlay (systems/tms/). Two systems of
record, deliberately separate (systems/reference-data.md): topology is
stable, availability is volatile.

Topology is itself split into two layers: a reusable, directed `RouteEdge`
pool (pure origin/destination/mode, no duration -- transit time is a
per-route planning fact, not intrinsic to the connection) and named
`Route`s that reference edges in order via `RouteEdgeRef`. This groundwork
exists for a future MCP-based route-finder to query real graph adjacency;
named routes remain the sole commercially-curated, authoritative paths --
a graph-traversable candidate is never automatically a commercial route.

All location codes (`RouteEdge.origin_id`/`destination_id`) are validated
against the masterdata API (ADR-010), never embedded."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

TransportMode = Literal["ocean", "rail", "road", "air"]


class RouteEdge(BaseModel):
    """Reusable, directed topology -- pure value/reference type, frozen
    since it's shared by id across multiple routes and should never be
    mutated in place. No duration, no schedule, no carrier, no price, no
    availability -- those are route-specific (RouteEdgeRef) or operational
    (RouteAvailability) facts, not intrinsic to the connection itself."""

    model_config = {"frozen": True}

    id: str
    origin_id: str  # masterdata Location code
    destination_id: str  # masterdata Location code
    mode: TransportMode


class RouteEdgeRef(BaseModel):
    """One edge's use within a specific named route -- carries the
    route-specific planning duration, since the same physical edge can
    legitimately have different indicative durations depending on the
    commercial route/service context it's used in."""

    edge_id: str
    indicative_duration_days: int = Field(gt=0)


# Tags, not a mutually-exclusive enum -- a route CAN carry more than one
# (e.g. ["alternative", "contracted"] is valid if a non-primary lane is
# still under contract). Don't accidentally enforce exclusivity anywhere
# consuming this (e.g. don't render as a single-select dropdown later).
RouteRole = Literal["primary", "contracted", "alternative", "contingency"]


class RouteApplicability(BaseModel):
    """Means 'this route is a valid alternative when this disruption
    occurs' -- not 'this route is impacted by it.' Named accordingly
    (`applicable_disruption_tags`, not `disruption_tags`) so a future
    reader can't invert the meaning."""

    applicable_disruption_tags: list[str] = Field(default_factory=list)


class Route(BaseModel):
    """Stable topology -- TMS's system of record. An ordered, curated
    commercial path composed from `RouteEdge`s; never a graph search
    result -- resolving a route's edges is always a direct id lookup."""

    id: str
    lane_id: str
    roles: list[RouteRole] = Field(default_factory=list)
    edges: list[RouteEdgeRef]
    applicability: RouteApplicability | None = None

    @field_validator("roles")
    @classmethod
    def _no_duplicate_roles(cls, v):
        if len(v) != len(set(v)):
            raise ValueError(f"duplicate role in {v!r}")
        return v


RouteAvailabilityStatus = Literal["available", "limited", "unavailable", "degraded"]


class RouteAvailability(BaseModel):
    """Volatile operational overlay -- changes independently of topology.
    Route-keyed (not edge-keyed): the one existing scenario pack
    (hamburg-port-closure.yaml) already works this way and there's no
    current consumer needing edge-scoped availability."""

    route_id: str
    status: RouteAvailabilityStatus
    reason: str | None = None
    effective_from: datetime | None = None
    expected_until: datetime | None = None
    affected_leg: str | None = None  # free-form, unchanged -- see tms.py's module note
    observed_at: datetime | None = None
    source_ref: str | None = None

    @model_validator(mode="after")
    def _until_after_from(self):
        if self.effective_from and self.expected_until and self.expected_until < self.effective_from:
            raise ValueError("expected_until must not precede effective_from")
        return self
