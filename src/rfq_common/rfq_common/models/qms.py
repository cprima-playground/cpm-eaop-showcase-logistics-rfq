"""QMS -- the quote system of record (systems/qms/, src/mock-qms/). Promoted
here from src/mock-qms/mock_qms/models.py (previously local/design-stage) now
that the shapes are stable enough to share -- these are still design-stage
in the sense that mock-qms's routes are null-op (business/qms-pricing-rules.md,
no store/R1-R6/Cedar wiring yet), but the SCHEMA itself is no longer
provisional; the openapi_extra x-domain-action/x-gap annotations live on
mock-qms's routes (mock_qms/api.py), not here -- this module only owns shape.

x-owner/x-role on fields (via Field(json_schema_extra=...)): who OWNS a
value (system of record), and whether THIS field merely REFERENCES it or
QMS COMPUTES it. Catches accidental duplication before implementation.

Quote vs QuoteVersion: Quote is the lightweight AGGREGATE (identity +
customer/RFQ linkage); QuoteVersion is the immutable, versioned commercial
record -- the split flagged as deferred during early design (a QuoteVersion
stub next to a still-flat Quote would have been a duplicate noun) turned out
to be needed once the full API boundary was specced, and is completed here."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RfqStatus = Literal[
    "draft", "awaiting_information", "sourcing_rates", "pricing",
    "approval_required", "issued", "accepted", "rejected", "expired",
]


class RFQ(BaseModel):
    """RFQ is a CASE (a multi-week engagement -- solicit rates, iterate,
    negotiate), not a document; `status` tracks the case's own progress.
    `accepted`/`rejected`/`expired` are DERIVED from the Quote that closed the
    case (see `derive_rfq_status_from_quote` below) -- never set independently.
    QuoteVersion is the primary fact (business/decisions.md, "SoR boundary:
    RFQ vs Quote"); this is CRM's projection of it, not a second authority."""

    rfq_id: str
    system_of_record: Literal["crm"] = "crm"
    status: RfqStatus = "draft"
    customer_id: str | None = None  # -> masterdata Party (ADR-010) -- reference, never copy
    origin: str | None = None
    destination: str | None = None
    quote_currency: str | None = None
    contracted_lane: str | None = None
    region: str | None = None


QuoteStatus = Literal[
    "draft", "priced", "approval_required", "approved", "published",
    "accepted", "rejected", "revise", "expired", "withdrawn",
]

# Quote.status -> the RfqStatus it implies, for the terminal outcomes only.
# Every other Quote status (draft/priced/approval_required/approved/published/
# revise) has no RFQ-level meaning yet -- the case is still in progress, so
# there is nothing to derive.
_RFQ_STATUS_FROM_TERMINAL_QUOTE_STATUS: dict[str, RfqStatus] = {
    "accepted": "accepted",
    "rejected": "rejected",
    "withdrawn": "rejected",
    "expired": "expired",
}


def derive_rfq_status_from_quote(quote_status: QuoteStatus) -> RfqStatus | None:
    """The code-level resolution of business/decisions.md's "SoR boundary: RFQ
    vs Quote": QuoteVersion.status is the primary fact (QMS-owned); RFQ.status's
    accepted/rejected/expired are a DERIVED projection of it (CRM-owned),
    never written independently. Returns None for every non-terminal Quote
    status -- the case is still open, there is nothing for RFQ to reflect yet.
    A future CRM would call this on every Quote status change, not accept a
    direct write to its own accepted/rejected/expired."""
    return _RFQ_STATUS_FROM_TERMINAL_QUOTE_STATUS.get(quote_status)


def _ref(owner: str) -> dict:
    return {"x-owner": owner, "x-role": "references"}


def _owns() -> dict:
    return {"x-owner": "qms", "x-role": "owns"}


def _computes(owner: str | None = "qms") -> dict:
    return {"x-owner": owner, "x-role": "computes"}


class Quote(BaseModel):
    """The aggregate -- identity + customer/RFQ linkage. Commercial content
    lives on QuoteVersion."""

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


class RuleResult(BaseModel):
    """One of R1-R6's evaluated outcomes (business/qms-pricing-rules.md).
    `not_evaluated` is a real, distinct outcome -- not a placeholder -- for
    a rule whose formula needs data QMS genuinely doesn't have (e.g. R1
    needs a sell price, whose origin is explicitly unresolved; see
    QuoteVersion.proposed_sell_price_eur_cents). A rule that can't run must
    say so, never silently omit itself or report a fabricated pass/fail."""

    rule_id: str
    actual_pct_x10: int | None = None
    threshold_pct_x10: int | None = None
    result: Literal["within_threshold", "below_floor", "over_threshold", "not_evaluated"]
    reason: str | None = Field(default=None, description="Required in practice when result=not_evaluated.")


class QuoteVersion(BaseModel):
    """The human-in-the-loop decision IS `status` here -- not a separate
    workflow record (business/decisions.md, ADR-005). `status`'s terminal
    values feed RFQ.status via `derive_rfq_status_from_quote` -- RFQ never
    sets its own accepted/rejected/expired independently. Immutable once
    written: a "revise" never mutates a QuoteVersion, it supersedes it with
    a new one (D17, quote.supersede)."""

    quote_id: str = Field(json_schema_extra=_owns())
    version: int = Field(json_schema_extra=_owns())
    prior_version: int | None = Field(default=None, json_schema_extra=_owns())
    status: QuoteStatus = Field(
        default="draft", json_schema_extra=_owns(),
        description="The human-in-the-loop decision (approval_required -> approved|rejected|revise) is a status change (decisions.md).",
    )
    currency: str | None = Field(default=None, json_schema_extra=_computes())
    total_cost_eur_cents: int | None = Field(default=None, json_schema_extra=_computes(), description="Null until priced.")
    proposed_sell_price_eur_cents: int | None = Field(
        default=None, json_schema_extra=_computes(owner="qms-pricing-policy"),
        description="Computed by a versioned, explicitly synthetic demo policy (see pricing_policy_ref, mock_qms/pricing_policy.py) -- not a decided commercial formula. No real pricing-terms source exists yet (see business/decisions.md).",
    )
    pricing_policy_ref: str | None = Field(
        default=None, json_schema_extra=_owns(),
        description="Which versioned pricing policy computed proposed_sell_price_eur_cents/margin_pct_x10 -- makes the demo formula auditable/replaceable instead of silent.",
    )
    margin_pct_x10: int | None = Field(default=None, json_schema_extra=_computes(), description="R1 -- (sell - cost) / sell * 1000, evaluated AFTER commercial rounding")
    fx_variance_pct_x10: int | None = Field(default=None, json_schema_extra=_computes(), description="R2, only once compared against a later current rate")
    fx_rate_snapshot: float | None = Field(
        default=None, json_schema_extra=_computes(),
        description="The actual FX rate resolved (via mock-fx /convert) when this version was priced -- captured so a LATER version's R2 can compare against it without a live re-fetch (qms-pricing-rules.md's own rule: 'never a live re-fetch').",
    )
    valid_until: str | None = Field(default=None, json_schema_extra=_owns())
    created_at: str | None = Field(default=None, json_schema_extra=_owns())
    created_by: str | None = Field(default=None, json_schema_extra=_owns(), description="Principal id (agent or human).")
    authorization_decision_ids: list[str] = Field(
        default_factory=list, json_schema_extra=_owns(),
        description="determining_policies from every Cedar call this version triggered -- rfq_common.pdp.AuthorizationDecision.determining_policies.",
    )
    pricing_rule_results: list[RuleResult] = Field(default_factory=list, json_schema_extra=_owns(), description="Every one of R1-R6's evaluated outcomes -- including not_evaluated ones, never silently omitted.")
    recommendation_id: str | None = Field(default=None, json_schema_extra=_ref("agent_state"))
    selected_route_id: str | None = Field(default=None, json_schema_extra=_ref("agent_state"), description="Which TMS route the recommendation resolved to -- needed to actually price against it.")
    rate_refs: list[str] = Field(default_factory=list, json_schema_extra=_ref("rate_management"))
    fx_rate_ref: str | None = Field(default=None, json_schema_extra=_ref("fx_service"))
    pricing_terms_ref: str | None = Field(default=None, json_schema_extra=_ref("qms"))
    margin_floor_ref: str | None = Field(default=None, json_schema_extra=_ref("qms"))
    trigger_event_ref: str | None = Field(default=None, json_schema_extra=_ref("varies"))


class PricingResult(BaseModel):
    """Customer-facing pricing result -- no buy-cost detail (see
    PricingBreakdown for that, D15-gated)."""

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
    """What D18 (buy-rate.disclose) actually governs -- excludes buy rates,
    confidential margins, policy diagnostics, rejected alternatives, internal
    comments."""

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


class CarrierRateView(BaseModel):
    """QMS's disclosure-gated READ PROJECTION of a carrier rate (D14
    rate.read / D15 buy-rate.read) -- distinct from rate.CarrierRate, which
    is mock-rate's own storage/quoting shape. A carrier rate is a
    SUPPLIER-side cost to the forwarder; "sell" is never a property of the
    rate itself, only of the QuoteVersion built from it
    (proposed_sell_price_eur_cents). One cost field, gated by D15 -- no
    second, confusable field."""

    rate_id: str = Field(json_schema_extra=_ref("rate_management"))
    carrier_id: str = Field(json_schema_extra=_ref("masterdata"))
    lane_id: str = Field(json_schema_extra=_ref("rate_management"))
    currency: str = Field(json_schema_extra=_ref("masterdata"))
    cost_cents: int | None = Field(
        default=None, json_schema_extra=_ref("rate_management"),
        description="The carrier's published rate to the forwarder -- present only if buy-rate.read (D15) is also authorized, absent (not zero) otherwise.",
    )
    confidentiality_class: str | None = Field(default=None, json_schema_extra=_ref("rate_management"))
