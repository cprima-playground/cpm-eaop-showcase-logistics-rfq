"""Pydantic entity models — the single source of truth shared by every mock
system's API, CLI, and jsonl fixtures (ADR-006 Decision 1).

Business objects mirror business/domain-model.yaml exactly. Identity models mirror
identity/claims-contract.md (the IdP-agnostic claim contract, same shape as cpm-eaop
InternalPrincipal). These are TWO LAYERS on purpose: business objects are not authz
entities — only authz-projection.yaml decides what crosses into Cedar.

Split into submodules by bounded context (identity/masterdata/fx/rate/tms/
repricing/qms) once this outgrew a single file -- this __init__ re-exports
everything so `from rfq_common.models import X` keeps working regardless of
which submodule X actually lives in. Import from the submodule directly
(e.g. `from rfq_common.models.qms import QuoteVersion`) if you want the
narrower, more self-documenting dependency; both work.
"""

from __future__ import annotations

from .fx import ExchangeRate
from .identity import InternalPrincipal, PrincipalKind
from .masterdata import (
    Commodity,
    Currency,
    DangerousGoodsClass,
    Equipment,
    Incoterm,
    Location,
    Party,
    PartyKind,
    PaymentTerm,
    UnitOfMeasure,
)
from .qms import (
    RFQ,
    AuditEvent,
    BuyCostLineItem,
    CarrierRateView,
    ChangeEvent,
    ChangeRequestInput,
    CreateNextVersionRequest,
    CreateQuoteRequest,
    CustomerQuoteView,
    DecisionRecord,
    ExtendValidityRequest,
    GenerateDocumentRequest,
    PricingBreakdown,
    PricingInputs,
    PricingResult,
    Quote,
    QuoteDecisionRequest,
    QuoteDocument,
    QuoteStatus,
    QuoteVersion,
    RfqStatus,
    RouteRecommendationInput,
    RuleResult,
    TimelineEntry,
    TriggerEventInput,
    ValidityInput,
    WithdrawRequest,
    derive_rfq_status_from_quote,
)
from .rate import CarrierRate
from .repricing import ApprovalTask, RouteOption, RouteRecommendation, TriggeredThreshold
from .tms import (
    Route,
    RouteApplicability,
    RouteAvailability,
    RouteAvailabilityStatus,
    RouteEdge,
    RouteEdgeRef,
    RouteRole,
    TransportMode,
)

__all__ = [
    "RFQ",
    "ApprovalTask",
    "AuditEvent",
    "BuyCostLineItem",
    "CarrierRate",
    "CarrierRateView",
    "ChangeEvent",
    "ChangeRequestInput",
    "Commodity",
    "CreateNextVersionRequest",
    "CreateQuoteRequest",
    "Currency",
    "CustomerQuoteView",
    "DangerousGoodsClass",
    "DecisionRecord",
    "Equipment",
    "ExchangeRate",
    "ExtendValidityRequest",
    "GenerateDocumentRequest",
    "Incoterm",
    "InternalPrincipal",
    "Location",
    "Party",
    "PartyKind",
    "PaymentTerm",
    "PricingBreakdown",
    "PricingInputs",
    "PricingResult",
    "PrincipalKind",
    "Quote",
    "QuoteDecisionRequest",
    "QuoteDocument",
    "QuoteStatus",
    "QuoteVersion",
    "RfqStatus",
    "Route",
    "RouteApplicability",
    "RouteAvailability",
    "RouteAvailabilityStatus",
    "RouteEdge",
    "RouteEdgeRef",
    "RouteOption",
    "RouteRecommendation",
    "RouteRecommendationInput",
    "RouteRole",
    "RuleResult",
    "TimelineEntry",
    "TransportMode",
    "TriggerEventInput",
    "TriggeredThreshold",
    "UnitOfMeasure",
    "ValidityInput",
    "WithdrawRequest",
    "derive_rfq_status_from_quote",
]
