"""approval-mcp -- M6's fourth real MCP slice. Two genuinely agent-facing
tools, both real edges in agents/catalog.yaml (route-decision-agent owns
route.recommend + route-deviation.propose, mcp_access: [approval-mcp]):

  record_recommendation -> route-deviation.propose
      Cedar gate: the LIVE QuoteVersion.status (fetched from mock-qms per
      request, supplied via additional_entities -- same mechanism qms-mcp
      introduced, never pre-loaded into the persisted store) must be
      "draft". Mirrors mock-qms's own real precondition for attaching a
      RouteRecommendation (store.py's compose_route_recommendation).

  resume_route_decision -> route.recommend
      Cedar gate: the PRE-EXISTING context-based policies D3a/D3b/D8/D9
      (authorization/policies.cedar, already decided, unconditional on
      resource state) -- reused as-is, not duplicated, same posture
      qms-mcp took reusing D2 for route-cost.normalize. Those policies
      cannot be made resource/state-sensitive without editing decided
      business policy, which this milestone does not do. Instead, a REAL
      business-state precondition (a decision must actually exist -- the
      live QuoteVersion.status must not still be "approval_required") is
      enforced as a 409 BEFORE Cedar is even consulted -- the same
      defense-in-depth split every business system in this repo already
      uses (Cedar decides WHO may act; the business system enforces
      whether the action is valid AT ALL in the current state).

NOT implemented (per direct instruction -- do not expose a tool just
because tools.yaml lists it): create_approval_task (system-internal
consequence of quote.submit-for-approval, never agent-invokable, Finding
2) and get_approval_status (a legitimate read, but has NO backing Cedar
action today -- tools.yaml's own comment flags this, not silently
invented here).
"""

from __future__ import annotations

import time
from pathlib import Path

import httpx
from fastapi import FastAPI, Header, HTTPException
from opentelemetry import metrics, trace
from pydantic import BaseModel

from rfq_common.app import create_app
from rfq_common.descriptor import DependencyInfo, build_descriptor, new_instance_id
from rfq_common.mcp_auth import AuthenticationError, authenticate_request, build_token_verifier
from rfq_common.pdp import PolicyBundle
from rfq_common.pdp.entities import entity, ref
from rfq_common.pep import AuthorizationDenied, ObligationEnforcementError, authorize_and_enforce
from rfq_common.settings import ServiceSettings

from . import settings

RFQ_ROOT = settings.RFQ_ROOT

IMPLEMENTED_TOOLS = ["record_recommendation", "resume_route_decision"]

_tracer = trace.get_tracer("approval_mcp")
_meter = metrics.get_meter("approval_mcp")
_tool_duration = _meter.create_histogram("mcp.tool.duration", unit="s", description="MCP tool call latency")
_tool_calls = _meter.create_counter("mcp.tool.calls", description="MCP tool invocations")

# A decision must actually exist before route-decision-agent may resume --
# draft/priced/approval_required all mean "no decision recorded yet."
_DECIDED_STATUSES = {"approved", "rejected", "revise"}


class RecordRecommendationRequest(BaseModel):
    quote_id: str
    version: int
    recommendation_id: str
    selected_route_id: str


class ResumeRouteDecisionRequest(BaseModel):
    quote_id: str
    version: int
    rfq_id: str
    cost_variance_pct_x10: int
    transit_variance_days: int
    margin_pct_x10: int
    non_contracted_lane: bool


