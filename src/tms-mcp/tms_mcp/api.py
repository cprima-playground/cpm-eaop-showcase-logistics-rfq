"""tms-mcp -- M6a's first real MCP slice. One tool: check_lane_capacity ->
capacity.check. Flow per ADR-001 decision #3: the CALLER (an agent) is the
Cedar principal, this server's own workload identity rides along as
context.executing_workload, never as the principal. Cedar authorization
happens via rfq_common.pep; the downstream call to mock-tms uses tms-mcp's
own transport credential (tms-api-key, decision #8's accepted shared-key
posture for this hop) -- two distinct credentials, never conflated (see
rfq_common.mcp_auth.verify's module docstring).

Does NOT add delegated_by -- unnecessary for proving agent-to-MCP
enforcement (per the M6a scope constraint)."""

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
from rfq_common.pdp.entities import ref
from rfq_common.pep import AuthorizationDenied, ObligationEnforcementError, authorize_and_enforce
from rfq_common.settings import ServiceSettings

from . import settings

RFQ_ROOT = settings.RFQ_ROOT

# M5.9: labels are `tool` only -- never route_id/principal id (cardinality
# rule, same as everywhere else in this milestone).
_tracer = trace.get_tracer("tms_mcp")
_meter = metrics.get_meter("tms_mcp")
_tool_duration = _meter.create_histogram("mcp.tool.duration", unit="s", description="MCP tool call latency")
_tool_calls = _meter.create_counter("mcp.tool.calls", description="MCP tool invocations")

# M6a implements only check_lane_capacity -- interfaces/mcp/tools.yaml also
# maps get_feasible_lanes/get_lane_transit_time/get_route_restrictions to
# this server, but the descriptor must reflect what's actually LIVE, not
# tools.yaml's aspirational full mapping (a descriptor claiming an
# unimplemented tool would be exactly the kind of drift M5.5 exists to
# prevent).
IMPLEMENTED_TOOLS = ["check_lane_capacity"]


class CheckLaneCapacityRequest(BaseModel):
    route_id: str


def build_app(
    *,
    root: Path | None = None,
    cedar_url: str | None = None,
    bundle: PolicyBundle | None = None,
    tms_client: httpx.Client | None = None,
    introspection_client_secret: str | None = None,
    tms_api_key: str | None = None,
    public_url: str | None = None,
    instance_id: str | None = None,
) -> FastAPI:
    root = root or RFQ_ROOT
    cedar_url = cedar_url or settings.cedar_url()
    bundle = bundle or PolicyBundle.from_path(root / "authorization" / "policies.cedar")
    tms_client = tms_client or httpx.Client(base_url=settings.tms_base_url(), timeout=5.0)
    introspection_client_secret = introspection_client_secret or settings.introspection_client_secret()
    token_verifier = build_token_verifier(
        mode="introspection", oidc_issuer_url=settings.oidc_issuer_url(),
        introspection_endpoint=settings.introspection_endpoint(),
        client_id=settings.KEYCLOAK_CLIENT_ID, client_secret=introspection_client_secret,
    )
    tms_api_key = tms_api_key or settings.tms_api_key()
    public_url = public_url or ServiceSettings.from_env(default_port=8104).public_url
    instance_id = instance_id or new_instance_id()

    app = create_app("TMS MCP", system_id="tms")

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
            dependencies=[DependencyInfo(
                canonical_id="system.tms", relation="business-api", endpoint=settings.tms_base_url(),
            )],
        ).model_dump()

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

    @app.post("/tools/check_lane_capacity")
    def check_lane_capacity(body: CheckLaneCapacityRequest, authorization: str | None = Header(default=None)) -> dict:
        tool = "check_lane_capacity"
        with _tracer.start_as_current_span(f"mcp.tool.{tool}") as span:
            span.set_attribute("mcp.tool", tool)
            t0 = time.monotonic()
            try:
                principal = authenticate_request(authorization, verifier=token_verifier, root=root)

                ctx = authorize_and_enforce(
                    cedar_url, bundle, principal,
                    action="capacity.check",
                    resource=ref("RouteOption", body.route_id),
                    context={"executing_workload": "workload.tms-mcp", "tool": tool},
                    root=root,
                )

                response = tms_client.get(f"/routes/{body.route_id}/capacity", headers={"X-API-Key": tms_api_key})
                if response.status_code == 404:
                    raise HTTPException(status_code=404, detail=f"no route {body.route_id!r}")
                response.raise_for_status()

                return {**response.json(), "authorized_as": ctx.principal.id, "executing_workload": ctx.executing_workload}
            finally:
                _tool_duration.record(time.monotonic() - t0, {"tool": tool})
                _tool_calls.add(1, {"tool": tool})

    return app
