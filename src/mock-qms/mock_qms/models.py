"""Pydantic models for the QMS API. Kept local to mock-qms (not rfq_common.models)
-- these are still design-stage and several carry deliberate x-gap fields;
promoting them to the shared library is a later step, once the business
rules/Cedar wiring behind them is real, not just route shapes. QuoteStatus
itself is the one exception -- reused as-is from rfq_common.models rather than
duplicated, since it's also the type derive_rfq_status_from_quote takes
(business/decisions.md's "SoR boundary: RFQ vs Quote").

x-owner/x-role on fields (via Field(json_schema_extra=...)) migrated from the
former interfaces/api/qms.openapi.yaml: who OWNS a value (system of record),
and whether THIS field merely REFERENCES it or QMS COMPUTES it. Catches
accidental duplication before implementation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from rfq_common.models import QuoteStatus as QuoteVersionStatus


def _ref(owner: str) -> dict:
    return {"x-owner": owner, "x-role": "references"}


def _owns() -> dict:
    return {"x-owner": "qms", "x-role": "owns"}


def _computes(owner: str | None = "qms") -> dict:
    return {"x-owner": owner, "x-role": "computes"}


class RFQ(BaseModel):
    rfq_id: str
    status: str
    customer_id: str | None = None
    origin: str | None = None
    destination: str | None = None
    quote_currency: str | None = None
    contracted_lane: str | None = None
    region: str | None = None


class CarrierRate(BaseModel):
    """A carrier rate is a SUPPLIER-side cost to the forwarder -- "sell" is
    never a property of the rate itself, only of the Quote built from it
    (QuoteVersion.proposed_sell_price_eur_cents). One cost field, gated by
    D15 -- no second, confusable field."""

    rate_id: str = Field(json_schema_extra=_ref("rate_management"))
    carrier_id: str = Field(json_schema_extra=_ref("masterdata"))
    lane_id: str = Field(json_schema_extra=_ref("rate_management"))
    currency: str = Field(json_schema_extra=_ref("masterdata"))
    cost_cents: int | None = Field(
        default=None, json_schema_extra=_ref("rate_management"),
        description="The carrier's published rate to the forwarder -- present only if buy-rate.read (D15) is also authorized, absent (not zero) otherwise.",
    )
    confidentiality_class: str | None = Field(default=None, json_schema_extra=_ref("rate_management"))


class Quote(BaseModel):
    """The aggregate -- identity + customer/RFQ linkage. Commercial content lives on QuoteVersion."""

    quote_id: str = Field(json_schema_extra=_owns())
    rfq_id: str = Field(json_schema_extra=_ref("crm"))
    customer_id: str = Field(json_schema_extra=_ref("masterdata"))
    currency: str | None = Field(default=None, json_schema_extra=_owns(), description="Set at creation (CreateQuoteRequest); versions may normalize to it.")
    latest_version: int | None = Field(default=None, json_schema_extra=_owns())
    latest_version_status: str | None = Field(default=None, json_schema_extra=_owns())
    created_at: str | None = Field(default=None, json_schema_extra=_owns())


class CreateQuoteRequest(BaseModel):
    rfq_id: str = Field(json_schema_extra=_ref("crm"))
    customer_id: str = Field(json_schema_extra=_ref("masterdata"))
    currency: str = Field(json_schema_extra=_owns(), examples=["EUR"])


class RouteRecommendationInput(BaseModel):
    """This is what makes recommendation_id known -- the precondition for D16
    to later apply at POST .../price."""

    recommendation_id: str = Field(json_schema_extra=_ref("agent_state"), description="-> RouteRecommendation.")
    selected_route_id: str = Field(json_schema_extra=_ref("agent_state"))


class PricingInputs(BaseModel):
    fx_rate_ref: str = Field(json_schema_extra=_ref("fx_service"))
    rate_refs: list[str] = Field(default_factory=list, json_schema_extra=_ref("rate_management"))
    pricing_terms_ref: str = Field(json_schema_extra=_ref("qms"))
    margin_floor_ref: str = Field(json_schema_extra=_ref("qms"))


class ValidityInput(BaseModel):
    valid_until: str = Field(json_schema_extra=_owns())


class CreateNextVersionRequest(BaseModel):
    prior_version: int = Field(json_schema_extra=_owns())
    expected_latest_version: int = Field(
        json_schema_extra=_ref("caller"),
        description="Concurrency precondition (equivalent to If-Match) -- mismatch is 409, not 403.",
    )
    change_reason: str | None = Field(default=None, examples=["route_unavailable"])
    trigger_event_ref: str | None = Field(default=None, json_schema_extra=_ref("varies"))
    copy_from_prior: bool = Field(default=True, description="Whether composed draft fields (shipment/commercial-terms/etc.) carry forward or must be re-supplied.")


class QuoteVersion(BaseModel):
    quote_id: str = Field(json_schema_extra=_owns())
    version: int = Field(json_schema_extra=_owns())
    prior_version: int | None = Field(default=None, json_schema_extra=_owns())
    status: QuoteVersionStatus = Field(
        json_schema_extra=_owns(),
        description="The human-in-the-loop decision (approval_required -> approved|rejected|revise) is a status change (decisions.md).",
    )
    currency: str | None = Field(default=None, json_schema_extra=_computes())
    total_cost_eur_cents: int | None = Field(default=None, json_schema_extra=_computes(), description="Null until priced.")
    proposed_sell_price_eur_cents: int | None = Field(
        default=None, json_schema_extra=_computes(owner=None),
        description="x-owner left null on purpose -- see POST .../price's x-gap on sell-price origin.",
    )
    margin_pct_x10: int | None = Field(default=None, json_schema_extra=_computes(), description="R1 -- (sell - cost) / sell * 1000")
    fx_variance_pct_x10: int | None = Field(default=None, json_schema_extra=_computes(), description="R2, only once compared against a later current rate")
    valid_until: str | None = Field(default=None, json_schema_extra=_owns())
    created_at: str | None = Field(default=None, json_schema_extra=_owns())
    created_by: str | None = Field(default=None, json_schema_extra=_owns(), description="Principal id (agent or human).")
    authorization_decision_ids: list[str] = Field(
        default_factory=list, json_schema_extra=_owns(),
        description="determining_policies from every Cedar call this version triggered -- rfq_common.pdp.AuthorizationDecision.determining_policies.",
    )
    pricing_rule_results: list[str] = Field(default_factory=list, json_schema_extra=_owns(), description="Which of R1-R6 fired and their computed values.")
    recommendation_id: str | None = Field(default=None, json_schema_extra=_ref("agent_state"))
    rate_refs: list[str] = Field(default_factory=list, json_schema_extra=_ref("rate_management"))
    fx_rate_ref: str | None = Field(default=None, json_schema_extra=_ref("fx_service"))
    pricing_terms_ref: str | None = Field(default=None, json_schema_extra=_ref("qms"))
    margin_floor_ref: str | None = Field(default=None, json_schema_extra=_ref("qms"))
    trigger_event_ref: str | None = Field(default=None, json_schema_extra=_ref("varies"))


class RuleResult(BaseModel):
    rule_id: str
    actual_pct_x10: int
    threshold_pct_x10: int
    result: Literal["within_threshold", "below_floor", "over_threshold"]


class PricingResult(BaseModel):
    """Customer-facing pricing result -- no buy-cost detail (see PricingBreakdown for that, D15-gated)."""

    currency: str
    total_cost_cents: int
    proposed_sell_price_cents: int
    margin_pct_x10: int
    rule_results: list[RuleResult] = []


class BuyCostLineItem(BaseModel):
    rate_id: str
    cost_cents: int


class PricingBreakdown(PricingResult):
    buy_cost_line_items: list[BuyCostLineItem] = []


class DecisionRecord(BaseModel):
    decision: Literal["approved", "rejected", "revise"]
    approver: str = Field(json_schema_extra=_owns(), description="Principal id (human).")
    reason: str | None = None
    decided_at: str = Field(json_schema_extra=_owns())


class QuoteDecisionRequest(BaseModel):
    decision: Literal["approved", "rejected", "revise"]
    approver: str
    reason: str | None = None


class CustomerQuoteView(BaseModel):
    """What D18 actually governs -- excludes buy rates, confidential margins,
    policy diagnostics, rejected alternatives, internal comments."""

    quote_id: str
    version: int
    currency: str
    proposed_sell_price_cents: int
    valid_until: str
    route_summary: str = Field(description="Human-readable, not the internal RouteOption/RouteRecommendation shape.")


class QuoteDocument(BaseModel):
    document_id: str = Field(json_schema_extra=_owns())
    document_type: str = Field(examples=["proposal_pdf"])
    quote_id: str = Field(json_schema_extra=_owns())
    quote_version: int = Field(json_schema_extra=_owns(), description="Immutable reference -- regenerating from a later pricing-config change must produce a NEW document, never mutate this one.")
    generated_at: str = Field(json_schema_extra=_owns())
    url: str | None = None


class ChangeEvent(BaseModel):
    from_version: int | None = None
    to_version: int
    changed_fields: list[str] = []
    trigger_event_ref: str | None = None


class TimelineEntry(BaseModel):
    version: int
    status: str
    occurred_at: str


class AuditEvent(BaseModel):
    action: str = Field(examples=["quote.create-version"])
    authorization_decision_id: str
    principal: str
    occurred_at: str


class TriggerEventInput(BaseModel):
    type: str
    event_id: str


class ChangeRequestInput(BaseModel):
    requested_change: str | None = None


class WithdrawRequest(BaseModel):
    reason: str | None = None


class ExtendValidityRequest(BaseModel):
    new_valid_until: str


class GenerateDocumentRequest(BaseModel):
    document_type: str | None = None
