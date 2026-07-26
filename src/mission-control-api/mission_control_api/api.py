"""mission-control-api -- M8's read-only control-plane API. Skeleton only
(M8.1, step 3): /healthz, /descriptor, /swagger, /redoc, and an empty
/api/v1 router with no routes yet. Read models (registry, topology,
health, policy, identity, identity-drift, traces) land in later steps
(M8.2-M8.6), each behind bearer-token authentication (D6) once the first
real /api/v1 route exists.

Mission Control is a PROJECTION, never a source of truth, and never makes
an authorization decision -- it must never call cedar-agent's
/v1/is_authorized (mechanically enforced later by
test_no_authorization_decisions.py, M8.4)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, FastAPI

from rfq_common.app import create_app
from rfq_common.descriptor import build_descriptor, new_instance_id
from rfq_common.settings import ServiceSettings

from . import settings

RFQ_ROOT = settings.RFQ_ROOT


def build_app(
    *,
    public_url: str | None = None,
    instance_id: str | None = None,
) -> FastAPI:
    public_url = public_url or ServiceSettings.from_env(default_port=8300).public_url
    instance_id = instance_id or new_instance_id()

    app = create_app("Mission Control API", system_id="mission-control")

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

    api_v1 = APIRouter(prefix="/api/v1")
    # No routes yet -- M8.2 onward adds them (registry, topology, health,
    # policy, identities, identity-drift, traces), each a GET, each
    # requiring a valid bearer token per D6. Mounted now so the prefix
    # exists and /api/v1/openapi.json is a stable URL from the start.
    app.include_router(api_v1)

    return app
