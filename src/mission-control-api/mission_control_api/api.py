"""mission-control-api -- M8's read-only control-plane API.

Mission Control is a PROJECTION, never a source of truth, and never makes
an authorization decision -- it must never call cedar-agent's real
decision endpoint (mechanically enforced by
tests/test_no_authorization_decisions.py, M8.4).

Three separate concepts, kept separate in code even where they share
infrastructure (this module's descriptor cache, rfq_common/probe.py):
  Registry  -> instances, endpoints, protocols, reachability (registry.py,
               the 7 descriptor-bearing services only)
  Health    -> operational condition of the BROADER health-target roster
               (probe.py, M8.3 -- registry services + mock-* + Keycloak/
               cedar-agent/Vault, none of which are registry entries)
  Topology  -> relationships between components (topology.py, M8.2 --
               two separately-labeled layers: runtime-dependency +
               credential)

D6 -- access policy (not RBAC): every /api/v1/* route requires a valid
bearer token (same introspection path every MCP server uses); no Cedar
check, every authenticated principal sees the same data. Authenticated
internal metadata, not a public API -- never exposes secrets/credentials/
raw tokens in any response."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, Header
from fastapi.responses import JSONResponse

from rfq_common.app import create_app
from rfq_common.descriptor import build_descriptor, new_instance_id
from rfq_common.mcp_auth import AuthenticationError, authenticate_request, build_token_verifier
from rfq_common.settings import ServiceSettings

from . import settings
from .health import health_report
from .identity_drift import identity_drift_report
from .identity_model import identities_report
from .policy_model import policies_report, policy_drift
from .registry import ObservedServiceRegistry
from .topology import topology as build_topology
from .traces import get_trace, search_traces

RFQ_ROOT = settings.RFQ_ROOT


def build_app(
    *,
    root: Path | None = None,
    registry: ObservedServiceRegistry | None = None,
    introspection_client_secret: str | None = None,
    public_url: str | None = None,
    instance_id: str | None = None,
) -> FastAPI:
    root = root or RFQ_ROOT
    registry = registry or ObservedServiceRegistry(root=root)
    introspection_client_secret = introspection_client_secret or settings.introspection_client_secret()
    token_verifier = build_token_verifier(
        mode="introspection", oidc_issuer_url=settings.oidc_issuer_url(),
        introspection_endpoint=settings.introspection_endpoint(),
        client_id=settings.KEYCLOAK_CLIENT_ID, client_secret=introspection_client_secret,
    )
    public_url = public_url or ServiceSettings.from_env(default_port=8300).public_url
    instance_id = instance_id or new_instance_id()

    app = create_app("Mission Control API", system_id="mission-control")

    @app.exception_handler(AuthenticationError)
    def _auth_error(request, exc: AuthenticationError):
        return JSONResponse(status_code=401, content={"detail": str(exc)})

    @app.get("/descriptor")
    def descriptor() -> dict:
        return build_descriptor(
            canonical_id=settings.EXPECTED_CANONICAL_ID,
            kind="control-plane",
            instance_id=instance_id,
            base_url=public_url,
            protocol_type="rest",
            capability_source="openapi:/api/v1/openapi.json",
        ).model_dump()

    def _require_authenticated(authorization: str | None = Header(default=None)):
        """D6: authN yes, Cedar authZ deferred. Any authenticated
        principal may read -- never called "RBAC". Raises
        AuthenticationError (-> 401) for a missing/invalid/expired
        token; never silently passes an unauthenticated request through."""
        return authenticate_request(authorization, verifier=token_verifier, root=root)

    api_v1 = APIRouter(prefix="/api/v1")

    @api_v1.get("/services")
    def list_services(_principal=Depends(_require_authenticated)) -> dict:
        entries = registry.list_entries()
        return {"services": [_entry_dict(e) for e in entries]}

    @api_v1.get("/services/{canonical_id}")
    def get_service(canonical_id: str, _principal=Depends(_require_authenticated)) -> dict:
        entry = registry.get_entry(canonical_id)
        if entry is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail=f"no registry entry for {canonical_id!r}")
        return _entry_dict(entry)

    @api_v1.get("/topology")
    def get_topology(_principal=Depends(_require_authenticated)) -> dict:
        return build_topology(registry)

    @api_v1.get("/health")
    def get_health(_principal=Depends(_require_authenticated)) -> dict:
        return health_report(registry, root)

    @api_v1.get("/policies")
    def get_policies(_principal=Depends(_require_authenticated)) -> dict:
        return policies_report()

    @api_v1.get("/policies/drift")
    def get_policies_drift(_principal=Depends(_require_authenticated)) -> dict:
        from rfq_common.settings import CedarSettings
        return policy_drift(CedarSettings.from_env().cedar_url)

    @api_v1.get("/identities")
    def get_identities(_principal=Depends(_require_authenticated)) -> dict:
        return identities_report(root)

    @api_v1.get("/identity-drift")
    def get_identity_drift(_principal=Depends(_require_authenticated)) -> dict:
        return identity_drift_report()

    @api_v1.get("/traces")
    def list_traces(_principal=Depends(_require_authenticated)) -> dict:
        return search_traces()

    @api_v1.get("/traces/{trace_id}")
    def get_one_trace(trace_id: str, _principal=Depends(_require_authenticated)) -> dict:
        return get_trace(trace_id)

    app.include_router(api_v1)

    return app


def _entry_dict(entry) -> dict:
    return {
        "canonical_id": entry.canonical_id,
        "reachability": entry.reachability,
        "observed_at": entry.observed_at,
        "last_seen": entry.last_seen,
        "descriptor": entry.descriptor,
    }
