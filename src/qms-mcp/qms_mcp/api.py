"""qms-mcp -- M6's third real MCP slice, and the first with RESOURCE/
STATE-SENSITIVE authorization (not a blanket "active internal agent"
check like D10/D11/rate-mcp's own policy). Three tools:

  calculate_quote_price  -> quote-price.calculate
      Cedar gate: the LIVE QuoteVersion.status (fetched from mock-qms per
      request, supplied via additional_entities -- never pre-loaded into
      cedar-agent's persisted store) must be "draft". Mirrors mock-qms's
      own real precondition (store.py's price_version: draft-only).

  evaluate_quote_variance -> quote-variance.evaluate
      Cedar gate: the LIVE QuoteVersion.status must NOT be "draft" -- FX
      variance can only be evaluated once something has actually been
      priced (mock-qms only computes R2 against a prior priced snapshot).

  normalize_route_cost -> route-cost.normalize
      Cedar gate: D2 (authorization/policies.cedar, already decided,
      pre-existing) -- context.fx_age_seconds <= 900, computed from
      mock-fx's REAL observed_at on the requested currency pair, not
      supplied by the caller.

All three: authenticate caller -> fetch the live fact this decision
actually needs -> Cedar decides -> mock-qms/mock-fx is only called on
permit, using qms-mcp's own workload credential (never the caller's).
"""

from __future__ import annotations

import time
from pathlib import Path

import httpx
from fastapi import FastAPI, Header, HTTPException
from opentelemetry import metrics, trace
from pydantic import BaseModel

from rfq_common.app import create_app
from rfq_common.clock import age_seconds
from rfq_common.descriptor import DependencyInfo, build_descriptor, new_instance_id
from rfq_common.mcp_auth import AuthenticationError, authenticate_request, build_token_verifier
from rfq_common.pdp import PolicyBundle
from rfq_common.pdp.entities import entity, ref
from rfq_common.pep import AuthorizationDenied, ObligationEnforcementError, authorize_and_enforce
from rfq_common.settings import ServiceSettings

from . import settings

RFQ_ROOT = settings.RFQ_ROOT

IMPLEMENTED_TOOLS = ["calculate_quote_price", "evaluate_quote_variance", "normalize_route_cost"]

_tracer = trace.get_tracer("qms_mcp")
_meter = metrics.get_meter("qms_mcp")
_tool_duration = _meter.create_histogram("mcp.tool.duration", unit="s", description="MCP tool call latency")
_tool_calls = _meter.create_counter("mcp.tool.calls", description="MCP tool invocations")


class QuoteVersionRequest(BaseModel):
    quote_id: str
    version: int


class NormalizeRouteCostRequest(BaseModel):
    route_id: str
    amount: str
    from_currency: str
    to_currency: str


