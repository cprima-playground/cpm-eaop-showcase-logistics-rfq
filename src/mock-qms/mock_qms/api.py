"""Quote Management System (QMS) -- every documented path is a REAL FastAPI
route: null-op (501 Not Implemented) since there's no Quote store, R1-R6
pricing math, or Cedar wiring yet (business/qms-pricing-rules.md), but the
route/request/response SHAPES are real, and every x-domain-action/x-gap/
x-consults annotation lives in `openapi_extra` on the operation itself --
migrated from the former interfaces/api/qms.openapi.yaml (deleted: a
hand-authored file duplicating what /openapi.json now generates for real
was a drift risk, not a second source of truth worth keeping). See git
history for that file if you want the pre-migration draft framing.

A REAL DISCOVERY surfaced while drafting this: D16's own wording is "may the
commercial agent create a quote version FROM THIS RECOMMENDATION" -- that
only makes sense once recommendation_id is actually known, which happens via
PUT .../route-recommendation, BEFORE pricing. So D16 belongs at POST
.../price (where recommendation_id is finally in hand and R1-R6 actually
run), not at draft creation. D17 (supersede) stays at POST .../versions --
it doesn't need pricing content, just prior_version/trigger_event/
current_status."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Header, HTTPException

from rfq_common.app import create_app
from rfq_common.theme import load_theme

from rfq_common import models as m

RFQ_ROOT = Path(__file__).resolve().parents[3]

_NOT_IMPLEMENTED = "not implemented -- design-stage contract, see this operation's x-gap in /openapi.json"


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
    @app.get(
        "/quotes", tags=["Quotes"], response_model=list[m.Quote],
        summary="Operational search/list, not generic database search.",
        openapi_extra={"x-domain-action": "quote.read", "x-resource-type": "Quote"},
    )
    def search_quotes(customerId: str | None = None, rfqId: str | None = None,
                       status: str | None = None, validAt: str | None = None):
        _stub()

    @app.post(
        "/quotes", tags=["Quotes"], response_model=m.QuoteVersion, status_code=201,
        summary="Create the quote aggregate and its first version, as a real persisted draft.",
        openapi_extra={
            "x-domain-action": "quote.draft-create",  # NOT D16 -- see x-gap
            "x-resource-type": "Quote",
            "x-consults": [{
                "service": "masterdata", "endpoint": "GET /parties/{code}",
                "purpose": "validate customer_id is a known, active Party (ADR-010) before opening a case against it",
            }],
            "x-gap": (
                "D16 requires recommendation_id (see module docstring) -- not known yet at this "
                "point, since nothing has been composed. This command therefore needs ITS OWN "
                "decision, not D16: something like \"may this principal open a new quote for this "
                "RFQ/customer at all.\" Low-stakes (nothing priced, nothing committed) but still a "
                "real gate -- an agent shouldn't be able to spray empty draft quotes against an RFQ "
                "it has no assignment to. Not modeled in decisions.md yet."
            ),
        },
    )
    def create_quote(body: m.CreateQuoteRequest):
        _stub()

    @app.get(
        "/quotes/{quoteId}", tags=["Quotes"], response_model=m.Quote,
        summary="The quote aggregate (identity + customer/RFQ linkage, not commercial content).",
        openapi_extra={
            "x-domain-action": "quote.read", "x-resource-type": "Quote",
            "x-gap": (
                "No decision governs reading a quote at all today (applies to every operation "
                "marked quote.read in this file) -- distinct from D18, which governs disclosing "
                "buy-cost details specifically. Likely needs field-level filtering (internal vs. "
                "customer-facing view, see GET .../customer-view) rather than one read/no-read boolean."
            ),
        },
    )
    def get_quote(quoteId: str):
        _stub()

    @app.get(
        "/quotes/{quoteId}/versions", tags=["Quotes"], response_model=list[m.QuoteVersion],
        summary="Every version of a quote, oldest first (the full revision history).",
        openapi_extra={"x-domain-action": "quote.read", "x-resource-type": "Quote"},
    )
    def list_quote_versions(quoteId: str):
        _stub()

    @app.post(
        "/quotes/{quoteId}/versions", tags=["Quotes", "Revisions"], response_model=m.QuoteVersion, status_code=201,
        summary="Create the NEXT version (v2+) as a new draft, superseding an existing one.",
        description=(
            "D17 only (not D16 -- this creates an empty-ish draft, no recommendation resolved "
            "yet; D16 applies later at POST .../price for THIS new version). copy_from_prior "
            "controls which composed fields (shipment, commercial-terms, etc.) carry forward vs. "
            "must be re-supplied."
        ),
        openapi_extra={
            "x-domain-action": "quote.supersede",  # -> D17. NOT D16 -- see module docstring.
            "x-resource-type": "Quote",
            "x-authz-context": ["quote_id", "current_version", "current_status", "prior_version", "trigger_event"],
            "x-gap": (
                "Concurrency: two agents racing to supersede the same quote must not both succeed. "
                "expected_latest_version is the precondition (equivalent to If-Match) -- a mismatch "
                "is a lost race (409), not an authorization failure (403); conflating the two would "
                "make a retry loop look forbidden when it's actually just stale."
            ),
        },
    )
    def create_next_quote_version(quoteId: str, body: m.CreateNextVersionRequest, idempotency_key: str = Header(alias="Idempotency-Key")):
        _stub()

    @app.get(
        "/quotes/{quoteId}/versions/{version}", tags=["Quotes"], response_model=m.QuoteVersion,
        summary="Read one specific, immutable quote version (internal representation).",
        openapi_extra={"x-domain-action": "quote.read", "x-resource-type": "Quote"},
    )
    def get_quote_version(quoteId: str, version: int):
        _stub()

    @app.post(
        "/quotes/{quoteId}/versions/{version}/revise", tags=["Revisions"], response_model=m.QuoteVersion,
        summary="Flip THIS version's status to `revise` -- distinct from creating v2+.",
        openapi_extra={"x-gap": (
            "This is the human decision's \"revise\" outcome, expressed as its own endpoint -- but "
            "decisions.md's D6/D19-candidate already covers the decision itself (POST .../decisions "
            "with decision=\"revise\" does the same thing). Two endpoints for one transition is a "
            "real duplication risk this draft is surfacing, not resolving: pick one path before "
            "implementing, most likely folding this into POST .../decisions and removing this endpoint."
        )},
    )
    def mark_version_for_revision(quoteId: str, version: int):
        _stub()

    @app.get(
        "/quotes/{quoteId}/changes", tags=["Audit"], response_model=list[m.ChangeEvent],
        summary="Diffs between consecutive versions of a quote.",
        openapi_extra={
            "x-domain-action": "quote.read", "x-resource-type": "Quote",
            "x-gap": (
                "Overlaps GET .../timeline and .../audit-events below -- three operations proposed "
                "for similar \"what changed\" questions. Kept distinct here (changes = diffs between "
                "versions; timeline = status transitions; audit-events = every authz-relevant action) "
                "but this is a candidate for collapsing once real usage shows which views are actually needed."
            ),
        },
    )
    def list_quote_changes(quoteId: str):
        _stub()

    @app.get(
        "/quotes/{quoteId}/versions/{version}/changes", tags=["Audit"], response_model=m.ChangeEvent,
        summary="What changed to produce THIS version from its prior_version.",
        openapi_extra={"x-domain-action": "quote.read", "x-resource-type": "Quote"},
    )
    def list_version_changes(quoteId: str, version: int):
        _stub()

    @app.get(
        "/quotes/{quoteId}/timeline", tags=["Audit"], response_model=list[m.TimelineEntry],
        summary="Status transitions across every version, in order.",
        openapi_extra={"x-domain-action": "quote.read", "x-resource-type": "Quote"},
    )
    def get_quote_timeline(quoteId: str):
        _stub()

    @app.get(
        "/quotes/{quoteId}/audit-events", tags=["Audit"], response_model=list[m.AuditEvent],
        summary="Every authorization-relevant action taken against this quote.",
        openapi_extra={
            "x-domain-action": "quote.read", "x-resource-type": "Quote",
            "x-gap": "Probably needs its own quote.audit-read, narrower than general read.",
        },
    )
    def list_quote_audit_events(quoteId: str):
        _stub()

    @app.get(
        "/quotes/requiring-action", tags=["Quotes"], response_model=list[m.Quote],
        summary="Operational view -- quotes sitting in approval_required, or expiring soon.",
        openapi_extra={"x-domain-action": "quote.read", "x-resource-type": "Quote"},
    )
    def list_quotes_requiring_action():
        _stub()

    @app.get(
        "/quotes/expiring", tags=["Validity"], response_model=list[m.Quote],
        summary="Quotes approaching valid_until.",
        openapi_extra={"x-domain-action": "quote.read", "x-resource-type": "Quote"},
    )
    def list_expiring_quotes(withinDays: int = 7):
        _stub()

    # ------------------------------------------------------ Draft Composition
    # x-gap (applies to every operation in this section): no decision in
    # decisions.md governs composing a draft's fields. All seven likely fold
    # under one quote.compose-draft action -- or split per component if a
    # scoping distinction ever matters (e.g. an agent that may select a route
    # but not set commercial terms). Not designed here; several bodies below
    # are placeholders for fields that are genuinely undesigned, not just
    # under-documented.
    _COMPOSE_DRAFT_EXTRA = {"x-domain-action": "quote.compose-draft", "x-resource-type": "Quote"}
    _UNDESIGNED_GAP = {**_COMPOSE_DRAFT_EXTRA, "x-gap": "Field shape entirely undesigned -- placeholder object, not a real contract yet."}

    @app.put(
        "/quotes/{quoteId}/versions/{version}/shipment", tags=["Draft Composition"], response_model=m.QuoteVersion,
        summary="Shipment requirements for this draft (cargo, weight, equipment, dates).",
        openapi_extra=_UNDESIGNED_GAP,
    )
    def put_quote_shipment(quoteId: str, version: int, body: dict):
        _stub()

    @app.put(
        "/quotes/{quoteId}/versions/{version}/route-recommendation", tags=["Draft Composition"], response_model=m.QuoteVersion,
        summary="Attach the RouteRecommendation this draft is being priced against.",
        description="This is what makes recommendation_id known -- the precondition for D16 to later apply at POST .../price.",
        openapi_extra=_COMPOSE_DRAFT_EXTRA,
    )
    def put_quote_route_recommendation(quoteId: str, version: int, body: m.RouteRecommendationInput):
        _stub()

    @app.put(
        "/quotes/{quoteId}/versions/{version}/commercial-terms", tags=["Draft Composition"], response_model=m.QuoteVersion,
        summary="Commercial terms for this draft (payment terms, incoterm, special conditions).",
        openapi_extra=_UNDESIGNED_GAP,
    )
    def put_quote_commercial_terms(quoteId: str, version: int, body: dict):
        _stub()

    @app.put(
        "/quotes/{quoteId}/versions/{version}/pricing-inputs", tags=["Draft Composition"], response_model=m.QuoteVersion,
        summary="Attach the references R1-R6 will be evaluated against.",
        openapi_extra=_COMPOSE_DRAFT_EXTRA,
    )
    def put_quote_pricing_inputs(quoteId: str, version: int, body: m.PricingInputs):
        _stub()

    @app.put(
        "/quotes/{quoteId}/versions/{version}/validity", tags=["Draft Composition", "Validity"], response_model=m.QuoteVersion,
        summary="Set or change valid_until for this draft.",
        openapi_extra=_COMPOSE_DRAFT_EXTRA,
    )
    def put_quote_validity(quoteId: str, version: int, body: m.ValidityInput):
        _stub()

    @app.put(
        "/quotes/{quoteId}/versions/{version}/assumptions", tags=["Draft Composition"], response_model=m.QuoteVersion,
        summary="Assumptions this quote's pricing depends on (e.g. weight bracket, expected capacity).",
        openapi_extra=_UNDESIGNED_GAP,
    )
    def put_quote_assumptions(quoteId: str, version: int, body: dict):
        _stub()

    @app.put(
        "/quotes/{quoteId}/versions/{version}/exclusions", tags=["Draft Composition"], response_model=m.QuoteVersion,
        summary="What this quote explicitly does NOT cover.",
        openapi_extra=_UNDESIGNED_GAP,
    )
    def put_quote_exclusions(quoteId: str, version: int, body: dict):
        _stub()

    # ---------------------------------------------------------------- Pricing
    @app.post(
        "/quotes/{quoteId}/versions/{version}/price", tags=["Pricing"], response_model=m.PricingResult,
        summary="draft -> priced. THE atomic command -- resolve, compute R1-R6, authorize D16, write.",
        description=(
            "Requires route-recommendation and pricing-inputs to already be composed (400 if not). "
            "Atomic: resolve referenced facts -> validate freshness/applicability -> calculate "
            "charges -> normalize currencies -> total cost -> derive sell price -> margin -> "
            "evaluate R1-R6 -> build Cedar context -> evaluate D16 -> write. On deny, the draft is "
            "untouched (still draft, not partially priced)."
        ),
        openapi_extra={
            "x-domain-action": "quote.create-version",  # -> D16. This IS where D16 belongs now.
            "x-resource-type": "Quote",
            "x-authz-context": ["rfq_id", "recommendation_id", "fx_rate_ref", "pricing_terms_ref", "margin_floor_ref"],
            "x-consults": [
                {"service": "fx", "endpoint": "GET /exchange-rates/{base}/{quote}",
                 "purpose": "resolve fx_rate_ref to an actual rate for currency normalization (R2)"},
                {"service": "masterdata", "endpoint": "GET /currencies/{code}",
                 "purpose": "minor_unit for correctly rounding total_cost/proposed_sell_price (ADR-010 -- same rounding authority mock-fx's own /convert uses, never duplicated here)"},
            ],
            "x-gap": (
                "Sell-price origin (still unresolved): R1 is (sell - cost)/sell, but nothing here "
                "says who computes the sell price -- unless pricing_terms_ref fully determines it. "
                "See QuoteVersion.proposed_sell_price_eur_cents' x-owner: null."
            ),
        },
    )
    def price_quote_version(quoteId: str, version: int):
        _stub()

    @app.get(
        "/quotes/{quoteId}/versions/{version}/pricing", tags=["Pricing"], response_model=m.PricingResult,
        summary="The customer-facing pricing result (no buy-cost detail).",
        openapi_extra={"x-domain-action": "quote.read", "x-resource-type": "Quote"},
    )
    def get_quote_pricing(quoteId: str, version: int):
        _stub()

    @app.get(
        "/quotes/{quoteId}/versions/{version}/pricing-breakdown", tags=["Pricing"], response_model=m.PricingBreakdown,
        summary="Internal breakdown INCLUDING carrier buy costs -- gated separately from the pricing summary.",
        openapi_extra={"x-domain-action": "buy-rate.read", "x-resource-type": "Quote"},  # -> D15, same split as /carrier-rates
    )
    def get_quote_pricing_breakdown(quoteId: str, version: int):
        _stub()

    # -------------------------------------------------------------- Approvals
    @app.post(
        "/quotes/{quoteId}/versions/{version}/submit-for-approval", tags=["Approvals"], response_model=m.QuoteVersion,
        summary="priced -> approval_required (or a D4b forbid, if FX moved and this is an automatic replacement).",
        description=(
            "D16 (pricing) and this action are separate decisions: pricing never implies automatic "
            "submission. D5 (below floor) and D12 (baseline, FX quiet + margin OK) both permit "
            "*submission*, both land on approval_required -- they differ in whether submission is "
            "currently authorized (and which obligation rides along), not in destination state. "
            "Only D4b changes the outcome shape, by forbidding the attempt entirely (403)."
        ),
        openapi_extra={
            "x-domain-action": "quote.submit-for-approval",  # -> D4 / D5 / D12
            "x-resource-type": "Quote",
            "x-authz-context": ["fx_variance_pct_x10", "margin_pct_x10"],
        },
    )
    def submit_quote_version_for_approval(quoteId: str, version: int):
        _stub()

    @app.get(
        "/quotes/{quoteId}/versions/{version}/approval-requirements", tags=["Approvals"], response_model=list[dict],
        summary="What triggered thresholds/obligations apply to this version, before deciding.",
        openapi_extra={
            "x-domain-action": "quote.read", "x-resource-type": "Quote",
            "x-gap": "Shape not designed -- likely TriggeredThreshold[] (rfq_common.models, already exists) plus which approver_role each obligation names (authorization/obligations.yaml).",
        },
    )
    def get_approval_requirements(quoteId: str, version: int):
        _stub()

    @app.get(
        "/quotes/{quoteId}/versions/{version}/decisions", tags=["Approvals"], response_model=list[m.DecisionRecord],
        summary="Approval history for this version -- supporting evidence, not the authoritative signal.",
        openapi_extra={"x-domain-action": "quote.read", "x-resource-type": "Quote"},
    )
    def list_quote_decisions(quoteId: str, version: int):
        _stub()

    @app.post(
        "/quotes/{quoteId}/versions/{version}/decisions", tags=["Approvals"], response_model=m.QuoteVersion,
        summary="The human-in-the-loop decision -- approval_required -> approved | rejected | revise.",
        description=(
            "The status transition IS the decision, per decisions.md's \"Human-in-the-loop = a "
            "status change\" principle. This endpoint is real and will be called; it currently runs "
            "without a dedicated Cedar gate of its own (see x-gap)."
        ),
        openapi_extra={
            "x-domain-action": None,  # NOT YET MODELED -- see x-gap
            "x-resource-type": "Quote",
            "x-gap": (
                "D6 only covers \"may a commercial manager approve a ROUTE DEVIATION within their "
                "limit\" -- not rejecting, requesting revision, approving without a route deviation, "
                "or acting on other triggered thresholds (margin floor, cost variance, transit "
                "variance). A future D19 should start from \"may this human record this decision on "
                "this quote version, under the approval requirements that applied when it entered "
                "approval_required\" -- not from mirroring this endpoint's name."
            ),
        },
    )
    def decide_quote_version(quoteId: str, version: int, body: m.QuoteDecisionRequest):
        _stub()

    # ------------------------------------------------------------ Publication
    @app.post(
        "/quotes/{quoteId}/versions/{version}/publish", tags=["Publication"], response_model=m.QuoteVersion,
        summary="approved -> published. NOT the same as approval -- this is the act of making it customer-visible.",
        openapi_extra={
            "x-domain-action": "quote.publish", "x-resource-type": "Quote",
            "x-gap": (
                "No decision governs this yet. Deliberately distinct from D18 (buy-rate.disclose, "
                "which gates WHAT content is visible) -- this gates the ACT of publishing at all. "
                "Also distinct from quote.submit-for-approval: approval and publication conflating "
                "into one status (\"approved\" meaning both \"a human signed off\" and \"the customer "
                "has it\") was the exact ambiguity this split resolves."
            ),
        },
    )
    def publish_quote_version(quoteId: str, version: int):
        _stub()

    @app.post(
        "/quotes/{quoteId}/versions/{version}/withdraw", tags=["Publication"], response_model=m.QuoteVersion,
        summary="published -> withdrawn (we pull it back before the customer responds).",
        openapi_extra={
            "x-domain-action": "quote.withdraw", "x-resource-type": "Quote",
            "x-gap": "No decision governs this yet -- who may withdraw, and does it require the same approval authority that published it?",
        },
    )
    def withdraw_quote_version(quoteId: str, version: int, body: m.WithdrawRequest | None = None):
        _stub()

    @app.get(
        "/quotes/{quoteId}/versions/{version}/customer-view", tags=["Publication", "Customer Response"], response_model=m.CustomerQuoteView,
        summary="The filtered, customer-facing representation. Makes D18 concrete.",
        description=(
            "Excludes buy rates, internal margins where confidential, internal policy diagnostics, "
            "rejected alternatives, and internal comments. This is the response shape D18 actually "
            "governs -- every other D18 mention in this file is really pointing back at this."
        ),
        openapi_extra={"x-domain-action": "buy-rate.disclose", "x-resource-type": "Quote"},  # -> D18
    )
    def get_quote_customer_view(quoteId: str, version: int):
        _stub()

    # -------------------------------------------------------------- Documents
    @app.get(
        "/quotes/{quoteId}/versions/{version}/documents", tags=["Documents"], response_model=list[m.QuoteDocument],
        summary="Generated documents for this immutable version.",
        openapi_extra={"x-domain-action": "quote.read", "x-resource-type": "Quote"},
    )
    def list_quote_documents(quoteId: str, version: int):
        _stub()

    @app.post(
        "/quotes/{quoteId}/versions/{version}/documents", tags=["Documents"], response_model=m.QuoteDocument, status_code=201,
        summary="Generate a document from this exact version -- must not silently change if pricing config changes later.",
        openapi_extra={
            "x-domain-action": "quote.document.generate", "x-resource-type": "Quote",
            "x-gap": "No decision governs this yet. Also undesigned: document TYPE (proposal PDF vs. formal offer vs. internal summary) and template ownership.",
        },
    )
    def generate_quote_document(quoteId: str, version: int, body: m.GenerateDocumentRequest | None = None):
        _stub()

    @app.get(
        "/quotes/{quoteId}/versions/{version}/documents/{documentId}", tags=["Documents"], response_model=m.QuoteDocument,
        summary="Fetch a specific generated document.",
        openapi_extra={"x-domain-action": "quote.read", "x-resource-type": "Quote"},
    )
    def get_quote_document(quoteId: str, version: int, documentId: str):
        _stub()

    # ------------------------------------------------------ Customer Response
    # x-gap (applies to all three below): these may initially be internal
    # integration endpoints called by CRM or a customer portal, not
    # customer-facing directly. They must not mutate commercial content --
    # accept/reject just transition status; request-change creates a business
    # event and eventually a new version via the normal supersede path, never
    # a direct field edit.
    _PRINCIPAL_KIND_GAP = "No decision governs this -- principal is likely 'CRM system' or 'Customer', a new principal kind not yet in identity/claims-contract.md."

    @app.post(
        "/quotes/{quoteId}/versions/{version}/accept", tags=["Customer Response"], response_model=m.QuoteVersion,
        summary="published -> accepted (customer accepted, relayed by CRM/portal).",
        openapi_extra={"x-domain-action": "quote.accept", "x-resource-type": "Quote", "x-gap": _PRINCIPAL_KIND_GAP},
    )
    def accept_quote_version(quoteId: str, version: int):
        _stub()

    @app.post(
        "/quotes/{quoteId}/versions/{version}/reject", tags=["Customer Response"], response_model=m.QuoteVersion,
        summary="published -> rejected (customer declined).",
        openapi_extra={"x-domain-action": "quote.reject", "x-resource-type": "Quote", "x-gap": "Same principal-kind gap as accept."},
    )
    def reject_quote_version(quoteId: str, version: int, body: m.ChangeRequestInput | None = None):
        _stub()

    @app.post(
        "/quotes/{quoteId}/versions/{version}/request-change", tags=["Customer Response"], status_code=202,
        summary="Customer wants something different -- creates a business event, does NOT edit this version.",
        description=(
            "Never mutates commercial content directly. Produces a trigger event that a subsequent "
            "POST .../versions (supersede, D17) consumes -- same shape as an FX or "
            "route-unavailable trigger, just customer-originated."
        ),
        openapi_extra={"x-domain-action": "quote.request-change", "x-resource-type": "Quote"},
    )
    def request_quote_change(quoteId: str, version: int, body: m.ChangeRequestInput | None = None) -> dict:
        _stub()

    # ----------------------------------------------------------------- Validity
    @app.post(
        "/quotes/{quoteId}/versions/{version}/expire", tags=["Validity"], response_model=m.QuoteVersion,
        summary="Force expiry before valid_until (vs. the passive expiry a scheduler would apply).",
        openapi_extra={
            "x-domain-action": "quote.expire", "x-resource-type": "Quote",
            "x-gap": "No decision governs manual expiry, and passive (valid_until reached) expiry isn't designed at all -- likely a scheduled job, not this endpoint, but that job's authority is undefined too.",
        },
    )
    def expire_quote_version(quoteId: str, version: int):
        _stub()

    @app.post(
        "/quotes/{quoteId}/versions/{version}/extend-validity", tags=["Validity"], response_model=m.QuoteVersion,
        summary="Push valid_until out -- but if rates/capacity/FX assumptions changed, this should force a new version instead.",
        openapi_extra={
            "x-domain-action": "quote.extend-validity", "x-resource-type": "Quote",
            "x-gap": (
                "This command should probably REFUSE (400, \"supersede instead\") if fx_rate_ref/"
                "rate_refs are stale relative to now, rather than silently extending a quote whose "
                "pricing assumptions no longer hold. Staleness check not designed."
            ),
        },
    )
    def extend_quote_validity(quoteId: str, version: int, body: m.ExtendValidityRequest):
        _stub()

    # --------------------------------------------------- Pricing Configuration
    # Read-only -- writes (POST /pricing-terms, POST /margin-floors)
    # deliberately excluded: effective-dating and authorization for CHANGING
    # commercial config must be specified before allowing writes.
    @app.get(
        "/customers/{customerId}/pricing-terms", tags=["Pricing Configuration"], response_model=dict,
        summary="Current effective pricing terms for a customer.",
        openapi_extra={"x-domain-action": "pricing-terms.read", "x-resource-type": "CustomerPricingTerms", "x-gap": "Not in decisions.md."},
    )
    def get_customer_pricing_terms(customerId: str):
        _stub()

    @app.get(
        "/customers/{customerId}/margin-floor", tags=["Pricing Configuration"], response_model=dict,
        summary="Current effective margin floor for a customer.",
        openapi_extra={"x-domain-action": "margin-floor.read", "x-resource-type": "MarginFloor", "x-gap": "Not in decisions.md."},
    )
    def get_customer_margin_floor(customerId: str):
        _stub()

    @app.get(
        "/pricing-terms/{pricingTermsId}", tags=["Pricing Configuration"], response_model=dict,
        summary="One pricing-terms revision by id (for margin_floor_ref/pricing_terms_ref resolution).",
        openapi_extra={"x-domain-action": "pricing-terms.read", "x-resource-type": "CustomerPricingTerms"},
    )
    def get_pricing_terms_by_id(pricingTermsId: str):
        _stub()

    @app.get(
        "/margin-floors/{marginFloorId}", tags=["Pricing Configuration"], response_model=dict,
        summary="One margin-floor revision by id.",
        openapi_extra={"x-domain-action": "margin-floor.read", "x-resource-type": "MarginFloor"},
    )
    def get_margin_floor_by_id(marginFloorId: str):
        _stub()

    # ------------------------------------------------------- legacy narrow-slice reads
    @app.get(
        "/rfqs/{rfqId}", tags=["Quotes"], response_model=m.RFQ,
        summary="Read an RFQ -- the pipeline's starting input.",
        openapi_extra={
            "x-domain-action": "rfq.read",  # -> D13
            "x-resource-type": "RFQ",
            "x-authz-context": ["customer_id", "region", "assignment", "rfq_status"],
        },
    )
    def get_rfq(rfqId: str):
        _stub()

    @app.get(
        "/carrier-rates", tags=["Pricing Configuration"], response_model=list[m.CarrierRateView],
        summary="Carrier rates for a lane, scoped to what the caller is entitled to see.",
        description=(
            "rate.read returns identity/lane/currency; cost_cents (the carrier's actual charge) "
            "additionally requires buy-rate.read (D15) -- same endpoint, field simply absent if "
            "D15 doesn't also permit."
        ),
        openapi_extra={
            "x-domain-action": "rate.read",  # -> D14
            "x-resource-type": "CarrierRate",
            "x-authz-context": ["customer_id", "contract_scope", "rate_type"],
            "x-consults": [{"service": "masterdata", "endpoint": "GET /currencies/{code}", "purpose": "validate the rate's currency (ADR-010)"}],
        },
    )
    def list_carrier_rates(laneId: str, customerId: str | None = None):
        _stub()

    return app


app = build_app()
