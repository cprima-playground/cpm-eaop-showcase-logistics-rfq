"""Pydantic entity models — the single source of truth shared by every mock
system's API, CLI, and jsonl fixtures (ADR-006 Decision 1).

Business objects mirror business/domain-model.yaml exactly. Identity models mirror
identity/claims-contract.md (the IdP-agnostic claim contract, same shape as cpm-eaop
InternalPrincipal). These are TWO LAYERS on purpose: business objects are not authz
entities — only authz-projection.yaml decides what crosses into Cedar.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# --- identity (claims-contract.md) --------------------------------------------

PrincipalKind = Literal["human", "service", "agent", "workload", "external"]


class InternalPrincipal(BaseModel):
    """The IdP-agnostic principal, resolved from any IdP's claims (claims-contract.md)."""

    id: str
    kind: PrincipalKind
    active: bool = True
    scope: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    member_of: list[str] = Field(default_factory=list)
    trust_domain: str | None = None
    department: str | None = None
    business_unit: str | None = None
    azp: str | None = None
    attributes: dict = Field(default_factory=dict)


# --- business objects (domain-model.yaml) -------------------------------------

RfqStatus = Literal[
    "draft", "awaiting_information", "sourcing_rates", "pricing",
    "approval_required", "issued", "accepted", "rejected", "expired",
]


class RFQ(BaseModel):
    rfq_id: str
    system_of_record: Literal["crm"] = "crm"
    status: RfqStatus = "draft"
    origin: str | None = None
    destination: str | None = None
    quote_currency: str | None = None
    contracted_lane: str | None = None
    region: str | None = None


QuoteStatus = Literal["draft", "priced", "approval_required", "approved", "rejected", "revise"]


class Quote(BaseModel):
    """The human-in-the-loop decision IS `status` here — not a separate workflow
    record (business/decisions.md, ADR-005)."""

    quote_id: str
    version: int
    system_of_record: Literal["cpq"] = "cpq"
    status: QuoteStatus = "draft"
    currency: str | None = None
    total_cost_eur_cents: int | None = None
    proposed_sell_price_eur_cents: int | None = None
    margin_pct_x10: int | None = None
    valid_until: str | None = None
    prior_version: int | None = None


class RouteOption(BaseModel):
    option_id: str
    lane_id: str | None = None
    carrier_rate_amount: int | None = None
    carrier_rate_currency: str | None = None
    transit_days: int | None = None
    capacity_status: Literal["available", "limited", "unavailable", "degraded"] | None = None


class ExchangeRate(BaseModel):
    pair: str  # e.g. "CNY-EUR"
    system_of_record: Literal["fx_service"] = "fx_service"
    rate: float | None = None
    rate_type: str | None = None
    source: str | None = None
    observed_at: str | None = None
    valid_until: str | None = None
    rate_ref: str | None = None


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