def build_app(
    *,
    root: Path | None = None,
    cedar_url: str | None = None,
    bundle: PolicyBundle | None = None,
    qms_client: httpx.Client | None = None,
    introspection_client_secret: str | None = None,
    qms_api_key: str | None = None,
    public_url: str | None = None,
    instance_id: str | None = None,
) -> FastAPI:
    root = root or RFQ_ROOT
    cedar_url = cedar_url or settings.cedar_url()
    bundle = bundle or PolicyBundle.from_path(root / "authorization" / "policies.cedar")
    # 20s -- same real-pipeline latency finding as qms-mcp's own client.
    qms_client = qms_client or httpx.Client(base_url=settings.qms_base_url(), timeout=20.0)
    introspection_client_secret = introspection_client_secret or settings.introspection_client_secret()
    token_verifier = build_token_verifier(
        mode="introspection", oidc_issuer_url=settings.oidc_issuer_url(),
        introspection_endpoint=settings.introspection_endpoint(),
        client_id=settings.KEYCLOAK_CLIENT_ID, client_secret=introspection_client_secret,
    )
    qms_api_key = qms_api_key or settings.qms_api_key()
    public_url = public_url or ServiceSettings.from_env(default_port=8107).public_url
    instance_id = instance_id or new_instance_id()

    app = create_app("Approval MCP", system_id="qms")

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
            dependencies=[DependencyInfo(canonical_id="system.qms", relation="business-api", endpoint=settings.qms_base_url())],
        ).model_dump()

    def _fetch_quote_version(quote_id: str, version: int) -> dict:
        r = qms_client.get(f"/quotes/{quote_id}/versions/{version}", headers={"X-API-Key": qms_api_key})
        if r.status_code == 404:
            raise HTTPException(status_code=404, detail=f"no version {version} for quote {quote_id!r}")
        r.raise_for_status()
        return r.json()

    @app.post("/tools/record_recommendation")
    def record_recommendation(body: RecordRecommendationRequest, authorization: str | None = Header(default=None)) -> dict:
        tool = "record_recommendation"
        with _tracer.start_as_current_span(f"mcp.tool.{tool}") as span:
            span.set_attribute("mcp.tool", tool)
            t0 = time.monotonic()
            try:
                principal = authenticate_request(authorization, verifier=token_verifier, root=root)

                live_version = _fetch_quote_version(body.quote_id, body.version)

                ctx = authorize_and_enforce(
                    cedar_url, bundle, principal,
                    action="route-deviation.propose",
                    resource=ref("RouteRecommendation", body.recommendation_id),
                    context={"executing_workload": "workload.approval-mcp", "tool": tool},
                    root=root,
                    additional_entities=[entity("RouteRecommendation", body.recommendation_id, {"quote_status": live_version["status"]})],
                )

                r = qms_client.put(
                    f"/quotes/{body.quote_id}/versions/{body.version}/route-recommendation",
                    headers={"X-API-Key": qms_api_key},
                    json={"recommendation_id": body.recommendation_id, "selected_route_id": body.selected_route_id},
                )
                if r.status_code == 409:
                    raise HTTPException(status_code=409, detail=r.json().get("detail", "quote version is no longer draft"))
                r.raise_for_status()

                return {**r.json(), "authorized_as": ctx.principal.id, "executing_workload": ctx.executing_workload}
            finally:
                _tool_duration.record(time.monotonic() - t0, {"tool": tool})
                _tool_calls.add(1, {"tool": tool})

    @app.post("/tools/resume_route_decision")
    def resume_route_decision(body: ResumeRouteDecisionRequest, authorization: str | None = Header(default=None)) -> dict:
        tool = "resume_route_decision"
        with _tracer.start_as_current_span(f"mcp.tool.{tool}") as span:
            span.set_attribute("mcp.tool", tool)
            t0 = time.monotonic()
            try:
                principal = authenticate_request(authorization, verifier=token_verifier, root=root)

                live_version = _fetch_quote_version(body.quote_id, body.version)
                if live_version["status"] not in _DECIDED_STATUSES:
                    # Real business-state precondition, enforced BEFORE Cedar
                    # -- no decision exists yet, nothing to resume from. Not
                    # an authorization question (Cedar never even runs here).
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"quote {body.quote_id!r} version {body.version} has no decision yet "
                            f"(status={live_version['status']!r}, need one of {sorted(_DECIDED_STATUSES)})"
                        ),
                    )

                ctx = authorize_and_enforce(
                    cedar_url, bundle, principal,
                    action="route.recommend",
                    resource=ref("RFQ", body.rfq_id),
                    context={
                        "cost_variance_pct_x10": body.cost_variance_pct_x10,
                        "transit_variance_days": body.transit_variance_days,
                        "margin_pct_x10": body.margin_pct_x10,
                        "non_contracted_lane": body.non_contracted_lane,
                        "executing_workload": "workload.approval-mcp", "tool": tool,
                    },
                    root=root,
                )

                return {
                    "quote_id": body.quote_id, "version": body.version, "rfq_id": body.rfq_id,
                    "decision_status": live_version["status"],
                    "resumed": True,
                    "obligations": ctx.obligations,
                    "authorized_as": ctx.principal.id, "executing_workload": ctx.executing_workload,
                }
            finally:
                _tool_duration.record(time.monotonic() - t0, {"tool": tool})
                _tool_calls.add(1, {"tool": tool})

    return app
