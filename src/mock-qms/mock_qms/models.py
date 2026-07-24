"""Pydantic models mirroring interfaces/api/qms.openapi.yaml's schemas exactly.
Kept local to mock-qms (not rfq_common.models) -- these are still design-stage
and several carry deliberate x-gap fields (see the OpenAPI file's comments);
promoting them to the shared library is a later step, once the business
rules/Cedar wiring behind them is real, not just route shapes. QuoteStatus
itself is the one exception -- reused as-is from rfq_common.models rather than
duplicated, since it's also the type derive_rfq_status_from_quote takes
(business/decisions.md's "SoR boundary: RFQ vs Quote")."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from rfq_common.models import QuoteStatus as QuoteVersionStatus


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
    rate_id: str
    carrier_id: str
    lane_id: str
    currency: str
    cost_cents: int | None = None
    confidentiality_class: str | None = None


class Quote(BaseModel):
    quote_id: str
    rfq_id: str
    customer_id: str
    currency: str | None = None
    latest_version: int | None = None
    latest_version_status: str | None = None
    created_at: str | None = None


class CreateQuoteRequest(BaseModel):
    rfq_id: str
    customer_id: str
    currency: str


class CreateNextVersionRequest(BaseModel):
    prior_version: int
    expected_latest_version: int
    change_reason: str | None = None
    trigger_event_ref: str | None = None
    copy_from_prior: bool = True


class QuoteVersion(BaseModel):
    quote_id: str
    version: int
    prior_version: int | None = None
    status: QuoteVersionStatus
    currency: str | None = None
    total_cost_eur_cents: int | None = None
    proposed_sell_price_eur_cents: int | None = None
    margin_pct_x10: int | None = None
    fx_variance_pct_x10: int | None = None
    valid_until: str | None = None
    created_at: str | None = None
    created_by: str | None = None
    authorization_decision_ids: list[str] = []
    pricing_rule_results: list[str] = []
    recommendation_id: str | None = None
    rate_refs: list[str] = []
    fx_rate_ref: str | None = None
    pricing_terms_ref: str | None = None
    margin_floor_ref: str | None = None
    trigger_event_ref: str | None = None


class RuleResult(BaseModel):
    rule_id: str
    actual_pct_x10: int
    threshold_pct_x10: int
    result: Literal["within_threshold", "below_floor", "over_threshold"]


class PricingResult(BaseModel):
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
    approver: str
    reason: str | None = None
    decided_at: str


class QuoteDecisionRequest(BaseModel):
    decision: Literal["approved", "rejected", "revise"]
    approver: str
    reason: str | None = None


class CustomerQuoteView(BaseModel):
    quote_id: str
    version: int
    currency: str
    proposed_sell_price_cents: int
    valid_until: str
    route_summary: str


class QuoteDocument(BaseModel):
    document_id: str
    document_type: str
    quote_id: str
    quote_version: int
    generated_at: str
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
    action: str
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
