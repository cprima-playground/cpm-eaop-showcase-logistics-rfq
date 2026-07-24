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
    customer_id: str | None = None  # -> masterdata Party (ADR-010) -- reference, never copy
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
    system_of_record: Literal["qms"] = "qms"
    status: QuoteStatus = "draft"
    customer_id: str | None = None  # -> masterdata Party (ADR-010)
    currency: str | None = None
    total_cost_eur_cents: int | None = None
    proposed_sell_price_eur_cents: int | None = None
    margin_pct_x10: int | None = None
    valid_until: str | None = None
    prior_version: int | None = None


class RouteOption(BaseModel):
    option_id: str
    lane_id: str | None = None
    carrier_id: str | None = None  # -> masterdata Party (ADR-010) -- was a bare string
    carrier_rate_amount: int | None = None
    carrier_rate_currency: str | None = None
    transit_days: int | None = None
    capacity_status: Literal["available", "limited", "unavailable", "degraded"] | None = None


# --- TMS: route topology + operational overlay (systems/tms/) ----------------
# Two systems of record, deliberately separate (systems/reference-data.md):
# topology is stable, availability is volatile. Route.legs reference masterdata
# Location codes -- validated via the masterdata API (ADR-010), never embedded.

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


# --- Rate: carrier rates (systems/rate/) --------------------------------------
# carrier_id -> masterdata Party (kind=carrier); currency -> masterdata Currency.
# Both validated via the masterdata API, never embedded (ADR-010).


class CarrierRate(BaseModel):
    route_id: str
    carrier_id: str
    currency: str
    base_cost: int
    surcharges: int
    capacity_status: RouteAvailabilityStatus


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


# --- masterdata / reference data (ADR-010) ------------------------------------
# Slow-changing, enterprise-wide reference data -- a DIFFERENT category from the
# transactional business objects above (ADR-002 governs those; this doesn't).
# Every code_field below is what CodeListStore keys on.

PartyKind = Literal["customer", "carrier", "forwarder", "consignee"]


class Party(BaseModel):
    party_id: str
    name: str
    kind: PartyKind
    country: str | None = None
    active: bool = True


class Location(BaseModel):
    """Real UN/LOCODE reference (systems/tms/fixtures/locations.yaml)."""

    locode: str
    name: str
    type: Literal["seaport", "airport", "inland_terminal", "rail_terminal"]
    country: str
    timezone: str
    lat: float | None = None
    lon: float | None = None


class Currency(BaseModel):
    """ISO 4217."""

    code: str
    name: str
    minor_unit: int  # decimal places, e.g. 2 for EUR/USD, 0 for JPY
    symbol: str | None = None
    active: bool = True


class Incoterm(BaseModel):
    """Incoterms(R) 2020."""

    code: str
    name: str
    responsibility_transfer: str
    version: str = "2020"


class Commodity(BaseModel):
    hs_code: str
    description: str
    dangerous_goods: bool = False
    dg_class: str | None = None  # -> DangerousGoodsClass.class_code, if applicable


class Equipment(BaseModel):
    code: str
    name: str
    type: Literal["container", "vehicle"]
    capacity: str | None = None


class UnitOfMeasure(BaseModel):
    code: str
    name: str
    quantity_kind: Literal["weight", "volume", "count"]


class DangerousGoodsClass(BaseModel):
    """IMDG classes 1-9."""

    class_code: str
    name: str
    description: str


class PaymentTerm(BaseModel):
    code: str
    name: str
    description: str | None = None
