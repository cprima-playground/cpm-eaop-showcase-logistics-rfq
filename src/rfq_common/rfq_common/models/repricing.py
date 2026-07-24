"""The repricing subprocess's agent-produced business objects
(business/domain-model.yaml): RouteOption/RouteRecommendation are ephemeral
evaluated snapshots (system_of_record: agent_state), not authoritative
stores. ApprovalTask is a MECHANISM only -- see its own docstring."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RouteOption(BaseModel):
    option_id: str
    lane_id: str | None = None
    carrier_id: str | None = None  # -> masterdata Party (ADR-010) -- was a bare string
    carrier_rate_amount: int | None = None
    carrier_rate_currency: str | None = None
    transit_days: int | None = None
    capacity_status: Literal["available", "limited", "unavailable", "degraded"] | None = None


class TriggeredThreshold(BaseModel):
    id: str
    actual_pct_x10: int | None = None
    actual: bool | None = None
    threshold_pct_x10: int | None = None
    threshold: bool | None = None


class RouteRecommendation(BaseModel):
    recommendation_id: str
    system_of_record: Literal["agent_state"] = "agent_state"
    rfq_id: str
    recommended_option: str | None = None
    reasoning: list[str] = Field(default_factory=list)
    decision_status: str | None = None
    triggered_thresholds: list[TriggeredThreshold] = Field(default_factory=list)


class ApprovalTask(BaseModel):
    """MECHANISM only -- surfaces the decision to a human. NOT the authoritative
    store; that's Quote.status (business/decisions.md)."""

    task_id: str
    system_of_record: Literal["workflow"] = "workflow"
    recommendation_id: str
    assignee_role: str | None = None
    evidence: dict = Field(default_factory=dict)