def build_app(
    *,
    root: Path | None = None,
    cedar_url: str | None = None,
    bundle: PolicyBundle | None = None,
    qms_client: httpx.Client | None = None,
    fx_client: httpx.Client | None = None,
    introspection_client_secret: str | None = None,
    qms_api_key: str | None = None,
    fx_api_key: str | None = None,
    public_url: str | None = None,
    instance_id: str | None = None,
) -> FastAPI:
    root = root or RFQ_ROOT
    cedar_url = cedar_url or settings.cedar_url()
    bundle = bundle or PolicyBundle.from_path(root / "authorization" / "policies.cedar")
    # 20s, not 5s -- POST .../price's real pipeline (mock-qms -> mock-rate
    # + mock-fx, sequentially) genuinely takes ~6s end to end; a 5s
    # timeout here fired spuriously (found running this milestone's own
    # real-stack tests against the live services, not a hypothetical).
    qms_client = qms_client or httpx.Client(base_url=settings.qms_base_url(), timeout=20.0)
    fx_client = fx_client or httpx.Client(base_url=settings.fx_base_url(), timeout=5.0)
    introspection_client_secret = introspection_client_secret or settings.introspection_client_secret()
    token_verifier = build_token_verifier(
        mode="introspection", oidc_issuer_url=settings.oidc_issuer_url(),
        introspection_endpoint=settings.introspection_endpoint(),
        client_id=settings.KEYCLOAK_CLIENT_ID, client_secret=introspection_client_secret,
    )
    qms_api_key = qms_api_key or settings.qms_api_key()
    fx_api_key = fx_api_key or settings.fx_api_key()
    public_url = public_url or ServiceSettings.from_env(default_port=8106).public_url
    instance_id = instance_id or new_instance_id()

    app = create_app("QMS MCP", system_id="qms")

    @app.exception_handler(AuthenticationError)
    def _auth_error(request, exc: AuthenticationError):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401, content={"detail": str(exc)})

    @app.exception_handler(AuthorizationDenied)
    def _denied(request, exc: AuthorizationDenied):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=403, content={
            "detail": str(exc),
            "determining_policies": exc.decision.determining_policies,
        })

    @app.exception_handler(ObligationEnforcementError)
    def _obligation_error(request, exc: ObligationEnforcementError):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    @app.get("/descriptor")
    def descriptor() -> dict:
        return build_descriptor(
            canonical_id=settings.EXPECTED_CANONICAL_ID,
            kind="mcp-server",
            instance_id=instance_id,
            base_url=public_url,
            protocol_type="mcp",
            capability_source="interfaces/mcp/tools.yaml",
            tools=IMPLEMENTED_TOOLS,
            dependencies=[
                DependencyInfo(canonical_id="system.qms", relation="business-api", endpoint=settings.qms_base_url()),
                DependencyInfo(canonical_id="system.fx", relation="business-api", endpoint=settings.fx_base_url()),
            ],
        ).model_dump()

    def _fetch_quote_version(quote_id: str, version: int) -> dict:
        r = qms_client.get(f"/quotes/{quote_id}/versions/{version}", headers={"X-API-Key": qms_api_key})
        if r.status_code == 404:
            raise HTTPException(status_code=404, detail=f"no version {version} for quote {quote_id!r}")
        r.raise_for_status()
        return r.json()

    @app.post("/tools/calculate_quote_price")
    def calculate_quote_price(body: QuoteVersionRequest, authorization: str | None = Header(default=None)) -> dict:
        tool = "calculate_quote_price"
        with _tracer.start_as_current_span(f"mcp.tool.{tool}") as span:
            span.set_attribute("mcp.tool", tool)
            t0 = time.monotonic()
            try:
                principal = authenticate_request(authorization, verifier=token_verifier, root=root)

                live_version = _fetch_quote_version(body.quote_id, body.version)

                ctx = authorize_and_enforce(
                    cedar_url, bundle, principal,
                    action="quote-price.calculate",
                    resource=ref("Quote", body.quote_id),
                    context={"executing_workload": "workload.qms-mcp", "tool": tool},
                    root=root,
                    additional_entities=[entity("Quote", body.quote_id, {"status": live_version["status"]})],
                )

                r = qms_client.post(
                    f"/quotes/{body.quote_id}/versions/{body.version}/price",
                    headers={"X-API-Key": qms_api_key},
                )
                if r.status_code == 409:
                    raise HTTPException(status_code=409, detail=r.json().get("detail", "quote is not priceable"))
                if r.status_code == 400:
                    raise HTTPException(status_code=400, detail=r.json().get("detail", "pricing preconditions not composed"))
                r.raise_for_status()

                return {**r.json(), "authorized_as": ctx.principal.id, "executing_workload": ctx.executing_workload}
            finally:
                _tool_duration.record(time.monotonic() - t0, {"tool": tool})
                _tool_calls.add(1, {"tool": tool})

    @app.post("/tools/evaluate_quote_variance")
    def evaluate_quote_variance(body: QuoteVersionRequest, authorization: str | None = Header(default=None)) -> dict:
        tool = "evaluate_quote_variance"
        with _tracer.start_as_current_span(f"mcp.tool.{tool}") as span:
            span.set_attribute("mcp.tool", tool)
            t0 = time.monotonic()
            try:
                principal = authenticate_request(authorization, verifier=token_verifier, root=root)

                live_version = _fetch_quote_version(body.quote_id, body.version)

                ctx = authorize_and_enforce(
                    cedar_url, bundle, principal,
                    action="quote-variance.evaluate",
                    resource=ref("Quote", body.quote_id),
                    context={"executing_workload": "workload.qms-mcp", "tool": tool},
                    root=root,
                    additional_entities=[entity("Quote", body.quote_id, {"status": live_version["status"]})],
                )

                return {
                    "quote_id": body.quote_id,
                    "version": body.version,
                    "status": live_version["status"],
                    "margin_pct_x10": live_version.get("margin_pct_x10"),
                    "total_cost_eur_cents": live_version.get("total_cost_eur_cents"),
                    "authorized_as": ctx.principal.id,
                    "executing_workload": ctx.executing_workload,
                }
            finally:
                _tool_duration.record(time.monotonic() - t0, {"tool": tool})
                _tool_calls.add(1, {"tool": tool})

    @app.post("/tools/normalize_route_cost")
    def normalize_route_cost(body: NormalizeRouteCostRequest, authorization: str | None = Header(default=None)) -> dict:
        tool = "normalize_route_cost"
        with _tracer.start_as_current_span(f"mcp.tool.{tool}") as span:
            span.set_attribute("mcp.tool", tool)
            t0 = time.monotonic()
            try:
                principal = authenticate_request(authorization, verifier=token_verifier, root=root)

                rate_resp = fx_client.get(
                    f"/exchange-rates/{body.from_currency}/{body.to_currency}",
                    headers={"X-API-Key": fx_api_key},
                )
                if rate_resp.status_code == 404:
                    raise HTTPException(status_code=404, detail=f"no FX rate for {body.from_currency}/{body.to_currency}")
                rate_resp.raise_for_status()
                observed_at = rate_resp.json()["observed_at"]
                fx_age = age_seconds(observed_at)

                ctx = authorize_and_enforce(
                    cedar_url, bundle, principal,
                    action="route-cost.normalize",
                    resource=ref("RouteOption", body.route_id),
                    context={
                        "fx_age_seconds": fx_age, "target_currency": body.to_currency,
                        "executing_workload": "workload.qms-mcp", "tool": tool,
                    },
                    root=root,
                )

                convert_resp = fx_client.get(
                    "/convert",
                    params={"amount": body.amount, "from_currency": body.from_currency, "to_currency": body.to_currency},
                    headers={"X-API-Key": fx_api_key},
                )
                convert_resp.raise_for_status()

                return {
                    **convert_resp.json(), "route_id": body.route_id, "fx_age_seconds": fx_age,
                    "authorized_as": ctx.principal.id, "executing_workload": ctx.executing_workload,
                }
            finally:
                _tool_duration.record(time.monotonic() - t0, {"tool": tool})
                _tool_calls.add(1, {"tool": tool})

    return app
