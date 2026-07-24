"""Quote Management System (QMS) -- every path from interfaces/api/qms.openapi.yaml
is a REAL FastAPI route now (not a static-YAML override of app.openapi): each
one is null-op (501 Not Implemented) since there's no Quote store, R1-R6
pricing math, or Cedar wiring yet (business/qms-pricing-rules.md) -- but the
route/request/response SHAPES are real, so /openapi.json is genuinely
FastAPI-generated from typed Pydantic models, the same discipline mock-fx and
mock-masterdata now follow, not a hand-authored file swapped in wholesale."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException

from rfq_common.app import create_app
from rfq_common.theme import load_theme

from . import models as m

RFQ_ROOT = Path(__file__).resolve().parents[3]

_NOT_IMPLEMENTED = "not implemented -- design-stage contract, see interfaces/api/qms.openapi.yaml"


def _stub():
    raise HTTPException(status_code=501, detail=_NOT_IMPLEMENTED)


def build_app() -> FastAPI:
    theme_pack = None
    try:
        theme_pack = load_theme(themes_dir=RFQ_ROOT / "themes")
    except Exception:
        pass  # theme is cosmetic; never block boot on it

    app = create_app("Quote Management System (QMS)", system_id="qms", theme_pack=theme_pack)

    # --------------------------------------------------------------- Quotes
    @app.get("/quotes", tags=["Quotes"], response_model=list[m.Quote])
    def search_quotes(customerId: str | None = None, rfqId: str | None = None,
                       status: str | None = None, validAt: str | None = None):
        _stub()

    @app.post("/quotes", tags=["Quotes"], response_model=m.QuoteVersion, status_code=201)
    def create_quote(body: m.CreateQuoteRequest):
        _stub()

    @app.get("/quotes/{quoteId}", tags=["Quotes"], response_model=m.Quote)
    def get_quote(quoteId: str):
        _stub()

    @app.get("/quotes/{quoteId}/versions", tags=["Quotes"], response_model=list[m.QuoteVersion])
    def list_quote_versions(quoteId: str):
        _stub()

    @app.post("/quotes/{quoteId}/versions", tags=["Quotes", "Revisions"], response_model=m.QuoteVersion, status_code=201)
    def create_next_quote_version(quoteId: str, body: m.CreateNextVersionRequest):
        _stub()

    @app.get("/quotes/{quoteId}/versions/{version}", tags=["Quotes"], response_model=m.QuoteVersion)
    def get_quote_version(quoteId: str, version: int):
        _stub()

    @app.post("/quotes/{quoteId}/versions/{version}/revise", tags=["Revisions"], response_model=m.QuoteVersion)
    def mark_version_for_revision(quoteId: str, version: int):
        _stub()

    @app.get("/quotes/{quoteId}/changes", tags=["Audit"], response_model=list[m.ChangeEvent])
    def list_quote_changes(quoteId: str):
        _stub()

    @app.get("/quotes/{quoteId}/versions/{version}/changes", tags=["Audit"], response_model=m.ChangeEvent)
    def list_version_changes(quoteId: str, version: int):
        _stub()

    @app.get("/quotes/{quoteId}/timeline", tags=["Audit"], response_model=list[m.TimelineEntry])
    def get_quote_timeline(quoteId: str):
        _stub()

    @app.get("/quotes/{quoteId}/audit-events", tags=["Audit"], response_model=list[m.AuditEvent])
    def list_quote_audit_events(quoteId: str):
        _stub()

    @app.get("/quotes/requiring-action", tags=["Quotes"], response_model=list[m.Quote])
    def list_quotes_requiring_action():
        _stub()

    @app.get("/quotes/expiring", tags=["Validity"], response_model=list[m.Quote])
    def list_expiring_quotes(withinDays: int = 7):
        _stub()

    # ------------------------------------------------------ Draft Composition
    @app.put("/quotes/{quoteId}/versions/{version}/shipment", tags=["Draft Composition"], response_model=m.QuoteVersion)
    def put_quote_shipment(quoteId: str, version: int, body: dict):
        _stub()

    @app.put("/quotes/{quoteId}/versions/{version}/route-recommendation", tags=["Draft Composition"], response_model=m.QuoteVersion)
    def put_quote_route_recommendation(quoteId: str, version: int, body: dict):
        _stub()

    @app.put("/quotes/{quoteId}/versions/{version}/commercial-terms", tags=["Draft Composition"], response_model=m.QuoteVersion)
    def put_quote_commercial_terms(quoteId: str, version: int, body: dict):
        _stub()

    @app.put("/quotes/{quoteId}/versions/{version}/pricing-inputs", tags=["Draft Composition"], response_model=m.QuoteVersion)
    def put_quote_pricing_inputs(quoteId: str, version: int, body: dict):
        _stub()

    @app.put("/quotes/{quoteId}/versions/{version}/validity", tags=["Draft Composition", "Validity"], response_model=m.QuoteVersion)
    def put_quote_validity(quoteId: str, version: int, body: dict):
        _stub()

    @app.put("/quotes/{quoteId}/versions/{version}/assumptions", tags=["Draft Composition"], response_model=m.QuoteVersion)
    def put_quote_assumptions(quoteId: str, version: int, body: dict):
        _stub()

    @app.put("/quotes/{quoteId}/versions/{version}/exclusions", tags=["Draft Composition"], response_model=m.QuoteVersion)
    def put_quote_exclusions(quoteId: str, version: int, body: dict):
        _stub()

    # ---------------------------------------------------------------- Pricing
    @app.post("/quotes/{quoteId}/versions/{version}/price", tags=["Pricing"], response_model=m.PricingResult)
    def price_quote_version(quoteId: str, version: int):
        _stub()

    @app.get("/quotes/{quoteId}/versions/{version}/pricing", tags=["Pricing"], response_model=m.PricingResult)
    def get_quote_pricing(quoteId: str, version: int):
        _stub()

    @app.get("/quotes/{quoteId}/versions/{version}/pricing-breakdown", tags=["Pricing"], response_model=m.PricingBreakdown)
    def get_quote_pricing_breakdown(quoteId: str, version: int):
        _stub()

    # -------------------------------------------------------------- Approvals
    @app.post("/quotes/{quoteId}/versions/{version}/submit-for-approval", tags=["Approvals"], response_model=m.QuoteVersion)
    def submit_quote_version_for_approval(quoteId: str, version: int):
        _stub()

    @app.get("/quotes/{quoteId}/versions/{version}/approval-requirements", tags=["Approvals"], response_model=list[dict])
    def get_approval_requirements(quoteId: str, version: int):
        _stub()

    @app.get("/quotes/{quoteId}/versions/{version}/decisions", tags=["Approvals"], response_model=list[m.DecisionRecord])
    def list_quote_decisions(quoteId: str, version: int):
        _stub()

    @app.post("/quotes/{quoteId}/versions/{version}/decisions", tags=["Approvals"], response_model=m.QuoteVersion)
    def decide_quote_version(quoteId: str, version: int, body: m.QuoteDecisionRequest):
        _stub()

    # ------------------------------------------------------------ Publication
    @app.post("/quotes/{quoteId}/versions/{version}/publish", tags=["Publication"], response_model=m.QuoteVersion)
    def publish_quote_version(quoteId: str, version: int):
        _stub()

    @app.post("/quotes/{quoteId}/versions/{version}/withdraw", tags=["Publication"], response_model=m.QuoteVersion)
    def withdraw_quote_version(quoteId: str, version: int, body: m.WithdrawRequest | None = None):
        _stub()

    @app.get("/quotes/{quoteId}/versions/{version}/customer-view", tags=["Publication", "Customer Response"], response_model=m.CustomerQuoteView)
    def get_quote_customer_view(quoteId: str, version: int):
        _stub()

    # -------------------------------------------------------------- Documents
    @app.get("/quotes/{quoteId}/versions/{version}/documents", tags=["Documents"], response_model=list[m.QuoteDocument])
    def list_quote_documents(quoteId: str, version: int):
        _stub()

    @app.post("/quotes/{quoteId}/versions/{version}/documents", tags=["Documents"], response_model=m.QuoteDocument, status_code=201)
    def generate_quote_document(quoteId: str, version: int, body: m.GenerateDocumentRequest | None = None):
        _stub()

    @app.get("/quotes/{quoteId}/versions/{version}/documents/{documentId}", tags=["Documents"], response_model=m.QuoteDocument)
    def get_quote_document(quoteId: str, version: int, documentId: str):
        _stub()

    # ------------------------------------------------------ Customer Response
    @app.post("/quotes/{quoteId}/versions/{version}/accept", tags=["Customer Response"], response_model=m.QuoteVersion)
    def accept_quote_version(quoteId: str, version: int):
        _stub()

    @app.post("/quotes/{quoteId}/versions/{version}/reject", tags=["Customer Response"], response_model=m.QuoteVersion)
    def reject_quote_version(quoteId: str, version: int, body: m.ChangeRequestInput | None = None):
        _stub()

    @app.post("/quotes/{quoteId}/versions/{version}/request-change", tags=["Customer Response"], status_code=202)
    def request_quote_change(quoteId: str, version: int, body: m.ChangeRequestInput | None = None) -> dict:
        _stub()

    # ----------------------------------------------------------------- Validity
    @app.post("/quotes/{quoteId}/versions/{version}/expire", tags=["Validity"], response_model=m.QuoteVersion)
    def expire_quote_version(quoteId: str, version: int):
        _stub()

    @app.post("/quotes/{quoteId}/versions/{version}/extend-validity", tags=["Validity"], response_model=m.QuoteVersion)
    def extend_quote_validity(quoteId: str, version: int, body: m.ExtendValidityRequest):
        _stub()

    # --------------------------------------------------- Pricing Configuration
    @app.get("/customers/{customerId}/pricing-terms", tags=["Pricing Configuration"], response_model=dict)
    def get_customer_pricing_terms(customerId: str):
        _stub()

    @app.get("/customers/{customerId}/margin-floor", tags=["Pricing Configuration"], response_model=dict)
    def get_customer_margin_floor(customerId: str):
        _stub()

    @app.get("/pricing-terms/{pricingTermsId}", tags=["Pricing Configuration"], response_model=dict)
    def get_pricing_terms_by_id(pricingTermsId: str):
        _stub()

    @app.get("/margin-floors/{marginFloorId}", tags=["Pricing Configuration"], response_model=dict)
    def get_margin_floor_by_id(marginFloorId: str):
        _stub()

    # ------------------------------------------------------- legacy narrow-slice reads
    @app.get("/rfqs/{rfqId}", tags=["Quotes"], response_model=m.RFQ)
    def get_rfq(rfqId: str):
        _stub()

    @app.get("/carrier-rates", tags=["Pricing Configuration"], response_model=list[m.CarrierRate])
    def list_carrier_rates(laneId: str, customerId: str | None = None):
        _stub()

    return app


app = build_app()
